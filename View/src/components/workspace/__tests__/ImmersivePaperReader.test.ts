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
      objective: { text: '', bullets: [], research_questions: ['长期轨迹中哪些状态值得主动重新激活？'] },
      method: { text: '', bullets: [], architecture_or_paradigm: '主动记忆干预架构', key_mechanisms: ['通过工具调用更新三部分记忆库。'] },
      data: { text: '', bullets: [], datasets_or_materials: ['LongBench-Agent'], data_scale: '6 类长期任务' },
      experiment_or_argumentation: { text: '', bullets: [], design: '比较固定检索与主动干预。', baselines_or_comparators: ['被动 RAG'] },
      metrics: { text: '', bullets: [], metric_names: ['任务成功率'] },
      results: { text: '', bullets: [], numerical_results: ['长期任务成功率提升 18–27%。'] },
      evidence_chain: { text: '', bullets: [], strongly_supported_claims: ['主动干预在长时程任务上更稳定。'] },
      limitations: { text: '', bullets: [], scope_boundaries: ['仅覆盖工具型智能体。'], threats_to_validity: ['仍需在更多真实任务上验证。'] },
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
    expect(wrapper.text()).toContain('研究问题与贡献')
    expect(wrapper.text()).toContain('主动记忆干预架构')
    expect(wrapper.text()).toContain('LongBench-Agent')
    expect(wrapper.text()).toContain('长期任务成功率提升 18–27%')
    expect(wrapper.text()).toContain('局限性与适用边界')
    expect(wrapper.text()).toContain('仍需在更多真实任务上验证。')
    expect(wrapper.text()).toContain('2 / 34')
    expect(wrapper.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('0')

    const relatedTab = wrapper.findAll('[role="tab"]').find(tab => tab.text().includes('相关论文'))
    await relatedTab?.trigger('click')
    expect(wrapper.text()).toContain('长时程记忆增强智能体')
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
    await wrapper.findAll('[role="tab"]').find(tab => tab.text().includes('相关论文'))?.trigger('click')
    await wrapper.find('.immersive-reader__related-paper').trigger('click')

    expect(wrapper.emitted('exit')).toHaveLength(1)
    expect(wrapper.emitted('next')).toHaveLength(1)
    expect(wrapper.emitted('startResearch')).toHaveLength(1)
    expect(wrapper.emitted('compare')).toHaveLength(1)
    expect(wrapper.emitted('selectRelated')).toEqual([[related.paper_id]])
    expect(buttons.filter(button => button.text().includes('与相关文章比较'))).toHaveLength(1)
    expect(buttons.filter(button => button.text().includes('深入追踪这条线索'))).toHaveLength(1)
  })

  it('keeps research context available as a drawer with focused tabs', async () => {
    const wrapper = mount(ImmersivePaperReader, {
      props: {
        paper,
        relatedPapers: [related],
        position: 1,
        total: 2,
      },
    })

    const context = wrapper.find('.immersive-workspace-shell__context')
    expect(context.attributes('data-open')).toBe('false')
    expect(wrapper.text()).toContain('阅读目录')

    await wrapper.find('button[aria-label="打开研究上下文"]').trigger('click')
    expect(context.attributes('data-open')).toBe('true')

    const tabs = wrapper.findAll('[role="tab"]')
    await tabs.find(tab => tab.text().includes('相关论文'))?.trigger('click')
    expect(wrapper.text()).toContain('长时程记忆增强智能体')
    await tabs.find(tab => tab.text().includes('课题'))?.trigger('click')
    expect(wrapper.text()).toContain('登录后可以保存论文、建立课题并持续追踪研究脉络')

    await wrapper.find('.immersive-workspace-shell__context-close').trigger('click')
    expect(context.attributes('data-open')).toBe('false')
  })

  it('reports document reading progress through the shared shell', async () => {
    const wrapper = mount(ImmersivePaperReader, {
      props: {
        paper,
        relatedPapers: [],
        position: 1,
        total: 1,
      },
    })
    const documentPane = wrapper.find('.immersive-workspace-shell__document')
    Object.defineProperties(documentPane.element, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 500, configurable: true },
      scrollTop: { value: 250, configurable: true },
    })

    await documentPane.trigger('scroll')
    expect(wrapper.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('50')
  })
})
