#!/usr/bin/env python3
"""Normalize a Notion page body to plain Markdown and print it or its version marker.

Input is a saved Notion fetch result: the tool's JSON (with a "text" field), the
text inside it, or just the page body. Anything between <content> and </content>
is the body; without those tags the whole input is.

    python3 notion_normalize.py fetch.json            # normalized Markdown
    python3 notion_normalize.py --marker fetch.json   # 16-hex version marker
    python3 notion_normalize.py --marker draft.md     # same marker for a local draft
    cat fetch.json | python3 notion_normalize.py -    # read stdin

Baselines and markers must both come from this script, so a page and its
baseline compare equal when only Notion's rendering differs.
"""

import argparse
import hashlib
import html
import json
import re
import sys


def body_of(raw):
    text = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            text = data["text"]
        elif isinstance(data, str):
            text = data
    except ValueError:
        pass
    m = re.search(r"<content>\n?(.*?)\n?</content>", text, re.S)
    return m.group(1) if m else text


INLINE = [
    (r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**"),
    (r"<(?:i|em)>(.*?)</(?:i|em)>", r"*\1*"),
    (r"<(?:s|strike|del)>(.*?)</(?:s|strike|del)>", r"~~\1~~"),
    (r"<code>(.*?)</code>", r"`\1`"),
    (r"<u>(.*?)</u>", r"\1"),
    (r"<span[^>]*>(.*?)</span>", r"\1"),
    # mentions render as their title
    (r"<mention-[a-z-]+[^>]*>(.*?)</mention-[a-z-]+>", r"\1"),
]

# Notion turns dotted identifiers like Y.Map into links to http://Y.Map
AUTOLINK = re.compile(r"\[([^\]\n]+)\]\((?:https?://)([^)\s]+)\)")
ESCAPE = re.compile(r"\\([\\.`*_{}\[\]()#+\-!>|~])")
BLOCK_COLOR = re.compile(r'\s*\{color="[^"]*"\}\s*$')


def normalize_line(line, in_fence):
    if in_fence:
        return line.rstrip()
    for pattern, repl in INLINE:
        line = re.sub(pattern, repl, line)
    line = AUTOLINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else m.group(0), line)
    line = BLOCK_COLOR.sub("", line)
    line = ESCAPE.sub(r"\1", line)
    line = html.unescape(line)
    return line.rstrip()


def normalize(raw):
    out, in_fence = [], False
    for line in body_of(raw).replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            out.append(line.rstrip())
            in_fence = not in_fence
            continue
        out.append(normalize_line(line, in_fence))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return text + "\n"


def marker(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", help="saved fetch result or Markdown file; - for stdin")
    p.add_argument("--marker", action="store_true", help="print the version marker instead of the text")
    args = p.parse_args()
    raw = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    text = normalize(raw)
    sys.stdout.write(marker(text) + "\n" if args.marker else text)


if __name__ == "__main__":
    main()
