import { describe, expect, it } from 'vitest'
import { captureReadingAnchor, locateReadingAnchor, parseReadingAnchor, excerptHtml } from '../readingAnchor'
import { readingPalette, readingPapers } from '../readingPalette'

describe('reading excerpt anchors', () => {
  it('round-trips a selection across formatted text and relocates after a preceding edit', () => {
    const body = document.createElement('div')
    body.innerHTML = '<p>前文。</p><p>这是<strong>论文</strong>的关键结论。</p>'
    const paragraph = body.lastElementChild!
    const range = document.createRange()
    range.setStart(paragraph.firstChild!, 1)
    range.setEnd(paragraph.lastChild!, 5)
    const anchor = captureReadingAnchor(body, range)!
    expect(anchor.text).toBe('是论文的关键结论')
    const decoded = parseReadingAnchor('#' + encodeURIComponent(JSON.stringify(anchor)))!
    expect(locateReadingAnchor(body, decoded)?.toString()).toBe(anchor.text)
    body.prepend(document.createTextNode('新增内容'))
    expect(locateReadingAnchor(body, decoded)?.toString()).toBe(anchor.text)
    paragraph.textContent = '完全改写了的段落'
    expect(locateReadingAnchor(body, decoded)).toBeNull()
  })
  it('rejects invalid anchors and escapes note text', () => {
    expect(parseReadingAnchor('#broken')).toBeNull()
    expect(parseReadingAnchor('#' + JSON.stringify({ start: 0, text: '提高 15%', prefix: '', suffix: '' }))?.text).toBe('提高 15%')
    expect(parseReadingAnchor('#' + encodeURIComponent(JSON.stringify({ start: -1, text: 'x', prefix: '', suffix: '' })))).toBeNull()
    const html = excerptHtml('<img onerror="bad">', '/reading-source/p?x=1&y=2')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
    expect(html).toContain('x=1&amp;y=2')
  })
})

describe('reading paper palette', () => {
  it('supports continuous depth and custom colors', () => {
    expect(readingPalette('custom', 100, '#123456')['--trial-bg']).toBe('rgb(18, 52, 86)')
    expect(readingPalette('green', 10, '')).not.toEqual(readingPalette('green', 70, ''))
    for (const paper of readingPapers) expect(readingPalette(paper.value, 0, '#123456')['--trial-bg']).toBe('rgb(255, 255, 255)')
  })
})
