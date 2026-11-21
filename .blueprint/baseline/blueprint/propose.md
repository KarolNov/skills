## Purpose

Turns a solution the user already has in mind into an approved blueprint: a brief for agents and a review for people, written to the docs backend only after the user approves.

## Requirements

### Requirement: Mode selection

`/blueprint` SHALL go into propose mode when its arguments describe a change or are empty, into apply mode when the first word is `apply`, into map mode when the arguments are `map` alone or followed only by its options (`--out PATH`, `--json`), and into review mode only when the first word is `review` followed by a `.json` review file that exists. Any other text starting with "review" or "map" SHALL be treated as a change description.

- **Scenario: Change described**
  - **WHEN** the user runs `/blueprint add SSO login`
  - **THEN** propose mode starts with that solution
- **Scenario: Nothing given**
  - **WHEN** the user runs `/blueprint` with no arguments and the conversation holds no solution
  - **THEN** it asks in one line what they want to build and how
- **Scenario: Review submitted**
  - **WHEN** `/blueprint review /path/review.json` runs
  - **THEN** review mode applies that file
- **Scenario: Change that starts with "review"**
  - **WHEN** the user runs `/blueprint review flow should require two approvers`
  - **THEN** propose mode starts with that solution
- **Scenario: Map**
  - **WHEN** the user runs `/blueprint map`
  - **THEN** the capability map is written and opened
- **Scenario: Change that starts with "map"**
  - **WHEN** the user runs `/blueprint map pads to sounds by default`
  - **THEN** propose mode starts with that solution

### Requirement: Setup first in an unset repo

When `.blueprint/blueprint.json` is missing, blueprint SHALL say so in one line, run setup inline, and then return to the request. When setup and propose run together, their questions SHALL be asked in a single round.

- **Scenario: Unset repo**
  - **GIVEN** a repo with no `.blueprint/`
  - **WHEN** the user runs `/blueprint <change>`
  - **THEN** setup runs first, its questions sharing a round with the playback, and propose continues afterwards

### Requirement: Playback before questions

Before asking anything, propose SHALL collect facts from the code, the touched specs, open blueprints and any glossary or ADRs. It SHALL then play the solution back as Destination, Solution, Touches, Out of scope and Collides with, followed by a rough before → after sketch.

- **Scenario: Collision found**
  - **GIVEN** the code contradicts part of the solution
  - **WHEN** the playback is shown
  - **THEN** its Collides with line quotes the conflicting fact

### Requirement: Solution-first grilling

Grilling SHALL test the user's design, not look for another one. A question SHALL be asked only if its answer changes the spec delta, an interface, a data shape, a migration or a test. Each round SHALL hold at most five questions, each with a recommendation, and there SHALL be at most three rounds. Anything still unsettled goes to Open questions.

- **Scenario: Low-stakes choice**
  - **WHEN** a choice would not change the delta, an interface, data, a migration or a test
  - **THEN** it is decided by convention and listed under Assumed instead of being asked
- **Scenario: Three rounds used**
  - **WHEN** questions remain after the third round
  - **THEN** they go into the brief's Open questions with recommendations, and no fourth round starts

### Requirement: Alternatives only on collision

Propose SHALL raise an alternative design only when the solution collides with a fact, and only once, quoting the fact.

- **Scenario: No collision**
  - **WHEN** the user's design meets no hard constraint
  - **THEN** no alternative design is offered

### Requirement: Brief shape

The brief SHALL follow the documented format: Destination, Why, Solution, Decisions, Assumed, Out of scope, Code map, Spec delta, Tasks and Open questions. Tasks SHALL be vertical slices, and the last task SHALL always be folding the delta into the specs.

- **Scenario: Behavior-free change**
  - **WHEN** the change alters no observable behavior
  - **THEN** the Spec delta is empty and says so in one line

### Requirement: Long briefs go to a file

A draft brief over about 6,000 characters SHALL be written to a file the user can open. Chat then shows only the picture, the Decisions, the Tasks and one line per delta block.

- **Scenario: Long brief**
  - **WHEN** the drafted brief is longer than about 6,000 characters
  - **THEN** it is saved as `<change id>.brief.md` and its full path is given

### Requirement: Nothing written before approval

Propose SHALL write nothing to the backend, the tracker or `.blueprint/` until the user approves the brief. Capability specs SHALL stay unchanged until apply.

- **Scenario: Approved**
  - **WHEN** the user approves the brief
  - **THEN** the brief, then the review, then (after listing them) the tickets are created, and the change is recorded in `blueprint.json` as `approved` with `baseCommit` set to HEAD

### Requirement: Review is derived from the brief

The review SHALL restate the brief with pictures first and add nothing of its own. Whenever the brief changes, the review SHALL be rebuilt in the same turn. Comments people leave on the review SHALL be put to the user as proposed brief changes and never applied directly.

- **Scenario: Stale review**
  - **WHEN** the brief's version marker differs from the "Built from brief" marker on the review
  - **THEN** the review is rebuilt before anyone is asked to look at it

### Requirement: Visuals in reviews only

Diagrams and playgrounds SHALL appear only in reviews, never in briefs or capability specs. A review SHALL always include a before → after diagram. A playground SHALL be offered, not built by default, and only for changes about behavior over time.

- **Scenario: Backend shows Mermaid as code**
  - **WHEN** the backend can't render Mermaid
  - **THEN** each diagram is placed as an SVG image, with its Mermaid source and a terminal version in a collapsed toggle

### Requirement: Terminal version of each diagram

Wherever diagrams go in as images, each SHALL also get a terminal version: the same diagram drawn by hand in box-drawing characters, at most 56 columns wide and laid out top to bottom. Fan-outs and decisions SHALL be drawn as lists, not rows of boxes or diamonds. It SHALL use the image's words, say in words what color would show, and contain no tabs, emoji or wide characters. Each SHALL pass `scripts/text_diagram.py` before the review is written.

- **Scenario: Too wide**
  - **WHEN** a terminal version is wider than 56 columns or has a corner that joins no line
  - **THEN** `text_diagram.py` reports it, and the review is not written until it prints `ok`

### Requirement: Older format points to tidy

Every blueprint skill except tidy SHALL read `version` from `blueprint.json` first and, when it is older than the plugin's format version, say in one line that `/blueprint-tidy` migrates it, then continue without writing a migration.

- **Scenario: Old repo**
  - **GIVEN** a repo set up before format version 2
  - **WHEN** the user runs `/blueprint <change>`
  - **THEN** the first line says the repo is on format 1 and `/blueprint-tidy` upgrades it, and propose carries on

### Requirement: Domain names

A capability name SHALL be `<domain>/<capability>` or a bare `<capability>`, and SHALL never also be a domain name. A new capability proposed in a brief SHALL go into an existing domain when one fits.

- **Scenario: New capability in a domain repo**
  - **GIVEN** a domain `board` exists
  - **WHEN** a brief adds a capability for pad layouts
  - **THEN** it is proposed as `board/pads`, not `pads`

### Requirement: Artifacts in a brief

When the user names resources outside the repo that the change affects or that describe it, the brief SHALL carry an **Artifacts** section listing each with its id, type, value, description and capabilities.

- **Scenario: Support article named**
  - **WHEN** the user mentions a help-center article about the feature being changed
  - **THEN** the brief lists it under Artifacts as a `webpage` (or the type of the tool it lives in) covering the touched capability
