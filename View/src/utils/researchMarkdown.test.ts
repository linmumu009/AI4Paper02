import { describe, expect, it } from 'vitest'
import { renderResearchMarkdown } from './researchMarkdown'

describe('renderResearchMarkdown', () => {
  it('turns only known research paper IDs into interactive citations', () => {
    const html = renderResearchMarkdown('结论来自 2607.08716，未知论文 9999.00001 不应可点。', ['2607.08716'])
    expect(html).toContain('data-research-paper-id="2607.08716"')
    expect(html).toContain('>2607.08716</button>')
    expect(html).not.toContain('data-research-paper-id="9999.00001"')
  })

  it('keeps IDs inside code spans as code instead of citations', () => {
    const html = renderResearchMarkdown('命令示例：`2607.08716`', ['2607.08716'])
    expect(html).toContain('<code>2607.08716</code>')
    expect(html).not.toContain('data-research-paper-id')
  })
})
