import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchPaperDetail } from '../../../api'
import { clearWorkspacePaperDetailCache } from '../../../composables/useWorkspacePaperDetail'
import type { PaperDetailResponse, PaperSummary } from '../../../types/paper'
import ImmersivePaperReader from '../ImmersivePaperReader.vue'

vi.mock('../../../api', () => ({
  fetchPaperDetail: vi.fn(),
  fetchResearchProjects: vi.fn().mockResolvedValue([]),
  addResearchProjectAsset: vi.fn(),
}))

const paper: PaperSummary = {
  institution: 'Meta AI',
  short_title: '主动记忆干预改善长期记忆智能体',
  '📖标题': 'Active Memory Intervention for Long-Horizon Agents',
  '🌐来源': 'arXiv',
  paper_id: '2607.08716',
  '推荐理由': '把记忆更新从被动检索升级为主动干预。',
  '🛎️文章简介': {
    '🔸研究问题': '如何在长期任务中重新激活关键状态？',
    '🔸主要贡献': '提出主动记忆干预框架。',
  },
  '📝重点思路': ['固定间隔观察轨迹', '用结构化记忆更新保持沉默'],
  '🔎分析总结': ['在多项长期任务上稳定提升。'],
  '💡个人观点': '适合持续研究代理。',
  abstract: '本文研究长期任务中的主动记忆干预。',
  relevance_score: 1,
  institution_tier: 1,
  categories: ['cs.AI', 'cs.LG'],
  authors: ['Yifan Wu', 'Lizhu Zhang'],
}

const related: PaperSummary = {
  ...paper,
  paper_id: '2606.04721',
  short_title: '长时程记忆增强智能体',
  '📖标题': 'Long-Horizon Memory-Augmented Agents',
  relevance_score: 0.96,
}

const detail: PaperDetailResponse = {
  summary: { ...paper, authors: [], categories: [] },
  paper_assets: {
    paper_id: paper.paper_id,
    title: paper['📖标题'],
    url: `https://arxiv.org/abs/${paper.paper_id}`,
    year: 2026,
    blocks: {
      method: { text: '', bullets: [], key_mechanisms: ['通过工具调用更新三部分记忆库。'] },
      results: { text: '', bullets: [], numerical_results: ['长期任务成功率提升 18–27%。'] },
      limitations: { text: '', bullets: [], threats_to_validity: ['仍需在更多真实任务上验证。'] },
    },
  },
  date: '2026-07-11',
  images: [],
  arxiv_url: `https://arxiv.org/abs/${paper.paper_id}`,
  pdf_url: `https://arxiv.org/pdf/${paper.paper_id}`,
}

describe('ImmersivePaperReader', () => {
  beforeEach(() => {
    clearWorkspacePaperDetailCache()
    vi.mocked(fetchPaperDetail).mockResolvedValue(detail)
  })

  it('renders the focused reading document with evidence and real related context', async () => {
    const wrapper = mount(ImmersivePaperReader, {
      props: {
        paper,
        relatedPapers: [related],
        publicationDate: '2026-07-11',
        position: 2,
        total: 34,
        canGoPrevious: true,
        canGoNext: true,
      },
    })
    await flushPromises()

    expect(fetchPaperDetail).toHaveBeenCalledWith(paper.paper_id)
    expect(wrapper.text()).toContain('主动记忆干预改善长期记忆智能体')
    expect(wrapper.text()).toContain('Yifan Wu, Lizhu Zhang')
    expect(wrapper.text()).toContain('长期任务成功率提升 18–27%')
    expect(wrapper.text()).toContain('长时程记忆增强智能体')
    expect(wrapper.text()).toContain('2 / 34')
  })

  it('emits navigation and research decisions from the focused workspace', async () => {
    const wrapper = mount(ImmersivePaperReader, {
      props: {
        paper,
        relatedPapers: [related],
        position: 1,
        total: 2,
        canGoPrevious: false,
        canGoNext: true,
        returnMode: 'card',
      },
    })

    const buttons = wrapper.findAll('button')
    await wrapper.find('button[aria-label="返回卡片模式"]').trigger('click')
    await wrapper.find('button[aria-label="下一篇论文"]').trigger('click')
    await buttons.find(button => button.text().includes('深入追踪这条线索'))?.trigger('click')
    await buttons.find(button => button.text().includes('与相关文章比较'))?.trigger('click')
    await wrapper.find('.immersive-reader__related-paper').trigger('click')

    expect(wrapper.emitted('exit')).toHaveLength(1)
    expect(wrapper.emitted('next')).toHaveLength(1)
    expect(wrapper.emitted('startResearch')).toHaveLength(1)
    expect(wrapper.emitted('compare')).toHaveLength(1)
    expect(wrapper.emitted('selectRelated')).toEqual([[related.paper_id]])
    expect(buttons.filter(button => button.text().includes('与相关文章比较'))).toHaveLength(1)
    expect(buttons.filter(button => button.text().includes('深入追踪这条线索'))).toHaveLength(1)
  })
})
