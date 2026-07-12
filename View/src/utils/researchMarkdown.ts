import MarkdownIt from 'markdown-it'

type ResearchMarkdownEnv = {
  paperIds?: string[]
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const defaultTextRenderer = md.renderer.rules.text

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

md.renderer.rules.text = (tokens, index, options, env: ResearchMarkdownEnv, self) => {
  const rendered = defaultTextRenderer
    ? defaultTextRenderer(tokens, index, options, env, self)
    : md.utils.escapeHtml(tokens[index].content)
  const paperIds = [...new Set(env.paperIds || [])]
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)
  if (!paperIds.length) return rendered

  const pattern = new RegExp(`(${paperIds.map(escapeRegExp).join('|')})`, 'g')
  return rendered.replace(pattern, (paperId) => {
    const safeId = md.utils.escapeHtml(paperId)
    return `<button type="button" class="research-paper-link" data-research-paper-id="${safeId}">${safeId}</button>`
  })
}

export function renderResearchMarkdown(markdown: string, paperIds: string[] = []) {
  return md.render(markdown, { paperIds })
}

export function researchPaperIdFromClick(event: MouseEvent): string | null {
  const target = event.target
  if (!(target instanceof Element)) return null
  return target.closest<HTMLElement>('[data-research-paper-id]')?.dataset.researchPaperId || null
}
