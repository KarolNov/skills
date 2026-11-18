import { tabStart } from './tabs'

// Test helpers: type into the editor's field, and switch its tab, the way each surface takes it.

type Ui = {
  input: (t: { key: string; text: string; kind?: 'change' | 'submit' }) => Promise<unknown>
  press: (t: { key: string }) => Promise<unknown>
  pointer: (e: { type: 'down' | 'up'; x: number; y: number; button?: 'left'; in?: string }) => Promise<void>
}

/** Types `text` into the field `key` and, unless `submit` is false, presses Enter. */
export async function typeInto(ui: Ui, key: string, text: string, submit = true): Promise<void> {
  await ui.input({ key, text, kind: submit ? 'submit' : 'change' })
}

/** Switches block `block`'s editor to a tab: a plain Button on the terminal, a click in the tab bar on the desktop. */
export async function pickTab(ui: Ui, surface: 'terminal' | 'desktop', block: number, mode: 'comment' | 'suggest'): Promise<void> {
  if (surface === 'terminal') {
    await ui.press({ key: `tab-${mode[0]}-${block}` })
    return
  }
  const x = tabStart(mode) + 2
  await ui.pointer({ type: 'down', x, y: 0, button: 'left', in: 'tabs' })
  await ui.pointer({ type: 'up', x, y: 0, button: 'left', in: 'tabs' })
}
