"""
Structured logging configuration for the ArxivPaper4 FastAPI server.

Usage in api.py startup:
    from config.logging_config import configure_logging
    configure_logging()

Or set environment variables before starting:
    LOG_LEVEL=INFO    (DEBUG / INFO / WARNING / ERROR / CRITICAL)
    LOG_FORMAT=json   (json | text)
"""

import logging
import os
import sys


def configure_logging() -> None:
    """Configure root logger based on LOG_LEVEL and LOG_FORMAT env vars."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.environ.get("LOG_FORMAT", "text").lower()

    if fmt == "json":
        formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured log ingestion (e.g. Loki, CloudWatch)."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        import traceback

        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exc"] = record.exc_text

        # Attach extra fields (e.g. request_id, user_id) if callers pass them
        for key in ("request_id", "user_id", "paper_id", "session_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)
