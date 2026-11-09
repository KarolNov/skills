# Formats

Three shapes: the capability spec, the blueprint (a brief and its review), and `.blueprint/blueprint.json`. Backends render them in their own way (Notion blocks, Markdown files, issue bodies), but the sections and their order are the same everywhere, so any of them can be read back and diffed as Markdown.

## Capability spec

A **behavior contract**: what users or other systems can observe and rely on. The quick test for every line: if the implementation could change without anyone outside noticing, the line belongs in a blueprint's design, not here. No file paths, class names or library choices; those go stale first. No diagrams either: a spec is text that agents read and sync diffs, and pictures of it belong in a review.

```markdown
# <capability name, e.g. auth/session>

## Purpose
<one or two sentences: what this capability is for>

## Requirements

### Requirement: <short name, unique within the spec>
<one behavior, stated with SHALL / MUST>

- **Scenario: <name>**
  - **GIVEN** <state, optional>
  - **WHEN** <trigger>
  - **THEN** <observable outcome>
```

Headings stop at level 4 everywhere, because Notion and Confluence have no deeper headings; that is why scenarios are list items rather than headings. A requirement block reads the same in a spec and in a brief's delta, except that its heading is one level deeper in the brief.

- One behavior per requirement; edge cases go in scenarios, not in the requirement text.
- Every requirement has at least one scenario, and every scenario a WHEN and a THEN.
- The requirement name is its identity. Sync and deltas match on it, so rename only through a delta's RENAMED section.

## Blueprint: a brief and a review

Each change has two documents that sit side by side in the backend and link to each other. Both are named for the change (`Add SSO login`); the change also has a kebab-case id (`add-sso-login`) used in `blueprint.json` and branch names.

- The **brief** is for agents: plain text, exhaustive, no pictures. It is the **source of truth**. Apply and sync read only the brief, and every decision lands here first.
- The **review** is for people: the picture first, then the same change told briefly in plain language. It is **derived** from the brief and rebuilt whenever the brief changes. Nobody edits it as the record. Comments and edits people leave on it are input that gets folded into the brief, with the user's yes.

### Brief

```markdown
# <change title>: brief

- Status: draft | approved | building | applied | abandoned
- Capabilities: <capability names this touches, linked>
- Review: <link to the review>
- Branch / PR: <filled in by apply>

## Destination
<one or two lines: what is true when this is done>

## Why
<the problem, from the user's side; two or three sentences>

## Solution
<the user's design, in their terms: 3 to 8 bullets>

## Decisions
- **<decision>**: <what was chosen and the one-line reason>. <Rejected alternative, only if one was actually discussed.>

## Assumed
- <defaults you chose without asking, one line each, so the user can skim and veto>

## Out of scope
- <what this change deliberately does not do>

## Code map
- <area>: <files or modules this change works in, and what they do today>; one line each, for the agent that builds it

## Spec delta

### <capability> · ADDED
<for a new capability, first a line: **Purpose**: …>

#### Requirement: <name>
<full requirement block, as in the capability spec, heading one level deeper>

### <capability> · MODIFIED

#### Requirement: <existing name, unchanged>
<the whole block as it should read afterwards>

### <capability> · REMOVED
- **<requirement name>**: <why, and what replaces it for anyone relying on it>

### <capability> · RENAMED
- <old name> → <new name>

## Tasks
- [ ] 1. <a vertical slice: one observable step that can be built and checked on its own>
- [ ] 2. …

## Open questions
<only what grilling could not settle; empty when approved>
```

- MODIFIED always carries the complete requirement, scenarios included: merging replaces the old block wholesale, so a partial block loses detail.
- A change that alters no observable behavior (a refactor, tooling) has an empty Spec delta and says so in one line.
- Tasks are tracer bullets, each ending in something runnable or testable, not layers ("all the models", then "all the endpoints").
- The Code map is the one place for file paths: it guides the build and goes stale harmlessly once the change is applied. Capability specs never carry it.

### Review

```markdown
# <change title>

<Status> · <capabilities> · Brief: <link to the brief> · Built from brief <version marker>

## Destination
<the brief's destination, word for word>

## Picture
<one to three diagrams with captions (visuals.md)>
<Playground: link, if there is one>

## What changes
<3 to 6 bullets in plain language: what someone using the system will notice>

## Decisions
<one line each, the brief's decisions without the alternatives>

## Behavior
<each spec requirement from the delta as one sentence with its key scenario, marked new / changed / removed; for reviewers who approve behavior, not wording>

## Progress
<tasks done of total, with the next one named>
```

- The review restates; it never adds. Anything that appears only in the review is a bug: move it into the brief or drop it.
- "Built from brief <version>" records the brief's version marker at the time of the rebuild. When it differs from the brief's current marker, the review is stale; rebuild it before anyone is asked to look.

## `.blueprint/blueprint.json`

```json
{
  "docs": {
    "backend": "notion",
    "location": { "...": "backend-specific: database ids, vault path, project key; see the backend file" }
  },
  "tickets": {
    "tracker": "github",
    "location": { "...": "tracker-specific: repo, team, project key or tasks database; see tickets.md" },
    "conventions": { "label": "blueprint", "areaLabels": ["transport", "persistence"] }
  },
  "project": "<URL of the existing project page, row or project these specs belong to, if any>",
  "specs": {
    "auth/session": {
      "ref": "<page URL or path>",
      "specVersion": "<backend version marker as of the last sync>",
      "anchors": ["src/auth/**", "!**/*.test.ts"],
      "anchorsHash": "<written by drift.py stamp>",
      "syncedCommit": "<written by drift.py stamp>"
    }
  },
  "changes": {
    "add-sso-login": {
      "brief": "<page URL or path of the brief>",
      "review": "<page URL or path of the review>",
      "playground": "<where the playground file lives in the backend, if there is one>",
      "tickets": "<link to this change's tickets, e.g. a filtered issue list>",
      "status": "building",
      "baseCommit": "<HEAD when the blueprint was approved>",
      "branch": "kn/add-sso-login"
    }
  }
}
```

- **anchors** are git-style globs relative to the repo root. A bare directory covers everything under it; `!` excludes. Leave tests out of anchors unless the tests themselves are the contract.
- **specVersion** is whatever the backend offers as a cheap "has this page changed" marker (see the backend file). When it differs from the backend's current marker, the spec moved.
- `anchorsHash` and `syncedCommit` are written only by `drift.py stamp`; never edit them by hand.
