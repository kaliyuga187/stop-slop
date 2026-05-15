import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("requests", types.SimpleNamespace())
sys.path.insert(0, str(ROOT / "scripts"))

import slop_lint


class TestPatchParsing(unittest.TestCase):
    def test_parse_patch_to_hunks_single_hunk(self) -> None:
        patch = "\n".join(
            [
                "@@ -1,3 +1,4 @@",
                " line1",
                "-line2",
                "+line2a",
                "+line2b",
                " line3",
            ]
        )
        hunks = slop_lint.parse_patch_to_hunks(patch)
        self.assertEqual(len(hunks), 1)
        self.assertEqual(hunks[0].start_line, 2)
        self.assertEqual(hunks[0].lines, [(2, "line2a"), (3, "line2b")])

    def test_parse_patch_to_hunks_multiple_hunks(self) -> None:
        patch = "\n".join(
            [
                "@@ -1,2 +1,2 @@",
                "-old",
                "+new",
                "@@ -10,2 +10,3 @@",
                " line10",
                "+line11",
                "+line12",
            ]
        )
        hunks = slop_lint.parse_patch_to_hunks(patch)
        self.assertEqual(len(hunks), 2)
        self.assertEqual(hunks[0].lines, [(1, "new")])
        self.assertEqual(hunks[1].start_line, 11)
        self.assertEqual(hunks[1].lines, [(11, "line11"), (12, "line12")])


class TestReviewFilters(unittest.TestCase):
    def test_should_review_filters_non_markdown_and_skips(self) -> None:
        self.assertFalse(slop_lint.should_review({"filename": "notes.txt"}))
        self.assertFalse(slop_lint.should_review({"filename": "LICENSE"}))
        self.assertFalse(slop_lint.should_review({"filename": "references/rules.md"}))
        self.assertFalse(
            slop_lint.should_review({"filename": "readme.md", "status": "removed"})
        )
        self.assertTrue(slop_lint.should_review({"filename": "docs/guide.md"}))

    def test_build_numbered_hunks_formats_lines(self) -> None:
        hunks = [
            slop_lint.Hunk(start_line=5, lines=[(5, "alpha"), (6, "beta")]),
            slop_lint.Hunk(start_line=10, lines=[(10, "gamma")]),
        ]
        rendered = slop_lint.build_numbered_hunks(hunks)
        self.assertIn("    5: alpha", rendered)
        self.assertIn("    6: beta", rendered)
        self.assertIn("---", rendered)
        self.assertIn("   10: gamma", rendered)


class TestSummaryHelpers(unittest.TestCase):
    def test_aggregate_score_averages_dimensions(self) -> None:
        reviews = [
            slop_lint.FileReview(
                path="a.md",
                findings=[],
                score={
                    "directness": 6,
                    "rhythm": 4,
                    "trust": 8,
                    "authenticity": 5,
                    "density": 7,
                },
                summary="ok",
            ),
            slop_lint.FileReview(
                path="b.md",
                findings=[],
                score={"directness": 4, "rhythm": "n/a", "trust": 6},
                summary="ok",
            ),
        ]
        agg = slop_lint.aggregate_score(reviews)
        self.assertAlmostEqual(agg["per_dimension"]["directness"], 5.0)
        self.assertAlmostEqual(agg["per_dimension"]["rhythm"], 4.0)
        self.assertAlmostEqual(agg["total"], sum(agg["per_dimension"].values()))

    def test_format_summary_body_handles_empty(self) -> None:
        self.assertEqual(
            slop_lint.format_summary_body([]),
            "No reviewable prose changes detected. Stop Slop skipped.",
        )

    def test_format_summary_body_includes_tables(self) -> None:
        reviews = [
            slop_lint.FileReview(
                path="docs/guide.md",
                findings=[{"line": 1}],
                score={
                    "directness": 2,
                    "rhythm": 2,
                    "trust": 2,
                    "authenticity": 2,
                    "density": 2,
                },
                summary="Needs work.",
            )
        ]
        body = slop_lint.format_summary_body(reviews)
        self.assertIn("## Stop Slop review", body)
        self.assertIn("Reviewed 1 file(s), found 1 potential slop pattern(s).", body)
        self.assertIn("| Dimension | Score |", body)
        self.assertIn("Aggregate is below 35/50", body)
        self.assertIn("### Per-file summary", body)
        self.assertIn("docs/guide.md", body)


if __name__ == "__main__":
    unittest.main()
