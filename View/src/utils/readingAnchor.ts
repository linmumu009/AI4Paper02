export interface ReadingAnchor {
  start: number
  text: string
  prefix: string
  suffix: string
}

export function captureReadingAnchor(body: HTMLElement, range: Range): ReadingAnchor | null {
  if (!body.contains(range.startContainer) || !body.contains(range.endContainer)) return null
  const text = range.toString()
  if (!text.trim() || text.length > 10000) return null
  const before = range.cloneRange()
  before.selectNodeContents(body)
  before.setEnd(range.startContainer, range.startOffset)
  const start = before.toString().length
  const all = body.textContent ?? ''
  return { start, text, prefix: all.slice(Math.max(0, start - 48), start), suffix: all.slice(start + text.length, start + text.length + 48) }
}

export function locateReadingAnchor(body: HTMLElement, anchor: ReadingAnchor): Range | null {
  const all = body.textContent ?? ''
  let start = anchor.start
  if (all.slice(start, start + anchor.text.length) !== anchor.text || all.slice(Math.max(0, start - anchor.prefix.length), start) !== anchor.prefix) {
    const matches: number[] = []
    let at = all.indexOf(anchor.text)
    while (at !== -1) {
      if ((!anchor.prefix || all.slice(Math.max(0, at - anchor.prefix.length), at) === anchor.prefix)
        && (!anchor.suffix || all.slice(at + anchor.text.length, at + anchor.text.length + anchor.suffix.length) === anchor.suffix)) matches.push(at)
      at = all.indexOf(anchor.text, at + 1)
    }
    if (matches.length !== 1) return null
    start = matches[0]!
  }
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT)
  const range = document.createRange()
  let offset = 0
  let started = false
  while (walker.nextNode()) {
    const node = walker.currentNode
    const length = node.textContent?.length ?? 0
    if (!started && start < offset + length) {
      range.setStart(node, start - offset)
      started = true
    }
    if (started && start + anchor.text.length <= offset + length) {
      range.setEnd(node, start + anchor.text.length - offset)
      return range
    }
    offset += length
  }
  return null
}

export function parseReadingAnchor(hash: string): ReadingAnchor | null {
  try {
    const raw = hash.replace(/^#/, '')
    const value = JSON.parse(raw.startsWith('{') ? raw : decodeURIComponent(raw))
    if (!Number.isSafeInteger(value.start) || value.start < 0 || typeof value.text !== 'string' || !value.text.trim() || value.text.length > 10000
      || typeof value.prefix !== 'string' || value.prefix.length > 48 || typeof value.suffix !== 'string' || value.suffix.length > 48) return null
    return value
  } catch { return null }
}

export function excerptHtml(text: string, href: string): string {
  const escape = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  const link = escape(href)
  return `<blockquote><p><a href="${link}" target="_blank" rel="noopener noreferrer">${escape(text).replace(/\n/g, '<br>')}</a></p></blockquote><p><a href="${link}" target="_blank" rel="noopener noreferrer">返回论文原文 ↗</a></p>`
}
