# Apply

Build an approved blueprint, then fold its spec delta into the capability specs, so the specs change in the same breath as the code.

## 1. Load

- **Pick the change**: the one named in the arguments; otherwise the only change in `blueprint.json` with status `approved` or `building`; otherwise list them and ask.
- Fetch the brief; the review is not needed to build. Read the state of its tickets and tick any task whose ticket was closed by hand, so you resume where the team actually is. Check the review for comments or edits people left since it was built and put each to the user as a proposed change to the brief before building. If the brief has **Open questions**, settle them with the user first (same round format as [propose.md](propose.md)) and update the brief.
- Run `python3 .blueprint/drift.py check <capabilities it touches>` and compare each touched spec's version marker. If a touched capability has drifted, its MODIFIED blocks may rest on stale text: settle it first with `blueprint-drift` (its spec moved, or its code broke the spec) or `blueprint-sync` (its code moved on purpose), then recheck the delta.
- If the session sits on the default branch, create a branch for the change. Set the brief's status to `building` and record the branch in `blueprint.json` and on the brief.

## 2. Build, one task at a time

For each unticked task, in order:

1. Build it, with tests where the repo has them. Use the repo's own conventions and any skills the user normally reaches for (TDD, for one).
2. Run the checks that cover it.
3. Close its ticket ([tickets.md](tickets.md)) with a note of what was built, and tick it in the brief. Refresh the review's Progress line when you stop, not after every task.

**When the plan meets reality**: if a task cannot be built as written, or building it shows the delta is wrong (a requirement is impossible, a scenario is missing, a decision doesn't hold), stop and tell the user what you found and what you propose. After a yes, amend the brief first (Decisions gets a line `**Changed during build**: …`, the delta is corrected), rebuild the review and any playground from it, then continue. The brief never trails the code silently.

Stop after a task when the session is getting long: tick what is done, and say which task is next so a fresh `/blueprint apply <change>` picks up there.

## 3. Verify against the delta

When every task but the last is ticked, check each requirement and scenario in the delta against the code:

| Requirement / scenario | Evidence | Status |
| --- | --- | --- |
| `<name>` | `<test name or file:line>` | covered / missing / contradicts |

Fix what is missing or contradicts (or amend the brief, with the user's yes, if the code is right and the delta is not). Also run `python3 .blueprint/drift.py unanchored --since <baseCommit>` and propose anchors for any changed file that implements behavior but belongs to no capability.

## 4. Fold the delta into the specs

For each capability in the delta, produce the spec as it should read now: apply RENAMED, then REMOVED, then MODIFIED (replace the whole block matched by name), then ADDED, raising each block's heading one level as it moves from the brief into the spec. A new capability gets a fresh page from its ADDED requirements and Purpose. Drop any `Not yet built → <this blueprint>` line that sync left under a requirement.

Show each merged spec as a diff against the current page and write it after the user approves. Then, for each capability written, set `ref` for new pages and do the spec bookkeeping from [status.md](status.md). Stamp after the code is final; a later code edit to an anchored file reads as drift, which is correct.

Tick the last task, set the brief's status to `applied`, add the branch or PR link to it, and rebuild the review one last time so it shows the change as shipped.

## Done when

Every task is ticked, every delta requirement has evidence, the capability specs read as the system now behaves, and `drift.py check` is clean for the touched capabilities. Report: what was built, the specs that changed (linked), any amendments made during the build. The `.blueprint/` changes belong in the same commit or PR as the code.
