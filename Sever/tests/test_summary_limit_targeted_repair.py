from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


SEVER_ROOT = Path(__file__).resolve().parents[1]
if str(SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SEVER_ROOT))

from services.recommend_card_prompt_eval import deterministic_report  # noqa: E402
from services.recommend_card_targeted_repair import (  # noqa: E402
    repair_card_contract,
)


SOURCE_CARD = """笔记标题：框架贡献评测
📖标题：A Controlled Benchmark
🌐来源：arXiv,2608.00001
推荐理由：用受控协议分开模型与框架收益。

🛎️文章简介
🔸研究问题：如何测量运行框架的独立贡献？
🔸主要贡献：构建受控协议，分离测量模型、任务与框架影响。

📝重点思路
🔸固定模型和任务，只替换框架。
🔸隔离开发、验证和测试数据。
🔸在统一预算下记录并比较收益。

🔎分析总结
🔸框架会改变同一模型的任务表现。
🔸框架收益随任务变化。
🔸受控协议可分开模型与框架贡献。

💡个人观点
协议提高了框架比较的可解释性，但受任务范围限制。

一句话记忆版：固定模型和任务，才能看清框架本身对智能体表现的独立贡献以及不同任务条件、统一预算、数据隔离和修改轨迹下的变化边界与适用范围。
"""

REPAIRED_MEMORY = "固定模型，才能看清框架贡献。"


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _cfg() -> dict:
    return {
        "card_prompt": "compress",
        "model": "test-model",
        "base_url": "https://example.com/v1",
        "max_tokens": 2048,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
    }


def _errors(candidate: str) -> list[str]:
    return list(
        deterministic_report(
            candidate,
            source_text=SOURCE_CARD,
            refinement_input=SOURCE_CARD,
        )["contract_errors"]
    )


class TargetedCardRepairTests(unittest.TestCase):
    def test_repairs_only_the_invalid_memory_field(self) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = _response(REPAIRED_MEMORY)

        repaired, calls = repair_card_contract(
            client,
            SOURCE_CARD,
            source_draft=SOURCE_CARD,
            effective_cfg=_cfg(),
        )

        self.assertEqual(calls, 1)
        self.assertEqual(_errors(repaired), [])
        self.assertIn(f"一句话记忆版：{REPAIRED_MEMORY}", repaired)
        self.assertIn("🔸框架收益随任务变化。", repaired)

    def test_overlong_field_repair_is_locally_clipped_without_new_content(self) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = _response(
            "固定模型和任务，才能看清框架本身对智能体表现的独立贡献以及不同任务条件下的变化边界。"
        )

        repaired, calls = repair_card_contract(
            client,
            SOURCE_CARD,
            source_draft=SOURCE_CARD,
            effective_cfg=_cfg(),
        )

        self.assertEqual(calls, 1)
        self.assertEqual(_errors(repaired), [])


if __name__ == "__main__":
    unittest.main()
