# Apply

Build an approved blueprint, then fold its spec delta into the capability specs, so the specs change in the same breath as the code.

## 1. Load

- **Pick the change**: the one named in the arguments; otherwise the only change in `blueprint.json` with status `approved` or `building`; otherwise list them and ask. A second argument names a PR group (step 2): build only that group.
- Fetch the brief; the review is not needed to build. Read the state of its tickets and tick any task whose ticket was closed by hand, so you resume where the team actually is. Check the review for comments or edits people left since it was built and put each to the user as a proposed change to the brief before building. If the brief has **Open questions**, settle them with the user first (same round format as [propose.md](propose.md)) and update the brief.
- Run `python3 .blueprint/drift.py check <capabilities it touches>` and compare each touched spec's version marker. If a touched capability has drifted, its MODIFIED blocks may rest on stale text: settle it first with `blueprint-drift` (its spec moved, or its code broke the spec) or `blueprint-sync` (its code moved on purpose), then recheck the delta.
- If `blueprint.json` has `targetRepo`, the repo doesn't exist yet: the first task creates it. Build that task, then move the pending `.blueprint/` folder into the new repo (copy `drift.py` from this skill's `scripts/` into it), drop `targetRepo`, and commit it with the task. From then on work in the new repo.
- If the session sits on the default branch, create a branch for the change. Set the brief's status to `building` and record the branch in `blueprint.json` and on the brief. With a PR plan, the branch is the group's (step 2) and is recorded on the brief alone.

## 2. Split into PRs

One PR per change works while the change is small. A big one makes a PR nobody reviews well and a session whose context grows with every task. Before building a brief that has no **PRs** section, judge its size from the Tasks and the Code map. Propose a split when it has more than about four build tasks, or touches several capabilities whose code doesn't overlap, or would change more than about 400 lines. Otherwise build it as one PR and skip to step 3.

**Group the tasks.** Each group becomes one branch, one PR, built in its own session, small enough to review in one sitting: usually 2 to 4 tasks, never part of a task. Then decide how each group relates to the others:

- **Stacked** on group N when its tasks build on code group N adds (a type, an endpoint, a migration). Its branch is cut from group N's branch, and its PR targets that branch.
- **Parallel** when it shares no code with the groups before it and needs nothing they add. Its branch is cut from the default branch.

Two groups that would edit the same files are stacked, never parallel, even when the order doesn't matter: parallel PRs that touch one file conflict. Prefer parallel where it is honest: it shortens the wait for review.

**Specs** is always the last group: the fold task, run after every other group has merged ([step 5](#5-fold-the-delta-into-the-specs)). Code PRs leave `.blueprint/` alone, except the first to start, which records `building`. Parallel sessions then never write the same spec page or `blueprint.json` entry.

Show the plan as a table and change it until the user approves:

| Group | Tasks | Base | Runs |
| --- | --- | --- | --- |
| 1. Session store | 1, 2 | `main` | first |
| 2. Login endpoint | 3, 4 | group 1 | stacked on 1 |
| 3. Admin UI | 5 | `main` | parallel with 1 |
| Specs | 6 | `main` | after 1–3 merge |

On a yes, write it into the brief as a **PRs** section after Tasks, one line per group (`- [ ] 1. Session store · tasks 1, 2 · base main · branch: · PR:`), and mark each task line with its group (`- [ ] 3. … (group 2)`). The plan is on the brief, so every session reads the same one.

**Hand off.** Start the groups that can start now: those based on the default branch, and those stacked on a group whose PR is already open. Each runs `/blueprint apply <change> <group>` in a fresh session with its own worktree. Where the host can start sessions (Claude Code's desktop app can), offer one per ready group, parallel ones together. Otherwise give the commands to paste. When a group's PR opens, offer to start the groups stacked on it. Building a group here is fine too: it keeps the context small all the same.

**Building one group** follows steps 3 and 4 for that group's tasks only, on its own branch: cut from the default branch, or from its base group's branch when stacked. Verify only the requirements its tasks satisfy. Open its PR (stacked: against the base group's branch), and fill its line on the brief with the branch and PR, ticking it when the PR merges. When a base group merges, rebase the groups stacked on it onto the default branch and retarget their PRs. The Specs group runs step 4 in full over the merged code, then step 5.

## 3. Build, one task at a time

For each unticked task, in order:

1. Build it, with tests where the repo has them. Use the repo's own conventions and any skills the user normally reaches for (TDD, for one).
2. Run the checks that cover it.
3. Close its ticket ([tickets.md](tickets.md)) with a note of what was built, and tick it in the brief. Refresh the review's Progress line when you stop, not after every task.

**When the plan meets reality**: if a task cannot be built as written, or building it shows the delta is wrong (a requirement is impossible, a scenario is missing, a decision doesn't hold), stop and tell the user what you found and what you propose. After a yes, amend the brief first (Decisions gets a line `**Changed during build**: …`, the delta is corrected), rebuild the review and any playground from it, then continue. The brief never trails the code silently.

Stop after a task when the session is getting long: tick what is done, and say which task is next so a fresh `/blueprint apply <change>` picks up there.

## 4. Verify against the delta

When every task but the last is ticked, check each requirement and scenario in the delta against the code:

| Requirement / scenario | Evidence | Status |
| --- | --- | --- |
| `<name>` | `<test name or file:line>` | covered / missing / contradicts |

Fix what is missing or contradicts (or amend the brief, with the user's yes, if the code is right and the delta is not). Also run `python3 .blueprint/drift.py unanchored --since <baseCommit>` (when the change has a `baseRepo`, `baseCommit` isn't in this repo and the whole repo is new: run it without `--since`) and propose anchors for any changed file that implements behavior but belongs to no capability.

## 5. Fold the delta into the specs

For each capability in the delta, produce the spec as it should read now: apply RENAMED, then REMOVED, then MODIFIED (replace the whole block matched by name), then ADDED, raising each block's heading one level as it moves from the brief into the spec. A new capability gets a fresh page from its ADDED requirements and Purpose. A mapped capability with `"ref": null` gets the spec drafted from its code during propose, with the delta applied on top, so the page describes all of its behavior, not only this change. Drop any `Not yet built → <this blueprint>` line that `blueprint-drift` left under a requirement.

Show each merged spec as a diff against the current page and write it after the user approves. Then, for each capability written, set `ref` for new pages and do the spec bookkeeping from [status.md](status.md). Commit the code before stamping, so `syncedCommit` holds it, then commit the `.blueprint/` changes on top; a later code edit to an anchored file reads as drift, which is correct.

Tick the last task, set the brief's status to `applied`, add the branch or PR link to it, and rebuild the review one last time so it shows the change as shipped.

## Done when

Every task is ticked, every delta requirement has evidence, the capability specs read as the system now behaves, and `drift.py check` is clean for the touched capabilities. Report: what was built, the specs that changed (linked), any amendments made during the build. The `.blueprint/` changes belong in the same PR as the code; with a PR plan, in the Specs group's PR, the last to merge.
