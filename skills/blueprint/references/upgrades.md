# Upgrades

The ledger of breaking changes to the blueprint format: the shape of `.blueprint/` and of the structure in the backend. `version` in `blueprint.json` records which entry a repo has reached; absent means 1.

**Current format version: 2**

Only `/blueprint-tidy` reads this file to migrate. Every other skill compares the repo's `version` with the current one above and, when it is older, says in one line that `/blueprint-tidy` upgrades it, then carries on without migrating.

## How to migrate

Apply every entry newer than the repo's `version`, oldest first, each in full before the next:

1. Show the entry's writes for this repo and backend as one list (files, pages, properties), and apply them after the user's yes.
2. Run the entry's checks.
3. Set `version` in `blueprint.json` to the entry's number. A migration never renames a capability or changes anchors, stamps or `specVersion`, so it never reads as drift.

Entries are append-only. A new format version adds a section at the end, raises **Current format version**, and names what changed, how to migrate per backend, and how to verify.

## Version 2: domains

**What changed**

- `blueprint.json` gains `version` and `domains` (`name → { ref, purpose }`), [formats.md](formats.md).
- Capabilities can be grouped into domains, each with an overview page in the backend that holds its capabilities like a folder. A name is either a domain or a capability, never both.
- `drift.py` gains `version`, `overlaps`, `rename` and `hint`.

**Migrate**

- `blueprint.json`: add `"version": 2` as the first key and `"domains": {}` before `specs`. Leave every other key as it is.
- `.blueprint/drift.py`: overwrite with `scripts/drift.py` from the blueprint skill. With the Notion backend, also overwrite `.blueprint/notion_normalize.py` with `scripts/notion_normalize.py`.
- Backend, by `docs.backend`:
  - **notion**: add `"Kind" SELECT('Capability':gray, 'Domain':blue)` to the Specs data source and set every existing row to `Capability`, then turn on sub-items for it (a `Parent item` self-relation), so a domain row can hold capability rows.
  - **obsidian**: move each capability note from the flattened `<specs>/<domain>__<capability>.md` to the folder `<specs>/<domain>/<capability>.md`, then update its `ref` in `blueprint.json` and the `[[wikilinks]]` that point to it. A bare capability stays at `<specs>/<capability>.md`.
  - **markdown**, **linear**, **jira**, **github**: nothing to move; capability names already keep their `/`.
- No capability is renamed and no domain is created by the migration. Grouping is the next, separate step of the same `/blueprint-tidy` run.

**Verify**

- `python3 .blueprint/drift.py version` prints `2`.
- `python3 .blueprint/drift.py check` reports the same status for every capability as before the migration.
- Every `ref` in `blueprint.json` still opens its page (Obsidian: the moved file exists at the new path).
