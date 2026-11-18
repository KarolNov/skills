import type { BlueprintUiBlock } from '../types'

/** One block the pane draws: Markdown text, or a link standing in for what the pane can't draw. */
export type Block = BlueprintUiBlock

const MENTION = /<mention[^>]*\burl="([^"]+)"[^>]*>(.*?)<\/mention>/g
const SELF_MENTION = /<mention[^>]*\burl="([^"]+)"[^>]*\/>/g

/** Inline tags the normalizer leaves (mentions) become Markdown links. */
function inline(text: string): string {
  return text.replace(MENTION, (_, url, label) => `[${label}](${url})`).replace(SELF_MENTION, (_, url) => `<${url}>`)
}

const MEDIA = /^<(image|embed|pdf|file|video|audio|bookmark)\b[^>]*?(\/>|>([\s\S]*?)<\/\1>)\s*$/
const MEDIA_OPEN = /^<(image|embed|pdf|file|video|audio|bookmark)\b/
const PAGE = /^<page\b[^>]*\burl="([^"]+)"[^>]*>([\s\S]*?)<\/page>\s*$/
const HEADING = /^#{1,6}\s+(.*)$/
const TOP_ITEM = /^(?:[-*+]|\d+[.)])\s/
const FENCE = /^\s*(```+|~~~+)/

const MEDIA_LABEL: Record<string, string> = {
  image: 'Image',
  embed: 'Embedded page',
  pdf: 'PDF',
  file: 'File',
  video: 'Video',
  audio: 'Audio',
  bookmark: 'Bookmark',
}

/**
 * Splits a normalized page into blocks: a heading, a paragraph, a table, a code
 * fence, or one top-level list item with its nested lines. Images, embeds and
 * the Mermaid toggles under diagrams become links to the page; a subpage
 * becomes a link to itself.
 */
export function blocksOf(markdown: string, pageUrl: string): Block[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n')
  const out: Block[] = []
  let heading = ''
  let i = 0
  const push = (b: { kind: 'md'; text: string } | { kind: 'link'; label: string; href: string }) =>
    out.push({ ...b, id: out.length, heading })

  while (i < lines.length) {
    const line = lines[i]!
    if (!line.trim()) {
      i++
      continue
    }

    // A code fence, whole.
    const fence = FENCE.exec(line)
    if (fence) {
      const close = fence[1]!
      let j = i + 1
      while (j < lines.length && !lines[j]!.trim().startsWith(close)) j++
      push({ kind: 'md', text: lines.slice(i, Math.min(j + 1, lines.length)).join('\n') })
      i = j + 1
      continue
    }

    // A toggle: diagram source is left out (its image's link stands for it); others show their content.
    if (line.trim() === '<toggle>' || line.startsWith('<toggle ')) {
      let j = i + 1
      let depth = 1
      while (j < lines.length && depth > 0) {
        if (lines[j]!.startsWith('<toggle')) depth++
        if (lines[j]!.trim() === '</toggle>') depth--
        j++
      }
      const inner = lines.slice(i + 1, j - 1)
      if (!inner.some(l => /^\s*```mermaid/.test(l))) {
        const [title = '', ...rest] = inner.filter((l, k) => k > 0 || l.trim())
        const text = [`**▸ ${inline(title.replace(/<[^>]+>/g, '').trim())}**`, ...rest.map(inline)].join('\n').trim()
        push({ kind: 'md', text })
      }
      i = j
      continue
    }

    // Media, possibly with a caption over several lines.
    if (MEDIA_OPEN.test(line)) {
      let j = i
      let chunk = line
      while (!MEDIA.test(chunk) && j + 1 < lines.length) chunk += '\n' + lines[++j]
      const m = MEDIA.exec(chunk)
      const kind = m?.[1] ?? 'embed'
      const caption = (m?.[3] ?? '').replace(/<[^>]+>/g, '').trim()
      const what = MEDIA_LABEL[kind] ?? 'Embed'
      push({ kind: 'link', label: caption ? `${what}: ${caption}` : what, href: pageUrl })
      i = j + 1
      continue
    }

    if (line.startsWith('<page ')) {
      let j = i
      let chunk = line
      while (!PAGE.test(chunk) && j + 1 < lines.length) chunk += '\n' + lines[++j]
      const page = PAGE.exec(chunk)
      if (page) {
        push({ kind: 'link', label: page[2]!.replace(/<[^>]+>/g, '').trim() || 'Subpage', href: page[1]! })
        i = j + 1
        continue
      }
    }

    const h = HEADING.exec(line)
    if (h) {
      heading = h[1]!.replace(/[*`]/g, '').trim()
      push({ kind: 'md', text: inline(line) })
      i++
      continue
    }

    // A table: consecutive pipe rows.
    if (line.trimStart().startsWith('|')) {
      let j = i
      while (j < lines.length && lines[j]!.trimStart().startsWith('|')) j++
      push({ kind: 'md', text: lines.slice(i, j).map(inline).join('\n') })
      i = j
      continue
    }

    // One top-level list item and everything indented under it.
    if (TOP_ITEM.test(line)) {
      let j = i + 1
      while (j < lines.length && lines[j]!.trim() && /^\s+/.test(lines[j]!)) j++
      push({ kind: 'md', text: lines.slice(i, j).map(inline).join('\n') })
      i = j
      continue
    }

    // A paragraph, up to a blank line or the start of another block.
    let j = i + 1
    while (
      j < lines.length &&
      lines[j]!.trim() &&
      !HEADING.test(lines[j]!) &&
      !TOP_ITEM.test(lines[j]!) &&
      !FENCE.test(lines[j]!) &&
      !lines[j]!.startsWith('<')
    )
      j++
    push({ kind: 'md', text: lines.slice(i, j).map(inline).join('\n') })
    i = j
  }
  return out
}
