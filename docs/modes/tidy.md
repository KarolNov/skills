# Tidy

```
/blueprint-tidy [--dry-run]
```

Tidy restructures a repo's blueprint setup when you ask it to. It changes how things are organized, never what the specs say.

## What it does

1. **Migrates** `.blueprint/` and the backend's structure to the current format version, when the repo is on an older one. Every other mode only notices this and points here. See [Upgrading](/upgrading).
2. **Groups capabilities into domains.** It proposes domains from the capability names and code layout. Each domain gets an overview page that holds its capabilities like a folder.
3. **Fixes names** that are both a domain and a capability.
4. **Reports overlapping anchors**, where two capabilities claim the same files through broad globs.

Everything goes into one **move table** for you to approve. Renames keep each page and its history, so nothing shows up as drift. `--dry-run` shows the table and writes nothing.
