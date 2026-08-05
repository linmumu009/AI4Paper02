from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.safe_logging_service import (  # noqa: E402
    is_error_reference,
    is_public_error_detail,
    log_internal_error,
    public_error_detail,
    redact_sensitive_text,
)
from config.logging_config import _JsonFormatter, _RedactingFormatter  # noqa: E402


class SafeLoggingServiceTests(unittest.TestCase):
    def test_redacts_common_credentials_and_signed_query_values(self) -> None:
        raw = (
            'api_key="sk-secret-value-123" '
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature "
            "https://example.test/file?token=signed-private-value&paper=123 "
            "password=hunter2 enc:v1:encrypted-token-value"
        )
        redacted = redact_sensitive_text(raw)
        for secret in (
            "sk-secret-value-123",
            "eyJhbGciOiJIUzI1NiJ9.secret.signature",
            "signed-private-value",
            "hunter2",
            "encrypted-token-value",
        ):
            self.assertNotIn(secret, redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 5)

    def test_internal_error_has_reference_and_sanitized_log(self) -> None:
        logger = Mock(spec=logging.Logger)
        exc = RuntimeError("upstream rejected api_key=sk-private-123456")
        reference = log_internal_error(
            logger,
            "paper summary",
            exc,
            request_path="/api/test?token=private-link-token",
        )
        self.assertRegex(reference, r"^[0-9a-f]{12}$")
        self.assertTrue(is_error_reference(reference))
        self.assertFalse(is_error_reference("not-a-reference"))
        logged = " ".join(str(value) for value in logger.error.call_args.args)
        self.assertNotIn("sk-private-123456", logged)
        self.assertNotIn("private-link-token", logged)
        detail = public_error_detail(reference)
        self.assertTrue(is_public_error_detail(detail))

    def test_truncates_unbounded_upstream_errors(self) -> None:
        redacted = redact_sensitive_text("x" * 9000, max_length=100)
        self.assertLessEqual(len(redacted), 114)
        self.assertTrue(redacted.endswith("...[TRUNCATED]"))

    def test_text_and_json_formatters_redact_before_emitting(self) -> None:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request failed token=private-token-value",
            args=(),
            exc_info=None,
        )
        text_output = _RedactingFormatter("%(message)s").format(record)
        json_output = _JsonFormatter().format(record)
        self.assertNotIn("private-token-value", text_output)
        self.assertNotIn("private-token-value", json_output)


if __name__ == "__main__":
    unittest.main()
