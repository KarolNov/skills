# Finish

Ends the backfill: reports what it wrote and deletes `.blueprint/backfill/`. Run it where every domain session's work is merged, as fold is: the default branch, or a branch cut from it after their branches merged.

1. Run `backfill.py status`. When its `next:` list names anything other than `/blueprint-backfill` to finish the backfill, show the list and stop: a domain still has a pass to run or a fold to wait for.
2. Run `python3 .blueprint/drift.py check` over the whole repo and show anything not `in-sync` or `possibly-affected` with its fix (`/blueprint-sync <capability>`, as in fold's step 4). The backfill is done either way; this is the state it hands over.
3. Run `backfill.py finish`. It prints the report (per domain and in total: capabilities and how many are new, scenarios accepted, amended and rejected, tags added and artifacts recorded) and deletes the folder; git history keeps it. It exits 1 and says what's left when a domain isn't folded, has a pass not done or drafts left (back to step 1), or when files in the folder aren't committed (commit them and run it again).
4. Commit the deletion: `blueprint-backfill: finish`.
5. When the repo has no drift guard yet (pass 1 left setup's step 7 for now), offer it as setup's step 7 says ([../../blueprint-setup/SKILL.md](../../blueprint-setup/SKILL.md)); install nothing without a yes.

## Done when

`.blueprint/backfill/` is gone and the deletion is committed. Report what `finish` printed, the drift check's state, and the drift guard if one was added. Then suggest `/blueprint map` to see the capabilities, and `/blueprint <the change you have in mind>`.
