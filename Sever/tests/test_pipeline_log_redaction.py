from __future__ import annotations

import unittest
from pathlib import Path


_PIPELINE = Path(__file__).resolve().parents[1] / "routers" / "pipeline_router.py"


class PipelineLogRedactionTests(unittest.TestCase):
    def test_all_pipeline_log_boundaries_apply_redaction(self) -> None:
        source = _PIPELINE.read_text(encoding="utf-8")
        self.assertIn(
            "from services.safe_logging_service import "
            "redact_sensitive_data, redact_sensitive_text",
            source,
        )
        self.assertIn(
            'return [redact_sensitive_text(ln.rstrip("\\n")) for ln in lines[-n:]]',
            source,
        )
        self.assertEqual(
            source.count('line = redact_sensitive_text(line.rstrip("\\n"))'),
            2,
        )
        self.assertIn("msg = redact_sensitive_text(msg)", source)
        self.assertIn('redact_sensitive_text(f"[ERROR] {exc}")', source)
        self.assertIn('redact_sensitive_text(f"[RERUN] error: {exc!r}")', source)

    def test_structured_admin_diagnostics_are_sanitized(self) -> None:
        source = _PIPELINE.read_text(encoding="utf-8")
        for name in ("runs", "run", "steps", "events", "artifacts"):
            self.assertIn(f"redact_sensitive_data({name})", source)


if __name__ == "__main__":
    unittest.main()
