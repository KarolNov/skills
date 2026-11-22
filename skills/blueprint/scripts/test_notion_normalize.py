#!/usr/bin/env python3
"""Tests for notion_normalize.py: a Notion fetch and its baseline must read the same.

    python3 skills/blueprint/scripts/test_notion_normalize.py
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "notion_normalize.py"
sys.path.insert(0, str(SCRIPT.parent))
import notion_normalize as nn  # noqa: E402

BASELINE = "## Requirements\n\n- **Scenario: Shared doc**\n  - **THEN** the `Y.Map` holds the board\n"


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True)


class AutoLinked(unittest.TestCase):
    # @scenario blueprint/backends: Auto-linked identifier
    def test_code_tag_reads_as_inline_code_and_matches_the_baseline(self):
        for saved in ("<code>Y.Map</code>",                  # the HTML code tag
                      "<code>[Y.Map](http://Y.Map)</code>",  # with Notion's auto-link inside
                      "`[Y.Map](https://Y.Map)`"):           # or the link inside backticks
            with self.subTest(saved=saved):
                page = ("<page><content>\n## Requirements\n\n- <b>Scenario: Shared doc</b>\n"
                        f"  - <strong>THEN</strong> the {saved}"
                        " holds the board\n</content></page>")
                fetch = json.dumps({"metadata": {"type": "page"}, "text": page})
                self.assertEqual(nn.normalize(fetch), BASELINE)
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                    f.write(fetch)
                self.addCleanup(Path(f.name).unlink)
                with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as b:
                    b.write(BASELINE)
                self.addCleanup(Path(b.name).unlink)
                self.assertEqual(run(f.name).stdout, BASELINE)
                self.assertEqual(run("--marker", f.name).stdout, run("--marker", b.name).stdout)

    def test_a_real_link_is_kept(self):
        line = "See [the docs](https://example.com/docs) and [x.y](https://x.y/z)."
        self.assertEqual(nn.normalize(line), line + "\n")


class Normalize(unittest.TestCase):
    def test_escapes_entities_and_colors_go_fences_stay(self):
        raw = ("# Title {color=\"gray\"}\n\n\n\nA \\*star\\* &amp; <i>it</i>\n"
               "```\n<code>raw</code>  \n```\n")
        self.assertEqual(nn.normalize(raw), "# Title\n\nA *star* & *it*\n```\n<code>raw</code>\n```\n")

    def test_stdin_and_marker_length(self):
        out = run("--marker", "-", stdin="hello\n").stdout.strip()
        self.assertEqual(len(out), 16)
        self.assertEqual(out, nn.marker("hello\n"))


if __name__ == "__main__":
    unittest.main()
