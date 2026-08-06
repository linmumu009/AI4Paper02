import { computed, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { LocationQuery, Router } from 'vue-router'
import { useWorkspaceRouteState } from '../useWorkspaceRouteState'

function setup(initialQuery: LocationQuery) {
  const query = ref<LocationQuery>(initialQuery)
  const mode = ref<'card' | 'list' | 'immersive'>('card')
  const currentPaperId = ref<string | null>(null)
  const syncEnabled = ref(true)
  const replace = vi.fn().mockResolvedValue(undefined)
  const selectPaperById = vi.fn(() => true)

  useWorkspaceRouteState({
    query: () => query.value,
    router: { replace } as unknown as Router,
    mode,
    currentPaperId: computed(() => currentPaperId.value),
    paperIds: computed(() => ['2608.00001']),
    setMode: next => {
      mode.value = next
      return true
    },
    selectPaperById,
    paperQueryKey: 'digest_paper',
    shouldSync: current => syncEnabled.value && !current.tool && !current.tab,
  })

  return { query, mode, currentPaperId, syncEnabled, replace, selectPaperById }
}

describe('useWorkspaceRouteState route ownership', () => {
  it('does not restore a stale digest paper while another workspace owns the route', async () => {
    const state = setup({ tool: 'knowledge', digest_paper: '2608.00001' })
    state.currentPaperId.value = '2608.00001'
    state.mode.value = 'list'
    await nextTick()

    expect(state.selectPaperById).not.toHaveBeenCalled()
    expect(state.replace).not.toHaveBeenCalled()
  })

  it('keeps normal digest deep-link synchronization active', async () => {
    const state = setup({})
    state.currentPaperId.value = '2608.00001'
    await nextTick()

    expect(state.replace).toHaveBeenCalledWith({
      query: {
        view: 'card',
        digest_paper: '2608.00001',
        source: undefined,
      },
    })
  })

  it('honors an explicit route owner before a workspace query is committed', async () => {
    const state = setup({})
    state.syncEnabled.value = false
    state.currentPaperId.value = '2608.00001'
    await nextTick()

    expect(state.replace).not.toHaveBeenCalled()
  })
})
