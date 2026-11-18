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

/** What the pane shows now. */
export type BlueprintUiView = { page: string | null; editor?: BlueprintUiEditor | null }

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
  | { page: string; status: 'loading' }
  | { page: string; status: 'ready'; blocks: BlueprintUiBlock[]; readAt: string }
  | { page: string; status: 'error'; message: string; hint?: string }
  | { page: null; status: 'none' }

declare module 'claude-code' {
  interface PluginState {
    'blueprint-ui': {
      view: Shaped<BlueprintUiView>
      doc: Shaped<BlueprintUiDoc>
      pending: Shaped<BlueprintUiItem[]>
    }
  }
}
