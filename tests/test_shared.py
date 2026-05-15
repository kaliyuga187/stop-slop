import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=object))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _shared


class TestExtractJson(unittest.TestCase):
    def test_extracts_fenced_json(self) -> None:
        text = "```json\n{\"alpha\": 1}\n```"
        self.assertEqual(_shared.extract_json(text), {"alpha": 1})

    def test_extracts_inline_json_object(self) -> None:
        text = "Result: {\"beta\": 2} trailing"
        self.assertEqual(_shared.extract_json(text), {"beta": 2})

    def test_extracts_inline_json_array(self) -> None:
        text = "prefix [1, 2, 3] suffix"
        self.assertEqual(_shared.extract_json(text), [1, 2, 3])

    def test_raises_on_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            _shared.extract_json("nothing to parse")


if __name__ == "__main__":
    unittest.main()
