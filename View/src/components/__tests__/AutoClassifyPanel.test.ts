import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchUserSettings: vi.fn(),
  saveUserSettings: vi.fn(),
  fetchUserLlmPresets: vi.fn(),
  fetchUserPromptPresets: vi.fn(),
  syncAutoClassifyFolders: vi.fn(),
  reclassifyAllKbPapers: vi.fn(),
  fetchAutoClassifyPendingCount: vi.fn(),
  fetchAutoClassifyUnclassifiedCount: vi.fn(),
  suggestAutoClassifyFolders: vi.fn(),
  fetchKbTree: vi.fn(),
}))

vi.mock('../../api', () => api)

import AutoClassifyPanel from '../AutoClassifyPanel.vue'
import PresetSelector from '../PresetSelector.vue'

describe('AutoClassifyPanel', () => {
  beforeEach(() => {
    api.fetchUserSettings.mockResolvedValue({
      settings: {
        enabled: false,
        llm_preset_id: '',
        prompt_preset_id: '',
        confidence_threshold: 0.6,
        folders: [],
      },
    })
    api.fetchUserLlmPresets.mockResolvedValue({ presets: [] })
    api.fetchUserPromptPresets.mockResolvedValue({ presets: [] })
    api.fetchAutoClassifyPendingCount.mockResolvedValue({ pending: 0 })
    api.fetchAutoClassifyUnclassifiedCount.mockResolvedValue({ unclassified: 0 })
    api.fetchKbTree.mockResolvedValue({ folders: [] })
    api.saveUserSettings.mockResolvedValue({ settings: {} })
  })

  it('keeps personal model settings available while automatic classification is off', async () => {
    const wrapper = mount(AutoClassifyPanel)
    await flushPromises()

    expect(wrapper.get('[data-testid="auto-classify-settings-grid"]').classes())
      .not.toContain('pointer-events-none')
    expect(wrapper.get('[data-testid="auto-classify-model-card"]').classes())
      .not.toContain('opacity-40')
    expect(wrapper.get('[data-testid="auto-classify-confidence-card"]').classes())
      .toContain('opacity-40')
    expect(wrapper.get('[data-testid="auto-classify-confidence-input"]').attributes())
      .toHaveProperty('disabled')

    const modelSelector = wrapper.findAllComponents(PresetSelector)[0]
    expect(modelSelector.props('placeholder')).toBe('使用平台默认模型')
    expect(modelSelector.props('noneOption')).toEqual({ label: '使用平台默认模型' })
    expect(modelSelector.props('onGoToCreate')).toBeTypeOf('function')
    modelSelector.props('onGoToCreate')()
    expect(wrapper.emitted('navigate-settings')).toEqual([['llm_presets']])

    wrapper.unmount()
  })
})
