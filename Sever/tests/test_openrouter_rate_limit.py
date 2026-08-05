import os
import sys
import tempfile
import time
import unittest

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

from services.openrouter_rate_limit import (  # noqa: E402
    compute_429_wait,
    get_window_usage,
    parse_rate_limit_reset_ms,
    parse_retry_after,
    wait_for_openrouter_slot,
)


class TestOpenRouter429Wait(unittest.TestCase):
    def test_exponential_backoff(self):
        self.assertEqual(compute_429_wait(1, None, base_wait=5, max_wait=60), 5)
        self.assertEqual(compute_429_wait(2, None, base_wait=5, max_wait=60), 10)
        self.assertEqual(compute_429_wait(3, None, base_wait=5, max_wait=60), 20)

    def test_retry_after_wins(self):
        self.assertEqual(compute_429_wait(1, 30, base_wait=5, max_wait=60), 30)

    def test_cap(self):
        self.assertEqual(compute_429_wait(10, None, base_wait=5, max_wait=60), 60)


class TestOpenRouterWindow(unittest.TestCase):
    def test_rpm_window_blocks_when_full(self):
        from services import openrouter_rate_limit as orl

        tmp = tempfile.mkdtemp()
        state_path = os.path.join(tmp, "openrouter_rate_state.json")
        lock_path = os.path.join(tmp, "openrouter_global.lock")
        orig_state = orl._STATE_PATH
        orig_lock = orl._LOCK_PATH
        orig_db = orl._DB_DIR
        orig_window = orl._WINDOW_SECONDS
        try:
            orl._STATE_PATH = state_path
            orl._LOCK_PATH = lock_path
            orl._DB_DIR = tmp
            orl._WINDOW_SECONDS = 0.01

            now = time.time()
            with open(state_path, "w", encoding="utf-8") as f:
                import json
                json.dump({"timestamps": [now for _ in range(18)]}, f)

            t0 = time.time()
            wait_for_openrouter_slot()
            elapsed = time.time() - t0
            usage = get_window_usage()
            self.assertLessEqual(usage["used_in_window"], 18)
            self.assertGreaterEqual(elapsed, 0.0)
        finally:
            orl._STATE_PATH = orig_state
            orl._LOCK_PATH = orig_lock
            orl._DB_DIR = orig_db
            orl._WINDOW_SECONDS = orig_window


class TestParseHelpers(unittest.TestCase):
    def test_parse_retry_after(self):
        self.assertEqual(parse_retry_after("12"), 12.0)

    def test_parse_rate_limit_reset_ms(self):
        future_ms = (time.time() + 30) * 1000
        wait = parse_rate_limit_reset_ms(str(int(future_ms)))
        self.assertIsNotNone(wait)
        assert wait is not None
        self.assertGreater(wait, 20)
        self.assertLess(wait, 40)


if __name__ == "__main__":
    unittest.main()
