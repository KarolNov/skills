import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { pickTab, typeInto } from './typing'

const PANE = {
  plugin: 'blueprint-ui',
  component: 'Pane',
  requestId: 'blueprint-ui',
  props: { title: 'Blueprint', isFocused: false, bodyColumns: 70, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const MAP = JSON.stringify({
  docs: { backend: 'notion' },
  specs: { 'upload/retry': { ref: 'https://notion.so/retry' }, 'auth/session': { ref: 'https://notion.so/auth' } },
  changes: {},
})

const RETRY = [
  '## Requirement: Retry on failure',
  '',
  'The client SHALL retry a failed upload at most five times.',
  '',
  '- **Scenario: Flaky network**',
  '  - **WHEN** the first two uploads time out',
  '  - **THEN** the third try succeeds',
  '',
].join('\n')
const AUTH = '## Requirement: Login\n\nThe user SHALL log in with SSO.\n'

function notion(on: On) {
  let last = ''
  on('fs.read', () => ({ value: MAP }))
  on('tool.list', () => ({ value: [] }))
  on('mcp.call', (_, e) => {
    last = JSON.stringify(e)
    return { value: { content: [{ type: 'text', text: 'page' }], isError: false } }
  })
  on('process.run', (_, e) => ({
    value: {
      exitCode: 0,
      stdout: (e.argv as string[])[0] === 'mktemp' ? '/tmp/blueprint-review.X1\n' : last.includes('retry') ? RETRY : AUTH,
      stderr: '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))
}

for (const surface of ['terminal', 'desktop'] as const) {
  // @scenario blueprint/ui: Comment on a block
  // @scenario blueprint/ui: Suggest wording
  // @scenario blueprint/ui: Switch pages
  test(`comment and suggest on blocks, pending review, on ${surface}`, async ($, on) => {
    notion(on)
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'spec:upload/retry' })

    // Blocks: 0 heading, 1 requirement text, 2 scenario.
    // The desktop's tab bar is drawn hidden before any "+", so its code is loaded when one opens.
    if (surface === 'desktop') expect((await ui.find({ key: 'tabs' }))?.props?.props).toMatchObject({ id: '' })
    await ui.press({ key: 'plus-2' })
    await typeInto(ui, 'comment-2', 'why five?')
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^Comment on Requirement: Retry on failure$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^“Scenario: Flaky network WHEN/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Submit hands these to \/blueprint review/ })).toBeDefined()

    // One Add per editor: the desktop field's own button, named for it; on the terminal, Add below.
    // (Focusing the field is the engine's: the kit has no ui.focus.)
    await ui.press({ key: 'plus-0' })
    if (surface === 'desktop') {
      expect(await ui.find({ key: 'add-0' })).toBeUndefined()
      expect((await ui.find({ key: 'comment-0' }))?.props?.submitLabel).toBe('Add comment')
      await typeInto(ui, 'comment-0', 'typed, then Add')
    } else {
      await typeInto(ui, 'comment-0', 'typed, then Add', false)
      await ui.press({ key: 'add-0' })
    }
    expect(await ui.find({ type: 'Text', text: /Pending review · 2 comments$/ })).toBeDefined()
    const extra = await ui.find({ type: 'Button', text: '✕' })
    await ui.press({ key: String(extra?.key) })
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment$/ })).toBeDefined()

    // Suggest starts from the block's text; an unchanged suggestion adds nothing.
    await ui.press({ key: 'plus-1' })
    await pickTab(ui, surface, 1, 'suggest')
    const field = await ui.find({ key: 'suggest-1' })
    expect(field?.props?.value).toBe('The client SHALL retry a failed upload at most five times.')
    await typeInto(ui, 'suggest-1', 'The client SHALL retry a failed upload at most five times.')
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment$/ })).toBeDefined()
    await typeInto(ui, 'suggest-1', 'The client SHALL retry a failed upload at most three times.')
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment and 1 suggestion/ })).toBeDefined()

    // Switch pages and come back: both still pending, and the picker shows the count.
    await ui.press({ key: 'back' })
    expect(await ui.find({ type: 'Text', text: / · 2 pending/ })).toBeDefined()
    await ui.press({ key: 'spec:auth/session' })
    expect(await ui.find({ type: 'Text', text: /2 more pending on other pages/ })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.press({ key: 'spec:upload/retry' })
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 comment and 1 suggestion/ })).toBeDefined()

    // Remove one, then discard the rest.
    const rm = await ui.find({ type: 'Button', text: '✕' })
    await ui.press({ key: String(rm?.key) })
    expect(await ui.find({ type: 'Text', text: /Pending review · 1 suggestion/ })).toBeDefined()
    await ui.press({ key: 'discard' })
    expect(await ui.find({ type: 'Text', text: /Pending review/ })).toBeUndefined()
    await ui.unmount()
  })
}

// @scenario blueprint/ui: Submit
test('Submit review writes one file, runs /blueprint review with it, and clears the batch', async ($, on) => {
  notion(on)
  const ran: { command: string; args?: string }[] = []
  let written = ''
  on('command.list', () => ({ value: [{ name: 'blueprint:blueprint', description: 'Blueprint', source: 'plugin' as const }] }))
  on('fs.write', (_, e) => {
    written = String((e as { text?: string }).text ?? JSON.stringify(e))
    return { value: undefined }
  })
  on('command.run', (_, e) => {
    ran.push({ command: e.command, args: e.args })
    return { text: 'ok' }
  })
  on('ui.toast', () => ({ value: undefined }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'spec:upload/retry' })
  await ui.press({ key: 'plus-2' })
  await typeInto(ui, 'comment-2', 'why five?')
  await ui.press({ key: 'submit' })

  expect(ran).toHaveLength(1)
  expect(ran[0]!.command).toBe('blueprint:blueprint')
  expect(ran[0]!.args).toBe('review /tmp/blueprint-review.X1/review.json — 1 comment on upload/retry')
  const file = JSON.parse(written.includes('"version"') ? written.slice(written.indexOf('{')) : '{}')
  expect(file.page).toEqual({ id: 'spec:upload/retry', kind: 'spec', name: 'upload/retry', url: 'https://notion.so/retry' })
  expect(file.items[0].heading).toBe('Requirement: Retry on failure')
  expect(file.items[0].quote).toContain('Scenario: Flaky network')
  expect(file.items[0].text).toBe('why five?')
  expect(await ui.find({ type: 'Text', text: /Pending review/ })).toBeUndefined()
  await ui.unmount()
})
