# Markdown folder backend

Plain Markdown files in a folder outside the repo: a separate notes repo, a shared drive, a Dropbox or iCloud folder. Read and written directly.

## Location

```json
"location": {
  "root": "<absolute path, or ~-relative>",
  "specs": "specs",
  "blueprints": "blueprints"
}
```

`specs` and `blueprints` are relative to `root`.

## Set up

Ask for the folder. Refuse a path inside this repo's working tree (that is what OpenSpec does, and the point here is to keep specs outside); suggest a sibling folder or a dedicated notes repo instead. Create `specs/`, `blueprints/` and an `index.md` listing the capabilities.

If `root` is itself a git repository, commit there after each approved write (`blueprint: <capability or change> …`), only with the user's yes the first time; after that, follow what they chose.

## Pages

- **Capability spec**: `specs/<capability>.md`, keeping `/` as subfolders (`specs/auth/session.md`). The `ref` in `blueprint.json` is the path relative to `root`.
- **Blueprint**: two files side by side: the review `blueprints/<change id>.md` and the brief `blueprints/<change id>.brief.md`, linking each other relatively. The brief has a YAML frontmatter block for `status`, `capabilities`, `branch`, `pr`; tasks are Markdown checkboxes in it.

## Version marker

The SHA-256 of the file's contents, first 16 hex characters. If `root` is a git repo, the last commit touching the file (`git -C <root> log -1 --format=%H -- <file>`) works too, but only once every write is committed; the content hash works either way, so prefer it.

## Visuals

Keep Mermaid as ` ```mermaid ` blocks: GitHub, VS Code and most Markdown viewers render them. Save a playground as `blueprints/<change id>.playground.html` beside the review and link it relatively.
