# Notion backend

Uses the Notion connector. Before writing page content the first time in a session, read `notion://docs/notion-flavored-markdown-spec` with the Notion fetch tool, as the connector asks.

## Location

```json
"location": {
  "root": "<URL of the Specs & blueprints page>",
  "specs": "<collection:// data source of the Specs database>",
  "blueprints": "<collection:// data source of the Blueprints database>"
}
```

## Set up

The location comes from `blueprint-setup`: usually a new subpage of the repo's own page or row in the team's project tracker. Search under that parent first; reuse what exists and create only what is missing:

- **Root page** `Specs & blueprints` under that parent, with two lines saying what the databases hold, that the row page is the review and the brief is its subpage, and where tickets live (linked).
- **Specs** database under the root:
  `CREATE TABLE ("Capability" TITLE, "Purpose" RICH_TEXT, "Last edited" LAST_EDITED_TIME)`
- **Blueprints** database under the root:
  `CREATE TABLE ("Change" TITLE, "Status" STATUS('Draft':gray:to_do, 'Approved':blue:to_do, 'Building':yellow:in_progress, 'Applied':green:complete, 'Abandoned':red:complete), "Capabilities" RELATION('<specs data source>', DUAL 'Blueprints'), "Brief" URL, "Tickets" URL, "Branch" RICH_TEXT, "PR" URL, "Last edited" LAST_EDITED_TIME)`

Never put them in a private draft or at the workspace root: they belong next to where the team tracks the project. Never add rows or properties to the team's existing databases from here.

Fetch each database once after creating it and record its `collection://` URL in `location`.

## Pages

- **Capability spec**: a row in Specs. Title = capability name; page body = the spec from Purpose down (the title is the property, not a heading in the body).
- **Blueprint**: a row in Blueprints, titled with the change. The row's body is the **review**, because that's what people open from the database. The **brief** is a child page inside the row, titled `<change>: brief`, so the two always sit together; its URL also goes in the row's `Brief` property. Status and Capabilities are row properties, so drop those lines from both bodies.
- **Tasks** are Notion to-dos in the brief (`- [ ] 1. …`), each linking its ticket ([../tickets.md](../tickets.md)). Notion escapes the number on save, so the page reads back as `- [ ] 1\. …`: tick a task with `update_content`, replacing `- [ ] <n>\.` with `- [x] <n>\.`, copied from a fresh fetch.
- **Rewrite a spec**: `update_content` per changed requirement block when the edit is local; `replace_content` for a full merge.

## Version marker

For specs and briefs: the SHA-256 of the page body, normalized as in "Reading back as Markdown" below, first 16 hex characters. Not the last-edited time: Notion rounds it to the minute, so a teammate's edit in the same minute as your write would not show. Fetch the page **after the last write** of a sync and hash that.

## Reading back as Markdown

Fetch returns Notion-flavored Markdown. Before saving a baseline or diffing, normalize it: turn `<b>`/`<code>` back into `**`/backticks, unescape `\.`, drop Notion-only wrappers (colors, mention tags rendered as their plain title), and keep the heading structure intact. Baseline and current text must go through the same normalization, so diffs show content changes only.

## Comments

Spec pages may carry comments from teammates. During sync, fetch with `include_discussions` and surface open discussions on a requirement you are about to change.

## Visuals

Mermaid code blocks show as code when written through the connector, and a rebuild resets any block someone switched to preview, so diagrams go in as images:

1. Render the review's diagrams to SVG with `scripts/render_mermaid.py` (see visuals.md).
2. For each file, `notion-create-file-upload` (filename ending `.svg`), then POST the file to the returned `upload_url` as multipart field `file` with the returned headers: `curl -X POST <upload_url> -H "authorization: <value>" -F "file=@diagram.svg;type=image/svg+xml"`. Uploads expire within the hour unless placed on a page.
3. In the review, write `<image source="file-upload://<id>">caption</image>`, then a `<toggle>` holding a grey "Mermaid source" line and the ` ```mermaid ` block.

The playground runs inside the review: upload the HTML file the same way (filename ending `.html`) and place it with `<embed source="file-upload://<id>" />` in the Playground section. Notion renders it as a sandboxed live preview. On a rebuild, upload fresh files and replace the old blocks; read the page back to confirm each source turned into a `notion-file-block://` URL.
