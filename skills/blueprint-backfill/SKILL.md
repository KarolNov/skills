---
name: blueprint-backfill
description: Bring an existing repo fully under blueprint in five passes that can run in separate sessions: domains, capabilities with anchors, specs drafted from code and reviewed scenario by scenario, test tags and artifacts. Progress is kept in the repo, so any session resumes where the last one stopped.
disable-model-invocation: true
argument-hint: "[domain <name> | fold [domain ...]]"
---

# Blueprint backfill

Arguments: `$ARGUMENTS`

Write specs for everything an existing repo already does, as one plan carried across sessions. Setup maps a handful of capabilities and seeds lazily; backfill maps every domain, finds every capability with its anchors, and drafts and reviews every spec. The code is right throughout: a spec describes what it does today.

Shared material lives in the `blueprint` skill next to this one: `../blueprint/references/` and `../blueprint/scripts/`. Read the backend file `../blueprint/references/backends/<docs.backend>.md` before the first backend write.

## The passes

| Pass | Runs | Writes | Read |
| --- | --- | --- | --- |
| 1. Survey and domains | once, in this session | `progress.json`, `README.md` | [references/pass-1.md](references/pass-1.md) |
| 2. Capabilities and anchors | per domain | the domain's progress file, its overview page | [references/pass-2.md](references/pass-2.md) |
| 3. Spec drafts and scenario review | per domain | drafts, spec pages, baselines | [references/pass-3.md](references/pass-3.md) |
| Fold | when domains finish pass 3 | `blueprint.json` | [references/fold.md](references/fold.md) |
| 4. Test tags | per folded domain | tests | not written yet |
| 5. Artifacts | per folded domain | `blueprint.json` artifacts | not written yet |

Each domain's passes 2 and 3 can run in their own session, on their own branch: that is what the progress folder is for.

## Pick the work

By the arguments:

- **`fold`**, alone or with domain names: read [references/fold.md](references/fold.md).
- **`domain <name>`**: run that domain's next pass. Read it from `backfill.py status --json` (`domains[].nextPass`): 2 or 3 → that pass's file; 4 or more on an unfolded domain → it waits for fold: say so and offer `/blueprint-backfill fold <name>`; 4 or 5 on a folded domain → say those passes aren't written in this version of the skill yet, and stop.
- **Nothing**, with no `.blueprint/backfill/progress.json`: start the backfill with pass 1.
- **Nothing**, with a backfill in progress: **resume**. Run `backfill.py status` and show its board line, one line per domain and its `next:` list. Offer to continue with the first next step, and name the others as sessions to run (`/blueprint-backfill domain <name>`), so the user can start them in parallel. On a yes, carry on here as that step's arguments would.

`backfill.py` in these files means `python3 <skills>/blueprint/scripts/backfill.py`: the `blueprint` skill's script, in the folder next to this skill, run with the repo as working directory. The folder's full schema is in its docstring (`backfill.py --help`). It exits 2 with a message on a bad argument or a malformed progress file: show the message and fix the file with the user rather than working around it.

Before anything else, if `.blueprint/blueprint.json` exists, read its `version` (absent means 1); when it is below the current format version in [upgrades.md](../blueprint/references/upgrades.md), say in one line that this repo's `.blueprint/` is on format <n> and `/blueprint-tidy` upgrades it, and stop: backfill writes the current format only. A missing `blueprint.json` is pass 1's to handle.

## The progress folder

`.blueprint/backfill/` holds the backfill's state until it finishes:

- `progress.json`: the survey's plan and pass 1's state. Written once, by `backfill.py init`.
- `domains/<domain>.progress.json`: one per domain, written only by that domain's sessions. Its capabilities, anchors, glue globs, overview `ref`, spec refs and stamps live here, never in `blueprint.json`.
- `drafts/<domain>/<capability>.md` (a bare capability: `drafts/<capability>.md`): specs awaiting scenario review, deleted once the page is written.
- `README.md`: says a backfill is in progress, at which pass, and how to resume. Rewritten by `init` and `fold` only.

Rules every pass keeps:

- **One writer to `blueprint.json`**: fold. A domain session writes its own progress file, its drafts, and its capabilities' `.blueprint/baseline/` and `.blueprint/closure/` files, so two domain sessions on separate branches never conflict. Until fold, a domain's new capabilities are absent from `drift.py check`, the map and the board.
- **Pass state through the script**: `backfill.py pass <domain> <n> in-progress` when a pass starts, `done` when it ends. Capabilities, glue, `ref`, `covered` and review counts are edited in the domain's progress file directly, keeping the shape in the docstring.
- **Commit as you go**: commit the domain's progress file, drafts, baselines and closures at the end of each pass, and after each spec page in pass 3, with a message `blueprint-backfill: <domain> pass <n>: <what>`. Another session, worktree or machine resumes from the commit. On the default branch, ask once whether to commit there or on a branch for this domain.
- **Approval**: the user confirms each capability, the domain's coverage, and each scenario card. Backend writes follow `../blueprint/SKILL.md`'s rule: show before writing; a new overview page gets a preview.
- **Stop between units**: when the session grows long, stop after a capability (pass 2) or a card (pass 3): everything decided is already saved, and `/blueprint-backfill domain <name>` picks up there.

## Done when

The pass this session ran is `done` in the domain's progress file (or pass 1 in `progress.json`, or the named domains folded), its work is committed, and the report ends with the next commands from `backfill.py status`.
