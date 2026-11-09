# How to merge offline edits in the CRDT playground
Audience: readers of "Before you build a sync engine" | Start: top of the post | Result: both peers show "Oh, Hello world" and the status reads "In sync ✓" | App: none @ https://karolnov.dev

1. Intro (≤6s): scroll to the "A sequence CRDT" playground.
2. Step 1 · Take Bob offline: untick **online** next to Bob.
3. Step 2 · Edit as Alice: type " world" at the end of Alice's text.
4. Step 3 · Edit as Bob: type "Oh, " at the start of Bob's text.
5. Step 4 · Reconnect Bob: tick **online** again → wait for **In sync ✓**.
6. Result (≤5s): both edits survive in every copy.

Read-only: the playground lives in the page, so every run starts from "Hello".
