---
name: blueprint-ask
description: Answer how a feature should work, or how it works, from the repo's blueprint capability specs, after checking that each spec still agrees with the code. Use when someone asks "how should X work?", "how does X work?", "what happens when …?" or "what does the spec say about …?" in a repo with .blueprint/blueprint.json, from the terminal or through an agent such as Claude in Slack. Read only. Not for requests to change behavior.
argument-hint: <question>
---

# Answer from the specs

Question: `$ARGUMENTS` (when empty, the question is the one just asked in the conversation).

The capability specs are the record of intent; the code is the record of behavior. Answer from the spec, but only after checking whether the two still agree, and say plainly when they don't. You answer here; you never fix anything here.

A request to **change** behavior ("make sessions expire after a day") is not a question: say in one line that `/blueprint` plans changes, and stop.

Shared material lives in the `blueprint` skill next to this one: `../blueprint/references/`.

- **No `.blueprint/blueprint.json`**: say in one line that this repo has no specs yet and `/blueprint-setup` sets them up, then answer from the code, labelled as coming from the code alone. Never run setup.
- **Format**: read `version` from `blueprint.json` (absent means 1); when it is below the current format version in [upgrades.md](../blueprint/references/upgrades.md), say in one line that this repo's `.blueprint/` is on format <n> and `/blueprint-tidy` upgrades it, then answer. Never migrate.

## Read only

Write nothing: no `drift.py stamp`, no baseline, no edit to `blueprint.json`, the backend, tickets or code, no map page. Never pass `--tests` to `drift.py check` and never run tests or setup: answering a question runs nothing of the user's. When you find drift, name the skill that would fix it and leave it.

## 1. Find the capabilities

From the repo root:

```bash
python3 <blueprint skill>/scripts/graph.py --json
```

`<blueprint skill>` is `../blueprint` from this file. It prints, and writes nothing, every capability (`nodes`) with its domain, `purpose`, `requirements` (title and body with scenarios, from `baseline/`), anchored `files`, and its code-side drift: `status`, `chance`, `confidence`, `reasons`, `changed`. Match the question to capabilities by name, purpose, requirement titles and text, and file paths. Pick every capability the answer would rely on, usually one; more when the question spans them. A miss on all of that means no spec covers it (step 4).

If graph.py fails, fall back to `blueprint.json` names and the files in `.blueprint/baseline/`, and run the check in step 2 directly.

## 2. Check both sides

For each picked capability, as [status.md](../blueprint/references/status.md) says:

- **Code side**: the status from graph.py, or `python3 .blueprint/drift.py check --json <capabilities>`. If `drift.py check` exits 2 (a bad `drift.scoring` setting, an unknown capability), report the error in one line and treat the code side as unchecked.
- **Spec side**: fetch the spec page and its version marker as the backend file says (`../blueprint/references/backends/<docs.backend>.md`; for Notion, save the fetch and run `notion_normalize.py --marker`, writing only to the scratchpad), and compare it with `specVersion`. Different means the spec moved; diff `baseline/<capability>.md` against the page, matching requirements by name, to see which.
- **Backend unreachable** (no connector, fetch fails): answer from `.blueprint/baseline/<capability>.md`, and say it is the spec as of the last sync and that backend edits since then couldn't be checked. The code-side check still runs.
- **`no-spec`** (mapped, never synced, no baseline): no spec covers it yet; step 4, saying the capability exists but its spec isn't written, and that `/blueprint-sync <capability>` writes one.

## 3. Answer by status

Answer where you were asked (the terminal, a Slack thread), never in a file or page. Lead with the answer itself. Quote at most the one requirement the answer rests on, name its scenarios, and link the spec page (its `ref`). For several capabilities, answer per capability.

| Code side | Spec side | Answer |
| --- | --- | --- |
| `in-sync` | same | From the spec alone. Read no code. |
| `possibly-affected` (or confidence `low`) | same | Read the anchored code behind the requirement first. If it agrees, answer from the spec as in sync. If not, answer as code moved, adding the drift chance and confidence in one line. |
| `code-moved` / `deps-moved` | same | Read the changed code too. "The spec says X; the code does Y", naming the changed files (from `changed` or `reasons`). Point to `/blueprint-sync <capability>` if the code is right, `/blueprint-drift <capability>` if the spec is. If the code still does X, say the spec holds and the change didn't touch this. |
| `in-sync` / `possibly-affected` | moved | From the current page. Say the edited part is intent that isn't built yet, and that `/blueprint-drift <capability>` builds it. |
| `code-moved` / `deps-moved` | moved | Both: "the spec now says X (not built yet); the code does Y". Point to `/blueprint-drift <capability>` first, since the spec edit is new intent and a sync would overwrite it. |

When a side went unchecked (backend unreachable, `drift.py check` failed), say which in one clause and answer from what you have.

## 4. No spec covers it

Say that no spec covers it, then answer from the code, marked as coming from the code alone. When the files involved match no capability's anchors (`python3 .blueprint/drift.py unanchored` lists such files), end with one line: `drift.py unanchored` and `/blueprint-sync` can bring them under a spec.

## Done when

The question has an answer, each part of it says where it came from (spec, baseline, or code), any disagreement between spec and code is stated with the skill that settles it, and nothing in the repo or the backend changed.
