from __future__ import annotations

import os
import sys
import unittest


SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SEVER_ROOT not in sys.path:
    sys.path.insert(0, SEVER_ROOT)

from config.recommend_card_prompts import (  # noqa: E402
    ACTIVE_GENERATION_PROMPT,
    ACTIVE_REFINEMENT_VERSION,
    GENERATION_PROMPT_CURRENT,
    REFINEMENT_CANDIDATES,
    upgrade_known_generation_prompt,
)
from services.recommend_card_prompt_eval import (  # noqa: E402
    FIELD_ORDER,
    combine_scores,
    build_refinement_retry_note,
    deterministic_report,
    parse_card,
    promotion_table,
    render_card,
)


SAMPLE_CARD = """笔记标题：拆解视觉语用捷径
📖标题：A Controlled Benchmark
🌐来源：arXiv,2608.00001
推荐理由：用受控负例区分语用不一致与普通图文错配，能检验模型是否依赖表面线索。

🛎️文章简介
🔸研究问题：视觉语言模型识别讽刺时，究竟理解语用不一致还是只检测图文错配？
🔸主要贡献：构建3000对受控样本的PragMatch基准，将两种信号分开评测。

📝重点思路
🔸从MMSD2.0构造讽刺、字面与困难负例三类配对。
🔸系统操纵捷径线索并比较模型预测变化。
🔸在受控切分上评估多种视觉语言模型。

🔎分析总结
🔸模型在原始分布上表现较高，但在困难负例上明显下降。
🔸删除捷径线索后，多数模型的讽刺判断不稳定。
🔸结果显示图文匹配能力不能替代语用推理。

💡个人观点
受控负例比单一准确率更能揭示语用能力，但结论仍受社交媒体数据域限制。

一句话记忆版：PragMatch用受控负例区分语用理解与图文匹配。
"""

ZERO_STYLE_CARD = """- **中文短标题**：拆解视觉语用捷径
- **推荐理由**：用受控负例区分语用不一致与普通图文错配。
- **研究问题**：模型理解语用关系还是依赖表面线索？
- **主要贡献**：1）构建受控基准；2）设计扰动诊断。
- **重点思路**：构造三类配对；操纵捷径线索；比较模型预测。
- **分析总结**：困难负例导致性能下降；移除线索后判断不稳；图文匹配不能替代语用推理。
- **个人观点**：受控负例更有诊断力，但数据域有限。
- **一句话记忆**：用受控负例区分语用理解与图文匹配。
"""

MULTILINE_ZERO_STYLE_CARD = """- **中文短标题**：评测智能体运行框架
- **推荐理由**：将运行框架与模型能力分开评估。
- **研究问题**：如何测量智能体运行框架的独立贡献？
- **主要贡献**：
    1. 构建统一评测协议。
    2）比较多种框架和任务。
- **重点思路**：固定模型；替换运行框架；分析成功率。
- **分析总结**：框架影响成功率；差异随任务变化；组件贡献可分解。
- **个人观点**：协议有助于避免把框架收益误归因给模型。
- **一句话记忆**：固定模型才能看清运行框架贡献。
"""


class RecommendCardPromptEvalTests(unittest.TestCase):
    def test_parse_and_render_round_trip_keeps_all_eight_fields(self) -> None:
        card = parse_card(SAMPLE_CARD)

        self.assertEqual(card.short_title, "拆解视觉语用捷径")
        self.assertTrue(card.research_question.endswith("？"))
        self.assertEqual(len(card.key_ideas), 3)
        self.assertEqual(len(card.analysis_summary), 3)
        self.assertIn("PragMatch", card.memory_sentence)

        reparsed = parse_card(render_card(card))
        self.assertEqual(reparsed.score_fields(), card.score_fields())

    def test_parse_zero_prompt_markdown_list_extracts_all_fields(self) -> None:
        card = parse_card(ZERO_STYLE_CARD)

        self.assertTrue(all(card.score_fields().values()))
        self.assertEqual(len(card.key_ideas), 3)
        self.assertEqual(len(card.analysis_summary), 3)

    def test_parse_multiline_scalar_value_keeps_numbered_continuations(self) -> None:
        card = parse_card(MULTILINE_ZERO_STYLE_CARD)

        self.assertIn("构建统一评测协议", card.main_contribution)
        self.assertIn("比较多种框架和任务", card.main_contribution)
        self.assertTrue(all(card.score_fields().values()))

    def test_deterministic_report_flags_missing_and_unsupported_numbers(self) -> None:
        candidate = SAMPLE_CARD.replace("3000对", "9999对").replace(
            "一句话记忆版：PragMatch用受控负例区分语用理解与图文匹配。",
            "一句话记忆版：",
        )

        report = deterministic_report(candidate, source_text=SAMPLE_CARD)

        self.assertIn("memory_sentence", report["missing_fields"])
        self.assertIn("main_contribution", report["unsupported_numbers"])
        self.assertIn("9999", report["unsupported_numbers"]["main_contribution"])

    def test_refinement_contract_flags_hard_limit_and_metadata_changes(self) -> None:
        candidate = SAMPLE_CARD.replace(
            "拆解视觉语用捷径", "这是一个明显超过十六字程序硬上限的中文短标题"
        ).replace("A Controlled Benchmark", "Changed Title")

        report = deterministic_report(
            candidate,
            source_text=SAMPLE_CARD,
            refinement_input=SAMPLE_CARD,
        )

        self.assertFalse(report["contract_pass"])
        self.assertIn("short_title>16", report["contract_errors"])
        self.assertIn("original_title_changed", report["contract_errors"])

    def test_safe_budget_refinement_prompt_uses_margin_and_exact_template(self) -> None:
        prompt = REFINEMENT_CANDIDATES["r4_safe_budget_template"]

        self.assertIn("安全目标", prompt)
        self.assertIn("短标题不超过12字", prompt)
        self.assertIn("重点思路恰好3条", prompt)
        self.assertIn("论文原标题与来源必须逐字复制", prompt)

    def test_retry_note_reports_actual_length_and_safer_target(self) -> None:
        candidate = SAMPLE_CARD.replace(
            "拆解视觉语用捷径", "这是一个明显超过十六字程序硬上限的中文短标题"
        )

        note = build_refinement_retry_note(
            ["short_title>16"], candidate_text=candidate
        )

        self.assertIn("硬上限16字", note)
        self.assertIn("目标不超过12字", note)
        self.assertIn("至少再删", note)

    def test_atomic_safe_budget_prompt_has_extra_margin(self) -> None:
        prompt = REFINEMENT_CANDIDATES["r5_atomic_safe_budget"]

        self.assertIn("短标题不超过8字", prompt)
        self.assertIn("一句话记忆28字", prompt)

    def test_evidence_safe_budget_prompt_guards_strong_claims(self) -> None:
        prompt = REFINEMENT_CANDIDATES["r6_evidence_safe_budget"]

        self.assertIn("严格优于所有", prompt)
        self.assertIn("不得把相关性改成因果", prompt)
        self.assertIn("不能先删可核对的专有名词", prompt)

    def test_atomic_evidence_prompt_prioritizes_final_display_contract(self) -> None:
        prompt = REFINEMENT_CANDIDATES["r8_atomic_evidence_budget"]

        self.assertIn("第一优先级是全部字段一次通过", prompt)
        self.assertIn("一句话记忆不超过28字", prompt)
        self.assertIn("每条最多保留一组", prompt)

    def test_anchor_first_prompt_assigns_one_role_per_field(self) -> None:
        prompt = REFINEMENT_CANDIDATES["r9_anchor_first_microcopy"]

        self.assertIn("各选一个信息锚点", prompt)
        self.assertIn("一句话记忆≤30", prompt)
        self.assertIn("不得补充常识", prompt)

    def test_numeric_trace_tolerates_percent_sign_restored_from_mineru_table(self) -> None:
        candidate = SAMPLE_CARD.replace(
            "明显下降", "从85.9%下降到9.4%"
        )
        source = SAMPLE_CARD + "\nTable 2\n85.9\n9.4\n"

        report = deterministic_report(candidate, source_text=source)

        self.assertNotIn("analysis_summary", report["unsupported_numbers"])

    def test_major_factuality_problem_caps_score_at_59(self) -> None:
        perfect_fields = {
            key: {
                "faithfulness": 35,
                "role_fit": 20,
                "information_value": 20,
                "concision": 15,
                "non_redundancy": 10,
                "note": "",
            }
            for key in FIELD_ORDER
        }
        deterministic = deterministic_report(SAMPLE_CARD, source_text=SAMPLE_CARD)
        result = combine_scores(
            judge_result={
                "field_scores": perfect_fields,
                "hallucination_severity": "major",
                "unsupported_claims": ["unsupported"],
            },
            deterministic=deterministic,
        )

        self.assertEqual(result["score"], 59.0)
        self.assertIn("factuality_cap_59", result["caps"])

    def test_unverified_number_without_major_judge_error_does_not_force_cap(self) -> None:
        candidate = SAMPLE_CARD.replace("3000对", "9999对")
        deterministic = deterministic_report(candidate, source_text=SAMPLE_CARD)
        judge_fields = {
            key: {
                "faithfulness": 30,
                "role_fit": 18,
                "information_value": 18,
                "concision": 13,
                "non_redundancy": 9,
                "note": "需核对数字",
            }
            for key in FIELD_ORDER
        }

        result = combine_scores(
            judge_result={
                "field_scores": judge_fields,
                "hallucination_severity": "minor",
                "unsupported_claims": ["9999"],
            },
            deterministic=deterministic,
        )

        self.assertNotIn("factuality_cap_59", result["caps"])
        self.assertGreater(result["score"], 59.0)

    def test_promotion_requires_delta_wins_factuality_and_field_guardrail(self) -> None:
        def paper(score: float, factuality: float, field_score: float = 80.0) -> dict:
            return {
                "score": score,
                "factuality_score": factuality,
                "field_scores": {key: field_score for key in FIELD_ORDER},
            }

        scores = {
            "base": {"p1": paper(70, 85), "p2": paper(72, 85), "p3": paper(71, 85)},
            "good": {"p1": paper(76, 86), "p2": paper(75, 86), "p3": paper(74, 86)},
            "unsafe": {"p1": paper(82, 80), "p2": paper(81, 80), "p3": paper(80, 80)},
        }

        rows = promotion_table(scores, baseline="base", challengers=("good", "unsafe"))

        self.assertTrue(rows[0]["promoted"])
        self.assertEqual(rows[0]["champion_after"], "good")
        self.assertFalse(rows[1]["promoted"])
        self.assertEqual(rows[1]["champion_after"], "good")

    def test_refinement_promotion_allows_small_clean_factuality_variance(self) -> None:
        def paper(score: float, factuality: float) -> dict:
            return {
                "score": score,
                "factuality_score": factuality,
                "field_scores": {key: 90.0 for key in FIELD_ORDER},
                "judge": {
                    "hallucination_severity": "none",
                    "unsupported_claims": [],
                },
                "deterministic": {
                    "unsupported_numbers": {},
                    "contract_pass": True,
                },
            }

        scores = {
            "base": {key: paper(88, 97.0) for key in ("p1", "p2", "p3")},
            "clean": {key: paper(96, 96.5) for key in ("p1", "p2", "p3")},
        }

        rows = promotion_table(
            scores,
            baseline="base",
            challengers=("clean",),
            factuality_tolerance=1.0,
            require_clean_factuality=True,
        )

        self.assertTrue(rows[0]["promoted"])
        self.assertTrue(rows[0]["factuality_clean"])

    def test_refinement_safety_gate_uses_only_shared_papers(self) -> None:
        def paper(score: float) -> dict:
            return {
                "score": score,
                "factuality_score": 98.0,
                "field_scores": {key: 95.0 for key in FIELD_ORDER},
                "judge": {
                    "hallucination_severity": "none",
                    "unsupported_claims": [],
                },
                "deterministic": {
                    "unsupported_numbers": {},
                    "contract_pass": True,
                },
            }

        unsafe_extra = paper(100.0)
        unsafe_extra["judge"]["hallucination_severity"] = "major"
        scores = {
            "base": {key: paper(88.0) for key in ("p1", "p2", "p3")},
            "candidate": {
                **{key: paper(96.0) for key in ("p1", "p2", "p3")},
                "unpaired": unsafe_extra,
            },
        }

        rows = promotion_table(
            scores,
            baseline="base",
            challengers=("candidate",),
            require_clean_factuality=True,
        )

        self.assertTrue(rows[0]["promoted"])
        self.assertTrue(rows[0]["factuality_clean"])
        self.assertEqual(rows[0]["paper_count"], 3)

    def test_only_known_legacy_default_is_upgraded(self) -> None:
        self.assertEqual(
            upgrade_known_generation_prompt(GENERATION_PROMPT_CURRENT),
            ACTIVE_GENERATION_PROMPT,
        )
        custom = "我的自定义提示词"
        self.assertEqual(upgrade_known_generation_prompt(custom), custom)

    def test_failed_followup_candidates_do_not_replace_active_refinement(self) -> None:
        self.assertEqual(ACTIVE_REFINEMENT_VERSION, "r1_field_limits")


if __name__ == "__main__":
    unittest.main()
