/** One page the pane can show: a change's review or brief, or a capability spec. */
export type BlueprintUiPage = {
  /** `change:<name>:review`, `change:<name>:brief` or `spec:<capability>`. */
  id: string
  kind: 'review' | 'brief' | 'spec'
  /** The change or capability name. */
  name: string
  url: string
}

/** The inline editor under a block: GitHub's comment box, with Suggest as its other tab. */
export type BlueprintUiEditor = { page: string; block: number; quote: string; mode: 'comment' | 'suggest' }

/** What the pane shows now; `isDoneOpen` unfolds the board's finished changes, for this session. */
export type BlueprintUiView = { page: string | null; editor?: BlueprintUiEditor | null; isDoneOpen?: boolean }

/** One capability in `drift.py check --json`. */
export type BlueprintUiDriftRow = {
  capability: string
  status: 'in-sync' | 'code-moved' | 'no-spec' | 'no-anchors'
  changed?: string[]
}

/** The code side as last checked by `drift.py`, on every board open and ↻. */
export type BlueprintUiCode =
  | { status: 'none' }
  | { status: 'checking' }
  | {
      status: 'ready'
      report: BlueprintUiDriftRow[]
      /** Changed files since the oldest sync that no capability's anchors cover. */
      uncovered: number
      checkedAt: string
    }
  | { status: 'error'; message: string }

/** The spec side, checked on Check specs and kept for the session: each spec's marker, or why it couldn't be read. */
export type BlueprintUiSpecs = {
  markers: Record<string, { marker: string } | { error: string }>
  /** When the last full check finished; unset until one has. */
  checkedAt?: string
  /** A check running: how many specs are read of how many. */
  progress?: { done: number; total: number }
}

/** One pending comment or suggestion, anchored by heading and quote (never an offset). */
export type BlueprintUiItem = {
  id: string
  /** The page it was made on (BlueprintUiPage.id), and that page's kind and link. */
  page: string
  pageKind: 'review' | 'brief' | 'spec'
  pageUrl: string
  heading: string
  /** The whole block's text as it read when the item was made. */
  quote: string
  kind: 'comment' | 'suggest'
  /** The comment, or the block's suggested new text. */
  text: string
}

/** One block of the open page: Markdown text, or a link in place of what the pane can't draw. */
export type BlueprintUiBlock =
  | { id: number; kind: 'md'; heading: string; text: string; source: string }
  | { id: number; kind: 'link'; heading: string; label: string; href: string; source: string }

/** The open page as last read. */
export type BlueprintUiDoc =
  | {
      page: string
      status: 'loading'
      /** No Notion server answered yet: the session may still be connecting it, so the read is retried. */
      isWaiting?: boolean
    }
  | {
      page: string
      status: 'ready'
      blocks: BlueprintUiBlock[]
      readAt: string
      /** The first block a write changed, highlighted for a moment after the refresh. */
      changed?: number
    }
  | { page: string; status: 'error'; message: string; hint?: string }
  | { page: null; status: 'none' }

declare module 'claude-code' {
  interface PluginState {
    'blueprint-ui': {
      view: Shaped<BlueprintUiView>
      doc: Shaped<BlueprintUiDoc>
      pending: Shaped<BlueprintUiItem[]>
      code: Shaped<BlueprintUiCode>
      specs: Shaped<BlueprintUiSpecs>
      /** Bumped when blueprint.json may have changed, so a board showing it redraws. */
      rev: Shaped<number>
    }
  }
}
