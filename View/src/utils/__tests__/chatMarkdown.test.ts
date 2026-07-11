import { describe, expect, it } from 'vitest'
import { renderChatMarkdown } from '../chatMarkdown'

describe('renderChatMarkdown', () => {
  it('renders dollar and bracket LaTeX delimiters with KaTeX', () => {
    const html = renderChatMarkdown([
      'Inline $x^2$ and \\(y_1\\).',
      '',
      '$$\\sum_{i=1}^{n} i$$',
      '',
      '\\[\\frac{a}{b}\\]',
    ].join('\n'))

    expect(html.match(/class="katex"/g)?.length).toBeGreaterThanOrEqual(4)
    expect(html).toContain('katex-display')
  })

  it('renders LaTeX environments', () => {
    const html = renderChatMarkdown('\\begin{align}a&=b+c\\\\d&=e\\end{align}')
    expect(html).toContain('katex-display')
  })

  it('escapes raw HTML from model output', () => {
    const html = renderChatMarkdown('<img src=x onerror="alert(1)">')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })
})
