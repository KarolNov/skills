---
name: blueprint-tidy
description: Restructure a repo's blueprint setup on demand. Migrates .blueprint/ and the backend to the current format version, groups capabilities into domains with overview pages, renames names that are both a domain and a capability, and reports anchors that overlap through broad globs. Writes nothing until the user approves one move table.
disable-model-invocation: true
argument-hint: "[--dry-run]"
---

# Blueprint tidy

Arguments: `$ARGUMENTS`: `--dry-run` shows the migration and the move table, then stops without writing anything.

Keep the structure readable as the repo grows: bring `.blueprint/` up to the current format, group capabilities into domains, and narrow anchors that overlap by accident. Tidy changes **names, places and anchors**, never what a spec says, and never a capability's code. A repo that was in sync before tidy is in sync after it, under the new names.

Shared material lives in the `blueprint` skill next to this one: `../blueprint/references/`. If `.blueprint/blueprint.json` is missing, the repo isn't set up yet: say so and stop; `/blueprint-setup` creates it. Read the backend file named by `docs.backend` (`../blueprint/references/backends/<backend>.md`); its **Domains** section says how this backend creates an overview, nests, moves and renames a page, and when a rename needs `specVersion` re-recorded.

## 1. Migrate

Read `version` from `blueprint.json` (absent means 1) and the current format version from [upgrades.md](../blueprint/references/upgrades.md).

- **Current**: say so in one line and go to step 2.
- **Older**: follow that file's "How to migrate": every entry newer than the repo's version, oldest first, each shown as one list of writes for this repo and backend, applied after the user's yes, then verified by the entry's checks before `version` is raised. Run `python3 .blueprint/drift.py check --json` before the first entry and keep its output; each entry's checks compare against it. With `--dry-run`, show the lists and go on to step 2 as if migrated, reading the blueprint skill's own `scripts/drift.py` for the commands `.blueprint/drift.py` doesn't have yet.

If the user declines a migration, stop: grouping needs the current format (the `domains` map and `drift.py rename`). A migration never renames a capability or creates a domain; grouping is the next step of the same run.

## 2. Record where things stand

Before proposing anything, run `python3 .blueprint/drift.py check --json` (again, if a migration ran) and keep it as **before**, along with the output of `python3 .blueprint/drift.py unanchored`, and compute the spec side of each capability's status as [status.md](../blueprint/references/status.md) says. Tidy doesn't settle drift: a capability whose spec or code moved keeps that status through the move, and the report names it for `blueprint-drift` or `blueprint-sync`.

List the open blueprints: `changes` with status `draft`, `approved` or `building`, and the capabilities each names. A rename that touches one is listed first in the move table.

## 3. Propose domains

Read every capability's name, Purpose (from its page or baseline) and anchors, and the existing `domains`. Propose:

- **New domains**: two or more capabilities that share a name prefix (`board`, `board/ops`) or a top-level anchor folder (`src/board/`, `worker/agent/`, the folder `drift.py hint` counts), with a domain name in the repo's own vocabulary and a one-line purpose. One level deep, never deeper. A capability that fits no group stays bare; a domain of one is not worth a page.
- **Moves into domains**: each capability joining a domain, new or existing, is renamed `<domain>/<capability>` (`pads` → `board/pads`). Capabilities already named `<domain>/…` stay as they are.
- **Collisions**: every name that is both a capability and a domain (`board` beside `board/ops`). Propose the domain `board` and a new name for the leaf, offering two or three that fit its Purpose (`board/session`, `board/core`), and let the user pick. Never keep a collision ([formats.md](../blueprint/references/formats.md), naming rule).

Base each proposal on what you read, not on how many capabilities there are; the user may take some groups and leave others.

## 4. Report overlapping anchors

Run `python3 .blueprint/drift.py overlaps` and sort each file it lists:

- **Broad glob**: one capability matches it through a wide glob (`shared/**`) while another anchors that part more narrowly (`shared/board/**`). Propose narrowing the broad one: an exclusion (`!shared/board/**`) when most of the folder still belongs to it, or explicit narrower globs when only some does.
- **Intended**: shared entry points and wiring that more than one capability genuinely depends on (`worker/index.ts`). Leave them, and say why in one line.

Before proposing a narrower anchor, check which files it drops: compare `drift.py files <capability>` under the old and new anchors. A dropped file that another capability already matches is fine; it simply stops overlapping. A dropped file that nothing else matches would become **unanchored**. Keep it in the narrowed capability (an exclusion rather than explicit globs often does that), or, when it plainly belongs elsewhere, list it in the move table as left for `blueprint-sync` to anchor. Never widen another capability's anchors here: that changes what its spec covers, which is a sync decision, not a move.

Ask the user to confirm which overlaps are intended; those stay and are not raised again in this run. Anchors change only through the move table.

## 5. The move table

Show every proposed change as one table, open blueprints' renames first, then collisions, then the rest:

| Change | From | To | Touches |
| --- | --- | --- | --- |
| New domain | | `board`: the live jam board and what runs on it | overview page |
| Rename (collision) | `board` | `board/session` (or `board/core`) | page title, baseline, open blueprint *Pads v2* |
| Move into domain | `pads` | `board/pads` | page title and parent, baseline |
| Narrow anchor | `jams`: `shared/**` | `shared/**`, `!shared/board/**` | anchors, stamps |

Under it, a draft of each new overview's How they connect (two to four sentences from the anchors and Purposes) and the Capabilities list it will hold. Change the table until the user approves it as a whole. Write nothing before that yes. With `--dry-run`, stop here and say what applying it would write.

## 6. Apply the approved table

In one pass, in this order (each step needs the one before it):

1. **Overview pages**: create each new domain's overview as the backend's **Domains** section says, in the overview format ([formats.md](../blueprint/references/formats.md), "Domain overview"), Capabilities list left for step 6.
2. **Pages**: rename and move each capability's page (title, parent or path) as the backend's **Domains** section says. The page and its history stay; never create a new page for a rename. Re-record `specVersion` only where that section says a rename bumps the marker, and only after checking the body still matches the baseline.
3. **`blueprint.json`**: for each rename, run `python3 .blueprint/drift.py rename <old> <new>`, collisions first (`pads` can't become `board/pads` while `board` is still a capability). It moves the `specs` key and the baseline file, keeping `syncedCommit` and stamps; it touches nothing in the backend (steps 2 and 5 cover the pages and briefs), and refuses when a baseline already sits at the new name. Then add each new domain to `domains` with its `ref` and `purpose`, and update `ref` for any page whose path changed.
4. **Anchors**: edit the narrowed anchors. For a capability that was `in-sync` in **before**, run `drift.py stamp <capability>` so the files it no longer covers stop reading as removed. For one that was `code-moved`, delete from its `anchorsFiles` only the entries for files the new anchors no longer match, so its real changes still show.
5. **Open blueprints**: in each brief that names a renamed capability, update the Capabilities line and the `### <capability> · …` delta headings to the new names, then rebuild its review as the blueprint skill's rules say. Applied blueprints keep their briefs as written.
6. **Overview lists**: write each touched domain's Capabilities list, linked, one line each from the capability's Purpose, for new and existing domains alike. Leave an existing overview's Purpose and How they connect as people wrote them.

## 7. Verify and report

- `python3 .blueprint/drift.py check --json` reports, for every capability under its new name, the same status as **before**, and each renamed page's marker still equals its `specVersion`. A difference is a bug in this run: find it and fix it before reporting.
- `python3 .blueprint/drift.py overlaps` lists only the overlaps the user marked as intended.
- `python3 .blueprint/drift.py unanchored` lists nothing beyond what it listed before, apart from the files the table left for `blueprint-sync`.
- `python3 .blueprint/drift.py hint` prints nothing, unless the user left groups out on purpose.

Report: the migration applied (format <old> → <new>) or that the format was current; the domains created, each linked; the renames and moves; the anchors narrowed the overlaps kept as intended, and any files left unanchored for `blueprint-sync`; the open blueprints updated, linked; and any capability that was already drifted, for `blueprint-drift` or `blueprint-sync`. Commit nothing; offer to commit the `.blueprint/` changes as one commit on a yes.
