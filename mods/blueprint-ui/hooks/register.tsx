import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BlueprintUiBackfillDomain, BlueprintUiBlock, BlueprintUiDoc, BlueprintUiGroup, BlueprintUiItem, BlueprintUiPage, BlueprintUiSplit } from '../types'
import { BACKFILL_SPEC, BACKFILL_TOOL, NO_BACKFILL, cardOf, checkBackfill, counted as countedIn, countsOf, decide, decidedPrompt, domainPath, draftPath, inRoot, orderOf, parseDraft, reviewOf } from './backfill'
import type { Card, Decision, Draft } from './backfill'
import { blocksOf } from './blocks'
import { ago, backfillStep, boardOf, columnsFor, rowsOf, syncAll } from './board'
import type { CapRow, ChangeRow, Side, Step } from './board'
import { NO_CODE, NO_SPECS, NO_STEPS, checkCode, checkSpecs, isCheckingSpecs, recheckCode, recheckSpec, runStep, stepKey, wasStopped } from './checks'
import { candidates, fetchPage, fetchSvgs } from './notion'
import { BLUEPRINT_JSON, READ_TOOL, labelOf, pageFor, pagesNamed, pagesOf, parentOf, targetsOf } from './pages'
import { countOf, firstChange, itemFor, oneLine, quoteOf, rowsFor, sameText } from './review'
import type { Map } from './pages'
import { SPLIT_SPEC, SPLIT_TOOL, isReady, splitOf, startPrompt, stateOf, treeOf } from './split'
import { TABS, accentOf } from './tabs'
import type { Mode, TabsProps } from './tabs'

export const PANE = 'blueprint-ui'
const TITLE = 'Blueprint'

const view = atom({ plugin: 'blueprint-ui', key: 'view' } as const, { page: null }, { shape: 'view-1' })
const NO_DOC: BlueprintUiDoc = { page: null, status: 'none' }
const doc = atom({ plugin: 'blueprint-ui', key: 'doc' } as const, NO_DOC, { shape: 'doc-1' })
const NO_ITEMS: BlueprintUiItem[] = []
const pending = atom({ plugin: 'blueprint-ui', key: 'pending' } as const, NO_ITEMS, { shape: 'pending-1' })
// The checks' state, written by checks.ts; the engine's scan wants each file's own atoms, so they are named here too.
const code = atom({ plugin: 'blueprint-ui', key: 'code' } as const, NO_CODE, { shape: 'code-1' })
const specs = atom({ plugin: 'blueprint-ui', key: 'specs' } as const, NO_SPECS, { shape: 'specs-1' })
const rev = atom({ plugin: 'blueprint-ui', key: 'rev' } as const, 0, { shape: 'rev-1' })
const queued = atom({ plugin: 'blueprint-ui', key: 'queued' } as const, NO_STEPS, { shape: 'queued-1' })
/** Whether the main loop is mid-turn: a ▶ step then waits for it, and the board says so. */
const working = atom({ plugin: 'blueprint-ui', key: 'working' } as const, false, { shape: 'working-1' })
const NO_SPLITS: Record<string, BlueprintUiSplit> = {}
const splits = atom({ plugin: 'blueprint-ui', key: 'splits' } as const, NO_SPLITS, { shape: 'splits-1' })
// Written by backfill.ts with the code side.
const backfill = atom({ plugin: 'blueprint-ui', key: 'backfill' } as const, NO_BACKFILL, { shape: 'backfill-1' })

/** The split tool as the model calls it. */
const SPLIT_CALL = `mcp__blueprint-ui__${SPLIT_TOOL}`
/** The backfill tool as the model calls it. */
const BACKFILL_CALL = `mcp__blueprint-ui__${BACKFILL_TOOL}`

/** What each field of the card being amended holds, by its key. */
const amendDrafts = new Map<string, string>()
/** Cards whose decision is being saved: a second press waits for the first. */
const deciding = new Set<string>()

/** A domain's drafts awaiting review, in review order, and its first undecided card. */
type DomainCards = {
  domain: string
  order: string[]
  progress?: string
  drafts: Record<string, Draft | undefined>
  /** The capability whose card is next, and the card. */
  card?: Card
  /** Undecided scenarios by capability, and in the domain. */
  leftIn: Record<string, number>
  left: number
}

/** Reads a domain's progress file and drafts: what the Backfill view shows, read on each draw. */
async function cardsOf($: EngineInterface, root: string, d: BlueprintUiBackfillDomain): Promise<DomainCards> {
  const progress = await $.fs.read(inRoot(root, domainPath(d.name))).catch(() => undefined)
  const order = orderOf(progress, d.drafts)
  const drafts: Record<string, Draft | undefined> = {}
  const leftIn: Record<string, number> = {}
  let card: Card | undefined
  for (const cap of order) {
    const text = await $.fs.read(inRoot(root, draftPath(cap))).catch(() => undefined)
    const draft = text === undefined ? undefined : parseDraft(text)
    drafts[cap] = draft
    leftIn[cap] = draft ? countsOf(draft).undecided : 0
    if (!card && draft) card = cardOf(cap, draft)
  }
  const left = Object.values(leftIn).reduce((a, b) => a + b, 0)
  return { domain: d.name, order, drafts, leftIn, left, ...(progress !== undefined ? { progress } : {}), ...(card ? { card } : {}) }
}

/**
 * Saves one card's decision as pass 3 does: the draft first, then the count in the domain's progress
 * file, re-read just before it is written; when the count can't be written, the draft goes back as it was.
 * Once the capability has no undecided scenario, Claude is asked
 * to write its spec.
 */
async function decideCard($: EngineInterface, root: string, d: BlueprintUiBackfillDomain, card: Card, decision: Decision): Promise<void> {
  const key = `${card.capability}\n${card.name}`
  if (deciding.has(key)) return
  deciding.add(key)
  try {
    const draftFile = inRoot(root, draftPath(card.capability))
    const progressFile = inRoot(root, domainPath(d.name))
    let text: string
    let progress: string
    try {
      ;[text, progress] = await Promise.all([$.fs.read(draftFile), $.fs.read(progressFile)])
    } catch (err) {
      await $.ui.toast(`Not saved: couldn't read ${draftPath(card.capability)} or ${domainPath(d.name)} (${String(err)}).`)
      return
    }
    const got = decide(text, card.capability, card.name, decision)
    if ('error' in got) {
      await $.ui.toast(`Not saved: ${got.error}`)
      return
    }
    let counted: string
    try {
      counted = countedIn(progress, card.capability, decision.kind)
    } catch (err) {
      await $.ui.toast(`Not saved: ${domainPath(d.name)} can't take the count (${String(err)}).`)
      return
    }
    try {
      await $.fs.write(draftFile, got.text)
    } catch (err) {
      await $.ui.toast(`Not saved: couldn't write ${draftPath(card.capability)} (${String(err)}).`)
      return
    }
    try {
      // Claude edits this file too (pass 3, step 3): count on what it holds now, not on the earlier read.
      counted = countedIn(await $.fs.read(progressFile), card.capability, decision.kind)
      await $.fs.write(progressFile, counted)
    } catch (err) {
      // The marks and the counts never disagree: the draft goes back as it was.
      await $.fs.write(draftFile, text).catch(() => undefined)
      await $.ui.toast(`Not saved: couldn't count it in ${domainPath(d.name)} (${String(err)}).`)
      return
    }
    amendDrafts.clear()
    await update($, view, v => ({ ...v, amend: null }))
    await update($, rev, n => n + 1)
    if (countsOf(parseDraft(got.text)).undecided) return
    // The capability's last card: Claude writes its spec, while the person goes on to the next cards.
    const rest = await cardsOf($, root, d)
    try {
      await $.prompt.submit({ text: decidedPrompt(d.name, card.capability, reviewOf(counted, card.capability), rest.left), asUser: true })
    } catch {
      await $.ui.toast(`Every card of ${card.capability} is decided: ask Claude to write its spec.`)
    }
  } finally {
    deciding.delete(key)
  }
}

/**
 * Starts groups from the plan: marks them starting and sends Claude the prompt, as the person's own
 * words since they pressed it; Claude starts the sessions and calls the tool again to mark them started.
 */
async function startGroups($: EngineInterface, change: string, ids: string[]): Promise<void> {
  const split = (await read($, splits))[change]
  if (!split) return
  const groups = split.groups.filter(g => ids.includes(g.id) && isReady(split, g))
  if (!groups.length) return
  const mark = (status: BlueprintUiGroup['status'], from: BlueprintUiGroup['status']) =>
    update($, splits, all => {
      const cur = all[change]
      if (!cur) return all
      return { ...all, [change]: { ...cur, groups: cur.groups.map(g => (ids.includes(g.id) && g.status === from ? { ...g, status } : g)) } }
    })
  await mark('starting', 'planned')
  try {
    await $.prompt.submit({ text: startPrompt(split, groups), asUser: true })
  } catch {
    await mark('planned', 'starting')
    $.ui.toast('Could not send the start request: try again, or ask Claude to start the group.')
  }
}

/** What each open field holds, by its key, so "Add" can submit it like Enter does. */
const drafts = new Map<string, string>()

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

// The latest page read: an older read that finishes later is dropped.
let lastRead = 0
// Pages whose review is being submitted: a second press waits for the first.
const submitting = new Set<string>()

type Loaded = { map: Map } | { error: 'missing' | 'invalid'; detail?: string }

/** Where blueprint.json was found, by the session folder the walk started from. */
const roots = new Map<string, string>()

/**
 * The nearest folder, from the session's directory up, that holds blueprint.json, with its text;
 * a session started in a subfolder of the repo still finds it.
 */
async function nearest($: EngineInterface): Promise<{ root: string; text: string } | undefined> {
  let dir: string | undefined
  try {
    dir = await $.session.cwd()
  } catch {
    dir = '.'
  }
  const start = dir
  // Where it was found last: one read on each draw, not a walk up the tree.
  const known = roots.get(start)
  if (known !== undefined) {
    try {
      return { root: known, text: await $.fs.read(`${known.replace(/\/+$/, '')}/${BLUEPRINT_JSON}`) }
    } catch {
      roots.delete(start)
    }
  }
  for (; dir !== undefined; dir = dir === '.' ? undefined : parentOf(dir)) {
    try {
      const text = await $.fs.read(`${dir.replace(/\/+$/, '')}/${BLUEPRINT_JSON}`)
      roots.set(start, dir)
      return { root: dir, text }
    } catch {
      // Not here: one folder up.
    }
  }
  return undefined
}

// blueprint.json is read on every draw: it is small, and a write from blueprint shows at once.
async function load($: EngineInterface): Promise<Loaded> {
  const found = await nearest($)
  if (!found) return { error: 'missing' }
  try {
    return { map: pagesOf(found.text, found.root) }
  } catch (err) {
    return { error: 'invalid', detail: String(err) }
  }
}

/** How long a read waits for a Notion connection that isn't up yet, and how often it tries. */
const NOTION_WAIT_MS = 15000
const NOTION_RETRY_MS = 1000

/** How long the block a write changed stays highlighted. */
const HIGHLIGHT_MS = 2500

/** The desktop's one tab bar instance: it waits hidden and moves into an editor, so its code loads once. */
const TAB_BAR = 'tabs'

/** The element a block is scrolled to by: its "+" in the gutter. */
const plusKey = (block: number) => `plus-${block}`

/** Scrolls the pane to block `block`; not drawn, or the pane not placed, leaves it where it is. */
const scrollToBlock = ($: EngineInterface, block: number) =>
  $.ui.scroll({ to: { key: plusKey(block) }, in: PANE, block: 'center' }).catch(() => undefined)

/**
 * Shows `page` and reads it into `doc`; a later open of another page wins over this read.
 * With `mark`, a page that was showing scrolls to the first block that changed and lights it briefly.
 */
async function openPage(
  $: EngineInterface,
  page: BlueprintUiPage,
  map: Map,
  configured: string,
  mark = false,
): Promise<void> {
  const { backend, root } = map
  const before = await read($, doc)
  const was = mark && before.page === page.id && before.status === 'ready' ? before.blocks : null
  if (before.page !== page.id) drafts.clear()
  await update($, view, v => ({ ...v, page: page.id, split: null }))
  if (backend !== 'notion') {
    await update($, doc, (): BlueprintUiDoc => ({
      page: page.id,
      status: 'error',
      message: `The pane doesn't read the ${backend} backend yet.`,
      hint: 'Open the page itself with the link above.',
    }))
    return
  }
  const ticket = ++lastRead
  await update($, doc, (): BlueprintUiDoc => ({ page: page.id, status: 'loading' }))
  let got = await fetchPage($, page.url, await candidates($, configured), root)
  // At the start of a session the Notion connection may not be up yet: retry for a while before saying so.
  // `waited` counts each attempt's own time as well as the sleeps, so the wait stays near its bound.
  for (let waited = 0; 'error' in got && got.error === 'no-server' && waited < NOTION_WAIT_MS && ticket === lastRead; ) {
    if (!waited) await update($, doc, cur => (cur.page === page.id && cur.status === 'loading' ? { ...cur, isWaiting: true } : cur))
    try {
      await $.clock.sleep(NOTION_RETRY_MS)
    } catch {
      break
    }
    const started = Date.now()
    got = await fetchPage($, page.url, await candidates($, configured), root)
    waited += NOTION_RETRY_MS + (Date.now() - started)
  }
  // Diagrams already downloaded for this page carry over, so a re-read after a write doesn't flash their links.
  const known = before.page === page.id && before.status === 'ready' ? svgsOf(before.blocks) : {}
  const next: BlueprintUiDoc =
    'markdown' in got
      ? { page: page.id, status: 'ready', blocks: withSvgs(blocksOf(got.markdown, page.url), known), readAt: new Date().toISOString() }
      : got.error === 'no-server'
        ? {
            page: page.id,
            status: 'error',
            message: `No Notion connection answered under ${got.tried.map(n => `"${n}"`).join(' or ')}.`,
            hint: `Last error: ${got.detail || 'none'}. Set the server's name as /mcp lists it: /config, then blueprint-ui, then "Notion server".`,
          }
        : { page: page.id, status: 'error', message: `Couldn't read the page: ${got.detail}` }
  if (ticket !== lastRead) return
  const changed = was && next.status === 'ready' ? firstChange(was, next.blocks) : undefined
  const shown = changed === undefined || next.status !== 'ready' ? next : { ...next, changed }
  await update($, doc, cur => (cur.page === page.id ? shown : cur))
  if (shown.status === 'ready' && 'server' in got) void loadSvgs($, page.id, shown.readAt, got.server, shown.blocks)
  if (changed === undefined || shown.status !== 'ready') return
  const readAt = shown.readAt
  await scrollToBlock($, changed)
  $.clock.after(HIGHLIGHT_MS, () => {
    void update($, doc, cur =>
      cur.status === 'ready' && cur.readAt === readAt && cur.changed !== undefined ? withoutChange(cur) : cur,
    )
  })
}

/** The SVG markup a page's blocks hold, by picture reference. */
function svgsOf(blocks: BlueprintUiBlock[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const b of blocks) if (b.kind === 'link' && b.picture && b.svg) out[b.picture] = b.svg
  return out
}

/** `blocks` with each picture's markup from `svgs` filled in where it's known. */
function withSvgs(blocks: BlueprintUiBlock[], svgs: Record<string, string>): BlueprintUiBlock[] {
  return blocks.map(b => (b.kind === 'link' && b.picture && !b.svg && svgs[b.picture] ? { ...b, svg: svgs[b.picture] } : b))
}

/**
 * Downloads the page's SVG diagrams not yet drawn and fills them into the read they came from;
 * a newer read or another page leaves this one's result unused.
 */
async function loadSvgs($: EngineInterface, page: string, readAt: string, server: string, blocks: BlueprintUiBlock[]): Promise<void> {
  const refs = blocks.flatMap(b => (b.kind === 'link' && b.picture && !b.svg ? [b.picture] : []))
  if (!refs.length) return
  const svgs = await fetchSvgs($, server, refs).catch(() => ({}))
  if (!Object.keys(svgs).length) return
  await update($, doc, cur => (cur.page === page && cur.status === 'ready' && cur.readAt === readAt ? { ...cur, blocks: withSvgs(cur.blocks, svgs) } : cur))
}

const withoutChange =({ changed: _, ...rest }: Extract<BlueprintUiDoc, { status: 'ready' }>): BlueprintUiDoc => rest

/** Adds a pending item on block `b` of `page` and closes the editor; empty or unchanged text adds nothing. */
async function addItem(
  $: EngineInterface,
  page: BlueprintUiPage,
  b: BlueprintUiBlock,
  kind: BlueprintUiItem['kind'],
  text: string,
): Promise<void> {
  const t = text.trim()
  if (!t || (kind === 'suggest' && t === quoteOf(b).trim())) return
  drafts.delete(`${kind}-${b.id}`)
  await Promise.all([
    update($, pending, list => [...list, itemFor(page, b, kind, t, newId())]),
    update($, view, s => ({ ...s, editor: null })),
  ])
}

/**
 * Moves the pane's focus ring onto a field just drawn, and says whether it moved;
 * a pane not holding the keys is left alone.
 */
async function focusField($: EngineInterface, key: string): Promise<boolean> {
  try {
    const r = await $.ui.focus({ requestId: PANE, key })
    return !('deny' in r && r.deny)
  } catch {
    return false // The field takes the focus on the person's own click instead.
  }
}

/** The `/blueprint` command as this session names it: `blueprint`, or `<plugin>:blueprint` when installed as a plugin. */
async function blueprintCommand($: EngineInterface): Promise<string | undefined> {
  const all = await $.command.list()
  return (all.find(c => c.name === 'blueprint') ?? all.find(c => c.name.endsWith(':blueprint')))?.name
}

/**
 * Writes the page's pending items to a review file and runs `/blueprint review <file>`,
 * as if the person typed it; clears the batch once the command is queued.
 */
async function submit($: EngineInterface, page: BlueprintUiPage, items: BlueprintUiItem[]): Promise<void> {
  if (submitting.has(page.id)) return
  submitting.add(page.id)
  try {
    await submitOnce($, page, items)
  } finally {
    submitting.delete(page.id)
  }
}

async function submitOnce($: EngineInterface, page: BlueprintUiPage, items: BlueprintUiItem[]): Promise<void> {
  const command = await blueprintCommand($)
  if (!command) {
    await $.ui.toast('Submit failed: no /blueprint command in this session. Install the blueprint plugin.')
    return
  }
  const tmp = await $.process.run(['mktemp', '-d', '-t', 'blueprint-review.XXXXXX'])
  const dir = tmp.stdout.trim()
  if (tmp.exitCode !== 0 || !dir) {
    await $.ui.toast(`Submit failed: couldn't make a folder for the review file (${tmp.stderr.trim() || tmp.exitCode}).`)
    return
  }
  const file = `${dir}/review.json`
  const payload: ReviewFile = {
    version: 1,
    page: { id: page.id, kind: page.kind, name: page.name, url: page.url },
    items: items.map(({ id, heading, quote, kind, text }) => ({ id, heading, quote, kind, text })),
  }
  await $.fs.write(file, JSON.stringify(payload, null, 2) + '\n')
  try {
    await $.command.run({ command, args: `review ${file} — ${countOf(items)} on ${labelOf(page)}` })
  } catch (err) {
    // Stopping the session rejects the run whether it was queued or partway: the items stay, to submit again.
    await $.ui.toast(
      wasStopped(err)
        ? `/${command} review was stopped. The review is still pending, to submit again.`
        : `Submit failed: /${command} didn't start (${String(err)}). The review is still pending.`,
    )
    return
  }
  const sent = new Set(items.map(i => i.id))
  await update($, pending, list => list.filter(i => !sent.has(i.id)))
  await $.ui.toast(`Review submitted: ${countOf(items)} on ${labelOf(page)}.`)
}

type ReviewFile = {
  version: 1
  page: Pick<BlueprintUiPage, 'id' | 'kind' | 'name' | 'url'>
  items: Pick<BlueprintUiItem, 'id' | 'heading' | 'quote' | 'kind' | 'text'>[]
}

/**
 * After a tool wrote a page blueprint.json maps, shows it: refreshes the pane when it shows
 * that page, else opens the pane on it. Several pages named: the one showing wins, else the last.
 */
async function followWrite($: EngineInterface, args: string, configured: string): Promise<void> {
  const loaded = await load($)
  if (!('map' in loaded)) return
  const named = pagesNamed(loaded.map.pages, args)
  if (!named.length) return
  const v = await read($, view)
  const target = named.find(p => p.id === v.page) ?? named[named.length - 1]!
  await $.ui.open({ id: PANE, title: TITLE })
  await openPage($, target, loaded.map, configured, true)
  // A spec blueprint just wrote: its marker is re-read, so the board doesn't show it as moved.
  for (const p of named.filter(p => p.kind === 'spec')) {
    const s = loaded.map.specs.find(x => x.name === p.name)
    if (s) void recheckSpec($, s, loaded.map.root, configured).catch(() => undefined)
  }
}

/** A section's list under its header: a line of space, then indented, so it reads as that header's own. */
const LIST = { flexDirection: 'column', marginTop: 1, paddingLeft: 2 } as const

/** A change's status in its state's color; draft, abandoned and anything unknown stay dim. */
const STATUS_COLOR: Record<string, 'warning' | 'suggestion' | 'success'> = { building: 'warning', approved: 'suggestion', applied: 'success' }

/** Tools that may rewrite blueprint.json or its baselines outside MCP: the board redraws after them. */
const LOCAL_WRITE = /^(?:Edit|MultiEdit|Write|Bash|NotebookEdit)$/

export const register: Register = (on, options) => {
  const configured = String(options.notionServer ?? 'claude.ai Notion')

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'blueprint-ui',
      description: 'Open the blueprint pane: reviews, briefs and specs this repo maps',
      argumentHint: '[change or capability] [review|brief]',
    })
    await $.tool.register(SPLIT_SPEC)
    await $.tool.register(BACKFILL_SPEC)
    return next(e)
  })

  // The main loop's turns, so the board can say a ▶ step will wait; a subagent's turn is not the session's.
  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) await update($, working, () => true).catch(() => undefined)
    return next(e)
  })
  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined) await update($, working, () => false).catch(() => undefined)
    return next(e)
  })

  on('command.run', { command: 'blueprint-ui' }, async ($, e) => {
    const loaded = await load($)
    let note = 'Blueprint pane opened.'
    let toOpen: BlueprintUiPage | undefined
    if ('map' in loaded) {
      if (e.args.trim()) {
        toOpen = pageFor(loaded.map.pages, e.args)
        note = toOpen
          ? `Blueprint pane opened on ${labelOf(toOpen)}.`
          : `Nothing named "${e.args.trim()}" in ${BLUEPRINT_JSON}; showing the list.`
      }
      // Asked for by name: the board or a page, not the Backfill view.
      await update($, view, v => ({ ...v, backfill: null, amend: null, ...(toOpen ? {} : { page: null }) }))
    }
    await $.ui.open({ id: PANE, title: TITLE })
    if (toOpen && 'map' in loaded) void openPage($, toOpen, loaded.map, configured)
    // The pane is open, showing "Checking code…": the check is local and quick, so the command waits for it.
    else if ('map' in loaded) await checkCode($, loaded.map)
    return { text: note }
  })

  // apply's PR plan: kept by change and shown in the pane in place of the board.
  on('tool.call', { tool: new RegExp(`^${SPLIT_CALL}$`) }, async ($, e) => {
    const { tool: _, tool_use_id: __, ...input } = e as unknown as Record<string, unknown>
    const got = splitOf(input)
    if ('error' in got) return { isError: true as const, result: got.error, text: `Not shown: ${got.error}` }
    await update($, splits, all => {
      // A group whose start is on its way stays starting until a call says it started.
      const was = all[got.change]
      const groups = got.groups.map(g => (g.status === 'planned' && was?.groups.find(o => o.id === g.id)?.status === 'starting' ? { ...g, status: 'starting' as const } : g))
      return { ...all, [got.change]: { ...got, groups } }
    })
    await update($, view, v => ({ ...v, page: null, split: got.change, backfill: null, amend: null }))
    const { isPlaced } = await $.ui.open({ id: PANE, title: TITLE })
    const ready = got.groups.filter(g => isReady(got, g)).length
    const text = !isPlaced
      ? 'The plan is saved, but no pane is showing: draw the tree in chat instead.'
      : got.isApproved
        ? `Shown in the blueprint pane with ${ready} group${ready === 1 ? '' : 's'} ready to start: the user starts them from its ▶ buttons, or asks you to. Don't draw the tree in chat.`
        : "Shown in the blueprint pane as a proposal: don't draw the tree in chat; show the table and ask the user to approve or change it."
    // An MCP tool's result reaches the model as text or content blocks, never a bare object.
    return { result: text, text }
  })

  // Pass 3 of /blueprint-backfill: the domain's scenario cards, shown in the Backfill view in place of the board.
  on('tool.call', { tool: new RegExp(`^${BACKFILL_CALL}$`) }, async ($, e) => {
    const input = e as unknown as Record<string, unknown>
    const domain = typeof input.domain === 'string' ? input.domain.trim() : ''
    const fail = (text: string) => ({ isError: true as const, result: text, text })
    const loaded = await load($)
    if (!('map' in loaded)) return fail(`No ${BLUEPRINT_JSON} here: ask the cards in chat instead.`)
    await checkBackfill($, loaded.map.root)
    const bf = await read($, backfill)
    if (bf.status === 'error') return fail(`backfill status unavailable (${bf.message}): ask the cards in chat instead.`)
    if (bf.status !== 'ready') return fail('No backfill in progress: .blueprint/backfill/progress.json not found.')
    const d = bf.report.domains.find(x => x.name === domain)
    if (!d) return fail(`Unknown domain "${domain}": the backfill's domains are ${bf.report.domains.map(x => x.name).join(', ') || 'none'}.`)
    await update($, view, v => ({ ...v, page: null, split: null, backfill: { domain }, amend: null }))
    const { isPlaced } = await $.ui.open({ id: PANE, title: TITLE })
    const text = !isPlaced
      ? 'No pane is showing: ask the cards in chat instead.'
      : d.drafts.length
        ? `Shown in the blueprint pane's Backfill view: ${domain}'s cards, from ${d.drafts.length} draft${d.drafts.length === 1 ? '' : 's'}. ` +
          "The user decides them there: don't ask them in chat. End your turn now; a message comes each time a capability's last card is decided."
        : `Shown, but ${domain} has no drafts awaiting review.`
    return { result: text, text }
  })

  // A write through an MCP tool to a mapped page opens or refreshes the pane once it has run.
  // Awaited, so the pane reads as the page does when the call returns; only writes to mapped pages wait.
  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    const tool = String(e.tool)
    if (LOCAL_WRITE.test(tool) && !('deny' in result) && JSON.stringify(e).includes('.blueprint/')) {
      await update($, rev, n => n + 1).catch(() => undefined)
      // A sync records new anchors and commits: once the board has a code status, check it again.
      const loaded = await load($).catch(() => undefined)
      if (loaded && 'map' in loaded) void recheckCode($, loaded.map).catch(() => undefined)
      return result
    }
    if (tool === SPLIT_CALL || tool === BACKFILL_CALL || !tool.startsWith('mcp__') || 'deny' in result || result.isError || result.isReadOnly || READ_TOOL.test(tool)) return result
    try {
      await followWrite($, targetsOf(e), configured)
    } catch {
      // Never in a tool call's way: the call already ran, so its result stands.
    }
    return result
  })

  // A tab clicked in the desktop's tab bar: the editor on that block switches to it.
  on('ui.message', async ($, e, next) => {
    if (e.requestId !== PANE || !e.module.endsWith('tabs.tsx')) return next(e)
    // Posted by code, not the engine: checked before it is used.
    const data = e.data as { kind?: unknown; id?: unknown; mode?: unknown } | null
    const m = data && data.kind === 'mode' && typeof data.id === 'string' ? /^(comment|suggest)-(\d+)$/.exec(data.id) : null
    const mode = data?.mode as Mode | undefined
    if (!m || (mode !== 'comment' && mode !== 'suggest')) return {}
    drafts.clear()
    await update($, view, v => (v.editor?.block === Number(m[2]) ? { ...v, editor: { ...v.editor, mode } } : v))
    await focusField($, `${mode}-${m[2]}`)
    return {}
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Text, Button, Input, Link, Markdown, Code } = elements
    // Every Button on the desktop is a native button, so there the editor's tab bar is our own.
    const Client = e.surface === 'desktop' && 'Client' in elements ? elements.Client : undefined
    // The terminal's table answers `Svg` too, drawing only its alt: there the link stays instead.
    const Svg = e.surface !== 'terminal' && 'Svg' in elements ? elements.Svg : undefined
    const loaded = await load($)
    if ('error' in loaded) {
      return (
        <Box flexDirection="column">
          {loaded.error === 'missing' ? (
            <Text>This repo isn't set up for blueprint: there is no {BLUEPRINT_JSON} here or in any folder above.</Text>
          ) : (
            <Text color="error">
              {BLUEPRINT_JSON} could not be read: {loaded.detail}
            </Text>
          )}
          <Text dimColor>Run /blueprint-setup to set it up.</Text>
        </Box>
      )
    }
    const { pages, backend } = loaded.map
    const v = await read($, view)
    const open = pages.find(p => p.id === v.page)
    const plan = !open && v.split ? (await read($, splits))[v.split] : undefined

    // The Backfill view: one scenario card at a time from a domain's drafts, decided with Accept, Amend or Reject.
    if (!open && !plan && v.backfill) {
      await read($, rev) // A decision bumps it, so the next card is read from the saved draft.
      const bf = await read($, backfill)
      const isWorking = await read($, working)
      const waiting = new Set(await read($, queued))
      const root = loaded.map.root
      const toBoard = () => update($, view, s => ({ ...s, backfill: null, amend: null }))
      const nav = (choose: boolean) => (
        <Box flexDirection="row" gap={2}>
          <Button key="bf-back" plain label="← Board" onPress={toBoard} />
          {choose ? <Button key="bf-domains" plain label="← Domains" onPress={() => update($, view, s => ({ ...s, backfill: { domain: null }, amend: null }))} /> : null}
          <Button key="bf-refresh" plain label="↻" onPress={() => checkBackfill($, root)} />
        </Box>
      )
      if (bf.status !== 'ready') {
        return (
          <Box flexDirection="column" gap={1}>
            {nav(false)}
            {bf.status === 'error' ? (
              <Text color="error">Backfill status unavailable: {bf.message}</Text>
            ) : (
              <Text dimColor>No backfill in progress: there is no .blueprint/backfill/ here.</Text>
            )}
          </Box>
        )
      }
      const report = bf.report
      const reviewing = report.domains.filter(d => d.drafts.length)
      const chosen =
        report.domains.find(d => d.name === v.backfill!.domain) ?? (v.backfill.domain === null && reviewing.length === 1 ? reviewing[0] : undefined)

      // No domain chosen: the domains with drafts to review, and backfill.py's next steps.
      if (!chosen) {
        const counts = await Promise.all(reviewing.map(d => cardsOf($, root, d)))
        return (
          <Box flexDirection="column" gap={1}>
            {nav(false)}
            <Text bold size="heading">{report.line}</Text>
            {reviewing.length ? (
              <Box flexDirection="column">
                <Text bold>Scenario review</Text>
                <Box key="bf-domain-list" {...LIST}>
                  {reviewing.map((d, i) => (
                    <Box key={`bf-row-${d.name}`} flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
                      <Button key={`bf-domain-${d.name}`} plain label={d.name} onPress={() => update($, view, s => ({ ...s, backfill: { domain: d.name }, amend: null }))} />
                      <Text dimColor>
                        · {d.drafts.length} draft{d.drafts.length === 1 ? '' : 's'} · {counts[i]!.left} card{counts[i]!.left === 1 ? '' : 's'} left
                      </Text>
                    </Box>
                  ))}
                </Box>
              </Box>
            ) : (
              <Text dimColor>No drafts await scenario review.</Text>
            )}
            {report.next.length ? (
              <Box flexDirection="column">
                <Text bold>Next</Text>
                <Box key="bf-next-list" {...LIST}>
                  {report.next.map((n, i) => {
                    const step = backfillStep(n.command)
                    return (
                      <Box key={`bf-next-row-${i}`} flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
                        <Text>{n.command}</Text>
                        <Text dimColor>· {n.why}</Text>
                        {step ? (
                          waiting.has(stepKey(step)) ? (
                            <Text key={`bf-next-${i}`} color="warning">◷ queued</Text>
                          ) : (
                            <Button key={`bf-next-${i}`} plain dimColor={isWorking || undefined} label={step.label} onPress={() => void runStep($, step)} />
                          )
                        ) : null}
                      </Box>
                    )
                  })}
                </Box>
              </Box>
            ) : null}
          </Box>
        )
      }

      const cards = await cardsOf($, root, chosen)
      const card = cards.card
      const head = (
        <Box flexDirection="column">
          <Text bold size="heading">Backfill · {chosen.name}</Text>
          <Text dimColor>{report.line}</Text>
        </Box>
      )
      if (!card) {
        const waitingSpec = cards.order.filter(c => cards.drafts[c] && !cards.leftIn[c])
        return (
          <Box flexDirection="column" gap={1}>
            {nav(reviewing.length > 1)}
            {head}
            <Text key="bf-none">No cards left in {chosen.name}: every scenario in its drafts is decided.</Text>
            {waitingSpec.length ? (
              <Text dimColor>
                Waiting for Claude to write {waitingSpec.length === 1 ? 'the spec' : 'the specs'} of {waitingSpec.join(', ')}.
              </Text>
            ) : null}
          </Box>
        )
      }

      const cap = card.capability
      const review = reviewOf(cards.progress, cap)
      const draft = cards.drafts[cap]!
      const total = review.rejected + countsOf(draft).decided + countsOf(draft).undecided
      const index = review.rejected + countsOf(draft).decided + 1
      const amending = v.amend?.capability === cap && v.amend.scenario === card.name
      const fieldColumns = (e.props.bodyColumns ?? 60) - 4
      const field = (key: string, value: string) => (
        <Input
          key={key}
          value={value || undefined}
          rows={rowsFor(value, fieldColumns, 1)}
          submitLabel="save amendment"
          onInput={(t: string) => void amendDrafts.set(key, t)}
          onSubmit={(t: string) => (amendDrafts.set(key, t), void saveAmend())}
        />
      )
      const saveAmend = async () => {
        const scenario = amendDrafts.get('bf-amend-scenario') ?? card.scenario
        const statement = card.isFirstOfRequirement ? (amendDrafts.get('bf-amend-statement') ?? card.statement) : undefined
        const purpose = card.purpose !== undefined ? (amendDrafts.get('bf-amend-purpose') ?? card.purpose) : undefined
        const same = (a: string | undefined, b: string | undefined) => (a ?? '').trim() === (b ?? '').trim()
        if (same(scenario, card.scenario) && same(statement, card.isFirstOfRequirement ? card.statement : undefined) && same(purpose, card.purpose)) {
          await $.ui.toast('Nothing changed: edit the text, or press Accept.')
          return
        }
        await decideCard($, root, chosen, card, {
          kind: 'amend',
          scenario,
          ...(statement !== undefined ? { statement } : {}),
          ...(purpose !== undefined ? { purpose } : {}),
        })
      }

      return (
        <Box flexDirection="column" gap={1}>
          {nav(reviewing.length > 1)}
          {head}
          <Box flexDirection="row" gap={1} flexWrap="wrap">
            <Text bold>{cap}</Text>
            <Text key="bf-card-of" dimColor>· card {index} of {total}</Text>
            <Text key="bf-left" dimColor>· {cards.leftIn[cap]} left in {cap} · {cards.left} left in {chosen.name}</Text>
          </Box>
          <Box key={`bf-card-${cap}-${card.name}`} flexDirection="column" borderStyle="round" borderColor={amending ? 'suggestion' : undefined} paddingX={1} gap={1}>
            {card.purpose !== undefined ? (
              <Box flexDirection="column">
                <Text dimColor>Purpose</Text>
                {amending ? field('bf-amend-purpose', card.purpose) : <Markdown key="bf-purpose" text={card.purpose || '_(none)_'} />}
              </Box>
            ) : null}
            <Box flexDirection="column">
              <Text bold>Requirement: {card.requirement}</Text>
              {amending && card.isFirstOfRequirement ? (
                field('bf-amend-statement', card.statement)
              ) : (
                <Text key="bf-statement" dimColor={!card.isFirstOfRequirement || undefined}>{card.statement}</Text>
              )}
            </Box>
            {amending ? field('bf-amend-scenario', card.scenario) : <Markdown key="bf-scenario" text={card.scenario} />}
            {card.verify.map((q, i) => (
              <Text key={`bf-verify-${i}`} color="warning">Verify: {q}</Text>
            ))}
            {amending ? (
              <Box flexDirection="row" justifyContent="flex-end" gap={1}>
                <Button key="bf-cancel" plain dimColor label="Cancel" onPress={() => (amendDrafts.clear(), update($, view, s => ({ ...s, amend: null })))} />
                <Button key="bf-save" variant="primary" label="Save amendment" onPress={() => saveAmend()} />
              </Box>
            ) : (
              <Box flexDirection="row" gap={1}>
                <Button key="bf-accept" variant="primary" label="Accept" onPress={() => decideCard($, root, chosen, card, { kind: 'accept' })} />
                <Button
                  key="bf-amend"
                  label="Amend"
                  onPress={() => (amendDrafts.clear(), update($, view, s => ({ ...s, amend: { capability: cap, scenario: card.name } })))}
                />
                <Button key="bf-reject" label="Reject" onPress={() => decideCard($, root, chosen, card, { kind: 'reject' })} />
              </Box>
            )}
          </Box>
          <Text dimColor>
            {amending
              ? card.isFirstOfRequirement
                ? "Edit the scenario, the requirement's statement or the Purpose shown, then save."
                : "Edit the scenario, then save. The statement is editable on its requirement's first card."
              : card.verify.length
                ? 'Settle the question: Accept if the draft is right, Amend to change it.'
                : 'Each decision is saved to the draft and the progress file before the next card.'}
          </Text>
        </Box>
      )
    }

    // A change's PR plan: the tree of branches apply proposed, with ▶ start on the groups ready now.
    if (plan) {
      const isWorking = await read($, working)
      const ready = plan.groups.filter(g => isReady(plan, g))
      const stateColor = (g: BlueprintUiGroup) =>
        g.status === 'merged' ? 'success' : g.status === 'pr' || g.status === 'started' ? 'suggestion' : g.status === 'starting' ? 'warning' : undefined
      return (
        <Box flexDirection="column" gap={1}>
          <Box flexDirection="row" gap={2}>
            <Button key="split-back" plain label="← Board" onPress={() => update($, view, s => ({ ...s, split: null }))} />
          </Box>
          <Text bold size="heading">{plan.change} · PRs</Text>
          <Text key="split-note" dimColor>
            {!plan.isApproved
              ? 'Proposed: approve or change it in chat. ▶ start appears once it is approved.'
              : ready.length
                ? isWorking
                  ? 'Claude is working: a start waits until the turn ends.'
                  : '▶ start opens a new session for that group, with the prompt apply wrote for it.'
                : 'No group can start now: a stacked group waits for its base PR, Specs for every merge.'}
          </Text>
          <Box key="split-tree" flexDirection="column">
            <Text key="split-root" mono dimColor>{plan.defaultBranch}</Text>
            {treeOf(plan).map(({ prefix, group: g }) => (
              <Box key={`group-${g.id}`} flexDirection="row" gap={1} alignItems="center" flexWrap="wrap">
                <Text mono dimColor>{prefix.trimEnd()}</Text>
                <Text bold={g.id.toLowerCase() !== 'specs' || undefined}>{g.id.toLowerCase() === 'specs' ? g.name || 'Specs' : `${g.id}. ${g.name}`}</Text>
                <Text dimColor>· tasks {g.tasks}</Text>
                <Text key={`state-${g.id}`} italic size="footnote" color={stateColor(g)} dimColor={stateColor(g) ? undefined : true}>
                  {stateOf(plan, g)}
                </Text>
                {g.pr ? <Link href={g.pr} label="PR" /> : null}
                {isReady(plan, g) ? (
                  <Button key={`start-${g.id}`} plain dimColor={isWorking || undefined} label="▶ start" onPress={() => void startGroups($, plan.change, [g.id])} />
                ) : null}
              </Box>
            ))}
          </Box>
          {ready.length > 1 ? (
            <Box flexDirection="row">
              <Button
                key="start-all"
                plain
                dimColor={isWorking || undefined}
                label={`▶ start all ready (${ready.length})`}
                onPress={() => void startGroups($, plan.change, ready.map(g => g.id))}
              />
            </Box>
          ) : null}
        </Box>
      )
    }

    if (open) {
      const d = await read($, doc)
      const mine = d.page === open.id ? d : undefined
      const items = await read($, pending)
      const here = items.filter(i => i.page === open.id)
      const elsewhere = items.length - here.length
      const editor = v.editor && v.editor.page === open.id ? v.editor : null
      // The editor stays on its block only while that block reads as it did when opened.
      const editing = (b: BlueprintUiBlock) => editor?.block === b.id && sameText(editor.quote, quoteOf(b))
      const blocks = mine?.status === 'ready' ? mine.blocks : null
      const changed = mine?.status === 'ready' ? mine.changed : undefined

      const fieldKey = (block: number, mode: 'comment' | 'suggest') => `${mode}-${block}`
      const setEditor = (next: typeof editor) => (drafts.clear(), update($, view, s => ({ ...s, editor: next })))
      /** Opens the editor on a block in `mode` and puts the cursor in its field. */
      const edit = async (b: BlueprintUiBlock, mode: 'comment' | 'suggest') => {
        await setEditor({ page: open.id, block: b.id, quote: quoteOf(b), mode })
        await focusField($, fieldKey(b.id, mode))
      }
      const add = (b: BlueprintUiBlock, kind: BlueprintUiItem['kind'], text: string) => addItem($, open, b, kind, text)
      const remove = (id: string) => update($, pending, list => list.filter(i => i.id !== id))
      const blockOf = (i: BlueprintUiItem) => blocks?.find(b => sameText(quoteOf(b), i.quote))

      const kindTag = (i: BlueprintUiItem) => (
        <Text color={accentOf(i.kind === 'comment' ? 'comment' : 'suggest')} bold>{i.kind === 'comment' ? 'Comment' : 'Suggestion'}</Text>
      )

      // One item in the pending review: what it is, where it sits, what it says.
      const reviewItem = (i: BlueprintUiItem) => {
        const at = blockOf(i)
        return (
          <Box key={`item-bar-${i.id}`} flexDirection="row" gap={1}>
            <Button key={`rm-bar-${i.id}`} plain dimColor label="✕" onPress={() => remove(i.id)} />
            <Box flexDirection="column" flexGrow={1} flexShrink={1}>
              <Box flexDirection="row" gap={1}>
                <Text>
                  {kindTag(i)}
                  <Text dimColor> on {oneLine(i.heading || 'the top of the page', 48)}</Text>
                  {blocks !== null && !at ? <Text color="warning"> · outdated</Text> : null}
                </Text>
                {at ? (
                  <Button key={`goto-${i.id}`} plain dimColor label="↓ show in page" onPress={() => void scrollToBlock($, at.id)} />
                ) : null}
              </Box>
              <Text dimColor italic>“{oneLine(i.quote, 72)}”</Text>
              <Text>{i.kind === 'suggest' ? '→ ' : ''}{oneLine(i.text, 120)}</Text>
            </Box>
          </Box>
        )
      }

      // An item under its block, short: the block itself is right above.
      const inlineItem = (i: BlueprintUiItem) => (
        <Box key={`item-inline-${i.id}`} flexDirection="row" gap={1}>
          <Text dimColor>└</Text>
          <Text>
            {kindTag(i)}
            <Text> {i.kind === 'suggest' ? '→ ' : ''}{oneLine(i.text, 90)}</Text>
          </Text>
          <Button key={`rm-inline-${i.id}`} plain dimColor label="✕" onPress={() => remove(i.id)} />
        </Box>
      )

      // The field sits inside the gutter (3), the box's border and padding (4).
      const fieldColumns = (e.props.bodyColumns ?? 60) - 7
      const editorBox = (b: BlueprintUiBlock, mode: Mode) => {
        const quote = quoteOf(b)
        const key = fieldKey(b.id, mode)
        const value = mode === 'suggest' ? quote : ''
        const placeholder = mode === 'comment' ? 'Leave a comment on this block' : ''
        const hint = mode === 'suggest' ? "Edit the block's text into the wording you want." : undefined
        const rows = mode === 'comment' ? 3 : rowsFor(quote, fieldColumns)

        // The desktop: our own tab bar (its Buttons are native buttons). The terminal: plain buttons.
        const tabBar = Client ? (
          <Client key={TAB_BAR} module="./tabs.tsx" props={{ id: key, mode } satisfies TabsProps} width="100%" />
        ) : (
          <Box flexDirection="row" gap={4}>
            {TABS.map(t => (
              <Button key={`tab-${t.mode[0]}-${b.id}`} plain onPress={() => void edit(b, t.mode)}>
                {t.mode === mode ? (
                  <Text bold underline color={accentOf(t.mode)}>{t.label}</Text>
                ) : (
                  <Text dimColor>{t.label}</Text>
                )}
              </Button>
            ))}
          </Box>
        )
        // On the desktop the field's own button (it always draws one) is the Add button;
        // the terminal draws its label as a key hint only, so it has Add below as well.
        const addLabel = mode === 'comment' ? 'Add comment' : 'Add suggestion'
        return (
          <Box key={`editor-${b.id}`} flexDirection="column" borderStyle="round" borderColor={accentOf(mode)} paddingX={1} marginTop={1} gap={1}>
            {tabBar}
            <Box flexDirection="column">
              {hint ? <Text dimColor>{hint}</Text> : null}
              <Input key={key} value={value || undefined} placeholder={placeholder} submitLabel={Client ? addLabel : mode === 'comment' ? 'add comment' : 'add'} rows={rows} autoFocus onInput={(t: string) => void drafts.set(key, t)} onSubmit={(t: string) => add(b, mode, t)} />
            </Box>
            <Box flexDirection="row" justifyContent="flex-end" gap={1}>
              <Button key={`cancel-${b.id}`} plain dimColor label="Cancel" onPress={() => setEditor(null)} />
              {Client ? null : (
                <Button key={`add-${b.id}`} variant="primary" label={addLabel} onPress={() => add(b, mode, drafts.get(key) ?? value)} />
              )}
            </Box>
          </Box>
        )
      }

      return (
        <Box flexDirection="column" gap={1}>
          <Box flexDirection="row" gap={2}>
            <Button
              key="back"
              plain
              label="← All pages"
              onPress={async () => {
                await update($, view, s => ({ ...s, page: null, editor: null }))
                await checkCode($, loaded.map)
              }}
            />
            <Button key="refresh" plain label="↻ Refresh" onPress={() => void openPage($, open, loaded.map, configured)} />
            <Link href={open.url} label="Open in Notion" />
          </Box>
          <Text bold size="heading">{labelOf(open)}</Text>
          {here.length > 0 ? (
            <Box flexDirection="column" borderStyle="round" borderColor="suggestion" paddingX={1} gap={1}>
              <Box flexDirection="row" justifyContent="space-between" flexWrap="wrap" columnGap={2}>
                <Text bold>Pending review · {countOf(here)}</Text>
                <Box flexDirection="row" gap={1}>
                  <Button key="discard" plain dimColor label="Discard all" onPress={() => update($, pending, list => list.filter(i => i.page !== open.id))} />
                  <Button key="submit" variant="primary" label="Submit review" onPress={() => submit($, open, here)} />
                </Box>
              </Box>
              {here.map(reviewItem)}
              <Text dimColor>Submit hands these to /blueprint review, which applies them to the page in Notion.</Text>
            </Box>
          ) : (
            <Text dimColor>Press + beside a block to comment on it or suggest new wording. Your notes collect here as a pending review until you submit it.</Text>
          )}
          {elsewhere > 0 ? <Text dimColor>{elsewhere} more pending on other pages: ← All pages shows where.</Text> : null}
          {!mine || mine.status === 'loading' ? (
            <Text dimColor>{mine?.status === 'loading' && mine.isWaiting ? 'Waiting for the Notion connection…' : 'Reading the page…'}</Text>
          ) : mine.status === 'error' ? (
            <Box flexDirection="column">
              <Text color="error">{mine.message}</Text>
              {mine.hint ? <Text dimColor>{mine.hint}</Text> : null}
            </Box>
          ) : mine.status === 'ready' ? (
            <Box flexDirection="column" gap={1}>
              {mine.blocks.map(b => {
                const onBlock = here.filter(i => sameText(i.quote, quoteOf(b)))
                const isOpen = editing(b)
                const isChanged = changed === b.id
                return (
                  <Box key={`block-${b.id}`} flexDirection="column" backgroundColor={isChanged ? 'diffAddedDimmed' : undefined}>
                    <Box flexDirection="row">
                      <Box width={3} flexShrink={0}>
                        <Button
                          key={plusKey(b.id)}
                          plain
                          dimColor={isOpen ? undefined : true}
                          label={isOpen ? '−' : '+'}
                          onPress={() => (isOpen ? setEditor(null) : edit(b, 'comment'))}
                        />
                      </Box>
                      <Box flexDirection="column" flexGrow={1} flexShrink={1}>
                        {b.kind === 'md' ? (
                          <Markdown key={`b${b.id}`} text={b.text} />
                        ) : Svg && b.svg ? (
                          <Box flexDirection="column">
                            <Svg key={`svg${b.id}`} source={b.svg} alt={b.label} />
                            <Text dimColor>{b.label.replace(/^Image: /, '')}</Text>
                          </Box>
                        ) : !Svg && b.diagram ? (
                          // The terminal can't draw the image: the diagram's own text version stands in.
                          <Box flexDirection="column">
                            <Code key={`diagram${b.id}`} source={b.diagram} />
                            <Text dimColor>{b.label.replace(/^Image: /, '')}</Text>
                          </Box>
                        ) : (
                          <Link href={b.href} label={`↗ ${b.label} (open in Notion)`} />
                        )}
                        {onBlock.length > 0 ? <Box flexDirection="column" marginTop={1}>{onBlock.map(inlineItem)}</Box> : null}
                        {isOpen && editor ? editorBox(b, editor.mode) : null}
                      </Box>
                    </Box>
                  </Box>
                )
              })}
            </Box>
          ) : null}
          {Client && !blocks?.some(editing) ? (
            <Box height={0} overflow="hidden">
              <Client key={TAB_BAR} module="./tabs.tsx" props={{ id: '', mode: 'comment' } satisfies TabsProps} width="100%" />
            </Box>
          ) : null}
        </Box>
      )
    }

    // The status board: what needs a step first, then open changes, then everything quiet.
    await read($, rev) // A write to blueprint.json bumps it, so the board redraws from the new file.
    const c = await read($, code)
    const sp = await read($, specs)
    const items = await read($, pending)
    const waiting = new Set(await read($, queued))
    const isWorking = await read($, working)
    const plans = await read($, splits)
    const bf = await read($, backfill)
    const board = boardOf(loaded.map, c, sp, page => items.filter(i => i.page === page).length, bf)
    // A plan whose change has no row (renamed, removed, or never in blueprint.json) gets a row of its own,
    // so ← Board never strands it.
    const strayPlans = Object.keys(plans)
      .filter(n => !board.changes.some(r => r.name === n) && !board.done.some(r => r.name === n))
      .sort()
    const byId = (id: string | undefined) => (id ? pages.find(p => p.id === id) : undefined)
    const openId = (id: string | undefined) => {
      const p = byId(id)
      return p ? () => void openPage($, p, loaded.map, configured) : undefined
    }
    const now = Date.now()

    const glyphColor = (side: Side) => (side === 'code' ? 'warning' : side === 'none' ? undefined : 'error')
    const name = (label: string, page: string | undefined, key: string) => {
      const go = openId(page)
      return go ? <Button key={page!} plain label={label} onPress={go} /> : <Text key={key}>{label}</Text>
    }

    // Bare /blueprint-sync takes every capability whose code or imported code moved; offered once two or more did.
    const codeMoved = board.attention.filter(r => r.side === 'code' && r.step?.command === 'blueprint-sync').length
    const allSync = syncAll(codeMoved)
    /**
     * A ▶ step: queued once pressed, until the session runs it (`covered`: a queued sync all takes
     * this row too); while Claude works it is drawn dim, since pressing it only queues it.
     */
    const stepButton = (key: string, step: Step, covered = false) =>
      waiting.has(stepKey(step)) || covered ? (
        <Text key={key} color="warning">
          ◷ {step.label.replace(/^▶ /, '')} queued
        </Text>
      ) : (
        <Button key={key} plain dimColor={isWorking || undefined} label={step.label} onPress={() => void runStep($, step)} />
      )

    const capRow = (r: CapRow) => (
      <Box key={`att-${r.name}`} flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
        <Text color={glyphColor(r.side)} dimColor={r.side === 'none' ? true : undefined}>{r.side === 'none' ? '○' : '◐'}</Text>
        {name(r.name, r.page, `cap-${r.name}`)}
        <Text dimColor>{r.score ? `${r.reason} · ${r.score}` : r.reason}</Text>
        {r.pending ? <Text color="suggestion">· {r.pending} pending</Text> : null}
        {r.step ? stepButton(`step-${r.name}`, r.step, r.side === 'code' && waiting.has(stepKey(allSync))) : null}
      </Box>
    )

    const changeRow = (r: ChangeRow) => {
      const isActive = r.status === 'building' || r.status === 'approved'
      // Dots throughout: accent while it moves, green once applied, dim otherwise; a draft is an open ring.
      const dot = isActive ? 'suggestion' : r.status === 'applied' ? 'success' : undefined
      return (
        <Box key={`chg-${r.name}`} flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
          <Text color={dot} dimColor={dot ? undefined : true}>{r.status === 'draft' ? '○' : '●'}</Text>
          <Text key={`chg-name-${r.name}`}>{r.name}</Text>
          {/* A status, not a control: italic, smaller and in its state's color, unlike the dim links beside it. */}
          <Text key={`chg-status-${r.name}`} italic size="footnote" color={STATUS_COLOR[r.status]} dimColor={STATUS_COLOR[r.status] ? undefined : true}>
            {r.status}
          </Text>
          {r.pending ? <Text color="suggestion">· {r.pending} pending</Text> : null}
          {/* A change has two pages: each gets its own link, named for what it opens. */}
          {byId(r.review) ? <Button key={r.review!} plain dimColor label="review" onPress={openId(r.review)!} /> : null}
          {byId(r.brief) ? <Button key={r.brief!} plain dimColor label="brief" onPress={openId(r.brief)!} /> : null}
          {plans[r.name] ? <Button key={`prs-${r.name}`} plain dimColor label="PRs" onPress={() => update($, view, s => ({ ...s, split: r.name }))} /> : null}
          {r.step ? stepButton(`step-change-${r.name}`, r.step) : null}
        </Box>
      )
    }

    const specNote = sp.progress
      ? `Checking specs… ${sp.progress.done}/${sp.progress.total}`
      : sp.checkedAt
        ? `spec side checked ${ago(sp.checkedAt, now)}`
        : 'spec side not checked'
    const unknown = board.quiet.filter(q => q.unknown)
    // Each section folds like Done. What needs a step and open changes start open; In sync starts
    // folded, except when the code couldn't be checked: then the list is the only way to its specs.
    const isOpen = {
      attention: v.sections?.attention ?? true,
      changes: v.sections?.changes ?? true,
      sync: v.sections?.sync ?? !board.isCodeChecked,
    }
    const head = (key: keyof typeof isOpen, title: string, count: number, open: boolean, note?: string) => (
      <Box key={`head-${key}`} flexDirection="row" gap={1} alignItems="center" flexWrap="wrap">
        <Button
          key={`fold-${key}`}
          plain
          onPress={() => update($, view, s => ({ ...s, sections: { ...s.sections, [key]: !open } }))}
        >
          <Text bold>
            {open ? '▼' : '▶'} {title} ({count})
          </Text>
        </Button>
        {note ? <Text dimColor>· {note}</Text> : null}
      </Box>
    )
    const quiet = [...board.quiet].sort((a, b) => a.name.localeCompare(b.name))
    // The terminal has no hover, so there a possibly affected cell shows its score inline.
    const inlineMaybe = e.surface === 'terminal'
    const cols = columnsFor(quiet, e.props.bodyColumns ?? 60, inlineMaybe)

    return (
      <Box flexDirection="column" gap={1}>
        {/* A backfill in progress comes first: choosing its line opens the Backfill view. */}
        {board.backfill ? (
          board.backfill.error ? (
            <Text key="backfill-line" color="error">
              {board.backfill.line}: {board.backfill.error}
            </Text>
          ) : (
            <Button key="backfill" plain onPress={() => update($, view, s => ({ ...s, backfill: { domain: null }, amend: null }))}>
              <Text bold color="suggestion">{board.backfill.line}</Text>
            </Button>
          )
        ) : null}
        <Box flexDirection="row" justifyContent="space-between" flexWrap="wrap" columnGap={2}>
          <Text bold>{c.status === 'checking' ? 'Checking code…' : c.status === 'none' ? 'Code not checked yet: press ↻.' : board.summary}</Text>
          <Box flexDirection="row" gap={2}>
            <Button
              key="refresh-board"
              plain
              label="↻"
              onPress={async () => {
                const specsToo = sp.checkedAt && !isCheckingSpecs(loaded.map.root) ? checkSpecs($, loaded.map, configured) : undefined
                await Promise.all([checkCode($, loaded.map), specsToo])
              }}
            />
            <Button key="check-specs" plain label="Check specs" onPress={() => checkSpecs($, loaded.map, configured)} />
          </Box>
        </Box>
        {isWorking || waiting.size ? (
          <Text key="working-note" dimColor>
            {isWorking ? 'Claude is working: a ▶ step waits until the turn ends.' : 'A ▶ step is queued: it runs next.'}
          </Text>
        ) : null}
        {board.codeError ? (
          <Box flexDirection="column">
            <Text color="error">Code status unavailable: {board.codeError}</Text>
            <Text dimColor>Run /blueprint-setup to copy drift.py into .blueprint/.</Text>
          </Box>
        ) : null}
        {board.attention.length ? (
          <Box flexDirection="column">
            <Box flexDirection="row" justifyContent="space-between" flexWrap="wrap" columnGap={2}>
              {head('attention', 'Needs attention', board.attention.length, isOpen.attention)}
              {codeMoved > 1 ? stepButton('sync-all', allSync) : null}
            </Box>
            {isOpen.attention ? <Box key="list-attention" {...LIST}>{board.attention.map(capRow)}</Box> : null}
          </Box>
        ) : null}
        {board.changes.length || board.done.length || strayPlans.length ? (
          <Box flexDirection="column">
            {head('changes', 'Changes', board.changes.length + board.done.length + strayPlans.length, isOpen.changes)}
            {isOpen.changes ? (
              <Box key="list-changes" {...LIST}>
                {board.changes.map(changeRow)}
                {strayPlans.map(n => (
                  <Box key={`stray-${n}`} flexDirection="row" gap={1} flexWrap="wrap" alignItems="center">
                    <Text dimColor>○</Text>
                    <Text key={`stray-name-${n}`}>{n}</Text>
                    <Text key={`stray-note-${n}`} italic size="footnote" dimColor>
                      not in {BLUEPRINT_JSON}
                    </Text>
                    <Button key={`prs-${n}`} plain dimColor label="PRs" onPress={() => update($, view, s => ({ ...s, split: n }))} />
                  </Box>
                ))}
                {board.done.length ? (
                  // The arrow sits inside the button, on its text's baseline; the row starts at the left edge.
                  <Box key="done-row" flexDirection="row" marginTop={board.changes.length ? 1 : 0}>
                    <Button
                      key="done-fold"
                      plain
                      dimColor
                      label={`${v.isDoneOpen ? '▼' : '▶'} Done (${board.done.length})`}
                      onPress={() => update($, view, s => ({ ...s, isDoneOpen: !s.isDoneOpen }))}
                    />
                  </Box>
                ) : null}
                {/* Nested under the fold, as every section's list is under its header. */}
                {v.isDoneOpen && board.done.length ? (
                  <Box key="done-list" {...LIST}>
                    {board.done.map(changeRow)}
                  </Box>
                ) : null}
              </Box>
            ) : null}
          </Box>
        ) : null}
        {board.quiet.length ? (
          <Box flexDirection="column">
            {head('sync', board.isCodeChecked ? 'In sync' : 'Capabilities', board.quiet.length, isOpen.sync, specNote)}
            <Box key="list-sync" {...LIST} marginTop={isOpen.sync || unknown.length ? 1 : 0}>
              {/* A grid: a fixed number of equal columns, names in order, so it reads as a table. */}
              {(isOpen.sync ? rowsOf(quiet, cols) : []).map((row, i) => (
                <Box key={`quiet-row-${i}`} flexDirection="row">
                  {row.map(q => {
                    const go = openId(q.page)
                    // Possibly affected: still in sync, marked, its chance shown while the pointer is on the cell (inline on the terminal).
                    const mark = q.unknown ? (
                      <Text color="warning">?</Text>
                    ) : q.maybe ? (
                      <Text color="warning">◔</Text>
                    ) : board.isCodeChecked ? (
                      <Text color="success">✓</Text>
                    ) : (
                      <Text dimColor>·</Text>
                    )
                    return (
                      <Box key={`cell-${q.name}`} width={`${Math.floor(100 / cols)}%`} flexShrink={0} flexDirection="row">
                        {go ? (
                          <Button key={q.page!} plain onPress={go}>
                            {mark} {q.name}
                            {q.pending ? <Text color="suggestion"> · {q.pending} pending</Text> : ''}
                          </Button>
                        ) : (
                          <Text key={`quiet-${q.name}`}>
                            {mark} {q.name}
                          </Text>
                        )}
                        {q.maybe && inlineMaybe ? (
                          <Text dimColor> · possibly affected · {q.maybe}</Text>
                        ) : q.maybe ? (
                          <Box display="none" hover={{ display: 'flex' }}>
                            <Text dimColor> · possibly affected · {q.maybe}</Text>
                          </Box>
                        ) : null}
                      </Box>
                    )
                  })}
                </Box>
              ))}
              {/* A spec that couldn't be read is an error, shown even while the list is folded. */}
              {unknown.map(q => (
                <Text key={`unknown-${q.name}`} dimColor>
                  ? {q.name}: {q.unknown}
                </Text>
              ))}
            </Box>
          </Box>
        ) : board.attention.length ? (
          <Text dimColor>{specNote}</Text>
        ) : null}
        {board.uncovered > 0 ? (
          <Text dimColor>
            {board.uncovered} changed file{board.uncovered === 1 ? '' : 's'} no capability covers
          </Text>
        ) : null}
      </Box>
    )
  })
}
