from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import idea_combine, idea_ingest, idea_review  # noqa: E402
from services import idea_service  # noqa: E402
from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    InvalidLlmResponseError,
)


class _FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, **_kwargs):
        choices = [] if self.content is ... else [
            SimpleNamespace(message=SimpleNamespace(content=self.content))
        ]
        return SimpleNamespace(choices=choices)


def _client(content):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(content))
    )


class IdeaBatchModelContractTests(unittest.TestCase):
    def test_all_batch_model_calls_reject_empty_content(self) -> None:
        cfg = {"model": "test", "system_prompt": "extract"}
        calls = (
            lambda: idea_ingest._extract_atoms_llm(_client(None), cfg, "paper"),
            lambda: idea_combine._call_llm_json(
                _client(None), cfg, "system", "atoms"
            ),
            lambda: idea_review._call_llm_json(
                _client(None), cfg, "system", "candidate"
            ),
        )
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(EmptyLlmResponseError):
                    call()

    def test_ingest_requires_nonempty_valid_atoms(self) -> None:
        for atoms in (
            [],
            [{}],
            [{"type": "unknown", "content": "content"}],
            [{"type": "claim", "content": "  "}],
        ):
            with self.subTest(atoms=atoms):
                with self.assertRaises(InvalidLlmResponseError):
                    idea_ingest._validate_atoms(atoms)

        result = idea_ingest._validate_atoms(
            [{"type": "claim", "content": "  valid claim  "}]
        )
        self.assertEqual(result[0]["content"], "valid claim")

    def test_combine_rejects_empty_or_malformed_structures(self) -> None:
        atoms = [{"id": 1, "atom_type": "limitation", "paper_id": "p", "content": "c"}]
        with patch.object(idea_service, "list_atoms", return_value=atoms):
            with self.assertRaises(InvalidLlmResponseError):
                idea_combine.generate_questions(
                    _client('{"questions": []}'), {"model": "test"}, 7
                )

        question = {"question_text": "how", "id": None}
        with patch.object(idea_service, "search_atoms_fts", return_value=atoms):
            with self.assertRaises(InvalidLlmResponseError):
                idea_combine.generate_candidates_for_question(
                    _client('{"candidates":[{"title":"only title"}]}'),
                    {"model": "test"},
                    7,
                    question,
                )

    def test_review_requires_complete_scores_verdict_and_summary(self) -> None:
        with self.assertRaises(InvalidLlmResponseError):
            idea_review._validate_review({})
        with self.assertRaises(InvalidLlmResponseError):
            idea_review._validate_review(
                {
                    "scores": {
                        "consistency": 0,
                        "novelty": 0,
                        "feasibility": 0,
                        "impact": 0,
                        "overall": 0,
                    },
                    "verdict": "reject",
                    "summary": "",
                }
            )

        valid = idea_review._validate_review(
            {
                "scores": {
                    "consistency": 0.8,
                    "novelty": 0.7,
                    "feasibility": 0.6,
                    "impact": 0.9,
                    "overall": 0.75,
                },
                "verdict": "approve",
                "summary": "solid",
            }
        )
        self.assertEqual(valid["scores"]["overall"], 0.75)

    def test_ingest_failure_does_not_replace_existing_atoms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "paper.md"
            source.write_text("paper text", encoding="utf-8")
            with (
                patch.object(
                    idea_ingest,
                    "_extract_atoms_llm",
                    side_effect=EmptyLlmResponseError("empty"),
                ),
                patch.object(idea_service, "replace_atoms_for_paper") as replace,
            ):
                with self.assertRaises(EmptyLlmResponseError):
                    idea_ingest.process_one(
                        MagicMock(),
                        {},
                        {
                            "paper_id": "paper-a",
                            "content_file": str(source),
                            "source_file": "paper.md",
                        },
                        4,
                        "2026-08-05",
                    )
            replace.assert_not_called()

    def test_ingest_run_marks_partial_failure_and_exits_nonzero(self) -> None:
        paper = {
            "paper_id": "paper-a",
            "content_file": "unused.md",
            "source_file": "unused.md",
        }
        manifest = MagicMock()
        with (
            patch.object(sys, "argv", ["idea_ingest", "--date", "2026-08-05", "--user-id", "4"]),
            patch.dict(os.environ, {"PIPELINE_OUTPUT_MODE": "db"}),
            patch.object(idea_ingest, "_find_papers_for_date_db", return_value=[paper]),
            patch.object(idea_ingest, "_make_client", return_value=(MagicMock(), {})),
            patch.object(
                idea_ingest,
                "process_one",
                side_effect=EmptyLlmResponseError("empty"),
            ),
            patch.object(idea_ingest, "_write_manifest", manifest),
        ):
            with self.assertRaisesRegex(SystemExit, "1"):
                idea_ingest.run()
        self.assertEqual(manifest.call_args.args[1]["status"], "failed")

    def test_combine_run_preserves_old_generation_on_empty_response(self) -> None:
        atoms = [
            {
                "id": 1,
                "atom_type": "limitation",
                "paper_id": "paper-a",
                "content": "limitation",
            }
        ]
        manifest = MagicMock()
        with (
            patch.object(sys, "argv", ["idea_combine", "--date", "2026-08-05", "--user-id", "4"]),
            patch.object(
                idea_combine,
                "_make_client",
                side_effect=[
                    (_client(None), {"model": "test"}),
                    (_client('{"candidates": []}'), {"model": "test"}),
                ],
            ),
            patch.object(idea_service, "count_atoms_for_date", return_value=1),
            patch.object(idea_service, "list_atoms", return_value=atoms),
            patch.object(
                idea_service, "replace_questions_and_candidates_for_date"
            ) as replace,
            patch.object(idea_combine, "_write_manifest", manifest),
        ):
            with self.assertRaisesRegex(SystemExit, "1"):
                idea_combine.run()
        replace.assert_not_called()
        self.assertEqual(manifest.call_args.args[1]["status"], "failed")

    def test_review_run_does_not_archive_candidate_on_empty_response(self) -> None:
        candidate = {
            "id": 9,
            "title": "candidate",
            "goal": "goal",
            "mechanism": "mechanism",
            "risks": "risks",
            "strategy": "patch",
            "tags": [],
            "status": "draft",
        }
        manifest = MagicMock()
        with (
            patch.object(sys, "argv", ["idea_review", "--date", "2026-08-05", "--user-id", "4"]),
            patch.object(
                idea_review,
                "_make_client",
                side_effect=[(MagicMock(), {}), (MagicMock(), {})],
            ),
            patch.object(idea_service, "list_candidates", return_value=[candidate]),
            patch.object(
                idea_review,
                "review_candidate",
                side_effect=EmptyLlmResponseError("empty"),
            ),
            patch.object(idea_service, "update_candidate") as update,
            patch.object(idea_review, "_write_manifest", manifest),
        ):
            with self.assertRaisesRegex(SystemExit, "1"):
                idea_review.run()
        update.assert_not_called()
        self.assertEqual(manifest.call_args.args[1]["status"], "failed")


class IdeaServiceAtomicReplacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "idea.db")
        self.patch_db = patch.object(idea_service, "_DB_PATH", self.db_path)
        self.patch_db.start()
        idea_service.init_db()

    def tearDown(self) -> None:
        self.patch_db.stop()
        self.tmp.cleanup()

    def test_atom_replacement_rolls_back_if_new_batch_cannot_serialize(self) -> None:
        idea_service.create_atom(3, "paper-a", "claim", "old atom")
        invalid_batch = [
            {
                "date_str": "2026-08-05",
                "atom_type": "claim",
                "content": "new atom",
                "tags": {object()},
            }
        ]
        with self.assertRaises(TypeError):
            idea_service.replace_atoms_for_paper(3, "paper-a", invalid_batch)

        remaining = idea_service.list_atoms(user_id=3, paper_id="paper-a")
        self.assertEqual([row["content"] for row in remaining], ["old atom"])

    def test_daily_generation_replacement_is_atomic_and_date_scoped(self) -> None:
        date_str = "2026-07-01"
        old_question = idea_service.create_question(
            3, "old question", date_str=date_str
        )
        idea_service.create_candidate(
            3,
            "old title",
            goal="old goal",
            mechanism="old mechanism",
            risks="old risks",
            question_id=old_question["id"],
            date_str=date_str,
        )

        bad_batches = [
            {
                "question_text": "new question",
                "candidates": [{"goal": "missing title"}],
            }
        ]
        with self.assertRaises(KeyError):
            idea_service.replace_questions_and_candidates_for_date(
                3, date_str, bad_batches
            )

        questions = idea_service.list_questions(3)
        candidates = idea_service.list_candidates(3)
        self.assertEqual([row["question_text"] for row in questions], ["old question"])
        self.assertEqual([row["title"] for row in candidates], ["old title"])


if __name__ == "__main__":
    unittest.main()
