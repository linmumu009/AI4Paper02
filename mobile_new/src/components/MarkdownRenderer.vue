<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content: string
  readerMode?: 'mineru' | 'zh' | 'bilingual'
}>()

// Simple markdown to HTML renderer for mobile
// Handles: headers, bold, italic, code blocks, inline code, lists, horizontal rules, links
const html = computed(() => {
  let text = props.content || ''

  // Code blocks (must come first)
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="md-code-block"><code>${escapeHtml(code.trim())}</code></pre>`
  })

  // Tables (simplified: just make it scroll horizontally)
  text = text.replace(/((?:\|[^\n]+\|\n)+)/g, (match) => {
    return `<div class="md-table-wrapper"><table class="md-table">${parseTable(match)}</table></div>`
  })

  // Headers
  text = text.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>')
  text = text.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>')
  text = text.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>')

  // Bold + italic
  text = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')

  // Horizontal rule
  text = text.replace(/^---+$/gm, '<hr class="md-hr" />')

  // Unordered list
  text = text.replace(/^[-*] (.+)$/gm, '<li class="md-li">$1</li>')
  text = text.replace(/(<li class="md-li">[\s\S]*?<\/li>)\n(?!<li)/g, '<ul class="md-ul">$1</ul>\n')

  // Ordered list
  text = text.replace(/^\d+\. (.+)$/gm, '<li class="md-oli">$1</li>')

  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a class="md-link" href="$2" target="_blank" rel="noopener">$1</a>')

  // Bilingual: wrap consecutive non-blank lines in paired <span> blocks
  // Bilingual format: EN line followed by ZH line, separated by blank lines in pairs
  if (props.readerMode === 'bilingual') {
    text = applyBilingualHighlight(text)
  }

  // Paragraphs (wrap consecutive non-tag lines)
  const lines = text.split('\n')
  const result: string[] = []
  let inPara = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      if (inPara) { result.push('</p>'); inPara = false }
      continue
    }
    if (trimmed.startsWith('<') && !trimmed.startsWith('<code') && !trimmed.startsWith('<strong') && !trimmed.startsWith('<em') && !trimmed.startsWith('<a')) {
      if (inPara) { result.push('</p>'); inPara = false }
      result.push(line)
    } else {
      if (!inPara) { result.push('<p class="md-p">'); inPara = true }
      result.push(line)
    }
  }
  if (inPara) result.push('</p>')
  return result.join('\n')
})

// Bilingual highlight: wrap every other paragraph (Chinese) in a highlight span
function applyBilingualHighlight(text: string): string {
  // Split by double newlines to find paragraph pairs
  const blocks = text.split(/\n\n+/)
  return blocks.map((block, i) => {
    // Even index = English, Odd index = Chinese (highlight)
    if (i % 2 === 1 && block.trim() && !block.trim().startsWith('<h') && !block.trim().startsWith('<pre') && !block.trim().startsWith('<div')) {
      return `<span class="bilingual-zh">${block}</span>`
    }
    return block
  }).join('\n\n')
}

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function parseTable(raw: string): string {
  const rows = raw.trim().split('\n').filter((r) => r.trim())
  return rows
    .map((row, i) => {
      if (row.match(/^\s*\|[\s-:|]+\|\s*$/)) return ''
      const cells = row.split('|').filter((_, ci) => ci !== 0 && ci !== row.split('|').length - 1)
      const tag = i === 0 ? 'th' : 'td'
      return `<tr>${cells.map((c) => `<${tag} class="md-td">${c.trim()}</${tag}>`).join('')}</tr>`
    })
    .join('')
}
</script>

<template>
  <div
    class="md-content"
    :class="{
      'md-mode-mineru': readerMode === 'mineru',
      'md-mode-zh': readerMode === 'zh',
      'md-mode-bilingual': readerMode === 'bilingual',
    }"
    v-html="html"
  />
</template>

<style>
.md-content { color: var(--color-text-primary); font-size: var(--reader-font-size, 14px); line-height: 1.7; word-break: break-word; }
.md-h1 { font-size: 1.25em; font-weight: 700; margin: 20px 0 10px; color: var(--color-text-primary); }
.md-h2 { font-size: 1.1em; font-weight: 600; margin: 16px 0 8px; color: var(--color-text-primary); border-bottom: 1px solid var(--color-border); padding-bottom: 4px; }
.md-h3 { font-size: 1em; font-weight: 600; margin: 12px 0 6px; color: var(--color-tinder-blue); }
.md-p { margin: 0 0 12px; color: var(--color-text-secondary); }
.md-ul { margin: 4px 0 12px; padding-left: 0; list-style: none; }
.md-li { position: relative; padding-left: 16px; margin-bottom: 4px; color: var(--color-text-secondary); font-size: 0.93em; line-height: 1.6; }
.md-li::before { content: '·'; position: absolute; left: 0; color: var(--color-tinder-pink); font-weight: bold; }
.md-oli { padding-left: 4px; margin-bottom: 4px; color: var(--color-text-secondary); font-size: 0.93em; line-height: 1.6; }
.md-hr { border: none; border-top: 1px solid var(--color-border); margin: 16px 0; }
.md-code-block { background: var(--color-bg-elevated); border: 1px solid var(--color-border); border-radius: 10px; padding: 14px; overflow-x: auto; margin: 12px 0; font-size: 0.85em; line-height: 1.6; color: var(--color-text-secondary); font-family: 'Fira Code', 'Consolas', monospace; word-break: break-word; white-space: pre-wrap; }
.md-inline-code { background: var(--color-bg-elevated); border: 1px solid var(--color-border); border-radius: 4px; padding: 1px 5px; font-size: 0.85em; font-family: 'Fira Code', 'Consolas', monospace; color: var(--color-tinder-blue); }
.md-link { color: var(--color-tinder-blue); text-decoration: underline; text-underline-offset: 2px; }
.md-table-wrapper { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 12px 0; border-radius: 8px; border: 1px solid var(--color-border); max-width: 100%; }
.md-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.md-td { padding: 8px 12px; border: 1px solid var(--color-border); color: var(--color-text-secondary); text-align: left; vertical-align: top; word-break: break-word; }
th.md-td { background: var(--color-bg-elevated); font-weight: 600; color: var(--color-text-primary); }

/* ── Bilingual highlight ── */
.bilingual-zh {
  display: block;
  background: hsla(var(--bilingual-hue, 195), var(--bilingual-saturation, 70%), 55%, calc(var(--bilingual-intensity, 6) * 1%));
  border-left: 3px solid hsl(var(--bilingual-hue, 195), var(--bilingual-saturation, 70%), 55%);
  border-radius: 0 6px 6px 0;
  padding: 6px 10px;
  margin: 4px 0 12px;
  color: var(--color-text-primary);
  line-height: 1.75;
}
</style>
