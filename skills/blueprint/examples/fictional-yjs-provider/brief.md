# Sync over WebTransport: brief

- Status: draft (sample: illustrative, not settled)
- Capabilities: sync/transport (new), sync/awareness (new), persistence/cross-tab (modified)
- Review: [review.html](review.html)
- Branch / PR: none yet

## Destination

Every open document syncs between devices over one connection per browser. Cursors never hold up edits, and when WebTransport is blocked the board still syncs over WebSocket. The local log stays the source of truth.

## Why

fictional-yjs-provider syncs tabs of one browser through the local log and a BroadcastChannel, but nothing leaves the device. Network sync is the next planned package. The usual alternative, y-websocket, opens a socket per document per tab and sends cursors on the same ordered stream as edits, so a lost cursor delays the edits queued behind it.

## Solution

- New package `@fictional-yjs-provider/sync`, optional like the others; it depends only on `yjs`.
- One WebTransport session per browser, held by one tab.
- One bidirectional stream per open document; awareness as datagrams.
- On (re)connect, each document exchanges state vectors and sends only the missing updates.
- If WebTransport is unavailable, or no session opens within 3 s, one WebSocket carries every document and awareness with the same framing.
- Server: a Durable Object per document, behind one Worker that accepts the session and routes streams.

## Decisions

- **One connection per browser**: the tab holding the Web Lock `fictional-yjs-provider:<origin>` owns the session. Other tabs need no connection: `LocalPersistence` already writes and broadcasts every update whose origin is not the persistence itself, so an update the connected tab applies from the server reaches the other tabs through the existing channel.
- **Outgoing updates in the connected tab**: send every update whose origin is not the sync provider. That covers local edits and edits arriving from other tabs (origin: the persistence), and excludes updates that came from the server.
- **A stream per document**: a lost packet on one document's stream never stalls another document.
- **Awareness as datagrams**: awareness is latest-wins, so a lost update needs no retransmit. Rejected: awareness on the document stream, as y-websocket does, because a lost cursor then delays the edits behind it.
- **State vectors on (re)connect**: per document, sync step 1 / step 2 as in y-protocols, so catch-up is a diff.
- **WebSocket fallback**: a single socket, multiplexed with a document id prefix per frame, after 3 s without a session.

## Assumed

- The fallback is remembered for the page's lifetime, so a blocked network pays the 3 s once.
- Backoff after a lost connection: 1, 2, 4 … 30 s with jitter.
- Awareness is resent every 2 s without movement, so a lost last datagram never leaves a stale cursor.
- Leadership moves when the leading tab closes: the next tab to get the Web Lock opens the session.

## Out of scope

- Server-side storage format and compaction for the Durable Object (a separate storage package).
- Authentication and per-document permissions.
- Presence UI in the demo beyond showing cursors.

## Code map

- `packages/persistence/src/persistence/persistence.ts`: `LocalPersistence`; live tab sync over `BroadcastChannelLike`, `onEvent` for status. Read only: the forwarding decision relies on its origin handling, nothing here changes.
- `packages/persistence/src/index.ts`: package exports; the new package mirrors this layout.
- `packages/sync/` (new): provider, framing, transport selection, tests.
- `demo/src/session.ts`: builds the doc, persistence and status for the board; the provider is created here.
- `demo/src/status.ts`: status panel; gains a connection section (transport, streams, last sync).
- `demo/src/__tests__/two-tabs.test.ts`: two-tab browser test; the two-browser sync test sits beside it.

## Spec delta

### sync/transport · ADDED

**Purpose**: moves document updates between devices over as few connections as the browser allows, and keeps working when WebTransport is blocked.

#### Requirement: One connection per browser
The provider SHALL carry every open document of an origin over one connection, held by one tab at a time.

- **Scenario: Two tabs, three documents**
  - **WHEN** two tabs of one browser open three documents
  - **THEN** the server sees one session carrying three document streams

- **Scenario: The connected tab closes**
  - **GIVEN** two tabs with the session held by the first
  - **WHEN** the first tab closes
  - **THEN** the second tab opens a session and its documents keep syncing

#### Requirement: Catch-up sends only what is missing
On every (re)connect, the provider SHALL exchange state vectors per document and send only the updates the other side lacks.

- **Scenario: Reconnect after offline edits**
  - **GIVEN** a device that edited a document offline while another device also edited it
  - **WHEN** the device reconnects
  - **THEN** both devices hold every edit, and neither sent its full document state

#### Requirement: WebSocket fallback
When WebTransport is unavailable or no session opens within 3 seconds, the provider SHALL connect over a single WebSocket that carries every document and awareness.

- **Scenario: HTTP/3 blocked**
  - **GIVEN** a network that drops UDP
  - **WHEN** the provider connects
  - **THEN** documents sync over WebSocket within 3 seconds plus one WebSocket handshake

### sync/awareness · ADDED

**Purpose**: shares cursors and presence between devices without ever delaying document updates.

#### Requirement: Cursors never delay edits
Over WebTransport, awareness updates SHALL be sent as datagrams, and a lost awareness update SHALL NOT delay any document update.

- **Scenario: Lossy link**
  - **GIVEN** 10% packet loss
  - **WHEN** an awareness update is lost
  - **THEN** the next one replaces it, and document updates arrive no later than with awareness switched off

#### Requirement: Stale cursors expire
Each client SHALL resend its awareness state at least every 2 seconds, and other clients SHALL drop a cursor not refreshed for 30 seconds.

- **Scenario: Last datagram lost**
  - **WHEN** a user's final cursor move is lost and the user stops moving
  - **THEN** other devices show the correct position within 2 seconds

### persistence/cross-tab · MODIFIED

#### Requirement: Live sync between tabs
Tabs that open the same document SHALL converge without a reload, including updates that any tab applies from a source other than the persistence, such as a network provider.

- **Scenario: Remote edit reaches a second tab**
  - **GIVEN** two tabs with the document open and only the first connected to the server
  - **WHEN** another device edits the document
  - **THEN** both tabs show the edit

## Tasks

- [ ] 1. One document, one tab, WebTransport only: a Worker and Durable Object that relay updates between two browsers, with a test.
- [ ] 2. State-vector catch-up on connect, sending missing updates in both directions.
- [ ] 3. Several documents on one session, a stream each.
- [ ] 4. Awareness as datagrams, with the 2 s resend and 30 s expiry.
- [ ] 5. WebSocket fallback with the same framing, and the 3 s switch.
- [ ] 6. One connected tab per browser via Web Locks, with hand-over when it closes.
- [ ] 7. Demo: connection section in the status panel, and a two-browser test.
- [ ] 8. Update specs: fold this delta into the capability specs.

## Open questions

- Should the fallback decision be stored across page loads (for example in `localStorage`), so a blocked network never pays the 3 s again? Recommendation: no for v0.1; networks change between loads.
