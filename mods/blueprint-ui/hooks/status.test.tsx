import { expect, test } from 'claude-code/testing'
import type { EngineInterface, On } from 'claude-code'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const UI = 'https://app.notion.com/p/41c43cce21f28110a842d273ad44f951'
const PROPOSE = 'https://app.notion.com/p/41c43cce21f2815c94eeedfd0195028f'
const APPLY = 'https://app.notion.com/p/41c43cce21f281bbb3fef91cff515a26'

/** blueprint.json as the test's repo has it; `marker` is what each page now hashes to. */
function repo() {
  return {
    json: {
      docs: { backend: 'notion' },
      specs: {
        'blueprint/ui': { ref: UI, specVersion: 'aaaaaaaaaaaaaaaa', syncedCommit: 'c1' },
        'blueprint/propose': { ref: PROPOSE, specVersion: 'bbbbbbbbbbbbbbbb', syncedCommit: 'c2' },
        'blueprint/apply': { ref: APPLY, specVersion: 'cccccccccccccccc', syncedCommit: 'c2' },
        'blueprint/new': { ref: null },
      },
      changes: {
        shipped: { review: 'https://app.notion.com/p/41c43cce21f2816c8bc6c76cfdbd313d', status: 'applied' },
        board: {
          review: 'https://app.notion.com/p/41c43cce21f2813c9da1df66003ccfc0',
          brief: 'https://app.notion.com/p/41c43cce21f281e29297f0e5a3f95df2',
          status: 'building',
        },
      },
    } as Record<string, any>,
    drift: [
      { capability: 'blueprint/ui', status: 'code-moved', changed: ['a', 'b', 'c'] },
      { capability: 'blueprint/propose', status: 'in-sync' },
      { capability: 'blueprint/apply', status: 'in-sync' },
      { capability: 'blueprint/new', status: 'no-spec' },
    ] as unknown[] | null,
    unanchored: 'x.md\ny.md\n',
    marker: { [UI]: 'aaaaaaaaaaaaaaaa', [PROPOSE]: 'bbbbbbbbbbbbbbbb', [APPLY]: 'cccccccccccccccc' } as Record<string, string>,
    ran: [] as string[],
    toasts: [] as string[],
    commands: [{ name: 'blueprint:blueprint' }, { name: 'blueprint:blueprint-sync' }, { name: 'blueprint:blueprint-drift' }],
  }
}
type Repo = ReturnType<typeof repo>

const ok = (stdout: string, exitCode = 0, stderr = '') => ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })

type Read = (path: string) => string | undefined
type Run = (argv: readonly string[], cwd: string | undefined) => ReturnType<typeof ok> | undefined

/** The test's engine; `read` and `run` replace the file and process answers when a test needs its own. */
function world(on: On, r: Repo, own: { read?: Read; run?: Run } = {}) {
  on('fs.read', (_, e) => {
    const text = own.read ? own.read(e.path) : JSON.stringify(r.json)
    return text === undefined ? { deny: `ENOENT: ${e.path}` } : { value: text }
  })
  on('tool.list', () => ({ value: [] }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_, e) => {
    r.toasts.push(e.text)
    return { value: undefined }
  })
  on('command.register', () => ({ value: { command: 'blueprint-ui' } }))
  on('command.list', () => ({ value: r.commands.map(c => ({ ...c, description: '', source: 'plugin' as const })) }))
  on('command.run', (_, e) => {
    r.ran.push(`/${e.command} ${e.args}`)
    return { text: '' }
  })
  // The page's text is its URL, so the normalizer below can tell pages apart.
  on('mcp.call', (_, e) => ({ value: { content: [{ type: 'text', text: String(e.args.id) }], isError: false } }))
  on('process.run', (_, e) => {
    const mine = own.run?.(e.argv, e.init?.cwd)
    if (mine) return mine
    const [cmd, script, sub] = e.argv
    if (cmd === 'git') return ok('c2\nc1\n')
    if (script === '.blueprint/drift.py' && sub === 'check') {
      return r.drift ? ok(JSON.stringify(r.drift), 1) : ok('', 2, "python3: can't open file '.blueprint/drift.py': [Errno 2] No such file or directory")
    }
    if (script === '.blueprint/drift.py' && sub === 'unanchored') return ok(r.unanchored)
    if (e.argv.includes('--marker')) return ok(`${r.marker[String(e.init?.stdin)] ?? 'no page'}\n`)
    return ok('## Page\n')
  })
  on('tool.call', () => ({ result: {} }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

const typed = (args = '') =>
  ({ command: 'blueprint-ui', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } }) as const

type Caller = { tool: { call: EngineInterface['tool']['call'] } }
const call = ($: Caller, input: Record<string, unknown>) => $.tool.call(input as unknown as Parameters<EngineInterface['tool']['call']>[0])

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the board puts what needs a step first, on ${surface}`, async ($, on) => {
    const r = repo()
    world(on, r)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    await $.command.run(typed())
    const ui = await $.ui.mount({ ...PANE, surface })

    expect(await ui.find({ type: 'Text', text: '2 need attention · 2 in sync · 1 building' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Needs attention' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'code moved (3 files)' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'no spec yet' })).toBeDefined()
    expect(await ui.find({ key: 'spec:blueprint/new' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /spec side not checked/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^2 changed files no capability covers$/ })).toBeDefined()

    // Changes: the open one with ▶ apply, the applied one folded under Done.
    expect((await ui.find({ key: 'change:board:review' }))?.props?.label).toBe('review')
    expect((await ui.find({ key: 'change:board:brief' }))?.props?.label).toBe('brief')
    expect((await ui.find({ type: 'Text', text: /^building$/ }))?.props).toMatchObject({ italic: true, color: 'warning' })
    expect(await ui.find({ key: 'change:shipped:review' })).toBeUndefined()
    expect((await ui.find({ key: 'done-fold' }))?.props?.label).toBe('▶ Done (1)')
    await ui.press({ key: 'done-fold' })
    expect(await ui.find({ key: 'change:shipped:review' })).toBeDefined()

    // ▶ buttons run the command as typed, by the session's own names.
    await ui.press({ key: 'step-blueprint/ui' })
    await ui.press({ key: 'step-change-board' })
    expect(r.ran).toEqual(['/blueprint:blueprint-sync blueprint/ui', '/blueprint:blueprint apply board'])

    // Sections fold: what needs a step and the changes start open, In sync starts folded.
    expect(await ui.find({ type: 'Text', text: '▼ Needs attention (2)' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: '▶ In sync (2)' })).toBeDefined()
    expect(await ui.find({ key: 'spec:blueprint/propose' })).toBeUndefined()
    await ui.press({ key: 'fold-attention' })
    expect(await ui.find({ type: 'Text', text: 'code moved (3 files)' })).toBeUndefined()
    await ui.press({ key: 'fold-sync' })

    // A name opens its page.
    await ui.press({ key: 'spec:blueprint/propose' })
    expect(await ui.find({ type: 'Text', text: /^blueprint\/propose$/ })).toBeDefined()
    await ui.unmount()
  })
}

test('Check specs finds a teammate edit; a write blueprint stamps puts it back in sync', async ($, on) => {
  const r = repo()
  r.drift = r.drift!.map(d => ({ ...(d as object), status: (d as { status: string }).status === 'no-spec' ? 'no-spec' : 'in-sync', changed: undefined }))
  world(on, r)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run(typed())
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: 'spec moved' })).toBeUndefined()

  // Someone edited blueprint/propose in Notion; blueprint/apply can't be read.
  r.marker[PROPOSE] = 'dddddddddddddddd'
  delete r.marker[APPLY]
  await ui.press({ key: 'check-specs' })
  expect(await ui.find({ type: 'Text', text: 'spec moved' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /spec side checked just now/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^\? blueprint\/apply: the normalizer printed no marker/ })).toBeDefined()
  await ui.press({ key: 'step-blueprint/propose' })
  expect(r.ran).toEqual(['/blueprint:blueprint-drift blueprint/propose'])

  // Blueprint rewrites the spec, then records its marker: the board shows it in sync.
  r.marker[PROPOSE] = 'eeeeeeeeeeeeeeee'
  await call($, { tool: 'mcp__3c44__notion-update-page', page_id: '41c43cce21f2815c94eeedfd0195028f', command: 'replace_content' })
  r.json.specs['blueprint/propose'].specVersion = 'eeeeeeeeeeeeeeee'
  await call($, { tool: 'Edit', file_path: '.blueprint/blueprint.json', old_string: 'x', new_string: 'y' })
  await ui.press({ key: 'back' })
  expect(await ui.find({ type: 'Text', text: 'spec moved' })).toBeUndefined()
  await ui.unmount()
})

test('both sides moved reads drift → sync; a missing command toasts and runs nothing', async ($, on) => {
  const r = repo()
  r.commands = [{ name: 'blueprint:blueprint' }]
  world(on, r)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.command.run(typed())
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  r.marker[UI] = 'ffffffffffffffff'
  await ui.press({ key: 'check-specs' })
  expect(await ui.find({ type: 'Text', text: 'code and spec moved' })).toBeDefined()
  expect((await ui.find({ key: 'step-blueprint/ui' }))?.props?.label).toBe('▶ drift → sync')
  await ui.press({ key: 'step-blueprint/ui' })
  expect(r.ran).toEqual([])
  expect(r.toasts[0]).toContain('No /blueprint-drift command')
  await ui.unmount()
})

test('without drift.py the board says code status is unavailable and suggests /blueprint-setup', async ($, on) => {
  const r = repo()
  r.drift = null
  world(on, r)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run(typed())
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /^Code status unavailable: .blueprint\/drift.py is missing/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /\/blueprint-setup/ })).toBeDefined()
  await ui.unmount()
})

test('a session in a subfolder finds the nearest .blueprint/ and runs drift.py from there', async ($, on) => {
  const r = repo()
  const cwds: string[] = []
  world(on, r, {
    read: path => {
      return path === '/repo/.blueprint/blueprint.json' ? JSON.stringify(r.json) : undefined
    },
    run: (_, cwd) => (cwds.push(String(cwd)), undefined),
  })
  on('session.cwd', () => ({ value: '/repo/mods/blueprint-ui' }))
  await $.session.start({ cwd: '/repo/mods/blueprint-ui', surface: 'terminal', isInteractive: true })
  await $.command.run(typed())
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: 'code moved (3 files)' })).toBeDefined()
  expect(cwds.length > 0 && cwds.every(c => c === '/repo')).toBe(true)
  await ui.unmount()
})
