import type { ClientModule } from 'claude-code'

/**
 * The editor's Comment / Suggest change tab bar on the desktop, where every Button is a
 * native button and none can look like a tab. It draws the labels, the active one bold,
 * colored and underlined, and posts `{ kind: 'mode', id, mode }` when a tab is clicked.
 */
export type TabsProps = {
  /** Which editor it is in now (`comment-3`), or `''` while it waits hidden: one instance moves between editors, so its code loads with the page. */
  id: string
  mode: Mode
}

export type Mode = 'comment' | 'suggest'

export type TabsPost = { kind: 'mode'; id: string; mode: Mode }

/** The tabs, in order. */
export const TABS: readonly { mode: Mode; label: string }[] = [
  { mode: 'comment', label: 'Comment' },
  { mode: 'suggest', label: 'Suggest change' },
]

/** Cells each tab takes: its label and two cells of room either side. */
const tabWidth = (label: string) => label.length + 4

/** The first column of `mode`'s tab. */
export function tabStart(mode: Mode): number {
  let at = 0
  for (const t of TABS) {
    if (t.mode === mode) return at
    at += tabWidth(t.label)
  }
  return at
}

/** The tab under column `x`, if any. */
export function tabAt(x: number): Mode | undefined {
  let at = 0
  for (const t of TABS) {
    if (x >= at && x < at + tabWidth(t.label)) return t.mode
    at += tabWidth(t.label)
  }
  return undefined
}

/** The accent of each tab. */
export const accentOf = (m: Mode) => (m === 'comment' ? 'suggestion' : 'success')

const Tabs: ClientModule<TabsProps> = (props, surface) => {
  const { Box, Text } = surface.elements
  surface.onPointer(e => {
    if (e.type !== 'down' || !props.id) return
    const mode = tabAt(e.x)
    if (mode && mode !== props.mode) surface.post({ kind: 'mode', id: props.id, mode } satisfies TabsPost)
  })
  // With the focus on the bar, the arrow keys switch tabs too.
  surface.onKey(e => {
    if (!props.id || (e.key !== 'left' && e.key !== 'right')) return
    const at = TABS.findIndex(t => t.mode === props.mode)
    const to = TABS[at + (e.key === 'right' ? 1 : -1)]
    if (to) surface.post({ kind: 'mode', id: props.id, mode: to.mode } satisfies TabsPost)
  })
  return (
    <Box flexDirection="row">
      {TABS.map(t =>
        t.mode === props.mode ? (
          <Text key={t.mode}>
            {'  '}
            <Text bold underline color={accentOf(t.mode)}>{t.label}</Text>
            {'  '}
          </Text>
        ) : (
          <Text key={t.mode} dimColor>{`  ${t.label}  `}</Text>
        ),
      )}
    </Box>
  )
}

export default Tabs
