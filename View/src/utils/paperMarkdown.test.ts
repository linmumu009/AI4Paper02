import { describe, expect, it } from 'vitest'
import { normalizePaperMarkdown, renderPaperMarkdown } from './paperMarkdown'

describe('paper Markdown compatibility renderer', () => {
  it('restores MinerU titles, section hierarchy, superscripts and display formulas', () => {
    const source = [
      'ShortOPD: A Reliable Paper Reader',
      '',
      'Qingyu Zhang<sup>2,3</sup>',
      '',
      'Abstract',
      '',
      'Paper abstract.',
      '',
      '1 Introduction',
      '',
      'Introduction text.',
      '',
      '3.1 Attention Tuning',
      '',
      'Method text.',
      '',
      '$$$$',
      '\\hat { y } = q(x) \\tag{1}',
      '$$$$',
    ].join('\n')

    const html = renderPaperMarkdown(source)

    expect(html).toContain('<h1>ShortOPD: A Reliable Paper Reader</h1>')
    expect(html).toContain('<sup>2,3</sup>')
    expect(html).toContain('<h2>Abstract</h2>')
    expect(html).toContain('<h2>1 Introduction</h2>')
    expect(html).toContain('<h3>3.1 Attention Tuning</h3>')
    expect(html).toContain('katex-display')
    expect(html).not.toContain('$$$$')
    expect(html).not.toContain('&lt;sup&gt;')
  })

  it('supports bracket formulas used by translated Markdown', () => {
    const html = renderPaperMarkdown('公式如下：\n\n\\[a^2+b^2=c^2\\]')
    expect(html).toContain('katex-display')
  })

  it('keeps safe paper tables but removes executable tags and attributes', () => {
    const html = renderPaperMarkdown([
      'Paper title',
      '',
      '<table onclick="alert(1)"><tr><th scope="col">A</th><td colspan="2" style="color:red">B</td></tr></table>',
      '',
      '<script>alert("bad")</script>',
    ].join('\n'))

    expect(html).toContain('<table>')
    expect(html).toContain('<th scope="col">A</th>')
    expect(html).toContain('<td colspan="2">B</td>')
    expect(html).not.toContain('onclick')
    expect(html).not.toContain('style=')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('does not reinterpret adjacent numbered prose or inline code', () => {
    const source = [
      'Paper title',
      '',
      '1 Bonus token uncertainty. This is body text rather than a section heading.',
      '2 Acceptance length uncertainty. This adjacent line is in the same extracted block.',
      '',
      '`<script>safe example</script>`',
    ].join('\n')
    const normalized = normalizePaperMarkdown(source)
    const html = renderPaperMarkdown(source)

    expect(normalized).not.toContain('## 1 Bonus token uncertainty')
    expect(html).toContain('<code>&lt;script&gt;safe example&lt;/script&gt;</code>')
  })
})
