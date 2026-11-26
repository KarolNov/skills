# Pass 1: survey and domains

Runs once, in this session. Ends with `.blueprint/backfill/` written and committed, and one command per domain for the sessions that follow.

## 1. Set up, if the repo isn't

When `.blueprint/blueprint.json` is missing, read [../../blueprint-setup/SKILL.md](../../blueprint-setup/SKILL.md) and run its steps 1 to 3 (survey, docs/tickets/project, structure) and 6 (write `.blueprint/` with `domains: {}` and no specs), in the same round as this pass's questions where they overlap. Skip its step 4 (capability map) and step 5 (seeding): pass 2 and pass 3 do those, domain by domain. Its step 7 (drift guard) can wait for the end of the backfill.

## 2. Survey

With a subagent, map the repo as setup's step 4 does: entry points, top-level modules, public APIs, routes, jobs, existing spec material (OpenSpec, docs, ADRs). Add what the domain split needs:

- `git ls-files` counted by top-level folder (and one level below in a monorepo's packages), so every tracked folder is accounted for.
- Folders that hold no product behavior: vendored or generated code, fixtures, build and CI config, docs.
- What `blueprint.json` already has: its `domains` with their folders, and its `specs`, each with or without a `ref`.

## 3. Interview

One round, each question with your recommendation from the survey (format as in [../../blueprint/references/propose.md](../../blueprint/references/propose.md) step 2):

1. **Scope**: the folders to backfill, and those left out (the no-behavior folders above, plus anything the user names: a legacy area being deleted, an experiment).
2. **Vocabulary**: the words the team uses for the parts of the system, so domains and capabilities are named in them.
3. **Order**: which domain matters most, so its session goes first.

## 4. Propose domains

A table of domains, each with a name, a one-line purpose and its folders as globs (`src/auth/**`, `packages/billing/**`), plus one line for the excluded folders. Rules:

- Names follow [formats.md](../../blueprint/references/formats.md): one level deep, in the repo's vocabulary, and never a capability's name. A bare capability in `blueprint.json` whose name the user wants as a domain is `/blueprint-tidy`'s to rename first: say so and pick another name meanwhile.
- Domains already in `blueprint.json` are kept by name and purpose; propose only their folders.
- Every in-scope tracked file falls under exactly one domain's folders. Overlapping folders make a file count against two domains in pass 2's coverage check: split them.
- A domain that would hold one capability is usually part of another domain. Several dozen capabilities in one domain is usually two.

The user edits the table; iterate until they accept it.

## 5. Write the folder

Pipe the accepted plan to `backfill.py init`:

```json
{"survey": {"summary": "<three lines from step 2>", "excluded": ["<glob>", "..."],
            "vocabulary": {"<term>": "<meaning>"}, "order": ["<domain>", "..."]},
 "domains": {"<name>": {"purpose": "<one line>", "folders": ["<glob>", "..."]}}}
```

It refuses a domain that is a capability or nested, and an existing backfill; fix the plan with the user and run it again. It writes `progress.json`, `domains/`, `drafts/` and the `README.md`, marks pass 1 done, and prints one `/blueprint-backfill domain <name>` command per domain.

Commit `.blueprint/backfill/` (with the new `.blueprint/` files, when step 1 ran setup), so every domain session, in any worktree, starts from it.

## Done when

`backfill.py status` reads `pass 2 of 5 · 0 of <n> domains mapped`, and the commit holds the folder. Report the domains table, then the commands from `init` in the order from the interview, one session each: they can run in parallel, each on its own branch. Where the host can start sessions, offer one per domain; otherwise give the commands to paste.
