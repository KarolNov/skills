#!/usr/bin/env python3
"""Render Mermaid diagrams to standalone SVG images, for backends that show Mermaid as code.

    render_mermaid.py OUT_DIR FILE ...

Each FILE is a `.mmd` file (one diagram), or a Markdown / HTML file whose ```mermaid fences or
<pre class="mermaid"> blocks are rendered in order. Writes `<stem>-<n>.svg` per diagram and prints
the paths. The SVGs have plain text labels (no HTML inside), a fixed size and a white card behind
the drawing, so they display as <img> and read on dark pages too.

Needs Python Playwright with Chromium (`pip install playwright && playwright install chromium`,
or reuse an existing install such as ~/.walkthrough/venv). Mermaid itself loads from jsDelivr.
Without Playwright, `npx -y @mermaid-js/mermaid-cli -i in.mmd -o out.svg` is the fallback.
"""

import html
import re
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed for this Python; see the docstring for options.")

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs"

PAGE = """<!doctype html><meta charset="utf-8"><body><script type="module">
import m from '%s';
m.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'strict',
  fontFamily: 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif',
  htmlLabels: false, flowchart: { htmlLabels: false, useMaxWidth: false },
  sequence: { useMaxWidth: false }, state: { useMaxWidth: false } });
// Render, then re-serialize as XML with a fixed size and a white card, so it works as an <img>.
window.render = async (id, code) => {
  const { svg } = await m.render(id, code);
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const el = doc.documentElement;
  const [x, y, w, h] = el.getAttribute('viewBox').split(/[ ,]+/).map(Number);
  const pad = 16, box = [x - pad, y - pad, w + 2 * pad, h + 2 * pad];
  el.setAttribute('viewBox', box.join(' '));
  el.setAttribute('width', box[2]); el.setAttribute('height', box[3]);
  el.removeAttribute('style');
  const bg = doc.createElementNS('http://www.w3.org/2000/svg', 'rect');
  const attrs = { x: box[0], y: box[1], width: box[2], height: box[3], rx: 8, fill: '#ffffff' };
  for (const [k, v] of Object.entries(attrs)) bg.setAttribute(k, v);
  el.insertBefore(bg, el.firstChild);
  return new XMLSerializer().serializeToString(el);
};
window.ready = true;
</script>""" % MERMAID


def diagrams(path):
    text = path.read_text()
    if path.suffix == ".mmd":
        return [text.strip()]
    found = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    found += [html.unescape(b) for b in re.findall(r'<pre class="mermaid">(.*?)</pre>', text, re.S)]
    return [d.strip() for d in found]


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(Path(f), i, code) for f in sys.argv[2:] for i, code in enumerate(diagrams(Path(f)), 1)]
    if not jobs:
        sys.exit("no Mermaid diagrams found")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(PAGE)
        page.wait_for_function("window.ready === true", timeout=30000)
        for n, (src, i, code) in enumerate(jobs):
            svg = page.evaluate("([id, c]) => window.render(id, c)", [f"d{n}", code])
            name = out / (f"{src.stem}.svg" if src.suffix == ".mmd" else f"{src.stem}-{i}.svg")
            name.write_text(svg)
            print(name)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
