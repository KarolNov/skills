# Pass 4: test tags

Per folded domain, in that domain's session. Ends with every existing test that clearly checks one of the domain's scenarios tagged with `@scenario`, and the scenarios no test claims named. It runs coverage's `suggest` ([../../blueprint/references/coverage.md](../../blueprint/references/coverage.md)) over the domain's capabilities: the tag syntax, the rules for proposing a tag and the diff it shows are that file's, not repeated here.

Run `backfill.py pass <domain> 4 in-progress`. It refuses a domain that isn't folded: `coverage.py` reads capabilities from `blueprint.json`, so fold comes first (`/blueprint-backfill fold <domain>`).

## 1. Kinds

`coverage.py` needs `tests.kinds` in `blueprint.json`. When it is missing, settle it as coverage's step 1 says. That writes `blueprint.json`, so commit it on the default branch before any other domain's pass 4 starts, and in a domain session on its own branch, ask the user to merge that first. Every later domain finds it there.

## 2. Report

`coverage.py` is the `blueprint` skill's script, like `backfill.py`: `python3 <skills>/blueprint/scripts/coverage.py`, never a copy in the repo. Run `coverage.py <capability>` for each capability in the domain's progress file (the coverage report command in coverage.md, step 2), and show the domain's summary in a few lines: scenarios claimed of total per capability, and the problems coverage names. Fix orphan or unclassified tags only on the user's yes, as coverage says.

## 3. Suggest, one capability per round

For each capability with uncovered scenarios, largest first, run coverage's step 4 for it: read its scenarios from its baseline and the untagged tests likely to exercise it, propose the tags as one diff, and write on the user's yes, adding comment lines only. Skip a test you would have to stretch to tie to a scenario.

After each capability is written, add the number of tags written to the capability's `"tags"` in the domain's progress file (0 when the user declined them all; set 0 on a capability with nothing uncovered when the report shows it), and commit the test files with the progress file: `blueprint-backfill: <domain> pass 4: tag <capability>`. A resumed session takes the next capability that has no `"tags"` key yet.

## 4. Close

Rerun `coverage.py` for the domain's capabilities and show the new summary. Scenarios still unclaimed need tests: list them per capability as the user's work to plan (often a blueprint), never written here.

Run `backfill.py pass <domain> 4 done` and commit.

## Done when

Every capability in the domain has a `"tags"` count in the progress file, pass 4 is done, and the tags and progress file are committed. Report the tags added per capability, the scenarios claimed before and after, and the scenarios still unclaimed. Pass 5 writes `blueprint.json`, so it runs on the default branch: when this session is on it, carry on with pass 5 here if the user wants. On a domain branch, end by asking the user to merge this branch, then run `/blueprint-backfill domain <domain>` on the default branch.
