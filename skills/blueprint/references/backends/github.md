# GitHub backend

Uses the `gh` CLI. Specs live in the repo's **wiki**, which is a separate git repository (`<repo>.wiki.git`): outside the code, versioned, and readable on github.com. Blueprints are issues.

## Location

```json
"location": {
  "repo": "<owner/name>",
  "wikiClone": "<local path of the wiki clone, e.g. ~/.blueprint/wikis/<owner>__<name>>",
  "label": "blueprint"
}
```

## Set up

Check `gh auth status`. The wiki must be enabled and have at least one page before it can be cloned; if cloning fails, ask the user to create the first page on github.com (one click), then retry. Clone the wiki to `wikiClone`. Create the `blueprint` label if missing.

## Pages

- **Capability spec**: wiki page `Spec:-<capability with / replaced by ->.md`, e.g. `Spec:-auth-session.md`. Write the file in the clone, commit, and push. Add it to a `Specs.md` index page.
- **Blueprint**: an issue labelled `blueprint`, titled with the change; its body is the **review**. The **brief** is the wiki page `Blueprint:-<change id>.md`, linked at the top of the issue body; the brief links the issue back. Status: open while draft / approved / building, closed when applied (`--reason completed`) or abandoned (`--reason "not planned"`); the brief's `Status:` line says the same.
- **Tasks**: tickets per [../tickets.md](../tickets.md); with the `github` tracker they become sub-issues of the blueprint issue.

## Version marker

The wiki's last commit touching the page: `git -C <wikiClone> log -1 --format=%H -- <file>`, after `git pull`. Always pull before reading a spec; teammates edit the wiki on github.com.

## Visuals

Mermaid renders natively in issue bodies and wiki pages. GitHub won't serve a playground HTML file as a page: link the published one, or commit it to the wiki clone as `assets/<change id>-playground.html` and tell reviewers to download and open it.
