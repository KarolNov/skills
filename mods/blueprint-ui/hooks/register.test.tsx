import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

/** A Notion that answers every read with one short page. */
function notion(on: On) {
  on('mcp.call', () => ({ value: { content: [{ type: 'text', text: 'page' }], isError: false } }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: '## Page\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
}

const typed = (args: string) =>
  ({ command: 'blueprint-ui', args, origin: { kind: 'composer' }, presentation: { isFullscreen: true, columns: 120 } }) as const

const MAP = JSON.stringify({
  docs: { backend: 'notion' },
  specs: {
    'auth/session': { ref: 'https://notion.so/a' },
    'billing/invoices': { ref: 'https://notion.so/b' },
    draft: { ref: null },
  },
  changes: { 'add-sso': { brief: 'https://notion.so/brief', review: 'https://notion.so/review' } },
})

test('the picker lists mapped changes and specs, and opens one, on every surface', async ($, on) => {
  on('fs.read', () => ({ value: MAP }))
  notion(on)
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ key: 'change:add-sso:review' })).toBeDefined()
    expect(await ui.find({ key: 'change:add-sso:brief' })).toBeDefined()
    expect(await ui.find({ key: 'spec:auth/session' })).toBeDefined()
    expect(await ui.find({ key: 'spec:draft' })).toBeUndefined()
    await ui.press({ key: 'spec:auth/session' })
    expect(await ui.find({ type: 'Text', text: /^auth\/session$/ })).toBeDefined()
    await ui.press({ key: 'back' })
    expect(await ui.find({ key: 'spec:billing/invoices' })).toBeDefined()
    await ui.unmount()
  }
})

test('without blueprint.json the pane suggests /blueprint-setup', async ($, on) => {
  on('fs.read', () => {
    throw new Error('ENOENT')
  })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /\/blueprint-setup/ })).toBeDefined()
    await ui.unmount()
  }
})

test('/blueprint-ui <name> opens that page', async ($, on) => {
  on('fs.read', () => ({ value: MAP }))
  notion(on)
  on('command.register', () => ({ value: { command: 'blueprint-ui' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  const brief = await $.command.run(typed('add-sso brief'))
  expect(brief.text).toBe('Blueprint pane opened on add-sso · brief.')
  // The read it started has drawn the brief.
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /^add-sso · brief$/ })).toBeDefined()
  expect(await ui.find({ key: 'b0' })).toBeDefined()
  await ui.unmount()

  const missing = await $.command.run(typed('nope'))
  expect(missing.text).toContain('Nothing named "nope"')
})
