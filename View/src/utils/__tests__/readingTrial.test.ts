import { describe, expect, it } from 'vitest'
import { prepareTrialBilingual } from '../readingTrial'

describe('trial bilingual reading', () => {
  it('keeps translated content visible and source intact inside an accessible disclosure', () => {
    const result = prepareTrialBilingual('<blockquote><p>Source <em>term</em></p></blockquote><p><strong>[译]</strong></p><p>中文内容</p><table><tr><td>12</td></tr></table>')
    const doc = new DOMParser().parseFromString(result, 'text/html')
    expect(doc.querySelector('details summary')?.textContent).toBe('查看英文原文')
    expect(doc.querySelector('details blockquote em')?.textContent).toBe('term')
    expect(doc.querySelector('details')?.hasAttribute('open')).toBe(false)
    expect(doc.querySelector('.trial-pair > p')?.textContent).toBe('中文内容')
    expect(doc.querySelector('.trial-pair')?.firstElementChild?.tagName).toBe('P')
    expect(doc.querySelector('table td')?.textContent).toBe('12')
  })
  it('does not hide ordinary quotations or incomplete translations', () => {
    for (const source of ['<blockquote><p>Quote</p></blockquote><p>Regular paragraph</p>', '<blockquote><p>Pending source</p></blockquote><p>[译]</p><hr>']) {
      expect(prepareTrialBilingual(source)).not.toContain('<details')
    }
  })
})
