/** Wrap unambiguous author/year parentheses without changing the paper text. */
export function foldReadingCitations(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  let number = 0
  let references = false
  for (const element of Array.from(doc.body.querySelectorAll('h1,h2,h3,h4,p'))) {
    if (/^H/.test(element.tagName)) {
      references = /^(?:[\d.]+\s*)?(?:references|bibliography|参考文献)\s*$/i.test(element.textContent?.trim() || '')
      continue
    }
    if (references || element.closest('pre, code, .katex, .reading-citation')) continue
    const walker = doc.createTreeWalker(element, NodeFilter.SHOW_TEXT)
    const nodes: { node: Node; start: number; end: number }[] = []
    let text = ''
    while (walker.nextNode()) {
      const node = walker.currentNode
      nodes.push({ node, start: text.length, end: text.length + (node.textContent?.length || 0) })
      text += node.textContent || ''
    }
    const matches = Array.from(text.matchAll(/\([^()\n]{3,800}\)|（[^（）\n]{3,800}）/g)).filter(match => {
      const entries = match[0].slice(1, -1).split(/[;；]/)
      return entries.every(entry => /^\s*[A-ZÀ-ÖØ-Þ][\p{L}'’.-]*(?:[ \t]+(?:[A-ZÀ-ÖØ-Þ][\p{L}'’.-]*|et\s+al\.|and|&))*\s*,?\s*(?:19|20)\d{2}[a-z]?\s*$/u.test(entry))
    }).map(match => ({ text: match[0], start: match.index!, number: ++number }))
    for (const match of matches.reverse()) {
      const start = nodes.find(item => item.end > match.start)
      const end = nodes.find(item => item.end >= match.start + match.text.length)
      if (!start || !end || start.node.parentElement?.closest('code,.katex') || end.node.parentElement?.closest('code,.katex')) continue
      const range = doc.createRange()
      range.setStart(start.node, match.start - start.start)
      range.setEnd(end.node, match.start + match.text.length - end.start)
      if (Array.from(element.querySelectorAll('code,.katex')).some(node => range.intersectsNode(node))) continue
      const wrapper = doc.createElement('span')
      wrapper.className = 'reading-citation'
      const original = doc.createElement('span')
      original.className = 'reading-citation-text'
      original.append(range.extractContents())
      const button = doc.createElement('button')
      button.type = 'button'
      button.className = 'reading-citation-toggle'
      button.dataset.citationNumber = String(match.number)
      button.setAttribute('aria-label', `查看引用 ${match.number}`)
      button.setAttribute('aria-expanded', 'false')
      wrapper.append(original, button)
      range.insertNode(wrapper)
    }
  }
  return doc.body.innerHTML
}
