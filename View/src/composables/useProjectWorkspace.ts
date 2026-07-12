import type { PaperSummary, ResearchProject } from '../types/paper'

function projectTokens(text: string): Set<string> {
  const normalized = text.toLowerCase()
  const tokens = new Set(
    normalized
      .split(/[\s,，。:：;；/\\()（）\[\]]+/)
      .map(token => token.trim())
      .filter(token => token.length >= 2),
  )
  for (const sequence of normalized.match(/[\u3400-\u9fff]{2,}/g) ?? []) {
    for (let index = 0; index < sequence.length - 1; index++) {
      tokens.add(sequence.slice(index, index + 2))
    }
  }
  return tokens
}

function paperSearchText(paper: PaperSummary): string {
  return [
    paper.short_title,
    paper['📖标题'],
    paper.abstract,
    paper.why_recommended,
    paper['推荐理由'],
    paper['🛎️文章简介']?.['🔸研究问题'],
    paper['🛎️文章简介']?.['🔸主要贡献'],
    ...(paper.categories ?? []),
  ].filter(Boolean).join(' ')
}

export function rankProjectCandidates(
  project: Pick<ResearchProject, 'name' | 'objective' | 'description' | 'paper_ids'>,
  papers: PaperSummary[],
  limit = 6,
): PaperSummary[] {
  const projectTerms = projectTokens(`${project.name} ${project.objective} ${project.description}`)
  const existingIds = new Set(project.paper_ids)
  return papers
    .filter(paper => !existingIds.has(paper.paper_id))
    .map((paper) => {
      const paperTerms = projectTokens(paperSearchText(paper))
      let overlap = 0
      projectTerms.forEach((term) => {
        if (paperTerms.has(term)) overlap++
      })
      const relevance = paper.relevance_score == null
        ? 0
        : paper.relevance_score <= 1 ? paper.relevance_score * 100 : paper.relevance_score
      return { paper, rank: overlap * 20 + relevance }
    })
    .sort((a, b) => b.rank - a.rank)
    .slice(0, limit)
    .map(item => item.paper)
}