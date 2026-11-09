---
name: blueprint-sync
description: Spec sync. Judge the capability specs against the live code and update the specs where they no longer describe what the code does, or write a spec from the code for a capability that has none. The code is right; the spec moves.
disable-model-invocation: true
argument-hint: "[capability ...] [--deep]"
---

# Spec sync

Arguments: `$ARGUMENTS`: capability names (default: every capability whose code moved), and `--deep` to compare whole specs with the code even where nothing looks moved.

The **code is right**; the question is whether the spec still describes it. You change the spec here, never the code. If a code change looks like a mistake, that row belongs to `blueprint-drift`: say so and leave it.

Shared material lives in the `blueprint` skill next to this one: `../blueprint/references/`. If `.blueprint/blueprint.json` is missing, the repo isn't set up yet: say so in one line, then read [../blueprint-setup/SKILL.md](../blueprint-setup/SKILL.md) and follow it here before continuing.

## 1. Status

Compute the status table as [status.md](../blueprint/references/status.md) says and show it. Nothing moved and no `--deep`: say so and stop.

A capability whose **spec moved** waits: someone edited intent, and syncing would overwrite it. Leave it out, and name it as one for `blueprint-drift` first. Named `no-spec` capabilities are written from scratch in step 3.

## 2. Read what the code changed

For each `code-moved` capability:

1. Read `git diff <syncedCommit> -- <the changed files from drift.py check>` and the current code around each hunk. Check whether an applied blueprint explains the change; its delta is then the starting point.
2. Sort each change into **behavior** (something a caller, user or other system can observe: inputs, outputs, errors, states, limits, timing they rely on) or **internal** (refactors, renames, performance with no contract change). Internal changes never touch the spec.
3. For each behavior change, find the requirement it touches:
   - **Intended**: a commit message, PR or blueprint says so, or it extends behavior without contradicting the spec. Draft the spec edit.
   - **Suspect**: it contradicts a requirement and nothing says that was meant. Ask the user whether the code is right. If not, hand the requirement to `blueprint-drift` and leave it.

With `--deep`, also compare the whole spec with the code: requirements that describe behavior the code no longer has, and observable behavior in the anchored code that no requirement mentions. Run `drift.py unanchored` and propose anchors for changed files that implement behavior but belong to no capability.

## 3. Update the specs

For each capability, show the result as a delta (ADDED / MODIFIED / REMOVED, [formats.md](../blueprint/references/formats.md)) with one line per item naming the code that motivates it. Write it after the user's yes, then do the spec bookkeeping from [status.md](../blueprint/references/status.md).

For a capability with no spec yet, draft the whole spec from its anchored code: what the code does today, including behavior that looks accidental, marked `<!-- verify: … -->` for the user to decide. Create the page as the backend file says, set `ref`, and do the bookkeeping.

## Done when

Every capability in scope is `in-sync` in `drift.py check` with its `specVersion` and baseline matching the page, apart from those handed to `blueprint-drift`. Report one line per capability: what changed in the code, what changed in the spec (linked), and which capabilities to run `blueprint-drift` on.
