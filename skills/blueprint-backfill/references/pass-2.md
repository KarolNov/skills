# Pass 2: capabilities and anchors

Per domain, in that domain's session. Ends with every tracked file in the domain's folders anchored by a capability or marked glue, the user's confirmation that the domain is covered, and its overview page.

Run `backfill.py pass <domain> 2 in-progress`. The domain's progress file is `.blueprint/backfill/domains/<domain>.progress.json`; edit only that one.

## 1. List what exists

Every capability already in `blueprint.json` that belongs here (its name starts with `<domain>/`, or its anchors fall inside the domain's folders) goes into the progress file as found, unchanged:

```json
"<capability>": {"purpose": "<from its spec or the map>", "anchors": ["<as in blueprint.json>"],
                 "existing": true, "ref": "<its ref, or null>"}
```

Never edit an existing capability's anchors or name here: a wrong anchor is `/blueprint-sync`'s, a regrouping `/blueprint-tidy`'s. One with a `ref` is done; one with `"ref": null` gets its spec in pass 3.

## 2. Find capabilities, one at a time

Read the domain's code with a subagent when it is wide. Then put capabilities to the user one at a time, in the order a reader would meet them (the entry points first):

```
**auth/tokens**: Issue, refresh and revoke API tokens.
anchors: src/auth/tokens/**, src/routes/tokens.ts (7 files)
→ yes / rename / change anchors / not a capability
```

- A capability is a durable behavior boundary someone outside could observe and rely on, named in the repo's vocabulary from `progress.json`'s survey, as `<domain>/<name>` ([formats.md](../../blueprint/references/formats.md)): one level below the domain, never another domain's name or a name already in `blueprint.json`.
- Anchors are globs over tracked files, as in `blueprint.json`. Count the files they match with `git ls-files`, and list them when there are fewer than ten. Overlap with another capability is allowed where code really serves both; say so on the card.

On a yes, add it to the progress file (`{"purpose", "anchors"}`) and run `backfill.py uncovered <domain>` to show how many files are left. Then the next.

## 3. Check coverage

When the obvious capabilities are in, `backfill.py uncovered <domain>` lists every tracked file in the domain's folders that no capability anchors (here or in any other domain, or in `blueprint.json`) and no glue glob matches. For the files it names, propose one of:

- **anchors** on a capability already found, when the file is part of its behavior;
- **a new capability**, as in step 2, when they do something observable no capability covers;
- **glue**: code with no behavior of its own (shared helpers, wiring, types, build files, tests), added as a glob to the progress file's `"glue"`.

Group the files by folder so one answer settles many. Repeat until `uncovered` prints nothing, then ask the user to confirm the domain as covered: the capability table (name, purpose, anchors, existing or new) and the glue globs. On a yes, set `"covered": true`. Files missed now are added later through `/blueprint-sync`.

## 4. Write the overview

When the domain is not yet in `blueprint.json`'s `domains` and its progress file has no `ref`, create its overview page as the backend file's **Domains** section says, in the overview format ([formats.md](../../blueprint/references/formats.md), "Domain overview"): Purpose from `progress.json`, every capability in the Capabilities list (unlinked and marked "no spec yet" unless it has a `ref`), How they connect drafted from what step 2 read. Show it, create it on a yes, and set the progress file's `"ref"` to its URL. For a domain already in `blueprint.json`, add the new capabilities to its existing overview's list the same way, on the same yes.

Run `backfill.py pass <domain> 2 done` and commit.

## Done when

`backfill.py uncovered <domain>` prints nothing, the progress file has `"covered": true` and an overview `ref` (or the domain is already in `blueprint.json`), pass 2 is done, and it is committed. Report the capability table, the glue globs, and the overview link. Then carry on with pass 3 in this session when the user wants, or end with `/blueprint-backfill domain <domain>` as the next command.
