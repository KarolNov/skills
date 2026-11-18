import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BlueprintUiBlock, BlueprintUiDoc, BlueprintUiItem, BlueprintUiPage } from '../types'
import { blocksOf } from './blocks'
import { candidates, fetchPage } from './notion'
import { BLUEPRINT_JSON, READ_TOOL, labelOf, pageFor, pagesNamed, pagesOf } from './pages'
import { countOf, itemFor, oneLine, quoteOf, rowsFor, sameText } from './review'
import type { Map } from './pages'

export const PANE = 'blueprint-ui'
const TITLE = 'Blueprint'

const view = atom({ plugin: 'blueprint-ui', key: 'view' } as const, { page: null }, { shape: 'view-1' })
const NO_DOC: BlueprintUiDoc = { page: null, status: 'none' }
const doc = atom({ plugin: 'blueprint-ui', key: 'doc' } as const, NO_DOC, { shape: 'doc-1' })
const NO_ITEMS: BlueprintUiItem[] = []
const pending = atom({ plugin: 'blueprint-ui', key: 'pending' } as const, NO_ITEMS, { shape: 'pending-1' })

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

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

/** Shows `page` and reads it into `doc`; a later open of another page wins over this read. */
async function openPage($: EngineInterface, page: BlueprintUiPage, backend: string, configured: string): Promise<void> {
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
  await update($, doc, (): BlueprintUiDoc => ({ page: page.id, status: 'loading' }))
  const got = await fetchPage($, page.url, await candidates($, configured))
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
  await update($, doc, cur => (cur.page === page.id ? next : cur))
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
  const command = await blueprintCommand($)
  if (!command) {
    await $.ui.toast('Submit failed: no /blueprint command in this session. Install the blueprint plugin.')
    return
  }
  const tmp = await $.process.run(['mktemp', '-d', '-t', 'blueprint-review'])
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
  const sent = new Set(items.map(i => i.id))
  await update($, pending, list => list.filter(i => !sent.has(i.id)))
  void $.command.run({ command, args: `review ${file} — ${countOf(items)} on ${labelOf(page)}` })
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
  await openPage($, target, loaded.map.backend, configured)
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
    await followWrite($, JSON.stringify(e), configured)
    return result
  }).catch(($, e, next) => next(e)) // never in a tool call's way: a failure here passes the call through

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Input, Link, Markdown } = $.ui.resolve(e)
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

      const setEditor = (next: typeof editor) => update($, view, s => ({ ...s, editor: next }))
      const add = (b: BlueprintUiBlock, kind: BlueprintUiItem['kind'], text: string) => {
        const t = text.trim()
        if (!t || (kind === 'suggest' && t === quoteOf(b).trim())) return
        return Promise.all([
          update($, pending, list => [...list, itemFor(open, b, kind, t, newId())]),
          setEditor(null),
        ])
      }
      const remove = (id: string) => update($, pending, list => list.filter(i => i.id !== id))

      const blocks = mine?.status === 'ready' ? mine.blocks : null
      const isOutdated = (i: BlueprintUiItem) => blocks !== null && !blocks.some(b => sameText(quoteOf(b), i.quote))
      const itemLine = (i: BlueprintUiItem, where: boolean) => (
        <Box key={`item-${where ? 'bar' : 'inline'}-${i.id}`} flexDirection="row" gap={1}>
          <Button key={`rm-${where ? 'bar' : 'inline'}-${i.id}`} plain dimColor label="✕" onPress={() => remove(i.id)} />
          <Text>
            <Text color={i.kind === 'comment' ? 'suggestion' : 'success'}>{i.kind === 'comment' ? 'comment' : 'suggestion'}</Text>
            {isOutdated(i) ? <Text color="warning"> outdated</Text> : null}
            {where ? <Text dimColor> · {oneLine(i.heading || '(top of page)', 32)} · “{oneLine(i.quote, 36)}”</Text> : null}
            <Text> {oneLine(i.text, where ? 60 : 90)}</Text>
          </Text>
        </Box>
      )

      // The field sits inside the block indent (2), the box's border and padding (4).
      const fieldColumns = (e.props.bodyColumns ?? 60) - 6
      const editorBox = (b: BlueprintUiBlock, mode: 'comment' | 'suggest') => {
        const quote = quoteOf(b)
        return (
          <Box flexDirection="column" borderStyle="round" paddingX={1} gap={1}>
            <Box flexDirection="row" gap={1}>
              <Button key={`tab-c-${b.id}`} plain={mode !== 'comment' ? true : undefined} variant={mode === 'comment' ? 'primary' : undefined} label="Comment" onPress={() => setEditor({ page: open.id, block: b.id, mode: 'comment' })} />
              <Button key={`tab-s-${b.id}`} plain={mode !== 'suggest' ? true : undefined} variant={mode === 'suggest' ? 'primary' : undefined} label="Suggest change" onPress={() => setEditor({ page: open.id, block: b.id, mode: 'suggest' })} />
              <Button key={`cancel-${b.id}`} plain dimColor label="Cancel" onPress={() => setEditor(null)} />
            </Box>
            {mode === 'comment' ? (
              <Input key={`comment-${b.id}`} placeholder="Leave a comment" submitLabel="add comment" rows={3} autoFocus onSubmit={(t: string) => add(b, 'comment', t)} />
            ) : (
              <Input key={`suggest-${b.id}`} value={quote} submitLabel="add suggestion" rows={rowsFor(quote, fieldColumns)} autoFocus onSubmit={(t: string) => add(b, 'suggest', t)} />
            )}
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
          <Text bold>{labelOf(open)}</Text>
          {here.length > 0 ? (
            <Box flexDirection="column" borderStyle="round" paddingX={1}>
              <Box flexDirection="row" gap={2}>
                <Text bold>Pending review · {countOf(here)}</Text>
                <Button key="submit" variant="primary" label="Submit review" onPress={() => submit($, open, here)} />
                <Button key="discard" plain dimColor label="Discard" onPress={() => update($, pending, list => list.filter(i => i.page !== open.id))} />
              </Box>
              {here.map(i => itemLine(i, true))}
            </Box>
          ) : (
            <Text dimColor>Press + beside a block to comment on it or suggest new wording.</Text>
          )}
          {elsewhere > 0 ? <Text dimColor>{elsewhere} more pending on other pages.</Text> : null}
          {!mine || mine.status === 'loading' ? (
            <Text dimColor>Reading the page…</Text>
          ) : mine.status === 'error' ? (
            <Box flexDirection="column">
              <Text color="error">{mine.message}</Text>
              {mine.hint ? <Text dimColor>{mine.hint}</Text> : null}
            </Box>
          ) : mine.status === 'ready' ? (
            <Box flexDirection="column" gap={1}>
              {mine.blocks.map(b => {
                const onBlock = here.filter(i => sameText(i.quote, quoteOf(b)))
                return (
                  <Box key={`block-${b.id}`} flexDirection="column">
                    <Box flexDirection="row" gap={1}>
                      <Button key={`plus-${b.id}`} plain dimColor label="+" onPress={() => setEditor(editor?.block === b.id ? null : { page: open.id, block: b.id, mode: 'comment' })} />
                      <Box flexDirection="column" flexGrow={1}>
                        {b.kind === 'link' ? <Link href={b.href} label={`↗ ${b.label} (open in Notion)`} /> : <Markdown key={`b${b.id}`} text={b.text} />}
                      </Box>
                    </Box>
                    {onBlock.length > 0 ? <Box flexDirection="column" paddingLeft={2}>{onBlock.map(i => itemLine(i, false))}</Box> : null}
                    {editor?.block === b.id ? editorBox(b, editor.mode) : null}
                  </Box>
                )
              })}
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
