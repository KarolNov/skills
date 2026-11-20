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

Ask for the folder. Refuse a path inside this repo's working tree (that is what OpenSpec does, and the point here is to keep specs outside); suggest a sibling folder or a dedicated notes repo instead. Create `specs/`, `blueprints/` and an `index.md` listing the domains (each linking its overview) and the bare capabilities.

If `root` is itself a git repository, commit there after each approved write (`blueprint: <capability or change> …`), only with the user's yes the first time; after that, follow what they chose.

## Pages

- **Capability spec**: `specs/<capability>.md`, keeping `/` as subfolders (`specs/auth/session.md`). The `ref` in `blueprint.json` is the path relative to `root`.
- **Blueprint**: two files side by side: the review `blueprints/<change id>.md` and the brief `blueprints/<change id>.brief.md`, linking each other relatively. The brief has a YAML frontmatter block for `status`, `capabilities`, `branch`, `pr`; tasks are Markdown checkboxes in it.

## Domains

- **Overview**: `specs/<domain>/index.md`, in the overview format ([../formats.md](../formats.md), "Domain overview"), so the folder that holds the domain's capability files opens on it. Its path relative to `root` is the domain's `ref`.
- **Nesting**: the capability files already sit in the folder (`specs/auth/session.md`); a bare capability stays at `specs/<capability>.md`. No capability may be named `<domain>/index`.
- **Move or rename**: move the file (`git mv` when `root` is a git repo, so history follows), then update its `ref` and the relative links that point to it: `index.md`, the domain overviews, and briefs and reviews of open blueprints. Commit the move on its own, before any content edit.
- A move alone keeps the content, so the version marker (a content hash) carries over. A rename also changes the content. Before renaming, note whether the page is in sync (its current marker equals `specVersion`). Change the spec's `# <capability name>` heading to the new name, and the heading in `baseline/<new name>.md` the same way. When the page was in sync, record the new hash as `specVersion`, so the rename never reads as drift. An overview has no marker or baseline.

## Version marker

The SHA-256 of the file's contents, first 16 hex characters. If `root` is a git repo, the last commit touching the file (`git -C <root> log -1 --format=%H -- <file>`) works too, but only once every write is committed; the content hash works either way, so prefer it.

## Visuals

Keep Mermaid as ` ```mermaid ` blocks: GitHub, VS Code and most Markdown viewers render them. Save a playground as `blueprints/<change id>.playground.html` beside the review and link it relatively.
