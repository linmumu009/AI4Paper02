import unittest

from services.chat_service import _build_evidence_sources, _extract_referenced_sources


class ChatEvidenceTests(unittest.TestCase):
    def test_builds_section_and_page_aware_sources(self):
        content = """<!-- page: 3 -->
# Method
We optimize the objective with a constrained decoder.

The decoder preserves the graph structure during inference.

<!-- page: 4 -->
# Results
Accuracy improves by 4.2 points on the main benchmark.
"""
        annotated, sources = _build_evidence_sources(content, "full_text", "2401.00001")

        self.assertGreaterEqual(len(sources), 2)
        self.assertIn("[S1 | 第 3 页 · Method]", annotated)
        self.assertEqual(sources[0]["paper_id"], "2401.00001")
        self.assertEqual(sources[0]["page"], 3)
        self.assertNotIn("text", sources[0])

    def test_only_returns_sources_actually_cited_by_model(self):
        sources = [
            {"id": "S1", "excerpt": "one"},
            {"id": "S2", "excerpt": "two"},
            {"id": "S3", "excerpt": "three"},
        ]
        cited = _extract_referenced_sources("Claim [S2]. Another [S2]. Missing [S99].", sources)
        self.assertEqual(cited, [sources[1]])


if __name__ == "__main__":
    unittest.main()
