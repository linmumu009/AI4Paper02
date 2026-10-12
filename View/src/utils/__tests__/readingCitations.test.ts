import { describe, expect, it } from 'vitest'
import { foldReadingCitations } from '../readingCitations'

describe('reading citations', () => {
  it('folds grouped author-year references and preserves text and links for anchors', () => {
    const source = '<p>与研究一致 (Li et al., 2026; <a href="#zhu">Zhu et al., 2026</a>; Wang et al., 2026)，继续阅读 (Smith & Jones, 2025)。</p>'
    const result = new DOMParser().parseFromString(foldReadingCitations(source), 'text/html')
    const original = new DOMParser().parseFromString(source, 'text/html')
    expect(result.body.textContent).toBe(original.body.textContent)
    expect(result.querySelectorAll('.reading-citation-toggle')).toHaveLength(2)
    expect(result.querySelector('a')?.getAttribute('href')).toBe('#zhu')
  })
  it('leaves sections, explanations, numbers, code, math and reference lists intact', () => {
    const source = '<p>（§3）(2 to 53) (LLM) (in 2026) (Figure 3, 2026) <code>(Li et al., 2026)</code><span class="katex">(Li et al., 2026)</span></p><h2>References</h2><p>(Li et al., 2026)</p>'
    expect(foldReadingCitations(source)).not.toContain('reading-citation-toggle')
  })
  it('handles full-width parentheses and multiple groups in the same text node', () => {
    const html = foldReadingCitations('<p>先（Li et al., 2026a），再 (Zhu et al., 2025)。</p>')
    const doc = new DOMParser().parseFromString(html, 'text/html')
    expect(Array.from(doc.querySelectorAll('button')).map(b => b.dataset.citationNumber)).toEqual(['1', '2'])
  })
})
