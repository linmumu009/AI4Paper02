import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'

const SAFE_HTML_TAGS = new Set([
  'b', 'blockquote', 'br', 'caption', 'code', 'col', 'colgroup', 'dd', 'del',
  'details', 'div', 'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'hr', 'i', 'kbd', 'li', 'mark', 'ol', 'p', 'pre', 's', 'small', 'span',
  'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th',
  'thead', 'tr', 'u', 'ul',
])

const SECTION_HEADING_RE = /^(?:abstract|introduction|related work|background|preliminaries|method(?:s|ology)?|approach|experiment(?:s|al setup)?|results?(?: and analysis)?|discussion|conclusions?|limitations?|acknowledg(?:e)?ments?|references|appendix|broader impacts?|ethics statement|摘要|引言|相关工作|背景|预备知识|方法|方法论|研究方法|实验|实验设置|结果|结果与分析|讨论|结论|局限性|致谢|参考文献|附录|更广泛影响|伦理声明)$/i
const NUMBERED_HEADING_RE = /^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)(?:[.)])?\s+\S/
const FENCE_RE = /^\s{0,3}(`{3,}|~{3,})/
const MATH_FENCE_RE = /^\s*\${2,}\s*$/
const SAFE_TAG_RE = /<\/?([a-z][a-z0-9]*)(?:\s[^<>]*?)?\s*\/?>/gi
const INLINE_CODE_RE = /(`+)([^`\n]*?)\1/g

const paperMarkdown = new MarkdownIt({ html: true, linkify: true, breaks: true }).use(texmath, {
  engine: katex,
  delimiters: ['dollars', 'brackets', 'beg_end'],
  katexOptions: { throwOnError: false, strict: 'ignore' },
})

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function sanitizeAllowedTag(rawTag: string, rawName: string): string {
  const name = rawName.toLowerCase()
  if (!SAFE_HTML_TAGS.has(name)) return escapeHtml(rawTag)

  const closing = /^<\s*\//.test(rawTag)
  if (closing) return `</${name}>`

  const attrs: string[] = []
  if (name === 'td' || name === 'th') {
    const colspan = rawTag.match(/\bcolspan\s*=\s*["']?(\d{1,3})/i)?.[1]
    const rowspan = rawTag.match(/\browspan\s*=\s*["']?(\d{1,3})/i)?.[1]
    const align = rawTag.match(/\balign\s*=\s*["']?(left|center|right)/i)?.[1]?.toLowerCase()
    const scope = rawTag.match(/\bscope\s*=\s*["']?(row|col|rowgroup|colgroup)/i)?.[1]?.toLowerCase()
    if (colspan && Number(colspan) > 0) attrs.push(`colspan="${Math.min(Number(colspan), 100)}"`)
    if (rowspan && Number(rowspan) > 0) attrs.push(`rowspan="${Math.min(Number(rowspan), 100)}"`)
    if (align) attrs.push(`align="${align}"`)
    if (scope) attrs.push(`scope="${scope}"`)
  }

  const suffix = attrs.length > 0 ? ` ${attrs.join(' ')}` : ''
  return `<${name}${suffix}>`
}

/**
 * Keep the small subset of HTML commonly emitted by MinerU (tables, sup/sub,
 * basic emphasis), while escaping every executable/embedded tag and dropping
 * all event/style attributes. Fenced and inline code stay byte-for-byte intact.
 */
export function sanitizePaperHtml(source: string): string {
  let fenceMarker = ''
  let placeholderIndex = 0

  return source.split('\n').map((line) => {
    const fence = line.match(FENCE_RE)?.[1] ?? ''
    if (fence) {
      if (!fenceMarker) fenceMarker = fence[0]
      else if (fence[0] === fenceMarker) fenceMarker = ''
      return line
    }
    if (fenceMarker) return line

    const codeSpans: Array<{ token: string; value: string }> = []
    const protectedLine = line.replace(INLINE_CODE_RE, (value) => {
      const token = `AI4PAPERSINLINECODE${placeholderIndex++}TOKEN`
      codeSpans.push({ token, value })
      return token
    })

    let sanitized = protectedLine.replace(SAFE_TAG_RE, (rawTag, rawName: string) =>
      sanitizeAllowedTag(rawTag, rawName),
    )
    for (const { token, value } of codeSpans) sanitized = sanitized.replace(token, value)
    return sanitized
  }).join('\n')
}

function isIsolatedLine(lines: string[], index: number): boolean {
  const before = index === 0 || lines[index - 1].trim() === ''
  const after = index === lines.length - 1 || lines[index + 1].trim() === ''
  return before && after
}

function headingLevel(label: string): number {
  const number = label.match(NUMBERED_HEADING_RE)?.[1]
  if (!number) return 2
  const depth = (number.match(/\./g)?.length ?? 0) + 2
  return Math.min(depth, 6)
}

function isLikelyTitle(line: string): boolean {
  if (line.length < 4 || line.length > 240) return false
  if (/^(?:[#>`~$]|[-+*]\s|\d+[.)]\s|https?:\/\/|!\[|<)/.test(line)) return false
  if (/^\|.*\|$/.test(line)) return false
  return true
}

/**
 * Repair Markdown-ish output already stored by older MinerU/translation jobs:
 * - `$$$$` equation fences came from wrapping an already-delimited equation;
 * - MinerU sometimes labels section titles as plain paragraphs;
 * - the first standalone line is the paper title when it is otherwise unmarked.
 */
export function normalizePaperMarkdown(source: string): string {
  const lines = (source || '').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split('\n')
  let inCodeFence = false
  let codeFenceMarker = ''
  let inMathFence = false
  let firstContentSeen = false

  return lines.map((original, index) => {
    const trimmed = original.trim()
    const fence = original.match(FENCE_RE)?.[1] ?? ''
    if (fence) {
      if (!inCodeFence) {
        inCodeFence = true
        codeFenceMarker = fence[0]
      } else if (fence[0] === codeFenceMarker) {
        inCodeFence = false
        codeFenceMarker = ''
      }
      return original
    }
    if (inCodeFence || !trimmed) return original

    if (MATH_FENCE_RE.test(original)) {
      inMathFence = !inMathFence
      return original.replace(/\${4,}/g, () => '$$')
    }
    if (inMathFence) return original

    if (!firstContentSeen) {
      firstContentSeen = true
      if (isIsolatedLine(lines, index) && isLikelyTitle(trimmed)) return `# ${trimmed}`
    }

    if (/^\s{0,3}#{1,6}\s+/.test(original) || !isIsolatedLine(lines, index)) return original
    if (SECTION_HEADING_RE.test(trimmed) || NUMBERED_HEADING_RE.test(trimmed)) {
      const level = headingLevel(trimmed)
      return `${'#'.repeat(level)} ${trimmed}`
    }
    return original
  }).join('\n')
}

export function renderPaperMarkdown(source: string): string {
  const normalized = normalizePaperMarkdown(source)
  return paperMarkdown.render(sanitizePaperHtml(normalized))
}
