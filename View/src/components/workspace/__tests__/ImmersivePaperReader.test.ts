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
      objective: {
        text: '', bullets: [],
        research_questions: ['长期轨迹中哪些状态值得主动重新激活？'],
        claimed_contributions: ['提出主动记忆干预框架。'],
      },
      method: {
        text: '以工具型智能体为基座，在执行轨迹中周期性判断是否需要主动更新记忆。',
        bullets: [], input: '智能体执行轨迹', task_or_object: '长期任务中的关键状态保持',
        architecture_or_paradigm: '主动记忆干预架构',
        key_mechanisms: ['通过工具调用更新三部分记忆库。'],
        training_required: false,
        inference_strategy: '按固定间隔评估是否干预记忆。',
      },
      data: { text: '', bullets: [], datasets_or_materials: ['LongBench-Agent'], data_scale: '6 类长期任务' },
      experiment_or_argumentation: {
        text: '', bullets: [], design: '比较固定检索与主动干预。',
        baselines_or_comparators: ['被动 RAG'], ablation_or_counterfactual: '移除主动干预后性能下降。',
      },
      metrics: { text: '', bullets: [], metric_names: ['任务成功率'], evaluation_protocol: '在 6 类任务上统一评测。' },
      results: {
        text: '', bullets: [], numerical_results: ['长期任务成功率提升 18–27%。'],
        main_findings: ['主动干预在长时程任务上更稳定。'],
        mechanism_explanations: ['作者解释：主动更新减少了关键状态遗忘。'],
      },
      evidence_chain: {
        text: '', bullets: [], strongly_supported_claims: ['主动干预在长时程任务上更稳定。'],
        weakly_supported_claims: ['对开放环境的长期泛化尚缺少充分证据。'],
      },
      limitations: { text: '', bullets: [], scope_boundaries: ['仅覆盖工具型智能体。'], threats_to_validity: ['仍需在更多真实任务上验证。'] },
      critical_analysis: {
        text: '', bullets: [], strongest_argument: '跨六类任务的一致增益最有说服力。',
        reproduction_or_extension_priorities: ['在真实开放环境中复现长期任务结果。'],
      },
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
    const groups = wrapper.findAll('.immersive-reader__group')
    const questionGroup = groups.find(group => group.find('h3').text() === '研究问题')
    const contributionGroup = groups.find(group => group.find('h3').text() === '作者声称的贡献')
    expect(questionGroup?.text()).toContain('长期轨迹中哪些状态值得主动重新激活？')
    expect(questionGroup?.text()).not.toContain('提出主动记忆干预框架。')
    expect(contributionGroup?.classes()).toContain('is-claim')
    expect(contributionGroup?.text()).toContain('仍需结合结果与证据核验')
    const methodOverview = groups.find(group => group.find('h3').text() === '方法是什么')
    const implementationGroup = groups.find(group => group.find('h3').text() === '具体怎么实现')
    expect(methodOverview?.text()).toContain('在执行轨迹中周期性判断是否需要主动更新记忆')
    expect(methodOverview?.classes()).toContain('is-wide')
    expect(groups.find(group => group.find('h3').text() === '输入与任务')?.text()).toContain('输入：智能体执行轨迹')
    expect(implementationGroup?.findAll('.immersive-reader__implementation-list li')).toHaveLength(1)
    expect(implementationGroup?.text()).toContain('通过工具调用更新三部分记忆库。')
    expect(groups.find(group => group.find('h3').text() === '训练与优化')?.text()).toContain('无需训练或参数更新')
    expect(wrapper.text()).toContain('主动记忆干预架构')
    expect(wrapper.text()).toContain('LongBench-Agent')
    expect(wrapper.text()).toContain('长期任务成功率提升 18–27%')
    expect(groups.find(group => group.find('h3').text() === '数值证据')?.classes()).toContain('is-evidence')
    expect(groups.find(group => group.find('h3').text() === '机制解释')?.text()).toContain('不等同于已验证的因果机制')
    expect(wrapper.text()).toContain('局限性与适用边界')
    expect(wrapper.text()).toContain('证据支持较弱')
    expect(wrapper.text()).toContain('仍需在更多真实任务上验证。')
    expect(wrapper.text()).toContain('优先复现或扩展')
    expect(wrapper.text()).toContain('2 / 34')
    expect(wrapper.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('0')

    const relatedTab = wrapper.findAll('[role="tab"]').find(tab => tab.text().includes('相关论文'))
    await relatedTab?.trigger('click')
    expect(wrapper.text()).toContain('长时程记忆增强智能体')
  })

  it('normalizes numeric evidence fields and legacy scalar lists without crashing', async () => {
    const irregularDetail = {
      ...detail,
      summary: {
        ...paper,
        authors: 'Xinyan Chen, Ziyu Guo',
        '📝重点思路': '构建 OpenCoF-17K 数据集。',
        '🔎分析总结': '推理令牌进一步提升视频推理能力。',
      },
      paper_assets: {
        ...detail.paper_assets,
        blocks: {
          ...detail.paper_assets?.blocks,
          data: {
            text: '', bullets: [], datasets_or_materials: ['OpenCoF-17K'], data_scale: 17312,
          },
        },
      },
    } as unknown as PaperDetailResponse
    vi.mocked(fetchPaperDetail).mockResolvedValueOnce(irregularDetail)

    const wrapper = mount(ImmersivePaperReader, {
      props: { paper: { ...paper, paper_id: '2607.08763' }, relatedPapers: [], position: 2, total: 4 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Xinyan Chen, Ziyu Guo')
    expect(wrapper.text()).toContain('OpenCoF-17K')
    expect(wrapper.text()).toContain('17312')
    expect(wrapper.text()).toContain('推理令牌进一步提升视频推理能力。')
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
        canCompare: true,
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
