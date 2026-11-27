# Sync

```
/blueprint-sync [capability ...] [--deep]
```

The **code is right**, and the spec should describe it. Sync reads what the code changed since the spec last matched it and updates the spec. It changes specs, never code. It is the mirror image of [Drift](/modes/drift).

## What it does

1. Shows the status of every capability whose code moved. A capability whose *spec* also moved waits, because someone edited the intent and syncing would overwrite it. Run [Drift](/modes/drift) on it first.
2. Reads the diff since the last sync and sorts each change into **behavior** (something a caller or user can observe) or **internal** (a refactor, a rename). Internal changes never touch the spec.
3. Behavior changes that look intended become spec edits. One that contradicts a requirement with nothing saying it was meant to is flagged as suspect, and you decide which side is right.
4. Shows the result as a delta (added, modified, removed requirements), with the code behind each line, and writes it on your yes.

For a capability that has no spec yet, sync drafts the whole spec from its code, including behavior that looks accidental. Each such part is marked for you to decide on.

## Artifacts

An **artifact** is something outside the repo that describes a capability: a help-center article, a docs page, a Notion guide. It is recorded in `blueprint.json` with the capabilities it covers. When their code changes, the artifact turns *stale*. After syncing, blueprint asks about each stale one: **updated**, **still fine** or **not yet**. The first two mark it as checked.

This site is one too: it's registered as the `blueprint-docs` artifact, so a pull request that changes blueprint's behavior gets a reminder that the docs may need an update.
