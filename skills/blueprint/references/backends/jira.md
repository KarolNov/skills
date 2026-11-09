# Jira backend

Uses the Atlassian connector (Jira and Confluence). Specs go in Confluence, because Jira issues are the wrong shape for a long-lived contract; blueprints are Jira epics.

## Location

```json
"location": {
  "jiraProject": "<project key>",
  "confluenceSpace": "<space key>",
  "specsParent": "<page id of the parent page for spec pages>"
}
```

## Set up

Ask for the Jira project and the Confluence space. Find or create a parent page `<repo> specs` in the space. If the team has no Confluence, fall back to the epic's description for specs only after warning the user that specs then live on issues that get closed.

## Pages

- **Capability spec**: a Confluence page under `specsParent`, titled with the capability name. Body = the spec (Confluence converts Markdown to its storage format; headings and lists survive, so keep the format plain).
- **Blueprint**: a Jira epic, summary = change title; its description is the **review**. The **brief** is a Confluence page titled `<change>: brief` under a `<repo> blueprints` parent next to the specs, and the epic links it as a remote link, so it shows in the epic's sidebar. Status lives on the epic and maps to the project's workflow.
- **Tasks**: tickets per [../tickets.md](../tickets.md); with the `jira` tracker they become the epic's children.

## Version marker

The Confluence page's version number (`version.number`). It increments on every save, including yours; read it after the last write.

## Notes

Confluence round-trips lose some Markdown detail. Read the page back after writing and save that text, converted to Markdown, as the baseline.

## Visuals

Confluence and Jira don't render Mermaid unless the site has a Mermaid app installed; check by reading the page back. Otherwise use the image fallback in visuals.md, attaching the PNG to the page or epic and keeping the source in a code block under it. Attach a playground HTML file to the Confluence page, or link the published one.
