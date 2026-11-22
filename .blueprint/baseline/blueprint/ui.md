## Purpose

A pane beside the chat that shows blueprint pages read-only and lets the user review them like a GitHub pull request, handing the review to blueprint to apply.

## Requirements

### Requirement: Open the pane

`/blueprint-ui` SHALL open the pane on the status board. `/blueprint-ui <change or capability>` SHALL open that page directly. The pane SHALL use the nearest `.blueprint/blueprint.json` in the session's folder or any folder above it, and run blueprint's scripts from that folder.

- **Scenario: Board**
  - **GIVEN** `blueprint.json` maps two changes and six specs
  - **WHEN** the user runs `/blueprint-ui`
  - **THEN** the pane shows the status board, and choosing a capability, or a change's review or brief link, shows that page
- **Scenario: Session in a subfolder**
  - **GIVEN** the session runs in a subfolder of a repo set up for blueprint
  - **WHEN** the user runs `/blueprint-ui`
  - **THEN** the board shows that repo's capabilities and changes
- **Scenario: Repo not set up**
  - **GIVEN** neither the session's folder nor any folder above it has `.blueprint/blueprint.json`
  - **WHEN** the user runs `/blueprint-ui`
  - **THEN** the pane says so and suggests `/blueprint-setup`

### Requirement: Status board

The board SHALL show a summary line (how many capabilities need attention, how many are in sync, open changes by status, pending comments), then three sections in this order:

- Needs attention: capabilities whose code or spec moved, or that have no spec, each with its reason.
- Changes: draft, approved and building changes, each with its status, pending count, and a link to its review and to its brief. Applied and abandoned changes are folded under Done (n).
- In sync: every other capability, as a grid of names in order with a fixed number of columns that fits the pane.

Each section SHALL fold under its header, which shows its count. Needs attention and Changes SHALL start open, and In sync folded, except when the code side couldn't be checked: then that list starts open. A capability with comments pending on its spec page SHALL show that count too, in whichever section it sits. A section with nothing in it SHALL be left out. A footer SHALL count changed files that no capability covers since the last sync, only when there are any.

- **Scenario: Everything in sync**
  - **GIVEN** every capability's code and spec agree and the only change is applied
  - **WHEN** the board is shown
  - **THEN** there is no Needs attention section, a folded In sync holds every capability, and the change sits under a folded Done (1)
- **Scenario: Code moved**
  - **GIVEN** three files under `blueprint/ui`'s anchors changed since its last sync
  - **WHEN** the board is shown
  - **THEN** `blueprint/ui` is under Needs attention as "code moved (3 files)", and the summary counts it
- **Scenario: Uncovered files**
  - **GIVEN** two files changed since the last sync that no capability's anchors cover
  - **WHEN** the board is shown
  - **THEN** the footer reads "2 changed files no capability covers"

### Requirement: Checking code and specs

The code side SHALL be checked each time the board opens and on ↻. The spec side SHALL be checked only when the user presses Check specs: the pane reads each spec page, computes its version marker the way blueprint does, and compares it with the one `blueprint.json` records. Results SHALL be kept for the session, and the board SHALL say when the spec side was last checked, or that it wasn't. ↻ SHALL re-check the spec side too once it has been checked. After the pane follows a write to a spec, it SHALL re-check that spec's marker. A spec that can't be read SHALL show as unknown with the reason, even while In sync is folded, without stopping the others.

- **Scenario: Specs not checked yet**
  - **WHEN** the board opens for the first time in a session
  - **THEN** code status is shown, spec status is not, and the board says "spec side not checked"
- **Scenario: Teammate edited a spec**
  - **GIVEN** someone edited `blueprint/propose` in Notion after its last sync
  - **WHEN** the user presses Check specs
  - **THEN** `blueprint/propose` moves to Needs attention as "spec moved"
- **Scenario: Blueprint wrote a spec**
  - **GIVEN** the spec side was checked and `blueprint/ui` showed "spec moved"
  - **WHEN** blueprint writes that spec and records its new marker
  - **THEN** the board re-checks `blueprint/ui` and shows it in sync
- **Scenario: Drift tool missing**
  - **GIVEN** `.blueprint/drift.py` is missing
  - **WHEN** the board opens
  - **THEN** it says code status is unavailable and suggests `/blueprint-setup`

### Requirement: Run the next step from the board

Each row that has a next step SHALL offer a ▶ button labeled with it. The button runs that step's command for the row's capability or change, as if typed. The steps SHALL be:

- spec moved → drift, labeled "drift → sync" when the code also moved;
- code moved, or no spec → sync;
- approved or building change → apply.

A capability with no anchors SHALL get no button.

When the code of two or more capabilities moved, the Needs attention header SHALL offer ▶ sync all (n), which runs `/blueprint-sync` with no capability, so it takes every capability whose code moved. A capability with no spec is not in that and keeps its own button.

A step runs once the session is idle. While Claude is working, the board SHALL say that a step waits until the turn ends, and draw the ▶ buttons dim. A pressed step SHALL show as queued until it runs and SHALL NOT queue a second time; while sync all is queued, so are the rows it covers.

- **Scenario: Sync a capability**
  - **GIVEN** `blueprint/ui` shows "code moved (3 files)"
  - **WHEN** the user presses ▶ sync on its row
  - **THEN** `/blueprint-sync blueprint/ui` runs in the session
- **Scenario: Both sides moved**
  - **GIVEN** `blueprint/propose` shows "code and spec moved"
  - **WHEN** the user presses ▶ drift → sync
  - **THEN** `/blueprint-drift blueprint/propose` runs
- **Scenario: Apply a change**
  - **GIVEN** a change in status building
  - **WHEN** the user presses ▶ apply on its row
  - **THEN** `/blueprint apply <change>` runs
- **Scenario: Command missing**
  - **WHEN** the command a button needs isn't in the session
  - **THEN** a toast says which plugin to install, and nothing runs
- **Scenario: Sync all**
  - **GIVEN** `blueprint/ui` and `blueprint/propose` both show "code moved"
  - **WHEN** the user presses ▶ sync all (2)
  - **THEN** `/blueprint-sync` runs once, with no capability named
- **Scenario: Step while Claude works**
  - **GIVEN** Claude is mid-turn
  - **WHEN** the user presses ▶ sync on `blueprint/ui`
  - **THEN** the row shows "◷ sync queued" until the turn ends, then `/blueprint-sync blueprint/ui` runs once

### Requirement: PR plan

When `/blueprint apply` splits a change, it SHALL be able to show the plan in the pane, in place of the board, through the mod's `split` tool: a tree of branches under the default branch, with a stacked group under its base, parallel groups as siblings and Specs last, each group with its tasks and state. Until the plan is approved, the pane SHALL show it as a proposal with no buttons. Once it is approved, each group that can start now SHALL get ▶ start, and two or more such groups a ▶ start all ready (n). A press SHALL send Claude a message, as the user's, asking to start those groups, each in a new session with the prompt apply wrote for it, and SHALL show them as starting. A stacked group can start once its base's PR is open, a group that waits on other groups (its `after`) once they have all merged, and Specs once every other group has merged. Until then, a waiting group SHALL read which groups it still waits on. The `split` tool SHALL refuse a group that waits on itself, on Specs, or on no group. A change with a plan SHALL get a PRs link on its board row. A plan whose change has no row in `blueprint.json` SHALL get its own row under Changes, marked as not in `blueprint.json`, with a PRs link, so leaving the plan for the board never strands it.

- **Scenario: Proposed plan**
  - **GIVEN** apply proposes group 1, group 2 stacked on 1, group 3 and Specs
  - **WHEN** it calls the `split` tool
  - **THEN** the pane shows group 2 under group 1, group 3 beside group 1 and Specs last, with no ▶ start
- **Scenario: Start a group**
  - **GIVEN** the plan is approved
  - **WHEN** the user presses ▶ start on group 1
  - **THEN** Claude gets a message to start group 1 in a new session with its prompt, and the row reads "starting…"
- **Scenario: Stacked group waits**
  - **GIVEN** the plan is approved and group 1's PR is not open
  - **THEN** group 2 has no ▶ start and reads "waits for group 1's PR"
- **Scenario: Group waits for others to merge**
  - **GIVEN** the plan is approved and group 4 is cut from the default branch after groups 1, 2 and 3
  - **WHEN** groups 1 and 3 have merged
  - **THEN** group 4 has no ▶ start and reads "after group 2 merges", and gets ▶ start once group 2 merges too
- **Scenario: Plan for a change not in blueprint.json**
  - **GIVEN** the pane shows a plan for a change `blueprint.json` doesn't list
  - **WHEN** the user goes back to the board
  - **THEN** Changes holds a row for that change, marked "not in `blueprint.json`", whose PRs link reopens the plan

### Requirement: Opens after a blueprint write

When a tool call finishes whose id-like arguments (`page_id`, `parent`, `id` and the like) name a page that `blueprint.json` maps, the pane SHALL open on that page, or refresh it if it is already showing it. Links inside the written content SHALL NOT count. A refresh caused by a write SHALL scroll to the first block that changed and highlight it for about 2.5 seconds.

- **Scenario: Brief rewritten**
  - **WHEN** blueprint updates a change's brief in Notion
  - **THEN** the pane shows that brief as it now reads
- **Scenario: Write to the page showing**
  - **GIVEN** the pane shows a spec
  - **WHEN** blueprint rewrites one of its requirements
  - **THEN** the pane scrolls to the first changed block and highlights it briefly
- **Scenario: Content only links a mapped page**
  - **WHEN** a tool call writes an unmapped page whose content links a mapped one
  - **THEN** the pane does not open or change
- **Scenario: Unrelated page**
  - **WHEN** a tool call writes a Notion page that `blueprint.json` doesn't map
  - **THEN** the pane does not open or change

### Requirement: Read-only rendering

The pane SHALL draw the page's text block by block and SHALL never write to the backend. On the desktop, uploaded SVG diagrams SHALL be drawn in place with their caption beneath. In the terminal, a diagram whose toggle holds a terminal version SHALL show that version as a code block with its caption. Other images, embeds and playgrounds, and any diagram that can't be downloaded or drawn, SHALL appear as links that open them in the backend. A re-read of the same page SHALL keep diagrams already downloaded, so they don't flash back to links.

- **Scenario: Review with diagrams on the desktop**
  - **WHEN** a review with two SVG diagram images and a playground is shown on the desktop
  - **THEN** both diagrams are drawn in place with their captions, the playground is an "open in Notion" link, and the text around them reads as in Notion
- **Scenario: Review with diagrams in the terminal**
  - **GIVEN** each diagram's toggle holds a terminal version
  - **WHEN** the review is shown in the terminal
  - **THEN** each diagram shows as its terminal version with its caption
- **Scenario: Diagram without a terminal version**
  - **WHEN** a diagram whose toggle has only Mermaid source is shown in the terminal, or its SVG fails to download on the desktop
  - **THEN** it appears as an "open in Notion" link

### Requirement: Reads Notion through the session

The pane SHALL read Notion pages through the session's own Notion connection: the server named by a setting that defaults to `claude.ai Notion`, else the connected server that has `notion-fetch`. It SHALL clean them with the same normalization blueprint uses for baselines. When no Notion server answers, the pane SHALL show "Waiting for the Notion connection…" and retry for about 15 seconds before reporting it, since the session may still be connecting.

- **Scenario: No Notion connection**
  - **WHEN** no connected server answers under the configured name within the wait
  - **THEN** the pane says which names it tried, the last error, and how to change the setting
- **Scenario: Connection comes up during the wait**
  - **WHEN** the Notion server connects a few seconds after the pane opens
  - **THEN** the page is read and shown, with no error
- **Scenario: Other backend**
  - **WHEN** `docs.backend` is not `notion`
  - **THEN** the pane says that backend is not supported yet and links the page

### Requirement: Comment or suggest on a block

Each block SHALL have a "+" beside it that opens an editor under the block, with Comment and Suggest change tabs, and puts the cursor in its field where the surface allows. While the editor is open the "+" SHALL read "−" and close it. The editor SHALL offer Cancel and Add comment or Add suggestion. Every item SHALL carry the block's heading and the block's text as its quote. Suggest SHALL start from the block's own text, so the user edits it in place. Empty text, or a suggestion identical to the block, SHALL add nothing. The editor SHALL close if its block's text changes under it.

Known gap: on the desktop, "+" does not yet move the cursor into the field, because the app keeps the keys in the chat composer (anthropics/claude-code#110951).

- **Scenario: Comment on a block**
  - **WHEN** the user presses "+" on a scenario, chooses Comment and writes "why five?"
  - **THEN** a pending comment holds that requirement's heading, the scenario's text as its quote, and "why five?"
- **Scenario: Suggest wording**
  - **WHEN** the user presses Suggest on a requirement's text, edits it and saves
  - **THEN** a pending suggestion holds the block's heading, the original text as its quote, and the new text

### Requirement: Pending review

Comments and suggestions SHALL build up as a pending review that is shown with its count and survives until it is submitted, discarded or the session ends. Each item SHALL show its kind, the heading it sits under, its quote and its text, and SHALL also appear under its own block. While its block is on the page, an item SHALL offer "↓ show in page", which scrolls to the block. Each pending item SHALL be removable, and "Discard all" SHALL clear the page's pending review.

- **Scenario: Switch pages**
  - **GIVEN** two pending comments on a brief
  - **WHEN** the user opens a spec and comes back
  - **THEN** both comments are still pending

### Requirement: Submit review

"Submit review" SHALL write the pending review as one JSON file (page, kind, link, and for each item its heading, quote, kind and text) and run `/blueprint review <file>`, then clear the batch. If `/blueprint review` doesn't start, the pane SHALL say so and keep the review pending. A second press while a submit is running SHALL do nothing.

- **Scenario: Submit**
  - **GIVEN** three pending items on a brief
  - **WHEN** the user presses "Submit review"
  - **THEN** `/blueprint review` runs with the file, the transcript shows a one-line summary, and the pending count is zero
- **Scenario: Command doesn't start**
  - **WHEN** `/blueprint review` fails to start
  - **THEN** a toast says so and the pending items are kept

### Requirement: Outdated comments

After the page refreshes, a pending item whose quote no longer appears SHALL be marked outdated and kept, not dropped.

- **Scenario: Quote edited away**
  - **GIVEN** a pending comment quoting a sentence
  - **WHEN** the page is refreshed and that sentence is gone
  - **THEN** the comment shows as outdated, with its quote

### Requirement: Same pane in terminal and desktop

The pane SHALL offer the same pages and actions in the terminal and the desktop app. Where the desktop draws an element differently, the pane MAY draw its own: on the desktop it draws the editor's Comment / Suggest change tab bar itself, because buttons there can't look like tabs.

- **Scenario: Desktop**
  - **WHEN** the pane is opened in the desktop app
  - **THEN** it offers the same pages, buttons and inputs as in the terminal
