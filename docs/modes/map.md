# Map

```
/blueprint map [--out PATH] [--json] [--no-drift]
```

Map draws the repo's capabilities as one page and opens it. It reads only what is in the repo, so it needs no backend connection. The page is self-contained (d3 and the data are inlined), so it works offline and inside a Notion embed.

**[See this repo's own map →](/capability-map)**

## What's on it

- **Capabilities** are drawn as nodes, and **domains** as outlines around them. A line joins two capabilities whose anchors match the same files, and it gets thicker with the count. The layout is chosen as the least tangled of several seeded layouts, so the same data always gives the same picture.
- **Drift**: capabilities whose code moved are red, and possibly affected ones are a lighter tint. The panel shows the drift chance, the confidence and every reason.
- **Show as nodes**: anchored files, [artifacts](/modes/sync#artifacts) (violet diamonds, red when stale) and test files that claim scenarios (teal triangles). Large groups collapse into a bubble with a count until you zoom in.
- **Coverage**: each capability's panel lists its requirements and scenarios, with the tests that claim each scenario (see [Coverage](/modes/coverage)).
- **Search** (press `/`): names, purposes, requirements, scenarios, file paths, artifacts and test files.

## Options

- `--out PATH` writes the page somewhere else. By default it goes to `.blueprint/map.html`, which is kept out of git.
- `--json` prints the extracted data instead, which is handy for scripts.
- `--no-drift` draws the map without judging drift: no red, no stale marks, and no drift sections in the panels. The legend says drift isn't shown. It reads nothing beyond the files themselves, so it works from a shallow clone. This site's map is built this way.
