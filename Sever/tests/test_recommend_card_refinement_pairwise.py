from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SEVER_ROOT = Path(__file__).resolve().parents[1]
if str(SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SEVER_ROOT))

from services.recommend_card_prompt_eval import FIELD_ORDER  # noqa: E402
from config.recommend_card_prompts import REFINEMENT_CANDIDATES  # noqa: E402
from services.recommend_card_refinement_pairwise import (  # noqa: E402
    detailed_promotion_decision,
    normalize_pairwise_result,
)
from services.llm_request_options import build_thinking_kwargs  # noqa: E402
from scripts.recommend_card_refinement_detailed_ab import (  # noqa: E402
    _effective_cfg,
    _matched_stage_checks,
    _run_full_card_stage,
    _stage_base_version,
)


def _raw_pairwise(**overrides) -> dict:
    value = {
        "field_preferences": {key: "Y" for key in FIELD_ORDER},
        "more_faithful": "tie",
        "unsupported_content": "neither",
        "material_information_loss": "neither",
        "overall_preferred": "Y",
        "reason": "B更短且信息等价",
    }
    value.update(overrides)
    return value


def _score(score: float, field_score: float = 94.0) -> dict:
    return {
        "score": score,
        "factuality_score": 98.0,
        "field_scores": {key: field_score for key in FIELD_ORDER},
        "judge": {
            "hallucination_severity": "none",
            "unsupported_claims": [],
        },
        "deterministic": {
            "contract_pass": True,
            "unsupported_numbers": {},
        },
        "refinement_attempts": 1,
    }


class RecommendCardRefinementPairwiseTests(unittest.TestCase):
    def test_infrastructure_error_aborts_instead_of_freezing_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            draft = root / "outputs" / "generation" / "dev" / "current" / "p1.md"
            draft.parent.mkdir(parents=True)
            draft.write_text("有效卡片", encoding="utf-8")
            with patch(
                "scripts.recommend_card_refinement_detailed_ab."
                "production_limit.refine_full_card_text",
                return_value=("有效卡片", False, ConnectionError("offline")),
            ):
                with self.assertRaises(ConnectionError):
                    _run_full_card_stage(
                        client=MagicMock(),
                        generator_cfg={
                            "model": "deepseek-v4-flash",
                            "base_url": "https://api.deepseek.com",
                            "max_tokens": 4096,
                            "thinking": False,
                        },
                        output_root=root,
                        split="dev",
                        version="r1_field_limits",
                        paper_id="p1",
                    )

            stage = (
                root
                / "outputs"
                / "refinement_full_card_stage"
                / "dev"
                / "r1_field_limits"
                / "p1.md"
            )
            self.assertFalse(stage.exists())

    def test_aligned_variant_reuses_exact_base_full_card_stage(self) -> None:
        self.assertEqual(
            _stage_base_version("r10_r1_aligned_fallback"),
            "r1_field_limits",
        )
        scores = {
            "r1_field_limits": {
                "p1": {"stage_output_sha256": "same"},
                "p2": {"stage_output_sha256": "same-2"},
            },
            "r10_r1_aligned_fallback": {
                "p1": {"stage_output_sha256": "same"},
                "p2": {"stage_output_sha256": "same-2"},
            },
        }

        checks = _matched_stage_checks(
            scores,
            (("r1_field_limits", "r10_r1_aligned_fallback"),),
        )

        self.assertTrue(checks[0]["all_matched"])
        self.assertEqual(checks[0]["matched_count"], 2)

    def test_production_eval_explicitly_disables_deepseek_thinking(self) -> None:
        config = _effective_cfg(
            version="r1_field_limits",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(
            build_thinking_kwargs(config),
            {"extra_body": {"thinking": {"type": "disabled"}}},
        )

    def test_aligned_variant_includes_memory_and_current_card_contract(self) -> None:
        config = _effective_cfg(
            version="r10_r1_aligned_fallback",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(config["headline_limit"], 16)
        self.assertEqual(config["section_limits"]["memory"], 40)
        self.assertIn("一句话记忆版", config["structure_check_prompt"])
        self.assertEqual(
            config["card_prompt"],
            REFINEMENT_CANDIDATES["r1_field_limits"],
        )

    def test_evidence_budget_variant_skips_legacy_structure_gate(self) -> None:
        config = _effective_cfg(
            version="r14_r4_evidence_budget",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(config["headline_limit"], 21)
        self.assertEqual(config["structure_check_prompt"], "")
        self.assertEqual(config["section_limits"]["memory"], 48)
        self.assertIn("标签后的标题压到16字以内", config["headline_prompt"])
        self.assertIn("比较对象和方向", config["section_prompts"]["findings"])
        self.assertEqual(
            config["card_prompt"],
            REFINEMENT_CANDIDATES["r4_safe_budget_template"],
        )

    def test_robust_evidence_variant_keeps_output_headroom(self) -> None:
        config = _effective_cfg(
            version="r15_r4_robust_evidence",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(config["structure_check_prompt"], "")
        self.assertEqual(config["section_limits"]["findings"], 213)
        self.assertIn("合计不超过185字", config["section_prompts"]["findings"])
        self.assertIn("不得新增“需、应、建议、优先”", config["section_prompts"]["findings"])
        self.assertIn("不超过44字", config["section_prompts"]["memory"])

    def test_selective_variant_triggers_at_actual_contract_budget(self) -> None:
        config = _effective_cfg(
            version="r16_r4_selective_contract",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(config["headline_limit"], 21)
        self.assertEqual(config["section_limits"]["method"], 213)
        self.assertEqual(config["section_limits"]["findings"], 213)
        self.assertEqual(config["section_limits"]["opinion"], 75)
        self.assertIn("每行以“🔸”开头、正文不超过55字", config["section_prompts"]["findings"])

    def test_reliable_selective_variant_reuses_proven_short_prompts(self) -> None:
        config = _effective_cfg(
            version="r17_r4_reliable_selective",
            generator_cfg={
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "max_tokens": 4096,
                "thinking": False,
            },
        )

        self.assertEqual(config["headline_limit"], 21)
        self.assertEqual(config["section_limits"]["findings"], 213)
        self.assertIn("每条只写一个“结果+必要条件”", config["section_prompts"]["findings"])
        self.assertEqual(config["structure_check_prompt"], "")

    def test_normalizes_blind_labels_relative_to_challenger(self) -> None:
        raw = _raw_pairwise(
            unsupported_content="Y",
            material_information_loss="X",
        )

        result = normalize_pairwise_result(raw, challenger_label="Y")

        self.assertEqual(result["overall_preference"], "win")
        self.assertEqual(result["challenger_faithfulness"], "tie")
        self.assertTrue(result["challenger_unsupported"])
        self.assertFalse(result["challenger_material_loss"])
        self.assertTrue(result["baseline_material_loss"])
        self.assertTrue(
            all(value == "win" for value in result["field_preferences"].values())
        )

    def test_rejects_incomplete_pairwise_payload(self) -> None:
        raw = _raw_pairwise()
        del raw["field_preferences"]["memory_sentence"]

        with self.assertRaises(ValueError):
            normalize_pairwise_result(raw, challenger_label="Y")

    def test_promotes_only_when_every_frozen_gate_passes(self) -> None:
        baseline = {paper_id: _score(88.0, 90.0) for paper_id in ("p1", "p2", "p3")}
        challenger = {
            paper_id: _score(94.0, 95.0) for paper_id in ("p1", "p2", "p3")
        }
        verdicts = []
        for paper_id in ("p1", "p2", "p3"):
            verdict = normalize_pairwise_result(
                _raw_pairwise(), challenger_label="Y"
            )
            verdict["paper_id"] = paper_id
            verdicts.append(verdict)

        decision = detailed_promotion_decision(
            baseline_items=baseline,
            challenger_items=challenger,
            verdicts=verdicts,
        )

        self.assertTrue(decision["promoted"])
        self.assertTrue(all(decision["gates"].values()))

    def test_material_information_loss_blocks_promotion(self) -> None:
        baseline = {paper_id: _score(88.0, 90.0) for paper_id in ("p1", "p2", "p3")}
        challenger = {
            paper_id: _score(94.0, 95.0) for paper_id in ("p1", "p2", "p3")
        }
        verdicts = []
        for paper_id in ("p1", "p2", "p3"):
            raw = _raw_pairwise(
                material_information_loss="Y" if paper_id == "p2" else "neither"
            )
            verdict = normalize_pairwise_result(raw, challenger_label="Y")
            verdict["paper_id"] = paper_id
            verdicts.append(verdict)

        decision = detailed_promotion_decision(
            baseline_items=baseline,
            challenger_items=challenger,
            verdicts=verdicts,
        )

        self.assertFalse(decision["promoted"])
        self.assertFalse(decision["gates"]["pairwise_no_material_loss"])


if __name__ == "__main__":
    unittest.main()
