from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import llm_client_factory  # noqa: E402
from services.pipeline_schedule_policy import (  # noqa: E402
    deepseek_offpeak_metadata,
    is_deepseek_offpeak,
    next_deepseek_offpeak_start,
    seconds_until_deepseek_offpeak,
)


_CST = ZoneInfo("Asia/Shanghai")


class DeepSeekOffpeakWindowTests(unittest.TestCase):
    def test_weekday_windows_include_boundary_buffers(self) -> None:
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 25, 8, 54, tzinfo=_CST)))
        self.assertFalse(is_deepseek_offpeak(datetime(2026, 8, 25, 8, 55, tzinfo=_CST)))
        self.assertFalse(is_deepseek_offpeak(datetime(2026, 8, 25, 12, 4, tzinfo=_CST)))
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 25, 12, 5, tzinfo=_CST)))
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 25, 13, 49, tzinfo=_CST)))
        self.assertFalse(is_deepseek_offpeak(datetime(2026, 8, 25, 13, 50, tzinfo=_CST)))
        self.assertFalse(is_deepseek_offpeak(datetime(2026, 8, 25, 18, 4, tzinfo=_CST)))
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 25, 18, 5, tzinfo=_CST)))

    def test_weekend_is_offpeak_all_day(self) -> None:
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 29, 10, 0, tzinfo=_CST)))
        self.assertTrue(is_deepseek_offpeak(datetime(2026, 8, 30, 15, 0, tzinfo=_CST)))

    def test_next_window_is_reported_in_beijing_time(self) -> None:
        morning_peak = datetime(2026, 8, 25, 10, 0, tzinfo=_CST)
        afternoon_peak = datetime(2026, 8, 25, 15, 0, tzinfo=_CST)
        self.assertEqual(
            next_deepseek_offpeak_start(morning_peak).strftime("%H:%M"),
            "12:05",
        )
        self.assertEqual(
            next_deepseek_offpeak_start(afternoon_peak).strftime("%H:%M"),
            "18:05",
        )
        self.assertEqual(seconds_until_deepseek_offpeak(morning_peak), 7500.0)
        metadata = deepseek_offpeak_metadata(morning_peak)
        self.assertFalse(metadata["deepseek_offpeak_now"])
        self.assertIn("T12:05+08:00", metadata["deepseek_offpeak_next_start"])


class DeepSeekOffpeakClientTests(unittest.TestCase):
    class _FakeCompletions:
        def create(self, *args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    class _FakeOpenAI:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(
                completions=DeepSeekOffpeakClientTests._FakeCompletions()
            )

    def test_scheduled_direct_deepseek_request_uses_gate(self) -> None:
        cfg = {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
        }
        env = {
            "DEEPSEEK_OFFPEAK_ONLY": "1",
            "DEEPSEEK_OFFPEAK_CONFIG_PATH": "",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(llm_client_factory, "OpenAI", self._FakeOpenAI),
            patch.object(
                llm_client_factory,
                "validate_user_llm_base_url",
                side_effect=lambda value: value,
            ),
            patch.object(llm_client_factory, "_wait_for_deepseek_offpeak") as wait,
        ):
            client = llm_client_factory.build_llm_client(cfg)
            client.chat.completions.create(model=cfg["model"], messages=[])

        wait.assert_called_once_with(cfg)

    def test_non_deepseek_provider_is_not_delayed(self) -> None:
        cfg = {
            "api_key": "test-key",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
        }
        with (
            patch.dict(os.environ, {"DEEPSEEK_OFFPEAK_ONLY": "1"}, clear=False),
            patch.object(llm_client_factory, "OpenAI", self._FakeOpenAI),
            patch.object(
                llm_client_factory,
                "validate_user_llm_base_url",
                side_effect=lambda value: value,
            ),
            patch.object(llm_client_factory, "_wait_for_deepseek_offpeak") as wait,
        ):
            client = llm_client_factory.build_llm_client(cfg)
            client.chat.completions.create(model=cfg["model"], messages=[])

        wait.assert_not_called()

    def test_saved_admin_switch_can_release_waiting_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "schedule_config.json"
            config_path.write_text(
                json.dumps({"deepseek_offpeak_enabled": False}),
                encoding="utf-8",
            )
            env = {
                "DEEPSEEK_OFFPEAK_ONLY": "1",
                "DEEPSEEK_OFFPEAK_CONFIG_PATH": str(config_path),
            }
            with patch.dict(os.environ, env, clear=False):
                self.assertFalse(
                    llm_client_factory._should_apply_deepseek_offpeak_gate({
                        "base_url": "https://api.deepseek.com/v1",
                    })
                )


if __name__ == "__main__":
    unittest.main()
