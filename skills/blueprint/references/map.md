# Map

Draw the repo's capabilities as one local page and open it: how they group into domains, which share files, which drifted, and what each requires, with search across all of it. It reads only what is in the repo (`blueprint.json`, `baseline/`, the files), so it needs no backend connection and writes nothing outside `.blueprint/map.html` and, once, `.gitignore`.

## 1. Write the page

From anywhere inside the repo:

```bash
python3 <this skill>/scripts/graph.py
```

Run the skill's own `graph.py`, never a copy in the repo: it imports anchor matching from the `drift.py` next to it, so it works even where the repo's `.blueprint/drift.py` is an older copy. It writes `.blueprint/map.html` (repo root, the main checkout's name in the title when run in a worktree) with d3, the page script and the data inlined, so it opens offline and inside a Notion embed, and prints the path. `--out PATH` writes elsewhere; `--json` prints the extracted data instead, which is the quickest way to answer a question about the graph without opening it.

If it exits with an error, show the error and stop; don't hand-build the page.

## 2. Keep it out of git

The page is regenerated on demand and goes stale with the next commit, so it is never committed. Check:

```bash
git check-ignore -q .blueprint/map.html
```

When that fails (exit 1), append `.blueprint/map.html` on its own line to the repo root's `.gitignore` (create the file if there is none) and tell the user in one line that you added it. Don't commit it: it rides along with whatever the user commits next. When the check passes, say nothing about it.

## 3. Open it

Open the printed path with the platform's opener: `open` on macOS, `xdg-open` on Linux, `start ""` on Windows. Print the path either way, so a headless session or a failed opener still leaves the user one click away.

## 4. Report

Two or three lines: the path, how many capabilities and domains it shows, and which capabilities drifted on the code side (from `--json` or `python3 <this skill>/scripts/drift.py check`), each with what fixes it: `/blueprint-drift` when the spec is right, `/blueprint-sync` when the code is. Say that spec-side drift is not on the map and `/blueprint-sync` reports it, as the page's legend does. When no two capabilities share a file, say the page starts with files shown as nodes.

## What the page does

So you can answer questions about it without opening it:

- **Canvas**: capabilities as nodes, domains as outlines around theirs, a line between two capabilities whose anchors match the same files (thicker, stronger and labelled with the count). Each domain is a cluster, capabilities outside any domain sit in the middle, and lines between two clusters run as one bundle. Laid out before it shows, as the least tangled of several seeded layouts, so the same data always gives the same picture. Hovering or selecting a capability brings its lines, counts and neighbours forward; scroll zooms, dragging the background pans, dragging a capability pins it (its files follow), double-click frees it. Pinned positions aren't saved between runs.
- **Files switch**: shows each anchored file as a dot; on by default when no two capabilities share a file. A capability's own files sit in a block under it; files several capabilities share sit between them, tied to each by a thin line. Zoomed out, a group of more than three files is one bubble with its count; zooming in or clicking it shows each file, and hovering a dot shows its name.
- **Drift**: code-drifted capabilities in red, their changed files marked in the panel. Code side only.
- **Panel**: click a capability for its domain, status, spec link (or the spec's path when its ref is not a URL), purpose, requirements with scenarios (from `baseline/`), files and the capabilities it shares files with; click a line for the shared files; a file or domain for its own summary.
- **Search** (`/` focuses it, Esc clears it): names, purposes, requirement titles and text, scenarios and file paths, every typed word required. Non-matches dim, matches are listed with what matched, and a capability's matching requirements open with the words marked. Brief Decisions live in the backend and aren't searched.
