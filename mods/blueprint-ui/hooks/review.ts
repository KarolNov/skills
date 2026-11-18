import type { BlueprintUiBlock, BlueprintUiItem, BlueprintUiPage } from '../types'

/** The text an item quotes: the block's own lines on the page, so /blueprint review can find them. */
export const quoteOf = (b: BlueprintUiBlock) => b.source

/** A new pending item on block `b` of `page`. */
export function itemFor(
  page: BlueprintUiPage,
  b: BlueprintUiBlock,
  kind: BlueprintUiItem['kind'],
  text: string,
  id: string,
): BlueprintUiItem {
  return { id, page: page.id, pageKind: page.kind, pageUrl: page.url, heading: b.heading, quote: quoteOf(b), kind, text }
}

/** Squeezes Markdown into one plain line, for the pending list. */
export function oneLine(md: string, max = 70): string {
  const s = md
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>|]/g, '')
    .replace(/^\s*[-+]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

/** "1 comment", "2 suggestions", "1 comment and 2 suggestions". */
export function countOf(items: BlueprintUiItem[]): string {
  const c = items.filter(i => i.kind === 'comment').length
  const s = items.length - c
  const part = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`
  return [c && part(c, 'comment'), s && part(s, 'suggestion')].filter(Boolean).join(' and ') || 'nothing'
}

/**
 * How many rows a field needs to show `text` at `columns` wide, wrapped lines
 * included, between `min` and `max`; past `max` the field scrolls.
 */
export function rowsFor(text: string, columns: number, min = 2, max = 12): number {
  const width = Math.max(10, columns)
  const rows = text.split('\n').reduce((n, line) => n + Math.max(1, Math.ceil(line.length / width)), 0)
  return Math.min(max, Math.max(min, rows))
}

/** Two quotes match when they agree once whitespace and Markdown markup are ignored. */
export function sameText(a: string, b: string): boolean {
  const flat = (s: string) =>
    s
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/[*_`~#>|\\]/g, '')
      .replace(/^\s*(?:[-+]|\d+[.)])\s+/gm, '')
      .replace(/\s+/g, ' ')
      .trim()
  return flat(a) === flat(b)
}
