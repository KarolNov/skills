import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BlueprintUiBlock, BlueprintUiDoc, BlueprintUiItem, BlueprintUiPage } from '../types'
import { blocksOf } from './blocks'
import { candidates, fetchPage } from './notion'
import { BLUEPRINT_JSON, READ_TOOL, labelOf, pageFor, pagesNamed, pagesOf, targetsOf } from './pages'
import { countOf, firstChange, itemFor, oneLine, quoteOf, rowsFor, sameText } from './review'
import type { Map } from './pages'
import { TABS, accentOf } from './tabs'
import type { Mode, TabsProps } from './tabs'

export const PANE = 'blueprint-ui'
const TITLE = 'Blueprint'

const view = atom({ plugin: 'blueprint-ui', key: 'view' } as const, { page: null }, { shape: 'view-1' })
const NO_DOC: BlueprintUiDoc = { page: null, status: 'none' }
const doc = atom({ plugin: 'blueprint-ui', key: 'doc' } as const, NO_DOC, { shape: 'doc-1' })
const NO_ITEMS: BlueprintUiItem[] = []
const pending = atom({ plugin: 'blueprint-ui', key: 'pending' } as const, NO_ITEMS, { shape: 'pending-1' })

/** What each open field holds, by its key, so "Add" can submit it like Enter does. */
const drafts = new Map<string, string>()

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

// The latest page read: an older read that finishes later is dropped.
let lastRead = 0
// Pages whose review is being submitted: a second press waits for the first.
const submitting = new Set<string>()

type Loaded = { map: Map } | { error: 'missing' | 'invalid'; detail?: string }

// blueprint.json is read on every draw: it is small, and a write from blueprint shows at once.
async function load($: EngineInterface): Promise<Loaded> {
  let text: string
  try {
    text = await $.fs.read(BLUEPRINT_JSON)
  } catch {
    return { error: 'missing' }
  }
  try {
    return { map: pagesOf(text) }
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

/**
 * Shows `page` and reads it into `doc`; a later open of another page wins over this read.
 * With `mark`, a page that was showing scrolls to the first block that changed and lights it briefly.
 */
async function openPage(
  $: EngineInterface,
  page: BlueprintUiPage,
  backend: string,
  configured: string,
  mark = false,
): Promise<void> {
  const before = await read($, doc)
  const was = mark && before.page === page.id && before.status === 'ready' ? before.blocks : null
  await update($, view, v => ({ ...v, page: page.id }))
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
  let got = await fetchPage($, page.url, await candidates($, configured))
  // At the start of a session the Notion connection may not be up yet: retry for a while before saying so.
  for (let waited = 0; 'error' in got && got.error === 'no-server' && waited < NOTION_WAIT_MS && ticket === lastRead; waited += NOTION_RETRY_MS) {
    if (!waited) await update($, doc, cur => (cur.page === page.id && cur.status === 'loading' ? { ...cur, isWaiting: true } : cur))
    try {
      await $.clock.sleep(NOTION_RETRY_MS)
    } catch {
      break
    }
    got = await fetchPage($, page.url, await candidates($, configured))
  }
  const next: BlueprintUiDoc =
    'markdown' in got
      ? { page: page.id, status: 'ready', blocks: blocksOf(got.markdown, page.url), readAt: new Date().toISOString() }
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
  if (changed === undefined || shown.status !== 'ready') return
  const readAt = shown.readAt
  try {
    await $.ui.scroll({ to: { key: plusKey(changed) }, in: PANE, block: 'center' })
  } catch {
    // Not drawn, or the pane isn't placed: the highlight still shows.
  }
  $.clock.after(HIGHLIGHT_MS, () => {
    void update($, doc, cur =>
      cur.status === 'ready' && cur.readAt === readAt && cur.changed !== undefined ? withoutChange(cur) : cur,
    )
  })
}

const withoutChange = ({ changed: _, ...rest }: Extract<BlueprintUiDoc, { status: 'ready' }>): BlueprintUiDoc => rest

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
    await $.ui.toast(`Submit failed: /${command} didn't start (${String(err)}). The review is still pending.`)
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
  await openPage($, target, loaded.map.backend, configured, true)
}

export const register: Register = (on, options) => {
  const configured = String(options.notionServer ?? 'claude.ai Notion')

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'blueprint-ui',
      description: 'Open the blueprint pane: reviews, briefs and specs this repo maps',
      argumentHint: '[change or capability] [review|brief]',
    })
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
      if (!toOpen) await update($, view, v => ({ ...v, page: null }))
    }
    await $.ui.open({ id: PANE, title: TITLE })
    if (toOpen && 'map' in loaded) void openPage($, toOpen, loaded.map.backend, configured)
    return { text: note }
  })

  // A write through an MCP tool to a mapped page opens or refreshes the pane once it has run.
  // Awaited, so the pane reads as the page does when the call returns; only writes to mapped pages wait.
  on('tool.call', async ($, e, next) => {
    const result = await next(e)
    const tool = String(e.tool)
    if (!tool.startsWith('mcp__') || 'deny' in result || result.isError || result.isReadOnly || READ_TOOL.test(tool)) return result
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
    await update($, view, v => (v.editor?.block === Number(m[2]) ? { ...v, editor: { ...v.editor, mode } } : v))
    await focusField($, `${mode}-${m[2]}`)
    return {}
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Text, Button, Input, Link, Markdown } = elements
    // Every Button on the desktop is a native button, so there the editor's tab bar is our own.
    const Client = e.surface === 'desktop' && 'Client' in elements ? elements.Client : undefined
    const loaded = await load($)
    if ('error' in loaded) {
      return (
        <Box flexDirection="column">
          {loaded.error === 'missing' ? (
            <Text>This repo isn't set up for blueprint: there is no {BLUEPRINT_JSON}.</Text>
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
      const setEditor = (next: typeof editor) => update($, view, s => ({ ...s, editor: next }))
      /** Opens the editor on a block in `mode` and puts the cursor in its field. */
      const edit = async (b: BlueprintUiBlock, mode: 'comment' | 'suggest') => {
        await setEditor({ page: open.id, block: b.id, quote: quoteOf(b), mode })
        await focusField($, fieldKey(b.id, mode))
      }
      const add = (b: BlueprintUiBlock, kind: BlueprintUiItem['kind'], text: string) => addItem($, open, b, kind, text)
      const remove = (id: string) => update($, pending, list => list.filter(i => i.id !== id))
      const blockOf = (i: BlueprintUiItem) => blocks?.find(b => sameText(quoteOf(b), i.quote))
      const isOutdated = (i: BlueprintUiItem) => blocks !== null && !blockOf(i)

      const kindTag = (i: BlueprintUiItem) =>
        i.kind === 'comment' ? <Text color="suggestion" bold>Comment</Text> : <Text color="success" bold>Suggestion</Text>

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
                  {isOutdated(i) ? <Text color="warning"> · outdated</Text> : null}
                </Text>
                {at ? (
                  <Button key={`goto-${i.id}`} plain dimColor label="↓ show in page" onPress={() => void $.ui.scroll({ to: { key: plusKey(at.id) }, in: PANE, block: 'center' }).catch(() => undefined)} />
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
              <Button key={`cancel-${b.id}`} plain dimColor label="Cancel" onPress={() => (drafts.delete(key), setEditor(null))} />
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
            <Button key="back" plain label="← All pages" onPress={() => update($, view, s => ({ ...s, page: null, editor: null }))} />
            <Button key="refresh" plain label="↻ Refresh" onPress={() => void openPage($, open, backend, configured)} />
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
                        {b.kind === 'link' ? <Link href={b.href} label={`↗ ${b.label} (open in Notion)`} /> : <Markdown key={`b${b.id}`} text={b.text} />}
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

    const changes = pages.filter(p => p.kind !== 'spec')
    const specs = pages.filter(p => p.kind === 'spec')
    const items = await read($, pending)
    const row = (p: BlueprintUiPage) => {
      const n = items.filter(i => i.page === p.id).length
      return (
        <Button key={p.id} plain onPress={() => void openPage($, p, backend, configured)}>
          {labelOf(p)}
          {n ? <Text color="suggestion"> · {n} pending</Text> : ''}
        </Button>
      )
    }
    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>Changes</Text>
          {changes.length ? changes.map(row) : <Text dimColor>No changes yet.</Text>}
        </Box>
        <Box flexDirection="column">
          <Text bold>Specs</Text>
          {specs.length ? specs.map(row) : <Text dimColor>No specs with pages yet.</Text>}
        </Box>
      </Box>
    )
  })
}
