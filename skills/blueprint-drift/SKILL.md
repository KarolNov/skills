---
name: blueprint-drift
description: Intent drift. Judge the code against its capability specs and fix the code where it no longer does what the spec says, including spec edits people made outside the code. The spec is right; the code moves.
disable-model-invocation: true
argument-hint: "[capability ...] [--deep]"
---

# Intent drift

Arguments: `$ARGUMENTS`: capability names (default: every capability whose spec or code moved), and `--deep` to check every requirement of every capability in scope even where nothing looks moved.

The **spec is the intent** and is right; the question is whether the code still honors it. You change code here, never a requirement. If the user decides the code is right after all, that capability belongs to `blueprint-sync` instead: say so and leave it.

Shared material lives in the `blueprint` skill next to this one: `../blueprint/references/`. If `.blueprint/blueprint.json` is missing, run `blueprint-setup` first.

## 1. Status

Compute the status table as [status.md](../blueprint/references/status.md) says and show it. Nothing moved and no `--deep`: say so and stop. Skip `no-spec` capabilities: with no spec there is no intent to drift from.

## 2. Judge the code against the spec

For each capability in scope, check every requirement and scenario of the **current** spec against the code (tests first, then the implementation), not just the ones that changed. Where the spec moved, list its changed requirements first, from the baseline diff:

| Requirement / scenario | Evidence | Verdict |
| --- | --- | --- |
| `<name>` | `<test or file:line>` | holds / broken / not built / unclear |

- **holds**: the code does what the requirement says, and a test or a clear code path shows it.
- **broken**: the code does something else. Quote both: what the spec says, what the code does, and since when (`git log` on the lines).
- **not built**: nothing implements it yet, typically a requirement someone added to the spec.
- **unclear**: the requirement can't be checked as written. Quote it and propose a sharper wording; the user decides, and the spec edit is theirs to approve.

## 3. Bring the code back to the intent

Go through the broken and not-built rows with the user, one decision per row:

- **Small** (a few edits in one place): fix it now, with a test that pins the requirement, after the user's yes.
- **Larger**: turn it into a blueprint (`/blueprint`), with these requirements as its delta; propose then skips grilling on anything the spec already states. Or, if the change is already clear, open tickets for it ([tickets.md](../blueprint/references/tickets.md)).
- **The code is right after all**: the user overrules the spec. Leave the row for `blueprint-sync`.

Where work went into a blueprint or tickets instead of being done now, add a line under the requirement in the spec, `Not yet built → <blueprint or ticket link>`, with the user's yes. Apply removes it when it folds that blueprint in.

## 4. Record

For each capability whose code now satisfies its spec (or whose remaining gaps are all marked `Not yet built`), do the spec bookkeeping from [status.md](../blueprint/references/status.md). Leave capabilities the user handed to sync unrecorded.

## Done when

Every requirement in scope is holds, fixed, marked not yet built with a link, or handed to sync. Report one line per capability: what was broken, what was fixed (with tests), what became a blueprint or tickets, and which capabilities to run `blueprint-sync` on next.
