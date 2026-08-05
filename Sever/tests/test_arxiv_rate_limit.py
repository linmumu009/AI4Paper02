"""Unit tests for arXiv rate-limit helpers."""

import os
import sys
import unittest

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

from services.arxiv_rate_limit import compute_429_wait, parse_retry_after  # noqa: E402


class TestCompute429Wait(unittest.TestCase):
    def test_exponential_base(self):
        self.assertEqual(compute_429_wait(1, None, base_wait=60, max_wait=900), 60)
        self.assertEqual(compute_429_wait(2, None, base_wait=60, max_wait=900), 120)
        self.assertEqual(compute_429_wait(3, None, base_wait=60, max_wait=900), 240)

    def test_retry_after_larger(self):
        self.assertEqual(compute_429_wait(1, 300, base_wait=60, max_wait=900), 300)

    def test_cap(self):
        self.assertEqual(compute_429_wait(10, None, base_wait=60, max_wait=900), 900)


class TestParseRetryAfter(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_retry_after("120"), 120)

    def test_invalid(self):
        self.assertIsNone(parse_retry_after("n/a"))
        self.assertIsNone(parse_retry_after(None))


if __name__ == "__main__":
    unittest.main()
