# Formats

Four shapes: the capability spec, the domain overview, the blueprint (a brief and its review), and `.blueprint/blueprint.json`. Backends render them in their own way (Notion blocks, Markdown files, issue bodies), but the sections and their order are the same everywhere, so any of them can be read back and diffed as Markdown.

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
- Scenario names are unique within a capability, not only within their requirement: a test's tag names the scenario without its requirement (below). `coverage.py` reports a duplicate as a problem naming both requirements.

### Scenario tags

A test claims a scenario with a comment on the line or lines above it, such as `// @scenario auth/session: Expired session redirects to login`. (Examples in docs stay inline like this one: a line that starts with a comment marker and `@scenario` counts as a real tag wherever it sits, Markdown included.)

- The key is `<capability>: <scenario name>`, with no requirement name, so renaming a requirement never breaks a tag. Names match case-insensitively with whitespace collapsed; anything else (a typo, the old wording) is an orphan.
- Any line comment holds it (`//`, `#`, `--`, `/* */`, `*`, `<!-- -->`), so JS/TS, Rust, Go and Python tests are tagged the same way. One test may carry several tags, and many tests may claim one scenario.
- A tag says the test **claims** the scenario, never that it verifies it or passes: nothing is run. A skipped test still claims.
- The test's kind (unit, e2e, …) comes from where its file sits, by `tests.kinds` in `blueprint.json` below, never from the tag.
- Tags live in the tests, never in specs or `blueprint.json`. `drift.py rename` rewrites them when a capability is renamed, and apply when a MODIFIED block renames a scenario; [coverage.md](coverage.md) reports the rest.

## Domain overview

The page a domain lives on. It holds the domain's capabilities like a folder (how each backend nests them is in its **Domains** section) and tells a reader what the group is for before they open any spec.

```markdown
# <domain name, e.g. auth>

## Purpose
<one or two sentences: what this group of capabilities is for; the same line as `purpose` in blueprint.json>

## Capabilities
- <capability name, linked to its spec>: <its Purpose, shortened to one line>
- <capability with no spec yet>: <one line> (no spec yet)

## How they connect
<a few sentences or bullets: which capability calls or feeds which, what they share, the order a request passes through them>
```

- An overview is **not a spec**: no requirements, no baseline, no version marker, no drift check. People edit it freely, and editing it never makes a capability read as drifted.
- Only the **Capabilities** list is maintained by the skills: setup writes it, `apply` and `/blueprint-tidy` refresh it when a capability in the domain is added, renamed, removed or changes its Purpose. They leave Purpose and How they connect as people wrote them.
- List capabilities in name order, each with its full name (`auth/session`), so the list reads the same in backends that keep the prefix in titles.

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
- Target repo: <only when this change creates the repo: its name, and the pending setup folder>

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

## Artifacts
<optional: resources outside the repo that describe the touched capabilities; absent when none were named>
- **<id, kebab-case>** · <type> · <value> · <description> · covers <capabilities or domains>

## Tasks
- [ ] 1. <a vertical slice: one observable step that can be built and checked on its own>
- [ ] 2. …

## PRs
<written by apply when it splits the change; absent for a one-PR change>
- [ ] 1. <group name> · tasks 1, 2 · base main · branch: <branch> · PR: <link>
- [ ] 2. <group name> · tasks 3, 4 · base group 1 · branch: … · PR: …
- [ ] Specs · task <last> · after every group merges · branch: … · PR: …

## Open questions
<only what grilling could not settle; empty when approved>
```

- MODIFIED always carries the complete requirement, scenarios included: merging replaces the old block wholesale, so a partial block loses detail.
- A change that alters no observable behavior (a refactor, tooling) has an empty Spec delta and says so in one line.
- Tasks are tracer bullets, each ending in something runnable or testable, not layers ("all the models", then "all the endpoints").
- The Code map is the one place for file paths: it guides the build and goes stale harmlessly once the change is applied. Capability specs never carry it.
- **Artifacts** lists the resources outside the repo (a support article, a docs page, a README in another repo) that describe the capabilities this change touches, each in the shape of an `artifacts` entry in `blueprint.json` below. Apply adds them with `drift.py artifacts add`; until then they live only on the brief.

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
  "version": 2,
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
  "targetRepo": "<only while this repo doesn't exist yet: its intended name or URL>",
  "domains": {
    "auth": { "ref": "<page URL or path of the domain overview>", "purpose": "<one line>" }
  },
  "specs": {
    "auth/session": {
      "ref": "<page URL or path>",
      "specVersion": "<backend version marker as of the last sync>",
      "anchors": ["src/auth/**", "!**/*.test.ts"],
      "anchorsFiles": { "src/auth/session.ts": "<content hash, written by drift.py stamp>" },
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
      "baseRepo": "<only when baseCommit is in another repo, e.g. owner/source-repo>",
      "branch": "kn/add-sso-login"
    }
  },
  "artifacts": {
    "sso-help-article": {
      "type": "webpage",
      "value": "https://help.example.com/articles/sign-in-with-sso",
      "description": "Help-center article on signing in with SSO",
      "capabilities": ["auth"],
      "checkedFiles": { "src/auth/session.ts": "<content hash, written by drift.py artifacts add / checked, trimmed by prune>" }
    }
  },
  "tests": {
    "kinds": {
      "e2e": ["e2e/**"],
      "unit": ["**/*.test.ts", "**/*_test.go"]
    },
    "run": { "command": "npx vitest run --reporter=junit --outputFile=reports/junit.xml", "report": "reports/junit.xml" }
  },
  "drift": {
    "scoring": {
      "decay": 0.5,
      "packageWeight": 0.5,
      "lockfileWeight": 0.3,
      "threshold": 0.5,
      "maxDepth": 6,
      "packages": {
        "@company/core": { "weight": 1.0 },
        "@company/legacy": { "sideEffects": false }
      }
    }
  }
}
```

- **version** is the format version of this file and the backend structure it describes; absent means 1. The current version and what changed in each are in [upgrades.md](upgrades.md). Only `/blueprint-tidy` migrates an older one; every other skill says so in one line and carries on.
- **domains** maps each domain to its overview page (`ref`) and a one-line `purpose`. A domain groups capabilities; it has no anchors, baseline or version marker. Empty (`{}`) when the repo has none.
- **Capability names** are `<domain>/<capability>` (`auth/session`, where `auth` is in `domains`) or a bare `<capability>` (`search`). A name is either a domain or a capability, never both: no capability `board` beside `board/ops`. Domains are one level deep.
- **anchors** are git-style globs relative to the repo root. A bare directory covers everything under it; `!` excludes. Leave tests out of anchors unless the tests themselves are the contract.
- **targetRepo** (top level, optional) is set only while the repo this file describes doesn't exist yet: its intended name or URL. The file then lives in the pending folder `blueprint-setup` names, and `apply` moves it into the new repo and drops the key.
- **baseRepo** is set when `baseCommit` belongs to another repo (a change that creates this repo from another one's code). Without it, `baseCommit` is a commit of this repo.
- **specVersion** is whatever the backend offers as a cheap "has this page changed" marker (see the backend file). When it differs from the backend's current marker, the spec moved.
- `anchorsFiles` (a hash per anchored file) and `syncedCommit` are written only by `drift.py stamp` (and `anchorsFiles` trimmed by `drift.py prune`); never edit them by hand. Stamp also writes the capability's import closure to `.blueprint/closure/<capability>.json` (below), not here. `syncedCommit` is the commit that holds the synced code, so `git diff <syncedCommit>` shows only what changed after.
- **artifacts** (optional) maps a kebab-case id to a resource outside the repo that describes one or more capabilities, so whoever changes their code is told to check it. Older readers ignore the key, so it needs no format version bump.
  - `type` is one of `webpage` (value a URL), `file` (a file in another git repo: `<repo>:<path>`, where `<repo>` is `owner/name` on GitHub or a git URL), `notion`, `confluence`, `linear` or `github` (value the page's URL; `github` is for an issue, PR, wiki or Pages URL, while a file in a repo is `file`), `obsidian` (a path relative to the vault, or an `obsidian://` URL) or `markdown` (a path relative to the notes folder's root, or absolute). Types are named after the tool, not the repo's backend, and any type can be used whatever the backend is; when the backend is that tool, relative paths resolve against its `docs.location`.
  - `capabilities` names capabilities or domains; a domain stands for every capability in it at check time, so one added to the domain later is covered too.
  - `checkedFiles` is the artifact's own stamp: a hash per file its capabilities' anchors matched when someone last checked it. The artifact is **stale** from the moment one of those files is added, removed or edited until it is marked checked again, whether or not the spec was synced in between.
  - Manage them only through `drift.py`: `artifacts add --id <id> --type <type> --value <value> --description <text> <capability>…` adds one, stamped as checked (`--id` is derived from the description when left out, and the value's shape is checked per type); `add` refuses an unknown type, a value of the wrong shape, an empty description, a name that is neither a capability nor a domain, and an id that isn't kebab-case or is taken. `artifacts checked <id>… | --all` restamps; `artifacts remove <id>` drops one; `artifacts [--json] [--] [capability|domain…]` lists the stale ones with their changed files and exits 0 unless a filter names no capability or domain (`--` lets a filter be named `add`, `checked` or `remove`). It also lists, under any filter, an artifact whose `capabilities` names something that is no longer a capability or a domain, marked unknown; `checked` refuses such an artifact until its `capabilities` are fixed. `drift.py rename` renames a capability in every artifact too, and `drift.py prune` trims the stamps of artifacts over the pruned capability. Never edit `checkedFiles` by hand.
  - Artifacts are bookkeeping, like anchors: they stay in this file, never on spec pages.
- **tests** (optional) says how `/blueprint coverage` reads the repo's tests. Older readers ignore the key, so it needs no format version bump, and only coverage requires it.
  - `kinds` maps each kind name to git-style globs, in order; a test file gets the first kind whose globs match it. Kinds are free-form (`contract` or `visual` beside `unit`, `integration`, `e2e`). There are no default globs: without `kinds`, `coverage.py` exits 2 naming the key. The coverage mode proposes kinds from the repo's test layout on first run and writes them on the user's yes ([coverage.md](coverage.md)).
  - A tag in a file no kind matches still claims its scenario and is reported as unclassified, so a missing glob shows up without hiding coverage.
  - `run` (optional) says how `drift.py check --tests run` runs the tests: `{"command": "<shell command>", "report": "<JUnit XML path, relative to the repo root>"}`. The command runs at the repo root (its output goes to stderr, so `--json` stays clean) and must write the report; a failing run is fine, since failures are what the report is for. Check exits 2 when `run` is absent or not that shape, or when the report is missing or wasn't rewritten by the run. `check --tests <report.xml>` reads a report written some other way and needs no `run`. Without `--tests`, check uses no test results and never runs tests. A `testcase` counts for a scenario when its file and name match a tagged test (the test declared right below the tag, as coverage records it); failing or erroring scores 1, passing raises confidence, and skipped or unmatched is no result.
- **drift** (optional) tunes code-side drift. Older readers ignore the key, so it needs no format version bump. `drift.scoring` sets how `drift.py check` turns what changed into a **drift chance** from 0 to 1 ([status.md](status.md)); every key is optional and takes its default when absent:

  | Key | Default | Meaning |
  | --- | --- | --- |
  | `decay` | 0.5 | A change `n` import edges from an anchored file scores `decay^n` |
  | `packageWeight` | 0.5 | Multiplies that score once for each workspace package the import path enters |
  | `lockfileWeight` | 0.3 | Score of a changed locked version of an external package the closure imports |
  | `threshold` | 0.5 | A chance at or above it is `deps-moved` (drift, exit 1); above 0 and below it, `possibly-affected` (exit 0) |
  | `maxDepth` | 6 | Import edges followed from the anchored files; beyond 6 a change scores under 0.02 at the default decay |
  | `packages` | `{}` | Per workspace package name: `weight` replaces `packageWeight` for paths entering it, `sideEffects` overrides its `package.json` field |

  A changed anchored file always scores 1. Several signals combine as `1 − ∏(1 − sᵢ)`, so two changes scoring 0.25 give 0.4375 and nothing exceeds 1. Values must be numbers from 0 to 1 (`maxDepth` a whole number of at least 1, `sideEffects` `true`, `false` or a list of globs); anything else makes `check` and `stamp` exit 2 naming the key, reporting nothing. So `"@company/core": {"weight": 1.0}` makes a change one import away in that package score 0.5 instead of 0.25, as heavily as a change one import away inside the capability's own package.

### Side effects: what an import depends on

TS/JS imports are followed by symbol, like an editor's "go to definition": the repo's own `typescript` resolves each imported name to the declaration it really is, through re-exports, `export *` barrels, renames and `tsconfig` paths. A **named import from a file without side effects** depends on the imported declarations and the declarations they reference, followed across files and packages, so a change to a private helper `signToken` calls counts and a change to an unused sibling export doesn't. A **bare import** (`import '@company/polyfills'`), or any import from a file **with side effects**, depends on that whole file and everything it imports. Barrels are transparent: a reason names the symbol in the file that declares it, not the index that re-exports it.

Whether a file has side effects comes from the nearest `package.json` at or above it, by the `sideEffects` field bundlers already use, for workspace packages and the app's own package alike:

| `package.json` | Meaning |
| --- | --- |
| `"sideEffects": false` | No file has side effects: named imports are followed by symbol |
| `"sideEffects": ["**/*.css", "./src/polyfill.ts"]` | Files matching a glob have side effects and count whole; the rest by symbol. A glob without `/` matches the file name anywhere in the package; one with `/` matches the path from the package folder (a leading `./` is dropped) |
| field absent, or `true` | Every file has side effects: imports count whole files. Assuming "free" would hide real drift |

`drift.scoring.packages["<name>"].sideEffects` overrides the field with the same values, for a package whose `package.json` you'd rather not edit or that sets it wrong:

```json
"drift": { "scoring": { "packages": {
  "@company/legacy": { "sideEffects": false },
  "@company/ui": { "sideEffects": ["**/*.css"] }
} } }
```

Without Node or the repo's `typescript` (a CI checkout with no install, say), imports are followed by file: every reached file counts whole, side-effects rules don't apply, and the capability's confidence is low. External packages (`node_modules`) are leaves: only their name and locked version are recorded, never their source.

## `.blueprint/closure/<capability>.json`

The import closure of a TS/JS capability (one whose anchored files include `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.cts`, `.mjs` or `.cjs`), written by `drift.py stamp` beside `baseline/` and committed with it, so `check` compares hashes and needs no PR base. `drift.py rename` moves it, and refuses when one already sits at the new name; `drift.py prune` drops what the narrowed anchors no longer reach and keeps the stamped hashes of the rest. Another capability's stamp never touches it. Never edit it by hand: a stamp rewrites it.

```json
{
  "mode": "symbol",
  "files": {
    "packages/core/src/token.ts": { "distance": 1, "via": ["@company/core"], "hash": "<content hash>", "whole": false },
    "packages/polyfills/src/fill.ts": { "distance": 1, "via": ["@company/polyfills"], "hash": "<content hash>", "whole": true }
  },
  "symbols": [
    { "file": "packages/core/src/token.ts", "symbol": "signToken", "distance": 1, "via": ["@company/core"], "hash": "<declaration hash>" }
  ],
  "external": ["zod"],
  "locked": { "zod": "3.22.0" }
}
```

- `mode` is `symbol` when the TypeScript helper (`drift_ts.mjs`, beside `drift.py`) resolved imports, `file` when it couldn't; then `why` says what was missing (`"typescript not installed"`, `"node not found"`), and the capability stays at low confidence until a stamp with the tooling present.
- `files` holds every reached file with its shortest `distance` in import edges, the workspace packages the path enters (`via`, each discounted by its weight), its content hash, and `whole` when an import depends on all of it (side effects, a bare import, or `file` mode). A file that isn't `whole` is compared by its `symbols`.
- `symbols` holds each reached top-level declaration with a hash of its text; a symbol's dependencies are its own entries, at their own distance.
- `external` lists the external packages the closure imports; `locked` their versions from the repo-root lockfile (`package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml` or `yarn.lock`), `null` when unlocked, `"a, b"` when the lockfile holds several. A closure without `locked` (stamped by an older `drift.py`) gives no lockfile signal.
