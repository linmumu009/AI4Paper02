from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import (  # noqa: E402
    auto_classify_service,
    kb_service,
    user_presets_service,
    user_settings_service,
)
from services.llm_response_guard import InvalidLlmResponseError  # noqa: E402


class AutoClassifyFolderSuggestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder_defs = [
            {
                "name": "人工智能",
                "description": "AI 研究",
                "folder_id": 1,
                "parent_id": None,
                "origin": "user",
            },
            {
                "name": "强化学习",
                "description": "RL",
                "folder_id": 2,
                "parent_id": 1,
                "origin": "user",
            },
        ]

    def test_real_kb_tree_is_the_backbone_and_saved_settings_only_add_metadata(self) -> None:
        tree = {
            "folders": [
                {
                    "id": 1,
                    "name": "用户改名后的目录",
                    "children": [
                        {"id": 2, "name": "子目录", "children": [], "papers": []}
                    ],
                    "papers": [],
                }
            ],
            "papers": [],
        }
        saved = [
            {"folder_id": 1, "name": "旧名字", "description": "保留说明", "origin": "ai"},
            {"folder_id": 999, "name": "已删除目录", "description": "不应复活"},
        ]

        result = auto_classify_service.build_effective_folder_definitions(tree, saved)

        self.assertEqual([item["name"] for item in result], ["用户改名后的目录", "子目录"])
        self.assertEqual(result[0]["description"], "保留说明")
        self.assertEqual(result[0]["origin"], "ai")
        self.assertEqual(result[1]["parent_id"], 1)

    def test_parser_accepts_only_missing_folders_and_known_papers(self) -> None:
        raw = json.dumps(
            {
                "suggestions": [
                    {
                        "name": "推理优化",
                        "parent_path": "人工智能",
                        "description": "模型推理效率、缓存和解码优化",
                        "reason": "多篇论文尚无更具体的归属",
                        "paper_ids": ["p1", "p2", "invented", "p1"],
                    },
                    {
                        "name": "强化学习",
                        "parent_path": "人工智能",
                        "description": "重复目录",
                        "reason": "不应被采纳",
                        "paper_ids": ["p2"],
                    },
                ]
            },
            ensure_ascii=False,
        )

        result = auto_classify_service._parse_folder_suggestions_response(
            raw,
            self.folder_defs,
            {"p1", "p2"},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "推理优化")
        self.assertEqual(result[0]["parent_id"], 1)
        self.assertEqual(result[0]["origin"], "ai")
        self.assertEqual(result[0]["paper_ids"], ["p1", "p2"])
        self.assertEqual(result[0]["paper_count"], 2)

    def test_parser_recovers_one_valid_json_object_from_provider_wrapper(self) -> None:
        raw = (
            "目录建议如下：\n"
            '{"suggestions":[{"name":"推理优化","parent_path":"人工智能",'
            '"description":"推理效率研究","reason":"现有目录过宽",'
            '"paper_ids":["p1","p2"]}]}\n'
            "以上为建议。"
        )

        result = auto_classify_service._parse_folder_suggestions_response(
            raw,
            self.folder_defs,
            {"p1", "p2"},
        )

        self.assertEqual([item["name"] for item in result], ["推理优化"])

    def test_parser_rejects_unknown_parent_or_nested_name(self) -> None:
        for suggestion in (
            {
                "name": "新目录",
                "parent_path": "不存在",
                "description": "说明",
                "reason": "原因",
                "paper_ids": [],
            },
            {
                "name": "父/子",
                "parent_path": "",
                "description": "说明",
                "reason": "原因",
                "paper_ids": [],
            },
        ):
            with self.subTest(suggestion=suggestion):
                with self.assertRaises(InvalidLlmResponseError):
                    auto_classify_service._parse_folder_suggestions_response(
                        json.dumps({"suggestions": [suggestion]}, ensure_ascii=False),
                        self.folder_defs,
                        set(),
                    )

    def test_ambiguous_leaf_name_falls_back_to_unclassified(self) -> None:
        folders = [
            {"name": "A", "folder_id": 1, "parent_id": None},
            {"name": "共同子目录", "folder_id": 2, "parent_id": 1},
            {"name": "B", "folder_id": 3, "parent_id": None},
            {"name": "共同子目录", "folder_id": 4, "parent_id": 3},
        ]
        with patch.object(
            kb_service,
            "get_or_create_system_folder",
            return_value=99,
        ) as unclassified:
            result = auto_classify_service._resolve_or_create_folder(
                7, "共同子目录", "kb", folders
            )

        self.assertEqual(result, 99)
        unclassified.assert_called_once_with(7, "未分类", "kb")

    def test_suggestion_sample_prioritises_unclassified_papers(self) -> None:
        tree = {
            "folders": [
                {
                    "id": 1,
                    "name": "已有分类",
                    "papers": [{"paper_id": "classified", "paper_data": {}}],
                    "children": [],
                },
                {
                    "id": 2,
                    "name": "未分类",
                    "papers": [{"paper_id": "pending", "paper_data": {}}],
                    "children": [],
                },
            ],
            "papers": [],
        }

        sample = auto_classify_service._collect_suggestion_papers(tree)

        self.assertEqual(
            [item["paper_id"] for item in sample],
            ["pending", "classified"],
        )

    def test_suggestion_preview_never_creates_folders_or_moves_papers(self) -> None:
        tree = {
            "folders": [
                {
                    "id": 1,
                    "name": "人工智能",
                    "children": [],
                    "papers": [],
                }
            ],
            "papers": [
                {
                    "paper_id": "p1",
                    "paper_data": {
                        "short_title": "高效推理",
                        "abstract": "研究低延迟推理。",
                    },
                },
                {
                    "paper_id": "p2",
                    "paper_data": {
                        "short_title": "稀疏推理",
                        "abstract": "研究稀疏模型推理。",
                    },
                },
            ],
        }
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "suggestions": [
                                    {
                                        "name": "推理优化",
                                        "parent_path": "人工智能",
                                        "description": "推理效率研究",
                                        "reason": "现有目录过宽",
                                        "paper_ids": ["p1", "p2"],
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: response)
            )
        )
        with (
            patch.object(
                user_settings_service,
                "get_settings",
                return_value={"enabled": False, "folders": []},
            ),
            patch.object(
                auto_classify_service,
                "_resolve_llm_config",
                return_value={
                    "base_url": "https://example.invalid",
                    "api_key": "test",
                    "model": "test",
                    "max_tokens": 1000,
                    "temperature": 0.1,
                },
            ),
            patch.object(kb_service, "get_tree", return_value=tree),
            patch.object(kb_service, "create_folder") as create_folder,
            patch.object(kb_service, "move_papers") as move_papers,
            patch("services.llm_client_factory.build_llm_client", return_value=client),
        ):
            result = auto_classify_service.suggest_folders(7)

        create_folder.assert_not_called()
        move_papers.assert_not_called()
        self.assertEqual(result["suggestions"][0]["name"], "推理优化")
        self.assertEqual(result["analyzed_papers"], 2)

    def test_suggestion_retries_truncated_deepseek_json_with_larger_budget(self) -> None:
        tree = {
            "folders": [
                {
                    "id": 1,
                    "name": "人工智能",
                    "children": [],
                    "papers": [],
                }
            ],
            "papers": [
                {"paper_id": "p1", "paper_data": {"short_title": "高效推理"}},
                {"paper_id": "p2", "paper_data": {"short_title": "稀疏推理"}},
            ],
        }
        valid = json.dumps(
            {
                "suggestions": [
                    {
                        "name": "推理优化",
                        "parent_path": "人工智能",
                        "description": "推理效率研究",
                        "reason": "现有目录过宽",
                        "paper_ids": ["p1", "p2"],
                    }
                ]
            },
            ensure_ascii=False,
        )
        requests = []
        responses = iter(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"suggestions": ['),
                            finish_reason="length",
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=valid),
                            finish_reason="stop",
                        )
                    ]
                ),
            ]
        )

        def _create(**kwargs):
            requests.append(kwargs)
            return next(responses)

        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=_create)
            )
        )
        with (
            patch.object(
                user_settings_service,
                "get_settings",
                return_value={"enabled": False, "folders": []},
            ),
            patch.object(
                auto_classify_service,
                "_resolve_llm_config",
                return_value={
                    "base_url": "https://api.deepseek.com",
                    "api_key": "test",
                    "model": "deepseek-v4-flash",
                    "max_tokens": 512,
                    "temperature": 0.1,
                    "enable_thinking": False,
                },
            ),
            patch.object(kb_service, "get_tree", return_value=tree),
            patch("services.llm_client_factory.build_llm_client", return_value=client),
        ):
            result = auto_classify_service.suggest_folders(7)

        self.assertEqual(result["suggestions"][0]["name"], "推理优化")
        self.assertEqual([item["max_tokens"] for item in requests], [2048, 4096])
        self.assertEqual(
            [item.get("response_format") for item in requests],
            [{"type": "json_object"}, {"type": "json_object"}],
        )

    def test_user_model_preset_takes_priority_over_platform_default(self) -> None:
        with (
            patch.object(
                user_settings_service,
                "get_settings",
                return_value={"enabled": False, "llm_preset_id": 9},
            ),
            patch.object(
                user_presets_service,
                "get_llm_preset",
                return_value={
                    "base_url": "https://user.example/v1",
                    "api_key": "user-key",
                    "model": "user-model",
                    "max_tokens": 900,
                    "temperature": 0.25,
                    "enable_thinking": True,
                },
            ),
            patch.object(
                user_settings_service,
                "resolve_admin_llm_for_feature",
            ) as resolve_admin,
        ):
            result = auto_classify_service._resolve_llm_config(
                7,
                require_enabled=False,
            )

        self.assertEqual(result["base_url"], "https://user.example/v1")
        self.assertEqual(result["model"], "user-model")
        self.assertEqual(result["max_tokens"], 900)
        self.assertTrue(result["enable_thinking"])
        resolve_admin.assert_not_called()

    def test_platform_default_is_used_when_user_has_no_model(self) -> None:
        with (
            patch.object(
                user_settings_service,
                "get_settings",
                return_value={"enabled": False, "llm_preset_id": ""},
            ),
            patch.object(
                user_settings_service,
                "resolve_admin_llm_for_feature",
                return_value={
                    "llm_base_url": "https://api.deepseek.com",
                    "llm_api_key": "platform-key",
                    "llm_model": "deepseek-chat",
                    "max_tokens": 1200,
                    "temperature": 0.15,
                },
            ) as resolve_admin,
        ):
            result = auto_classify_service._resolve_llm_config(
                7,
                require_enabled=False,
            )

        resolve_admin.assert_called_once_with("auto_classify")
        self.assertEqual(result["base_url"], "https://api.deepseek.com")
        self.assertEqual(result["model"], "deepseek-chat")
        self.assertEqual(result["max_tokens"], 1200)
        self.assertEqual(result["temperature"], 0.15)

    def test_sync_uses_recreated_parent_id_for_existing_child(self) -> None:
        class _Connection:
            def __init__(self):
                self.row = None

            def execute(self, sql, params):
                if sql.startswith("SELECT id, name, parent_id"):
                    folder_id = params[0]
                    self.row = (
                        {"id": 2, "name": "子目录", "parent_id": None}
                        if folder_id == 2
                        else None
                    )
                else:
                    self.row = None
                return self

            def fetchone(self):
                return self.row

            def close(self):
                return None

        entries = [
            {
                "name": "父目录",
                "description": "",
                "folder_id": 99,
                "parent_id": None,
                "_key": "parent",
                "origin": "ai",
            },
            {
                "name": "子目录",
                "description": "",
                "folder_id": 2,
                "parent_id": 99,
                "_key": "child",
                "_parent_key": "parent",
                "origin": "user",
            },
        ]
        with (
            patch.object(kb_service, "_connect", side_effect=_Connection),
            patch.object(
                kb_service,
                "create_folder",
                return_value={"id": 10, "parent_id": None},
            ),
            patch.object(kb_service, "rename_folder") as rename_folder,
            patch.object(
                kb_service,
                "move_folder",
                return_value={"id": 2, "name": "子目录", "parent_id": 10},
            ) as move_folder,
        ):
            result = auto_classify_service.sync_folders(7, entries)

        rename_folder.assert_not_called()
        move_folder.assert_called_once_with(7, 2, 10, scope="kb")
        self.assertEqual(result[0]["folder_id"], 10)
        self.assertEqual(result[1]["parent_id"], 10)


if __name__ == "__main__":
    unittest.main()
