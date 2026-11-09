# Linear backend

Uses the Linear connector (or the Linear API if the user has a key in their environment). Specs are Linear documents; blueprints are issues, since that is where Linear's work lives.

## Location

```json
"location": {
  "team": "<team key>",
  "project": "<project id or URL holding the spec documents>",
  "label": "blueprint"
}
```

## Set up

Ask which team and which project the specs belong to; offer to create a project `<repo> specs` if there is none. Create a `blueprint` label on the team if missing.

## Pages

- **Capability spec**: a document in the project titled with the capability name. Body = the spec in Markdown.
- **Blueprint**: an issue labelled `blueprint`, titled with the change; its description is the **review**. The **brief** is a document in the same project titled `<change>: brief`, linked from the issue's description and as an issue link, so the two are one click apart. Status lives on the issue and maps to the team's workflow states (draft → Backlog, approved → Todo, building → In Progress, applied → Done, abandoned → Canceled).
- **Tasks**: tickets per [../tickets.md](../tickets.md); with the `linear` tracker they become sub-issues of the blueprint issue.

## Version marker

The document's `updatedAt`. Your own writes bump it; read it after the last write and record that.

## Notes

Linear's document editor normalizes Markdown (list markers, code fences). Read the spec back after writing and save that text as the baseline, not the text you sent.

## Visuals

Write Mermaid as ` ```mermaid ` blocks and read the issue or document back: if Linear shows the block as code, use the image fallback in visuals.md and attach the SVG/PNG to the issue. Link a published playground from the review (the issue); without one, attach the HTML file to the issue.
