import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=object))
sys.modules.setdefault("requests", types.SimpleNamespace())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mine_rules


class TestSampleLoading(unittest.TestCase):
    def test_load_local_samples_filters_and_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            samples_dir = Path(tmp)
            (samples_dir / "b.txt").write_text("Bravo", encoding="utf-8")
            (samples_dir / "a.md").write_text("Alpha", encoding="utf-8")
            (samples_dir / "empty.md").write_text("", encoding="utf-8")
            (samples_dir / "skip.rtf").write_text("Skip", encoding="utf-8")
            with mock.patch.object(mine_rules, "SAMPLES_DIR", samples_dir):
                samples = mine_rules.load_local_samples()

        self.assertEqual([s.name for s in samples], ["samples/a.md", "samples/b.txt"])
        self.assertEqual([s.text for s in samples], ["Alpha", "Bravo"])


class TestAdditions(unittest.TestCase):
    def test_apply_additions_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ref_dir = Path(tmp)
            phrases = ref_dir / "phrases.md"
            structures = ref_dir / "structures.md"
            phrases.write_text("Alpha\n", encoding="utf-8")
            structures.write_text("Beta\n", encoding="utf-8")
            additions = [
                {"kind": "phrase", "markdown_entry": "## New phrases\n- Example"},
                {"kind": "structure", "markdown_entry": "## New structures\n| Pattern | Problem |"},
            ]
            with mock.patch.object(mine_rules, "REFERENCES_DIR", ref_dir):
                changed = mine_rules.apply_additions(additions)

            self.assertEqual(set(changed), {phrases, structures})
            self.assertEqual(
                phrases.read_text(encoding="utf-8"),
                "Alpha\n\n## New phrases\n- Example\n",
            )
            self.assertEqual(
                structures.read_text(encoding="utf-8"),
                "Beta\n\n## New structures\n| Pattern | Problem |\n",
            )

    def test_format_pr_body_includes_additions(self) -> None:
        additions = [
            {
                "kind": "phrase",
                "title": "New rule",
                "frequency": 2,
                "rationale": "Why it matters.",
                "examples": ["Example one"],
                "fix": "Rewrite it.",
            }
        ]
        body = mine_rules.format_pr_body(additions, samples_used=3)
        self.assertIn("Mined 1 new rule addition(s) from 3 sample(s).", body)
        self.assertIn("### New rule (phrase, frequency 2)", body)
        self.assertIn("Why it matters.", body)
        self.assertIn("- Example one", body)
        self.assertIn("**Fix:** Rewrite it.", body)


if __name__ == "__main__":
    unittest.main()
