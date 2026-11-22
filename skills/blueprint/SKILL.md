---
name: blueprint
description: Architect a larger change from a solution you already have in mind. Grills it briefly, writes it as a spec change in Notion, Obsidian, Linear, Jira, GitHub or a notes folder, builds it, and keeps specs and code in sync in either direction.
disable-model-invocation: true
argument-hint: <the change you have in mind> | apply [change] [group] | map | coverage [capability | suggest [capability]] | review <file>
---

# Blueprint

Arguments: `$ARGUMENTS`

The user arrives with a **concrete solution**, not an open question. Your job is to sharpen that solution, write it down as a spec change outside the repo, build it, and keep the written spec and the code from drifting apart. You are the draftsperson, not a second architect: the user's design is the starting point, and you challenge it only where it collides with a fact.

## Modes

Pick by the first word of the arguments, then read that mode's file and follow it:

| Arguments | Mode | Read |
| --- | --- | --- |
| a description of a change, or nothing | Grill the solution and write the blueprint | [references/propose.md](references/propose.md) |
| `apply [change] [group]` | Build a blueprint, split into stacked or parallel PRs when it is big, then fold it into the capability specs | [references/apply.md](references/apply.md) |
| `map`, alone or with `--out PATH` / `--json` | Draw the repo's capabilities, domains, shared files and drift as one local page, and open it | [references/map.md](references/map.md) |
| `coverage`, alone, with a capability name, or with `suggest` | Trace spec scenarios to the tests that claim them, report the gaps and orphan tags, and propose tags | [references/coverage.md](references/coverage.md) |
| `review <file>.json …`, where that file exists | Apply a review submitted from the `blueprint-ui` pane to the page it was written on | [references/review.md](references/review.md) |

Any other text starting with "review", "map" or "coverage" (such as "review flow should require two approvers", "map pads to sounds by default" or "coverage should count skipped tests") is a change description: propose it.

If `.blueprint/blueprint.json` is missing, the repo isn't set up yet: say so in one line, then read [../blueprint-setup/SKILL.md](../blueprint-setup/SKILL.md) and follow it here (it can't be started with the Skill tool), and come back to the request when it is done. If the change creates a new repo, or one already pending in `~/.blueprint/pending/` matches it, use that folder's `blueprint.json` (setup's "Target repo doesn't exist yet").

**Format version**: when `.blueprint/blueprint.json` exists, first read its `version` (absent means 1). When it is below the current format version in [references/upgrades.md](references/upgrades.md), say in one line that this repo's `.blueprint/` is on format <n> and `/blueprint-tidy` upgrades it, then carry on with the request. Never migrate it here.

When setup and propose run together, don't ask twice: put setup's questions (docs, tickets, project) in the same round as propose's playback, and survey for both at once. Its writes still wait for the user's yes.

## The pieces

- **Capability spec**: the durable description of what one part of the system does, one page per capability in the backend (e.g. `auth/session`). Requirements with scenarios, nothing about how. Format in [references/formats.md](references/formats.md).
- **Blueprint**: one change, written twice, side by side in the backend and linked both ways. The **brief** is for agents: text only, the destination, decisions, the **spec delta** (requirements added, modified, removed) and tasks; it is the source of truth, and apply and sync read nothing else. The **review** is for people: the picture first, then the same change in plain language; it is rebuilt from the brief whenever the brief changes. When applied, the delta is merged into the capability specs.
- **Domain**: a group of related capabilities, named by the first part of their names (`auth` holds `auth/session` and `auth/tokens`). It has an **overview page** in the backend that holds its capabilities like a folder: Purpose, its capabilities, and how they connect. An overview is not a spec: no requirements, baseline or drift. A name is either a domain or a capability, never both ([references/formats.md](references/formats.md)).
- **Visuals** live only in reviews: Mermaid diagrams of the change, and for behavior over time an optional interactive playground. What to draw and how is in [references/visuals.md](references/visuals.md). Specs and briefs stay pure text, so agents read them cheaply and sync diffs them cleanly.
- **Backend**: where specs and blueprints live, outside the repo. How to read, write and version pages for each backend is in `references/backends/<backend>.md`; read only the one named by `docs.backend` in `blueprint.json`.
- **Tickets**: where a blueprint's tasks are tracked, which may be a different tool from the docs (specs in Notion, tickets in GitHub issues). How to create and close them is in [references/tickets.md](references/tickets.md), per `tickets.tracker`.
- **`.blueprint/` in the repo**: the only part that lives with the code. `blueprint.json` maps each capability to its page and its **anchors** (globs for the code that implements it), and records when each side was last synced. `baseline/<capability>.md` is the spec text as of the last sync: the merge base for three-way sync, never edited by hand, never the source of truth.
- **Format version**: `version` in `blueprint.json` (absent means 1) says which shape `.blueprint/` and the backend structure are in. When the skill's format moves on, [references/upgrades.md](references/upgrades.md) records what changed and how to migrate; `/blueprint-tidy` applies it. Every other skill only checks the version and points there.
- **Scenario tags**: a comment `@scenario <capability>: <scenario name>` above a test claims that scenario ([references/formats.md](references/formats.md)). `scripts/coverage.py` traces scenarios to the tests that claim them, by kind (`tests.kinds` in `blueprint.json`), statically: a claim is never "passing" ([references/coverage.md](references/coverage.md)).
- **Map**: `.blueprint/map.html`, one self-contained page drawn from `.blueprint/` and the repo's files by this skill's `scripts/graph.py` ([references/map.md](references/map.md)). Local and kept out of git (`.blueprint/.gitignore`), regenerated on demand; uploaded (say, as a Notion embed) only when the user asks.
- **Drift**: a capability whose spec or code moved since they last agreed. `.blueprint/drift.py` (copied there from this skill's `scripts/` by `blueprint-setup`) detects the code side with git alone; the spec side is detected by comparing the backend's version marker with the one in `blueprint.json` ([references/status.md](references/status.md)). Two sibling skills reconcile it, by which side is right: `blueprint-drift` judges the code against the spec and fixes the code; `blueprint-sync` judges the spec against the code and fixes the spec.

## Rules

- The backend is the source of truth for intent; the code is the source of truth for behavior. Sync reconciles the two and asks the user whenever they disagree on something a user of the system would notice.
- Write to the backend and to `.blueprint/` only after the user approves the content, and show what you will write first. Small edits can be approved inline ("yes"); new pages and spec merges get a preview.
- Every write to a capability spec ends with the spec bookkeeping in [references/status.md](references/status.md). A spec write without it reads as drift next time.
- Refer to blueprints and capabilities by name and link, never by bare id.
- Whenever a brief changes, rebuild its review in the same turn (and the playground, if the change touches what it shows). Before rebuilding, read the review for comments or edits people left since it was built, and put each to the user as a proposed change to the brief; the review never wins by itself.
- Facts are yours to find: read the code, the existing specs, and the docs yourself (a subagent for anything wide). Decisions are the user's.
