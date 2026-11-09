---
name: blueprint
description: Architect a larger change from a solution you already have in mind. Grills it briefly, writes it as a spec change in Notion, Obsidian, Linear, Jira, GitHub or a notes folder, builds it, and keeps specs and code in sync in either direction.
disable-model-invocation: true
argument-hint: <the change you have in mind> | apply [change]
---

# Blueprint

Arguments: `$ARGUMENTS`

The user arrives with a **concrete solution**, not an open question. Your job is to sharpen that solution, write it down as a spec change outside the repo, build it, and keep the written spec and the code from drifting apart. You are the draftsperson, not a second architect: the user's design is the starting point, and you challenge it only where it collides with a fact.

## Modes

Pick by the first word of the arguments, then read that mode's file and follow it:

| Arguments | Mode | Read |
| --- | --- | --- |
| a description of a change, or nothing | Grill the solution and write the blueprint | [references/propose.md](references/propose.md) |
| `apply [change]` | Build a blueprint, then fold it into the capability specs | [references/apply.md](references/apply.md) |

If `.blueprint/blueprint.json` is missing, the repo isn't set up yet: say so in one line, then run the `blueprint-setup` skill (with the Skill tool) and come back to the request when it is done.

## The pieces

- **Capability spec**: the durable description of what one part of the system does, one page per capability in the backend (e.g. `auth/session`). Requirements with scenarios, nothing about how. Format in [references/formats.md](references/formats.md).
- **Blueprint**: one change, written twice, side by side in the backend and linked both ways. The **brief** is for agents: text only, the destination, decisions, the **spec delta** (requirements added, modified, removed) and tasks; it is the source of truth, and apply and sync read nothing else. The **review** is for people: the picture first, then the same change in plain language; it is rebuilt from the brief whenever the brief changes. When applied, the delta is merged into the capability specs.
- **Visuals** live only in reviews: Mermaid diagrams of the change, and for behavior over time an optional interactive playground. What to draw and how is in [references/visuals.md](references/visuals.md). Specs and briefs stay pure text, so agents read them cheaply and sync diffs them cleanly.
- **Backend**: where specs and blueprints live, outside the repo. How to read, write and version pages for each backend is in `references/backends/<backend>.md`; read only the one named by `docs.backend` in `blueprint.json`.
- **Tickets**: where a blueprint's tasks are tracked, which may be a different tool from the docs (specs in Notion, tickets in GitHub issues). How to create and close them is in [references/tickets.md](references/tickets.md), per `tickets.tracker`.
- **`.blueprint/` in the repo**: the only part that lives with the code. `blueprint.json` maps each capability to its page and its **anchors** (globs for the code that implements it), and records when each side was last synced. `baseline/<capability>.md` is the spec text as of the last sync: the merge base for three-way sync, never edited by hand, never the source of truth.
- **Drift**: a capability whose spec or code moved since they last agreed. `.blueprint/drift.py` (copied there from this skill's `scripts/` by `blueprint-setup`) detects the code side with git alone; the spec side is detected by comparing the backend's version marker with the one in `blueprint.json` ([references/status.md](references/status.md)). Two sibling skills reconcile it, by which side is right: `blueprint-drift` judges the code against the spec and fixes the code; `blueprint-sync` judges the spec against the code and fixes the spec.

## Rules

- The backend is the source of truth for intent; the code is the source of truth for behavior. Sync reconciles the two and asks the user whenever they disagree on something a user of the system would notice.
- Write to the backend and to `.blueprint/` only after the user approves the content, and show what you will write first. Small edits can be approved inline ("yes"); new pages and spec merges get a preview.
- Every write to a capability spec ends with the spec bookkeeping in [references/status.md](references/status.md). A spec write without it reads as drift next time.
- Refer to blueprints and capabilities by name and link, never by bare id.
- Whenever a brief changes, rebuild its review in the same turn (and the playground, if the change touches what it shows). Before rebuilding, read the review for comments or edits people left since it was built, and put each to the user as a proposed change to the brief; the review never wins by itself.
- Facts are yours to find: read the code, the existing specs, and the docs yourself (a subagent for anything wide). Decisions are the user's.
