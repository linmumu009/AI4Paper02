import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchPaperDetail } from '../../../api'
import { clearWorkspacePaperDetailCache } from '../../../composables/useWorkspacePaperDetail'
import type { PaperDetailResponse, PaperSummary } from '../../../types/paper'
import PaperInspector from '../PaperInspector.vue'
import WorkspacePaperRow from '../WorkspacePaperRow.vue'

vi.mock('../../../api', () => ({
  fetchPaperDetail: vi.fn(),
  fetchResearchProjects: vi.fn().mockResolvedValue([]),
  addResearchProjectAsset: vi.fn(),
}))

const paper: PaperSummary = {
  institution: 'Meta AI',
  short_title: '长上下文记忆模型的新方法',
  '📖标题': 'A New Method for Long-context Memory Models',
  '🌐来源': 'arXiv',
  paper_id: '2607.08716',
  '推荐理由': '与长上下文记忆研究高度相关。',
  '🛎️文章简介': {
    '🔸研究问题': '如何减少长上下文中的记忆衰减？',
    '🔸主要贡献': '提出统一压缩、检索和重写的记忆框架。',
  },
  '📝重点思路': ['分层压缩长期记忆', '使用奖励信号校准检索'],
  '🔎分析总结': ['在多个长上下文基准上取得稳定提升。'],
  '💡个人观点': '适合用于持续学习型研究代理。',
  relevance_score: 0.97,
  institution_tier: 1,
  categories: ['cs.AI', 'cs.LG'],
  authors: ['Yifan Wu', 'Lizhu Zhang', 'Yankai Lin'],
}

const detailResponse: PaperDetailResponse = {
  summary: { ...paper, abstract: '该工作研究长上下文中的记忆压缩与检索。' },
  paper_assets: {
    paper_id: paper.paper_id,
    title: paper['📖标题'],
    url: `https://arxiv.org/abs/${paper.paper_id}`,
    year: 2026,
    blocks: {
      evidence_chain: {
        text: '',
        bullets: [],
        strongly_supported_claims: ['在四个长上下文任务上平均提升 12.3%。'],
      },
    },
  },
  date: '2026-07-11',
  images: [],
  arxiv_url: `https://arxiv.org/abs/${paper.paper_id}`,
  pdf_url: `https://arxiv.org/pdf/${paper.paper_id}`,
}

describe('WorkspacePaperRow', () => {
  it('renders dense research metadata and emits selection/actions', async () => {
    const wrapper = mount(WorkspacePaperRow, {
      props: {
        paper,
        index: 1,
        active: true,
        selected: false,
        collected: false,
        bookmarked: false,
        publicationDate: '2026-07-11',
      },
    })

    expect(wrapper.text()).toContain('长上下文记忆模型的新方法')
    expect(wrapper.text()).toContain('97')
    expect(wrapper.attributes('aria-selected')).toBe('true')

    await wrapper.trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)

    await wrapper.find('input[type="checkbox"]').trigger('change')
    expect(wrapper.emitted('toggleSelection')).toHaveLength(1)

    const collectButton = wrapper.findAll('button').find(button => button.text() === '收藏')
    expect(collectButton).toBeTruthy()
    await collectButton?.trigger('click')
    expect(wrapper.emitted('collect')).toHaveLength(1)
  })

  it('uses Enter for precision reading', async () => {
    const wrapper = mount(WorkspacePaperRow, {
      props: {
        paper,
        index: 0,
        active: true,
        selected: false,
        collected: false,
        bookmarked: false,
      },
    })
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('open')).toHaveLength(1)
  })

  it('disables collection while the paper is being saved', async () => {
    const wrapper = mount(WorkspacePaperRow, {
      props: {
        paper,
        index: 0,
        active: true,
        selected: false,
        collected: false,
        collecting: true,
        bookmarked: false,
      },
    })
    const collectButton = wrapper.findAll('button').find(button => button.text().includes('收藏中'))
    expect(collectButton?.attributes('disabled')).toBeDefined()
    expect(collectButton?.attributes('aria-busy')).toBe('true')
    await collectButton?.trigger('click')
    expect(wrapper.emitted('collect')).toBeUndefined()
  })
})

describe('PaperInspector', () => {
  beforeEach(() => {
    clearWorkspacePaperDetailCache()
    vi.mocked(fetchPaperDetail).mockResolvedValue({
      ...detailResponse,
      summary: { ...detailResponse.summary, authors: [], categories: [] },
    })
  })

  it('renders immediate summary content and enriches it with structured evidence', async () => {
    const wrapper = mount(PaperInspector, {
      props: {
        paper,
        publicationDate: '2026-07-11',
        collected: false,
        bookmarked: false,
      },
    })
    await flushPromises()

    expect(fetchPaperDetail).toHaveBeenCalledWith(paper.paper_id)
    expect(wrapper.text()).toContain('推荐理由')
    expect(wrapper.text()).toContain('Yifan Wu, Lizhu Zhang')
    expect(wrapper.text()).toContain('如何减少长上下文中的记忆衰减')
    expect(wrapper.text()).toContain('在四个长上下文任务上平均提升 12.3%')

    const collectButton = wrapper.findAll('button').find(button => button.text() === '收藏到知识库')
    await collectButton?.trigger('click')
    expect(wrapper.emitted('collect')).toHaveLength(1)
  })

  it('shows a pending collection state and blocks duplicate submission', async () => {
    const wrapper = mount(PaperInspector, {
      props: {
        paper,
        collecting: true,
      },
    })
    const collectButton = wrapper.findAll('button').find(button => button.text() === '正在收藏…')
    expect(collectButton?.attributes('disabled')).toBeDefined()
    expect(collectButton?.attributes('aria-busy')).toBe('true')
    await collectButton?.trigger('click')
    expect(wrapper.emitted('collect')).toBeUndefined()
  })
})
