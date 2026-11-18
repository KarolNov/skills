import type { BlueprintUiPage } from '../types'

export const BLUEPRINT_JSON = '.blueprint/blueprint.json'

type BlueprintJson = {
  docs?: { backend?: string }
  specs?: Record<string, { ref?: string | null; specVersion?: string; syncedCommit?: string | null }>
  changes?: Record<string, { brief?: string; review?: string; status?: string }>
}

/** A capability as blueprint.json records it: its page, if any, and where it last agreed with its code. */
export type SpecEntry = { name: string; ref: string | null; specVersion?: string; syncedCommit?: string }
/** A change and its status (`draft`, `approved`, `building`, `applied`, `abandoned`). */
export type ChangeEntry = { name: string; status: string; review?: string; brief?: string }

export type Map = { backend: string; pages: BlueprintUiPage[]; specs: SpecEntry[]; changes: ChangeEntry[] }

/** The pages blueprint.json maps (each change's review and brief, then each spec that has a page), and its records. */
export function pagesOf(text: string): Map {
  const json = JSON.parse(text) as BlueprintJson
  const pages: BlueprintUiPage[] = []
  const specs: SpecEntry[] = []
  const changes: ChangeEntry[] = []
  for (const [name, c] of Object.entries(json.changes ?? {})) {
    if (c.review) pages.push({ id: `change:${name}:review`, kind: 'review', name, url: c.review })
    if (c.brief) pages.push({ id: `change:${name}:brief`, kind: 'brief', name, url: c.brief })
    changes.push({ name, status: (c.status ?? 'draft').toLowerCase(), ...(c.review ? { review: c.review } : {}), ...(c.brief ? { brief: c.brief } : {}) })
  }
  for (const [name, s] of Object.entries(json.specs ?? {})) {
    if (s.ref) pages.push({ id: `spec:${name}`, kind: 'spec', name, url: s.ref })
    specs.push({
      name,
      ref: s.ref ?? null,
      ...(s.specVersion ? { specVersion: s.specVersion } : {}),
      ...(s.syncedCommit ? { syncedCommit: s.syncedCommit } : {}),
    })
  }
  return { backend: json.docs?.backend ?? 'unknown', pages, specs, changes }
}

/** `/blueprint-ui <change or capability> [review|brief]`: the page it names, if any. */
export function pageFor(pages: BlueprintUiPage[], args: string): BlueprintUiPage | undefined {
  const [name, which] = args.trim().split(/\s+/)
  if (!name) return undefined
  const spec = pages.find(p => p.kind === 'spec' && p.name === name)
  if (spec) return spec
  const kind = which === 'brief' ? 'brief' : 'review'
  return pages.find(p => p.kind === kind && p.name === name) ?? pages.find(p => p.name === name)
}

export const labelOf = (p: BlueprintUiPage) => (p.kind === 'spec' ? p.name : `${p.name} · ${p.kind}`)

const PAGE_ID = /[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}/gi

/** Every Notion-style page id in `text` (a URL, a dashed or bare UUID), as 32 lowercase hex characters. */
export function idsIn(text: string): string[] {
  return [...text.matchAll(PAGE_ID)].map(m => m[0].replace(/-/g, '').toLowerCase())
}

/** The mapped pages a tool call's arguments name, in the order they are named. */
export function pagesNamed(pages: BlueprintUiPage[], args: string): BlueprintUiPage[] {
  const named = idsIn(args)
  const byId = new globalThis.Map(pages.flatMap(p => idsIn(p.url).slice(-1).map(id => [id, p] as const)))
  const out: BlueprintUiPage[] = []
  for (const id of named) {
    const p = byId.get(id)
    if (p && !out.includes(p)) out.push(p)
  }
  return out
}

const TARGET_KEY = /^(?:id|ids|url|urls|parent|parent_id|page_id|page_ids|page_url|database_id|data_source_id|block_id)$/i

/**
 * The strings in a tool call's arguments that name what it writes to: values under id-like keys
 * (`page_id`, `parent`, `id`, …) at any depth, never page content, which may link other pages.
 */
export function targetsOf(args: unknown): string {
  const out: string[] = []
  const walk = (v: unknown, targeted: boolean) => {
    if (typeof v === 'string') {
      if (targeted) out.push(v)
    } else if (Array.isArray(v)) {
      for (const x of v) walk(x, targeted)
    } else if (v && typeof v === 'object') {
      for (const [k, x] of Object.entries(v)) walk(x, targeted || TARGET_KEY.test(k))
    }
  }
  walk(args, false)
  return out.join(' ')
}

/** Tools that only read, by name, for servers that don't declare it: `notion-fetch`, `get_issue`, `list_pages`. */
export const READ_TOOL = /(?:^|__|[-_])(?:fetch|get|query|search|list|read|view|download)(?:$|[-_])/i
