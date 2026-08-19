import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { clearSummaryDensityPreference } from '../../composables/useSummaryDensity'

const api = vi.hoisted(() => ({
  fetchPaperDetail: vi.fn(),
  nudgePaper: vi.fn(),
}))

vi.mock('../../api/index', () => ({
  fetchPaperDetail: api.fetchPaperDetail,
  nudgePaper: api.nudgePaper,
}))

vi.mock('../../composables/useEntitlements', () => ({
  useEntitlements: () => ({ tier: ref('free') }),
}))

import PaperCard from '../PaperCard.vue'

const concisePaper = {
  paper_id: '2999.00005',
  institution: '测试机构',
  institution_tier: 2,
  short_title: '速览标题',
  '📖标题': 'A Summary Variant Paper',
  '🌐来源': 'arXiv, 2999.00005',
  '推荐理由': '速览推荐理由',
  '🛎️文章简介': {
    '🔸研究问题': '速览研究问题',
    '🔸主要贡献': '速览主要贡献',
  },
  '📝重点思路': ['速览重点思路'],
  '🔎分析总结': ['速览分析总结'],
  '💡个人观点': '速览个人观点',
  has_detailed_summary: true,
} as any

const detailedPaper = {
  ...concisePaper,
  short_title: '详细标题',
  '推荐理由': '详细推荐理由',
  '🛎️文章简介': {
    '🔸研究问题': '详细研究问题',
    '🔸主要贡献': '详细主要贡献',
  },
  '📝重点思路': ['详细重点思路一', '详细重点思路二'],
}

describe('PaperCard summary variants', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearSummaryDensityPreference()
  })

  it('loads the detailed version on demand while keeping sharing concise', async () => {
    api.fetchPaperDetail.mockResolvedValueOnce({
      summary: concisePaper,
      summary_variants: { concise: concisePaper, detailed: detailedPaper },
      paper_assets: null,
      date: '2026-08-18',
      images: [],
      arxiv_url: '',
      pdf_url: '',
    })

    const wrapper = mount(PaperCard, {
      props: { paper: concisePaper },
      global: {
        stubs: {
          PaperCardShareMenu: {
            name: 'PaperCardShareMenu',
            props: ['paper', 'plainText'],
            template: '<div data-test="share-menu"></div>',
          },
        },
      },
    })

    expect(api.fetchPaperDetail).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('速览主要贡献')

    const detailedButton = wrapper.findAll('button')
      .find(button => button.text().includes('详细版'))
    await detailedButton!.trigger('click')
    await flushPromises()

    expect(api.fetchPaperDetail).toHaveBeenCalledWith('2999.00005')
    expect(wrapper.text()).toContain('详细主要贡献')
    expect(wrapper.text()).toContain('分享仍使用精简版')

    const shareMenu = wrapper.findComponent({ name: 'PaperCardShareMenu' })
    expect(shareMenu.props('paper')).toEqual(concisePaper)
    expect(shareMenu.props('plainText')).toContain('速览主要贡献')
    expect(shareMenu.props('plainText')).not.toContain('详细主要贡献')
  })

  it('disables detailed mode without making a detail request when unavailable', async () => {
    const wrapper = mount(PaperCard, {
      props: {
        paper: { ...concisePaper, has_detailed_summary: false },
      },
      global: {
        stubs: {
          PaperCardShareMenu: true,
        },
      },
    })

    const detailedButton = wrapper.findAll('button')
      .find(button => button.text().includes('详细版'))

    expect(detailedButton?.attributes('disabled')).toBeDefined()
    await detailedButton!.trigger('click')
    await flushPromises()
    expect(api.fetchPaperDetail).not.toHaveBeenCalled()
  })
})
