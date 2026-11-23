#!/usr/bin/env python3
"""Tests for text_diagram.py, the check a review's terminal diagrams pass before it is written.

    python3 skills/blueprint/scripts/test_text_diagram.py
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "text_diagram.py"

GOOD = """\
┌──────┐    ┌──────┐
│ cart ├───►│ pay  │
└──────┘    └──┬───┘
               ▼
            ┌──────┐
            │ ship │
            └──────┘
"""


def check(text):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
    try:
        out = subprocess.run([sys.executable, str(SCRIPT), f.name], capture_output=True, text=True)
    finally:
        Path(f.name).unlink()
    return out.returncode, out.stdout.replace(f.name, "D")


class TooWide(unittest.TestCase):
    # @scenario blueprint/propose: Too wide
    def test_wide_or_loose_corner_is_reported_until_it_prints_ok(self):
        code, out = check(GOOD)
        self.assertEqual((code, out), (0, "D: ok, 20 columns, 7 rows\n"))
        # 57 columns: one over.
        wide = "┌" + "─" * 55 + "┐\n└" + "─" * 55 + "┘\n"
        code, out = check(wide)
        self.assertEqual(code, 1)
        self.assertIn("D:1:57: 57 columns, over 56", out)
        self.assertNotIn("ok", out)
        self.assertEqual(check("┌" + "─" * 54 + "┐\n└" + "─" * 54 + "┘\n")[0], 0)  # 56 fits
        # A corner that joins no line: the box's right side is missing.
        loose = "┌──┐\n│ a\n└──┘\n"
        code, out = check(loose)
        self.assertEqual(code, 1)
        self.assertIn("D:1:4: '┐' reaches down but meets ' '", out)
        self.assertIn("D:3:4: '┘' reaches up but meets ' '", out)
        self.assertNotIn("ok", out)


class Other(unittest.TestCase):
    def test_tabs_trailing_spaces_blank_edges_and_wide_characters(self):
        code, out = check("\n│\tx \n│ 漢\n\n")
        self.assertEqual(code, 1)
        for msg in ("D:1:1: starts with a blank line", "tab: use spaces", "trailing spaces",
                    "wide character '漢'"):
            self.assertIn(msg, out)

    def test_line_into_the_side_of_another(self):
        code, out = check("──│\n  │\n")
        self.assertEqual(code, 1)
        self.assertIn("runs right into '│' without a join", out)

    def test_line_to_nowhere_and_label_beside_a_line(self):
        code, out = check("a ───  b\n")
        self.assertEqual(out, "D:1:5: '─' stops right in empty space\n")
        self.assertEqual(check("┌─ label\n│\n└─ two\n")[0], 0)

    def test_no_arguments_prints_usage(self):
        out = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("text_diagram.py FILE", out.stdout)


if __name__ == "__main__":
    unittest.main()
