# Obsidian backend

Plain files in an Obsidian vault, read and written directly. No connector needed.

## Location

```json
"location": {
  "vault": "<absolute path to the vault>",
  "specs": "<folder in the vault, e.g. Projects/<repo>/Specs>",
  "blueprints": "<folder in the vault, e.g. Projects/<repo>/Blueprints>"
}
```

## Set up

Ask for the vault path (look for a folder containing `.obsidian/` under the home directory to offer candidates). Create the two folders if missing, and a `<repo> blueprint.md` index note beside them that links both.

## Pages

- **Capability spec**: `<specs>/<capability>.md`, keeping `/` as real folders: `<specs>/auth/session.md` for `auth/session`, `<specs>/search.md` for a bare `search`. Repos on format 1 used flattened names (`auth__session.md`); the version 2 migration moves them ([../upgrades.md](../upgrades.md)). Frontmatter:
  ```yaml
  ---
  capability: auth/session
  repo: <repo remote URL>
  tags: [blueprint/spec]
  ---
  ```
- **Blueprint**: two notes side by side in `<blueprints>/`: the review `<change id>.md` and the brief `<change id>.brief.md`, each linking the other with a `[[wikilink]]`. The brief's frontmatter holds `status`, `capabilities` (as `[[wikilinks]]` to the spec notes), `branch`, `pr`, `tags: [blueprint/brief]`; the review's holds `brief`, `built-from` and `tags: [blueprint/review]`. Tasks are Markdown checkboxes in the brief.
- Links between notes use `[[wikilinks]]` with the path from the vault root and the capability name as the alias (`[[<specs>/auth/session|auth/session]]`), because leaf names like `session` repeat across domains. The `ref` in `blueprint.json` is the path relative to the vault.

## Domains

- **Overview**: the folder note `<specs>/<domain>/<domain>.md`, in the overview format ([../formats.md](../formats.md), "Domain overview"), with frontmatter `domain: <name>` and `tags: [blueprint/domain]`. The note named after its folder is the folder-note convention (the Folder notes community plugin opens it when the folder is clicked). Its path relative to the vault is the domain's `ref`. No capability may be named `<domain>/<domain>`.
- **Nesting**: the domain's capability notes are the other notes in `<specs>/<domain>/`.
- **Move or rename**: move the file on disk, create the folder (and its folder note) if the domain is new, then update its `ref`, the `capability:` frontmatter, and every `[[wikilink]]` to the old path (search the vault for it). Obsidian rewrites links only for moves made inside the app, so do it yourself. These edits change content hashes, of the moved note and of every other spec note whose links you rewrote, so first note which of them are in sync (current marker equals `specVersion`). Change the spec's `# <capability name>` heading to the new name, and the heading in `baseline/<new name>.md` the same way. Make the same link changes in the in-sync notes' baselines, then record each in-sync note's new hash as `specVersion`, so the rename never reads as drift. A note that was already out of sync keeps its old `specVersion`.
- An overview has no version marker or baseline.

## Version marker

The SHA-256 of the file's contents (`shasum -a 256 <file>`), first 16 hex characters. Content-based, so moving the vault or syncing it between machines doesn't read as drift.

## Notes

The vault may be synced (Obsidian Sync, iCloud, git). If a file has a sync-conflict sibling (`… (conflicted copy).md`, `.sync-conflict-…`), stop and ask the user which one is current.

## Visuals

Mermaid renders natively in ` ```mermaid ` blocks. Save a playground as `<blueprints>/assets/<change id>-playground.html` and link it with a plain Markdown link (`[Playground](assets/….html)`); Obsidian opens it in the default browser.
