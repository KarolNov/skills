# How to merge offline edits in the CRDT playground

See a CRDT keep two people's edits made while one of them was offline. **Before you start:** open
[Before you build a sync engine](https://karolnov.dev/blog/before-you-build-a-sync-engine/) and scroll to
the **A sequence CRDT** playground.

1. Untick **online** next to **Bob**.
2. Click at the end of Alice's text and type ** world**.
3. Click at the start of Bob's text and type **Oh, **. His edit shows as **waiting** while he's offline.
4. Tick **online** next to Bob again, and wait for the status to read **In sync ✓**.

**Result:** Alice, Bob and the server all show **Oh, Hello world**. Neither edit was lost.
