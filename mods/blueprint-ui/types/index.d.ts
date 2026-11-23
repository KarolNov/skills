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

/** The board's folding sections, by whether each is open; unset is the section's default. */
export type BlueprintUiSections = { attention?: boolean; changes?: boolean; sync?: boolean }

/** One PR group of a split change, as apply proposed it through the `split` tool. */
export type BlueprintUiGroup = {
  /** `1`, `2`, … or `specs`. */
  id: string
  name: string
  /** The brief's task numbers it builds, as written: `1, 2`. */
  tasks: string
  /** The default branch's name, or the id of the group it is stacked on. */
  base: string
  /** Groups that must merge before it can start, for a group cut from the default branch that needs their code. */
  after?: string[]
  /** What its session starts with: `/blueprint apply <change> <group>` and a short brief, written by apply. */
  prompt: string
  status: 'planned' | 'starting' | 'started' | 'pr' | 'merged'
  pr?: string
}

/** A change's PR plan; `isApproved` once the user said yes in chat, before which nothing starts. */
export type BlueprintUiSplit = { change: string; defaultBranch: string; isApproved: boolean; groups: BlueprintUiGroup[] }

/** What the pane shows now; `isDoneOpen` and `sections` are the board's folds, for this session. */
export type BlueprintUiView = {
  page: string | null
  /** The change whose PR plan is showing, in place of the board. */
  split?: string | null
  editor?: BlueprintUiEditor | null
  isDoneOpen?: boolean
  sections?: BlueprintUiSections
}

/** One capability in `drift.py check --json`. */
export type BlueprintUiDriftRow = {
  capability: string
  /**
   * `code-moved`: an anchored file changed; `deps-moved`: code it imports (or a failing tagged test)
   * took its drift chance to the threshold; `possibly-affected`: above 0, below the threshold.
   */
  status: 'in-sync' | 'code-moved' | 'deps-moved' | 'possibly-affected' | 'no-spec' | 'no-anchors'
  changed?: string[]
  /** Drift chance, 0 to 1; absent from a drift.py that predates scoring. */
  chance?: number
  confidence?: 'high' | 'medium' | 'low'
  /** What makes up the chance, and why the confidence is not higher. */
  reasons?: string[]
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
  | {
      id: number
      kind: 'link'
      heading: string
      label: string
      href: string
      source: string
      /** An uploaded SVG image's stable `notion-file-block://` reference: the pane draws it where it can. */
      picture?: string
      /** The picture's SVG markup once downloaded; until then, or if it can't be drawn, the link shows. */
      svg?: string
      /** The diagram's terminal version, drawn in box characters: what a terminal shows in its place. */
      diagram?: string
    }

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
      queued: Shaped<string[]>
      working: Shaped<boolean>
      /** PR plans by change, as apply last sent them. */
      splits: Shaped<Record<string, BlueprintUiSplit>>
    }
  }
}
