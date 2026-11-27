# Upgrading

## Updating the plugin

Refresh the marketplace, then update each plugin you installed from it:

```bash
claude plugin marketplace update karolnov-skills
claude plugin update blueprint@karolnov-skills
claude plugin update blueprint-ui@karolnov-skills
```

Restart Claude Code afterwards so the new versions load.

If you installed the skills by copying them, pull the repo and copy them again. Copy the whole `blueprint*` family together, because the skills link to each other's references.

## Format versions

The shape of `.blueprint/` and of the backend's structure has a **format version**, stored as `version` in `blueprint.json`. When the skills move to a newer format, repos set up before it keep working. Each blueprint mode says in one line that the repo is on an older format, and then carries on.

To migrate, run [`/blueprint-tidy`](/modes/tidy) once per repo. It applies every newer format entry in order and shows what each one will write before writing it. A migration never renames a capability or changes anchors, so nothing shows up as drift.

### Format 2: domains (0.6.0)

Capabilities can be grouped into domains, each with an overview page. The migration:

- adds `version` and `domains` to `blueprint.json`,
- refreshes `.blueprint/drift.py`,
- updates the backend's structure: in Notion, a `Kind` property and sub-items on the Specs database; in Obsidian, specs move from `domain__capability.md` into domain folders.

After migrating, tidy offers to group the capabilities into domains, and you can decline.

The full ledger of format changes is in [`upgrades.md`](https://github.com/KarolNov/skills/blob/main/skills/blueprint/references/upgrades.md).
