import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ResearchPanel from '../ResearchPanel.vue'

vi.mock('../../api', () => ({
  fetchResearchStream: vi.fn(), fetchResearchSessions: vi.fn(), deleteResearchSession: vi.fn(),
  fetchResearchSession: vi.fn(), fetchResearchContinueRound3: vi.fn(), fetchResearchFollowup: vi.fn(),
  cancelResearchSession: vi.fn(),
}))
vi.mock('../../composables/useResearchStream', () => ({ useResearchStream: () => ({ consumeStream: vi.fn() }) }))
vi.mock('../../composables/useGlobalChat', () => ({ useGlobalChat: () => ({ requestResearch: vi.fn() }) }))
vi.mock('../../composables/useEngagement', () => ({
  useEngagement: () => ({ loaded: ref(false), bestResearchReward: ref(null), loadActiveRewards: vi.fn() }),
}))
vi.mock('../../composables/useEntitlements', () => ({
  useEntitlements: () => ({ loaded: ref(true), canUse: () => true, quotaSummary: () => '0 / 30', limit: () => null, refreshEntitlements: vi.fn() }),
}))

describe('ResearchPanel', () => {
  it('clamps Top N to the available paper count on first render', async () => {
    const paperIds = ['a', 'b', 'c', 'd']
    const wrapper = mount(ResearchPanel, {
      props: { paperIds, paperTitles: Object.fromEntries(paperIds.map(id => [id, `论文 ${id}`])) },
      global: {
        stubs: {
          PaperPickerDialog: true,
          ResearchHistoryDrawer: true,
          UpgradePrompt: true,
          QuotaWarningBanner: true,
          RewardBoostBanner: true,
        },
      },
    })

    const settingsButton = wrapper.get('button[title="研究设置"]')
    expect(settingsButton.text()).toContain('Top 4')
    await settingsButton.trigger('click')
    expect(wrapper.get<HTMLInputElement>('input[type="range"]').element.value).toBe('4')
  })
})
