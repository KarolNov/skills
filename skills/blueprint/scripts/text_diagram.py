#!/usr/bin/env python3
"""Check a hand-drawn text diagram before it goes into a review.

    text_diagram.py FILE ...      (or - for stdin)

Each FILE holds one diagram drawn with box-drawing characters: the terminal version of a review
diagram, which the blueprint-ui pane shows where it can't draw the SVG. Prints each problem as
`FILE:LINE:COL: message` and exits 1 if there are any, 0 (printing the size) if there are none.

What it checks:
- width: at most 56 columns, so it fits the pane beside its gutter; wide characters (CJK, emoji)
  count two and are refused, since terminals disagree on them.
- no tabs, no trailing spaces, no blank first or last line.
- joins: every corner, tee, cross and arrowhead meets a line coming the other way, and no line
  runs straight into the side of another (`──│`), and no line stops in empty space. Text beside a
  line is fine, one space away at most: labels sit on lines.
"""

import sys
import unicodedata

MAX_COLUMNS = 56

U, D, L, R = "U", "D", "L", "R"
OPPOSITE = {U: D, D: U, L: R, R: L}
STEP = {U: (-1, 0), D: (1, 0), L: (0, -1), R: (0, 1)}

# The directions each character reaches out in.
ARMS = {
    "─": {L, R}, "━": {L, R}, "│": {U, D}, "┃": {U, D},
    "┌": {R, D}, "┐": {L, D}, "└": {U, R}, "┘": {U, L},
    "╭": {R, D}, "╮": {L, D}, "╰": {U, R}, "╯": {U, L},
    "├": {U, D, R}, "┤": {U, D, L}, "┬": {L, R, D}, "┴": {L, R, U}, "┼": {U, D, L, R},
    # An arrowhead reaches back along its tail.
    "▼": {U}, "▲": {D}, "►": {L}, "◄": {R}, "▶": set(), "◀": set(),
}
LINES = {"─", "━", "│", "┃"}
ARROWS = {"▼", "▲", "►", "◄"}
# Characters whose every arm must join something: corners, tees, crosses, arrowheads.
STRICT = set(ARMS) - LINES - {"▶", "◀"}


def width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 0 if unicodedata.combining(ch) else 1


def check(text: str, name: str) -> list[str]:
    problems: list[str] = []
    say = lambda row, col, msg: problems.append(f"{name}:{row + 1}:{col + 1}: {msg}")
    lines = text.rstrip("\n").split("\n")
    if not lines or not lines[0].strip():
        say(0, 0, "starts with a blank line")
    if lines and not lines[-1].strip():
        say(len(lines) - 1, 0, "ends with a blank line")
    grid = []
    for row, line in enumerate(lines):
        if "\t" in line:
            say(row, line.index("\t"), "tab: use spaces")
        if line != line.rstrip():
            say(row, len(line.rstrip()), "trailing spaces")
        for col, ch in enumerate(line):
            if width(ch) == 2 or ch == "️":
                say(row, col, f"wide character {ch!r}: terminals disagree on its width")
        cols = sum(width(ch) for ch in line)
        if cols > MAX_COLUMNS:
            say(row, MAX_COLUMNS, f"{cols} columns, over {MAX_COLUMNS}")
        grid.append(line)

    def at(row: int, col: int) -> str:
        return grid[row][col] if 0 <= row < len(grid) and 0 <= col < len(grid[row]) else " "

    for row, line in enumerate(grid):
        for col, ch in enumerate(line):
            if ch not in ARMS:
                continue
            for arm in ARMS[ch]:
                dr, dc = STEP[arm]
                other = at(row + dr, col + dc)
                joins = OPPOSITE[arm] in ARMS.get(other, set())
                if ch in STRICT and not joins:
                    say(row, col, f"{ch!r} reaches {arm_name(arm)} but meets {other!r}")
                elif ch in LINES and other in ARMS and not joins and other not in ("▶", "◀"):
                    say(row, col, f"{ch!r} runs {arm_name(arm)} into {other!r} without a join")
                elif ch in LINES and other == " " and at(row + 2 * dr, col + 2 * dc) == " ":
                    # One space then a label is a line with its text beside it; two spaces is a line to nowhere.
                    say(row, col, f"{ch!r} stops {arm_name(arm)} in empty space")
    return problems


def arm_name(arm: str) -> str:
    return {U: "up", D: "down", L: "left", R: "right"}[arm]


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    problems: list[str] = []
    for path in paths:
        text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        found = check(text, path)
        problems += found
        if not found:
            rows = text.rstrip("\n").split("\n")
            print(f"{path}: ok, {max(sum(width(c) for c in r) for r in rows)} columns, {len(rows)} rows")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
