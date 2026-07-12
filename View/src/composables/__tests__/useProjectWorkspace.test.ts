import { describe, expect, it } from 'vitest'
import type { PaperSummary, ResearchProject } from '../../types/paper'
import { rankProjectCandidates } from '../useProjectWorkspace'

function paper(id: string, title: string, relevance = 0): PaperSummary {
  return {
    institution: 'Test Lab', short_title: title, '📖标题': title, '🌐来源': 'arXiv', paper_id: id,
    '🛎️文章简介': { '🔸研究问题': title, '🔸主要贡献': title },
    '📝重点思路': [], '🔎分析总结': [], '💡个人观点': '', relevance_score: relevance,
  }
}

const project = {
  name: '长期记忆智能体', objective: '如何让长期任务中的智能体主动更新记忆？', description: '关注记忆干预和状态保持。',
  paper_ids: ['existing'],
} as Pick<ResearchProject, 'name' | 'objective' | 'description' | 'paper_ids'>

describe('rankProjectCandidates', () => {
  it('excludes existing papers and ranks project-term matches first', () => {
    const ranked = rankProjectCandidates(project, [
      paper('existing', '主动记忆干预', 1),
      paper('generic', '通用语言模型评测', 0.95),
      paper('memory', '长期记忆智能体的主动状态更新', 0.4),
    ])

    expect(ranked.map(item => item.paper_id)).toEqual(['memory', 'generic'])
  })
})
