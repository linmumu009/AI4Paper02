from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import paperList_remove_duplications as dedup  # noqa: E402


class PaperDedupRetryIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_path = self.root / "arxiv" / "2026-09-02.json"
        self.output_path = self.root / "dedup" / "2026-09-02.json"
        self.history_path = self.root / "config" / "paperList.json"
        self.input_path.parent.mkdir(parents=True)
        self.input_path.write_text(
            json.dumps(
                {
                    "papers": [
                        {"arxiv_id": "2609.00001", "title": "First"},
                        {"arxiv_id": "2609.00002", "title": "Second"},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self) -> dict:
        argv = [
            "paperList_remove_duplications.py",
            "--json",
            str(self.input_path),
            "--out-json",
            str(self.output_path),
        ]
        with (
            patch.object(dedup, "CONFIG_PATH", self.history_path),
            patch.object(sys, "argv", argv),
        ):
            dedup.run()
        return json.loads(self.output_path.read_text(encoding="utf-8"))

    def test_same_batch_retry_keeps_papers_without_duplicating_history(self) -> None:
        first = self._run()
        second = self._run()
        history = json.loads(self.history_path.read_text(encoding="utf-8"))

        self.assertEqual(first["selected"], 2)
        self.assertEqual(second["selected"], 2)
        self.assertEqual(len(history), 2)
        self.assertEqual({item["batch_date"] for item in history}, {"2026-09-02"})

    def test_previous_batch_still_filters_true_historical_duplicates(self) -> None:
        self.history_path.parent.mkdir(parents=True)
        self.history_path.write_text(
            json.dumps(
                [
                    {
                        "title": "First",
                        "source": "2609.00001",
                        "writing_datetime": "2026-09-01T01:00:00+00:00",
                        "batch_date": "2026-09-01",
                    }
                ]
            ),
            encoding="utf-8",
        )

        result = self._run()
        history = json.loads(self.history_path.read_text(encoding="utf-8"))

        self.assertEqual(result["selected"], 1)
        self.assertEqual(result["papers"][0]["arxiv_id"], "2609.00002")
        self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
