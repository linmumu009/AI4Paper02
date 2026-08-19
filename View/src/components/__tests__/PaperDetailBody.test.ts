import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearSummaryDensityPreference } from '../../composables/useSummaryDensity'

const api = vi.hoisted(() => ({
  addKbPaper: vi.fn(),
  fetchPaperResourceStatus: vi.fn(),
  processKbPaper: vi.fn(),
  showToast: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('../../stores/auth', async () => {
  const { ref } = await import('vue')
  return { isAuthenticated: ref(true) }
})

vi.mock('../../api', () => ({
  addKbPaper: api.addKbPaper,
  fetchPaperResourceStatus: api.fetchPaperResourceStatus,
  processKbPaper: api.processKbPaper,
}))

vi.mock('../../composables/useToast', () => ({
  useToast: () => ({
    showToast: api.showToast,
    showError: api.showError,
  }),
}))

import PaperDetailBody from '../PaperDetailBody.vue'

const detail = {
  date: '2026-08-17',
  arxiv_url: 'https://arxiv.org/abs/2601.00001',
  pdf_url: '',
  images: [],
  summary: {
    paper_id: '2601.00001',
    short_title: '测试论文',
    '📖标题': 'A Test Paper',
    institution: '测试机构',
    institution_tier: 4,
  },
} as any

describe('PaperDetailBody resource recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearSummaryDensityPreference()
    api.fetchPaperResourceStatus.mockResolvedValue({
      paper_id: '2601.00001',
      state: 'ready',
      recoverable: false,
    })
  })

  it('explains an expired cache and can save then recover it', async () => {
    api.fetchPaperResourceStatus.mockResolvedValueOnce({
      paper_id: '2601.00001',
      scope: 'kb',
      state: 'expired',
      local_pdf_available: false,
      mineru_available: false,
      saved_to_kb: false,
      recoverable: true,
      action: 'save_and_reprocess',
      message: '本地 PDF 与 MinerU 解析缓存均已过期',
    })
    api.addKbPaper.mockResolvedValueOnce({ paper_id: '2601.00001' })
    api.processKbPaper.mockRejectedValueOnce({
      response: { data: { detail: '处理已在进行中' } },
    })

    const wrapper = mount(PaperDetailBody, {
      props: { detail, effectiveSource: 'recommendation' },
      global: {
        stubs: {
          SummarySection: true,
          AssetsAccordion: true,
          ResearchMemoryPanel: true,
          AddToProjectDialog: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('本地全文资源需要恢复')
    expect(wrapper.text()).toContain('收藏并恢复全文')

    const recoverButton = wrapper.findAll('button')
      .find(button => button.text().includes('收藏并恢复全文'))
    await recoverButton!.trigger('click')
    await flushPromises()

    expect(api.addKbPaper).toHaveBeenCalledWith(
      '2601.00001',
      detail.summary,
      null,
      'kb',
    )
    expect(api.processKbPaper).toHaveBeenCalledWith('2601.00001')
    expect(wrapper.text()).toContain('恢复中')
    expect(api.showError).not.toHaveBeenCalled()
  })

  it('defaults to the detailed version and lets the user switch to concise', async () => {
    const variantDetail = {
      ...detail,
      summary: {
        ...detail.summary,
        short_title: '速览标题',
        '🛎️文章简介': {
          '🔸研究问题': '速览研究问题',
          '🔸主要贡献': '速览主要贡献',
        },
      },
      summary_variants: {
        concise: {
          ...detail.summary,
          short_title: '速览标题',
          '🛎️文章简介': {
            '🔸研究问题': '速览研究问题',
            '🔸主要贡献': '速览主要贡献',
          },
        },
        detailed: {
          ...detail.summary,
          short_title: '详细标题',
          '🛎️文章简介': {
            '🔸研究问题': '详细研究问题',
            '🔸主要贡献': '详细主要贡献',
          },
        },
      },
    } as any

    const wrapper = mount(PaperDetailBody, {
      props: { detail: variantDetail, effectiveSource: 'recommendation' },
      global: {
        stubs: {
          SummarySection: {
            props: ['summary'],
            template: '<div data-test="summary-section">{{ summary[\'🛎️文章简介\'][\'🔸主要贡献\'] }}</div>',
          },
          AssetsAccordion: true,
          ResearchMemoryPanel: true,
          AddToProjectDialog: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('详细标题')
    expect(wrapper.get('[data-test="summary-section"]').text()).toContain('详细主要贡献')

    const conciseButton = wrapper.findAll('button')
      .find(button => button.text().includes('精简版'))
    await conciseButton!.trigger('click')

    expect(wrapper.text()).toContain('速览标题')
    expect(wrapper.get('[data-test="summary-section"]').text()).toContain('速览主要贡献')
    expect(window.localStorage.getItem('ai4papers-summary-density')).toBe('concise')
  })
})
