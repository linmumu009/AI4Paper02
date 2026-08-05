#!/usr/bin/env python3
"""Run content-free production health checks and emit a durable state file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


_SEVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEVER_ROOT))

from services.system_health_service import (  # noqa: E402
    _DEFAULT_STATE_PATH,
    build_health_report,
    persist_report_and_alert,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", default=str(_DEFAULT_STATE_PATH))
    parser.add_argument("--api-origin", default="http://127.0.0.1:8000")
    parser.add_argument("--no-alert", action="store_true")
    args = parser.parse_args()

    report = build_health_report(api_origin=args.api_origin)
    webhook_url = None if args.no_alert else os.environ.get("AI4PAPERS_ALERT_WEBHOOK_URL")
    try:
        persist_report_and_alert(
            report,
            state_path=args.state_file,
            webhook_url=webhook_url,
        )
    except Exception as exc:
        report["issues"] = sorted(set(report.get("issues", [])) | {"alert_delivery_failed"})
        report["status"] = "degraded"
        persist_report_and_alert(report, state_path=args.state_file, webhook_url=None)
        print(f"healthcheck alert error: {type(exc).__name__}", file=sys.stderr)

    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report.get("status") == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
