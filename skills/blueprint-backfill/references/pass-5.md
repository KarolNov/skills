# Pass 5: artifacts

Per folded domain, after its pass 4. Ends with the outside resources the user names for the domain recorded as artifacts in `blueprint.json`, so whoever changes the domain's code is told to check them. Artifacts are asked for, never searched for: don't look through the backend, the web or other repos for candidates.

Run `backfill.py pass <domain> 5 in-progress`.

`drift.py artifacts add` writes `blueprint.json`, which separate domain branches would each edit in the same `artifacts` object. Run this pass on the default branch (it is short), or on a branch merged before the next domain's pass 5 starts.

## 1. Ask once

List the artifacts `blueprint.json` already has that cover the domain or one of its capabilities (`capabilities` naming either), so none is added twice. Then ask one question for the domain:

> Which resources outside this repo describe **<domain>** (<purpose>)? For example a docs page, a support article, a README in another repo, a Notion or Confluence page. Name as many as you like, or none.

## 2. Record what the user names

For each resource named, propose the entry in the shape of formats.md's **artifacts** key ([../../blueprint/references/formats.md](../../blueprint/references/formats.md)): a kebab-case id, its type and value, a one-line description, and what it covers: the domain when it describes the domain as a whole (a domain stands for every capability in it, including ones added later), otherwise the capabilities it describes. Show them as one table; on the user's yes, add each:

```bash
python3 .blueprint/drift.py artifacts add --id <id> --type <type> --value <value> --description "<text>" <domain or capabilities>
```

It refuses a value of the wrong shape for its type, an id that is taken, or an unknown name: fix the entry with the user and add it again. Append each added id to the domain progress file's `"artifacts"` list.

Only what the user named is added. "None" is a fine answer: the list stays empty.

## 3. Close

Run `backfill.py pass <domain> 5 done`, and commit `blueprint.json` with the domain's progress file: `blueprint-backfill: <domain> pass 5: artifacts`.

## Done when

The artifacts the user named are in `blueprint.json` and in the progress file's `"artifacts"`, pass 5 is done, and it is committed. Report the artifacts added (id, type, value, what they cover). When `backfill.py status` now names `/blueprint-backfill` to finish the backfill, carry on with [finish.md](finish.md) where every domain's work is merged; otherwise end with the next commands from `backfill.py status`.
