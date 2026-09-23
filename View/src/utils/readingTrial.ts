/** Collapse only recognised source/translation pairs; preserve unmatched quotes. */
export function prepareTrialBilingual(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  for (const quote of Array.from(doc.body.querySelectorAll(':scope > blockquote'))) {
    const marker = quote.nextElementSibling
    if (marker?.tagName !== 'P' || !/^\[?译\]?[：:]?$/.test(marker.textContent?.trim() ?? '')) continue
    const translation = marker.nextElementSibling
    if (!translation || translation.tagName === 'HR' || translation.tagName === 'BLOCKQUOTE') continue
    const details = doc.createElement('details')
    details.className = 'trial-source'
    const summary = doc.createElement('summary')
    summary.textContent = '查看英文原文'
    quote.before(details)
    details.append(summary, quote)
    marker.remove()
  }
  return doc.body.innerHTML
}
