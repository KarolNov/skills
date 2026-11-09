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

- **Capability spec**: `<specs>/<capability with / replaced by __>.md`, e.g. `auth__session.md`. Frontmatter:
  ```yaml
  ---
  capability: auth/session
  repo: <repo remote URL>
  tags: [blueprint/spec]
  ---
  ```
- **Blueprint**: two notes side by side in `<blueprints>/`: the review `<change id>.md` and the brief `<change id>.brief.md`, each linking the other with a `[[wikilink]]`. The brief's frontmatter holds `status`, `capabilities` (as `[[wikilinks]]` to the spec notes), `branch`, `pr`, `tags: [blueprint/brief]`; the review's holds `brief`, `built-from` and `tags: [blueprint/review]`. Tasks are Markdown checkboxes in the brief.
- Links between notes use `[[wikilinks]]`; the `ref` in `blueprint.json` is the path relative to the vault.

## Version marker

The SHA-256 of the file's contents (`shasum -a 256 <file>`), first 16 hex characters. Content-based, so moving the vault or syncing it between machines doesn't read as drift.

## Notes

The vault may be synced (Obsidian Sync, iCloud, git). If a file has a sync-conflict sibling (`… (conflicted copy).md`, `.sync-conflict-…`), stop and ask the user which one is current.

## Visuals

Mermaid renders natively in ` ```mermaid ` blocks. Save a playground as `<blueprints>/assets/<change id>-playground.html` and link it with a plain Markdown link (`[Playground](assets/….html)`); Obsidian opens it in the default browser.
