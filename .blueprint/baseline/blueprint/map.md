## Purpose

Draws a repo's capabilities as one local, interactive page: how they group into domains, which share files, which drifted, and what each requires, with search across all of it.

## Requirements

### Requirement: One self-contained page

`/blueprint map` SHALL write `.blueprint/map.html` as a single file with its script, styles and data inlined, needing no server and no network, and open it in the browser. It SHALL make sure the file is ignored by git without touching the repo root's ignore file, telling the user when it adds the ignore line. With `--out PATH` it SHALL write the page there instead and leave ignore files alone; with `--json` it SHALL print the map's data instead of writing a page.

- **Scenario: Offline**
  - **GIVEN** a repo set up with blueprint and no network connection
  - **WHEN** the user runs `/blueprint map` and opens the page
  - **THEN** the map draws and every control works
- **Scenario: First run**
  - **GIVEN** `.blueprint/map.html` is not ignored by git
  - **WHEN** the map is written
  - **THEN** an ignore line for it is added and the user is told
- **Scenario: Elsewhere**
  - **WHEN** the user runs `/blueprint map --out docs/map.html`
  - **THEN** the page is written to `docs/map.html` and no ignore line is added

### Requirement: Capabilities, domains and shared files

The map SHALL show each capability in `blueprint.json` as a node, each domain as an outline around its capabilities, and a line between two capabilities for every pair whose anchors match the same files, thicker for more shared files and labelled with the count.

- **Scenario: Shared files**
  - **GIVEN** the anchors of `jams` and `agent` both match 7 files
  - **WHEN** the map is drawn
  - **THEN** a line labelled 7 joins them, thicker than a line labelled 1
- **Scenario: Domain**
  - **GIVEN** a domain `blueprint` holding `blueprint/sync` and `blueprint/setup`
  - **WHEN** the map is drawn
  - **THEN** one outline labelled `blueprint` surrounds both

### Requirement: Files as nodes

The map SHALL offer a switch that shows each anchored file as a small node linked to the capabilities that match it. The switch SHALL start on when no two capabilities share a file, and off otherwise. Zoomed out, a group of more than three files SHALL show as one bubble with its count.

- **Scenario: No shared files**
  - **GIVEN** no file is matched by two capabilities
  - **WHEN** the map opens
  - **THEN** files are shown as nodes
- **Scenario: Many files**
  - **GIVEN** a capability with 23 anchored files and the map zoomed out
  - **WHEN** files are shown
  - **THEN** they appear as one bubble labelled 23, and zooming in or clicking it shows each file

### Requirement: Code drift shown

A capability whose anchored code moved since its last stamp, as `drift.py check` reports it, SHALL be drawn in the drift color, and its panel SHALL mark the changed files. The legend SHALL say that spec-side drift is not shown and that `/blueprint-sync` reports it.

- **Scenario: Code moved**
  - **GIVEN** one of `blueprint/sync`'s anchored files changed since its stamp
  - **WHEN** the map is drawn
  - **THEN** `blueprint/sync` is drawn in the drift color and the changed file is marked in its panel

### Requirement: Details panel

Clicking a capability SHALL show its name, domain, status, a link to its spec, its purpose, every requirement with its scenarios (from `baseline/`), its files, and the capabilities it shares files with, each clickable. Clicking a line SHALL list the files the two capabilities share. A capability with no baseline SHALL show that it has no spec yet.

- **Scenario: Follow a neighbour**
  - **WHEN** the user clicks `looper`, then `jams` in its "Shares files with" list
  - **THEN** the panel shows `jams` and the map centres on it

### Requirement: Search

A search box SHALL match capability names, purposes, requirement titles and text, scenarios and file paths, requiring every typed word. Non-matching capabilities SHALL be dimmed, matches listed with what matched, and in a capability's panel the matching requirements SHALL be opened and the words highlighted.

- **Scenario: Find the logic for tempo**
  - **WHEN** the user types `tempo`
  - **THEN** every capability whose requirements mention tempo is listed and highlighted, the rest are dimmed, and opening `looper` shows its "Tempo" requirement opened with the word marked

### Requirement: Steady layout

The map SHALL appear already laid out, without nodes drifting into place, and the same data SHALL always be laid out the same way. Dragging a capability SHALL move it and its files while the rest move little, and leave it where it was dropped until the user double-clicks it. Scrolling SHALL zoom and dragging the background SHALL pan.

- **Scenario: Drop a node**
  - **WHEN** the user drags `pads` to an empty area and lets go
  - **THEN** `pads` and its file nodes stay there, and the other capabilities stay roughly where they were
- **Scenario: Same picture twice**
  - **WHEN** the map is written twice from the same `blueprint.json`
  - **THEN** both pages show every node in the same place
