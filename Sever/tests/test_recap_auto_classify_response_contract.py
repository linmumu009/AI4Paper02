from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import recap_service  # noqa: E402
from services import auto_classify_service, kb_service, user_settings_service  # noqa: E402
from services.auto_classify_service import (  # noqa: E402
    _parse_classification_response,
)
from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    InvalidLlmResponseError,
)


class RecapResponseContractTests(unittest.TestCase):
    paper_ids = {"2608.00001", "2608.00002", "2608.00003"}

    def _valid_payload(self) -> dict:
        return {
            "title": "本周研究主题",
            "summary": "三篇论文形成了一条清晰研究主线。",
            "themes": [
                {
                    "name": "推理优化",
                    "paper_ids": ["2608.00001", "2608.00002"],
                    "insight": "两篇论文从不同角度提升推理效率。",
                }
            ],
            "connections": [],
            "recommended_revisit": ["2608.00001"],
            "next_questions": ["如何统一评估推理成本？"],
        }

    def test_recap_requires_complete_visible_structure_and_known_ids(self) -> None:
        valid = recap_service._validate_recap_payload(
            self._valid_payload(), self.paper_ids
        )
        self.assertEqual(valid["title"], "本周研究主题")

        invalid_payloads = [
            {},
            {**self._valid_payload(), "title": " "},
            {**self._valid_payload(), "themes": []},
            {
                **self._valid_payload(),
                "themes": [
                    {
                        "name": "主题",
                        "paper_ids": ["invented-id"],
                        "insight": "内容",
                    }
                ],
            },
            {**self._valid_payload(), "recommended_revisit": ["invented-id"]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(
                    (EmptyLlmResponseError, InvalidLlmResponseError)
                ):
                    recap_service._validate_recap_payload(payload, self.paper_ids)

    def test_failed_forced_refresh_preserves_valid_cached_recap(self) -> None:
        payload = self._valid_payload()
        cached = {
            "status": "ok",
            "recap": {**payload, "paper_count": 3},
            "paper_ids": sorted(self.paper_ids),
        }
        papers = [{"_paper_id": paper_id} for paper_id in sorted(self.paper_ids)]
        with (
            patch.object(recap_service, "_get_cached_recap", return_value=cached),
            patch.object(recap_service, "_get_saved_papers", return_value=papers),
            patch.object(recap_service, "_get_llm_config", return_value={"model": "x"}),
            patch.object(recap_service, "_generate_recap_with_llm", return_value=None),
            patch.object(recap_service, "_upsert_recap") as upsert,
        ):
            result = recap_service.get_or_generate_recap(7, force=True)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["recap"]["title"], payload["title"])
        upsert.assert_not_called()

    def test_empty_recap_model_response_is_never_a_success(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  "))]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: response)
            )
        )
        papers = [{"_paper_id": paper_id} for paper_id in sorted(self.paper_ids)]
        with (
            patch.object(
                recap_service,
                "_get_llm_config",
                return_value={
                    "llm_model": "test",
                    "max_tokens": 100,
                    "temperature": 0.1,
                },
            ),
            patch(
                "services.llm_client_factory.build_llm_client",
                return_value=client,
            ),
        ):
            self.assertIsNone(recap_service._generate_recap_with_llm(7, papers))


class AutoClassifyResponseContractTests(unittest.TestCase):
    def test_classification_requires_complete_bounded_structure(self) -> None:
        self.assertEqual(
            _parse_classification_response(
                '{"folder":"NLP","confidence":0.8,"reason":"主题匹配"}'
            ),
            ("NLP", 0.8, "主题匹配"),
        )
        self.assertEqual(
            _parse_classification_response(
                '```json\n{"folder":"NLP","confidence":0.8,"reason":"匹配"}\n```'
            )[0],
            "NLP",
        )

        for raw, error_type in (
            (None, EmptyLlmResponseError),
            (" ", EmptyLlmResponseError),
            ("{}", EmptyLlmResponseError),
            ('{"folder":"NLP","confidence":2,"reason":"匹配"}', InvalidLlmResponseError),
            ('{"folder":"NLP","confidence":true,"reason":"匹配"}', InvalidLlmResponseError),
            ('{"folder":"NLP","confidence":0.8,"reason":""}', EmptyLlmResponseError),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(error_type):
                    _parse_classification_response(raw)

    def test_auto_classify_never_exposes_raw_model_output(self) -> None:
        source = (_SEVER / "services" / "auto_classify_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('error=f"LLM 返回格式错误: {raw[:200]}"', source)
        self.assertIn('error="模型返回内容无效，请重试"', source)

    def test_invalid_classification_never_moves_paper_or_leaks_raw_output(self) -> None:
        class _Connection:
            def execute(self, *_args, **_kwargs):
                return self

            def fetchone(self):
                return {"paper_data": "{}"}

            def close(self):
                return None

        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="secret malformed model output")
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: response)
            )
        )
        settings = {
            "enabled": True,
            "folders": [
                {
                    "name": "NLP",
                    "description": "语言研究",
                    "folder_id": 1,
                    "parent_id": None,
                }
            ],
            "confidence_threshold": 0.6,
        }
        with (
            patch.object(user_settings_service, "get_settings", return_value=settings),
            patch.object(
                auto_classify_service,
                "_resolve_llm_config",
                return_value={
                    "base_url": "https://example.invalid",
                    "model": "test",
                    "max_tokens": 100,
                    "temperature": 0.1,
                },
            ),
            patch.object(kb_service, "_connect", return_value=_Connection()),
            patch.object(kb_service, "set_classify_status") as set_status,
            patch.object(kb_service, "move_papers") as move_papers,
            patch(
                "services.llm_client_factory.build_llm_client",
                return_value=client,
            ),
        ):
            auto_classify_service._do_classify(7, "2608.00001")

        move_papers.assert_not_called()
        self.assertEqual(set_status.call_args.kwargs["status"], "failed")
        self.assertEqual(
            set_status.call_args.kwargs["error"], "模型返回内容无效，请重试"
        )
        self.assertNotIn("secret", set_status.call_args.kwargs["error"])


if __name__ == "__main__":
    unittest.main()
