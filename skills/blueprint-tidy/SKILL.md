---
name: blueprint-tidy
description: Restructure a repo's blueprint setup on demand. Migrates .blueprint/ and the backend to the current format version, groups capabilities into domains with overview pages, renames names that are both a domain and a capability, and reports anchors that overlap through broad globs. Writes nothing without the user's yes: each migration entry, then one move table.
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
- **Older**: follow that file's "How to migrate": every entry newer than the repo's version, oldest first, each shown as one list of writes for this repo and backend, applied after the user's yes, then verified by the entry's checks before `version` is raised. Run `python3 .blueprint/drift.py check --json` before the first entry and keep its output; each entry's checks compare against it. With `--dry-run`, show the lists and go on to step 2 as if migrated, running the blueprint skill's own `scripts/drift.py` (`python3 ../blueprint/scripts/drift.py`, from this skill's folder) wherever later steps say `.blueprint/drift.py`, since the repo's copy lacks `overlaps`, `hint` and the anchor argument of `files`.

If the user declines a migration, stop: grouping needs the current format (the `domains` map and `drift.py rename`). A migration never renames a capability or creates a domain; grouping is the next step of the same run.

## 2. Record where things stand

Before proposing anything, run `python3 .blueprint/drift.py check --json` (again, if a migration ran) and keep it as **before**, along with the output of `python3 .blueprint/drift.py unanchored`, and compute the spec side of each capability's status as [status.md](../blueprint/references/status.md) says. Tidy doesn't settle drift: a capability whose spec or code moved (`code-moved`, `deps-moved`, or `possibly-affected` through code it imports) keeps that status and drift chance through the move, and the report names it for `blueprint-drift` or `blueprint-sync`.

List the open blueprints from both sides: `changes` with status `draft`, `approved` or `building`, and the blueprints the backend itself marks open (in Notion, Blueprints rows whose Status is Draft, Approved or Building), with the capabilities each names. A blueprint can be open on one side only: made in the backend by hand, recorded on a branch that never merged, or left `Building` after it shipped. Treat it as open all the same, so a rename still reaches its brief, and name each mismatch in the report for the user to settle; tidy doesn't change a blueprint's status. A rename that touches an open blueprint is listed first in the move table.

## 3. Propose domains

Read every capability's name, Purpose (from its page or baseline) and anchors, and the existing `domains`. Propose:

- **New domains**: two or more capabilities that share a name prefix (`board`, `board/ops`) or a top-level anchor folder (`src/board/`, `worker/agent/`, the folder `drift.py hint` counts), with a domain name in the repo's own vocabulary and a one-line purpose. One level deep, never deeper. A capability that fits no group stays bare; a domain of one is not worth a page.
- **Moves into domains**: each capability joining a domain, new or existing, is renamed `<domain>/<capability>` (`pads` → `board/pads`). Capabilities already named `<domain>/…` with that domain in `domains` stay as they are.
- **Prefixes without a domain**: a capability named `<prefix>/…` whose prefix isn't in `domains` (common on format 1) breaks the naming rule. Propose the domain `<prefix>` even if it holds only that capability, or a bare name for it, and let the user pick.
- **Collisions**: every name that is both a capability and a domain (`board` beside `board/ops`). Propose the domain `board` and a new name for the leaf, offering two or three that fit its Purpose (`board/session`, `board/core`), and let the user pick. Never keep a collision ([formats.md](../blueprint/references/formats.md), naming rule).

Base each proposal on what you read, not on how many capabilities there are; the user may take some groups and leave others.

## 4. Report overlapping anchors

Run `python3 .blueprint/drift.py overlaps` and sort each file it lists:

- **Broad glob**: one capability matches it through a wide glob (`shared/**`) while another anchors that part more narrowly (`shared/board/**`). Propose narrowing the broad one: an exclusion (`!shared/board/**`) when most of the folder still belongs to it, or explicit narrower globs when only some does.
- **Intended**: shared entry points and wiring that more than one capability genuinely depends on (`worker/index.ts`). Leave them, and say why in one line.

Before proposing a narrower anchor, check which files it drops: compare `drift.py files <capability>` with `drift.py files <capability> <new anchors…>`, which lists what the proposed anchors match without writing anything. A dropped file that another capability already matches is fine; it simply stops overlapping. A dropped file that nothing else matches would become **unanchored**. Keep it in the narrowed capability (an exclusion rather than explicit globs often does that), or, when it plainly belongs elsewhere, list it in the move table as left for `blueprint-sync` to anchor. Never widen another capability's anchors here: that changes what its spec covers, which is a sync decision, not a move.

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
2. **Pages**: rename and move each capability's page (title, parent or path) as the backend's **Domains** section says. The page and its history stay; never create a new page for a rename. Where that section changes the heading in `baseline/<new name>.md`, change it in `baseline/<old name>.md` instead: step 3 moves that file, and `drift.py rename` refuses if one already sits at the new name. Re-record `specVersion` only where that section says a rename bumps the marker, and only after checking the body still matches the baseline.
3. **`blueprint.json`**: first overwrite `.blueprint/drift.py` and `.blueprint/drift_ts.mjs` with the blueprint skill's `scripts/drift.py` and `scripts/drift_ts.mjs` (no format version change): an older copy renames without rewriting tags or moving closure files, and says nothing. Then, for each rename, run `python3 .blueprint/drift.py rename <old> <new>`, collisions first (`pads` can't become `board/pads` while `board` is still a capability). It moves the `specs` key, the baseline file and the closure file (`.blueprint/closure/<capability>.json`), keeping `syncedCommit` and stamps, and rewrites the capability in artifacts and in tests' `@scenario` tags; it touches nothing in the backend (steps 2 and 5 cover the pages and briefs), and refuses when a baseline or closure file already sits at the new name. Then add each new domain to `domains` with its `ref` and `purpose`, and update `ref` for any page whose path changed.
4. **Anchors**: edit the narrowed anchors, then run `drift.py prune <capability>` for each. It drops the stamps of files the new anchors no longer match, so they stop reading as removed, and keeps every other stamp and `syncedCommit`, so a capability that was `code-moved` still shows its real changes. For a TS/JS capability it also re-records the import closure for the narrowed anchors: what they no longer reach drops out, and everything still reached keeps its stamped hash and locked version, so a capability that was `deps-moved` or `possibly-affected` through code it still imports stays so. It never creates a closure that wasn't stamped, and keeps the stamped one when imports would now be followed differently (by symbol rather than by file, or back), saying so. It trims the same files from the `checkedFiles` of artifacts over that capability, unless another capability they cover still matches them, so narrowing never makes an artifact stale.
5. **Open blueprints**: in each brief that names a renamed capability, update the Capabilities line and the `### <capability> · …` delta headings to the new names, then rebuild its review as the blueprint skill's rules say. A blueprint with no brief page (an older one, written as a single page) gets the old names replaced in that page's text instead. Applied blueprints keep their briefs as written.
6. **Overview lists**: write each touched domain's Capabilities list, linked, one line each from the capability's Purpose, for new and existing domains alike. Leave an existing overview's Purpose and How they connect as people wrote them.

## 7. Verify and report

- `python3 .blueprint/drift.py check --json` reports, for every capability under its new name, the same status as **before** (a narrowed capability may lose drift chance only from imports its dropped files alone reached: name those in the report), and the spec side, computed again for every capability as in step 2 (not only renamed pages: an Obsidian move rewrites links in other notes), matches **before** too. A difference is a bug in this run: find it and fix it before reporting.
- `python3 .blueprint/drift.py overlaps` lists only the overlaps the user marked as intended or whose narrowing they left out of the table.
- `python3 .blueprint/drift.py unanchored` lists nothing beyond what it listed before, apart from the files the table left for `blueprint-sync`.
- `python3 .blueprint/drift.py hint` prints nothing, unless the user left groups out on purpose or it counts capabilities step 3 found no group for.

Report: the migration applied (format <old> → <new>) or that the format was current; the domains created, each linked; the renames and moves; the anchors narrowed the overlaps kept as intended, and any files left unanchored for `blueprint-sync`; the open blueprints updated, linked; any blueprint whose status differs between `changes` and the backend; and any capability that was already drifted, for `blueprint-drift` or `blueprint-sync`. Commit nothing; offer to commit the `.blueprint/` changes as one commit on a yes.
