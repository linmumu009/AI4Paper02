import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ComparePanel from '../ComparePanel.vue'

vi.mock('../../api', () => ({
  fetchCompareStream: vi.fn(),
  saveCompareResult: vi.fn(),
}))

vi.mock('../../composables/useAnalytics', () => ({ trackEvent: vi.fn() }))
vi.mock('../../composables/useEngagement', () => ({
  useEngagement: () => ({
    loaded: ref(false),
    bestCompareReward: ref(null),
    loadActiveRewards: vi.fn(),
    loadStatus: vi.fn(),
    notifyRewardUsed: vi.fn(),
  }),
}))
vi.mock('../../composables/useEntitlements', () => ({
  useEntitlements: () => ({
    loaded: ref(true),
    canUse: () => true,
    quotaSummary: () => '2 / 30',
    limit: () => 30,
    refreshEntitlements: vi.fn(),
  }),
}))

describe('ComparePanel', () => {
  it('renders a responsive comparison brief with real paper sources', () => {
    const wrapper = mount(ComparePanel, {
      props: {
        paperIds: ['2607.08716', '2607.08421'],
        paperTitles: {
          '2607.08716': '主动记忆干预改善长时程智能体',
          '2607.08421': '循环记忆机制的状态空间模型',
        },
        scope: 'kb',
      },
      global: { stubs: { RewardBoostBanner: true, QuotaWarningBanner: true, UpgradePrompt: true } },
    })

    expect(wrapper.find('.compare-workspace').exists()).toBe(true)
    expect(wrapper.text()).toContain('准备比较 2 篇论文')
    expect(wrapper.text()).toContain('主动记忆干预改善长时程智能体')
    expect(wrapper.text()).toContain('局限与适用边界')
    expect(wrapper.text()).toContain('本月对比：2 / 30')
  })

  it('keeps the close action wired to the parent workspace', async () => {
    const wrapper = mount(ComparePanel, {
      props: { paperIds: ['a', 'b'] },
      global: { stubs: { RewardBoostBanner: true, QuotaWarningBanner: true, UpgradePrompt: true } },
    })
    await wrapper.find('.compare-workspace__close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
