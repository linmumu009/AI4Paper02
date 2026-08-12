import { computed, effectScope, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { usePaperDecisionActions } from '../usePaperDecisionActions'
import {
  applyDiversitySort,
  useResearchWorkspace,
  type ResearchWorkspacePaper,
} from '../useResearchWorkspace'
import { useWorkspaceRouteState } from '../useWorkspaceRouteState'

interface TestPaper extends ResearchWorkspacePaper {
  title: string
}

const samplePapers: TestPaper[] = [
  { paper_id: 'p1', title: 'One', relevance_score: 90, institution_tier: 1, categories: ['cs.AI'] },
  { paper_id: 'p2', title: 'Two', relevance_score: 99, institution_tier: 3, categories: ['cs.LG'] },
  { paper_id: 'p3', title: 'Three', relevance_score: 80, institution_tier: 2, categories: ['cs.AI'] },
  { paper_id: 'p4', title: 'Four', relevance_score: 70, institution_tier: 1, categories: ['cs.CL'] },
]

describe('useResearchWorkspace', () => {
  it('keeps sorting, filtering, selection and history in one state boundary', async () => {
    const papers = ref(samplePapers)
    const workspace = useResearchWorkspace({ papers, pageSize: 2, supportedModes: ['card', 'list'] })

    workspace.sortMode.value = 'relevance'
    await nextTick()
    expect(workspace.displayPapers.value.map(paper => paper.paper_id)).toEqual(['p2', 'p1', 'p3', 'p4'])

    expect(workspace.selectPaperById('p3')).toBe(true)
    expect(workspace.currentIndex.value).toBe(2)
    expect(workspace.listPage.value).toBe(1)

    workspace.rememberCurrentIndex()
    workspace.moveToNext()
    expect(workspace.currentPaper.value?.paper_id).toBe('p4')
    expect(workspace.restorePreviousIndex()).toBe(true)
    expect(workspace.currentPaper.value?.paper_id).toBe('p3')

    workspace.topicFilter.value = 'cs.AI'
    await nextTick()
    expect(workspace.currentIndex.value).toBe(0)
    expect(workspace.history.value).toEqual([])
    expect(workspace.displayPapers.value.map(paper => paper.paper_id)).toEqual(['p1', 'p3'])

    expect(workspace.togglePaperSelection('p1')).toBe(true)
    workspace.selectPaperIds(['p1', 'p3'])
    expect([...workspace.selectedPaperIds.value]).toEqual(['p1', 'p3'])
    workspace.clearPaperSelection()
    expect(workspace.selectedPaperIds.value.size).toBe(0)
  })

  it('interleaves lower-tier papers after every two high-tier papers', () => {
    expect(applyDiversitySort(samplePapers).map(paper => paper.paper_id)).toEqual(['p1', 'p3', 'p2', 'p4'])
  })

  it('activates immersive mode when the focused reader presentation is enabled', () => {
    const workspace = useResearchWorkspace({
      papers: ref(samplePapers),
      supportedModes: ['card', 'list', 'immersive'],
    })
    expect(workspace.setMode('immersive')).toBe(true)
    expect(workspace.mode.value).toBe('immersive')
  })

  it('returns immersive reading to the presentation that opened it', () => {
    const workspace = useResearchWorkspace({
      papers: ref(samplePapers),
      supportedModes: ['card', 'list', 'immersive'],
      immersiveFallbackMode: 'list',
    })

    expect(workspace.enterImmersive()).toBe(true)
    expect(workspace.immersiveReturnMode.value).toBe('card')
    expect(workspace.exitImmersive()).toBe(true)
    expect(workspace.mode.value).toBe('card')

    workspace.setMode('list')
    expect(workspace.enterImmersive('list')).toBe(true)
    expect(workspace.exitImmersive()).toBe(true)
    expect(workspace.mode.value).toBe('list')
  })

  it('does not activate a mode whose presentation has not landed yet', () => {
    const workspace = useResearchWorkspace({
      papers: ref(samplePapers),
      supportedModes: ['card', 'list'],
    })
    expect(workspace.setMode('immersive')).toBe(false)
    expect(workspace.mode.value).toBe('card')
  })
})

describe('useWorkspaceRouteState', () => {
  it('restores the selected mode and paper, then keeps the URL current', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/?view=list&paper=p3')
    await router.isReady()

    const workspace = useResearchWorkspace({
      papers: ref(samplePapers),
      supportedModes: ['card', 'list'],
    })
    const scope = effectScope()
    scope.run(() => {
      useWorkspaceRouteState({
        query: () => router.currentRoute.value.query,
        router,
        mode: workspace.mode,
        currentPaperId: workspace.currentPaperId,
        paperIds: computed(() => workspace.displayPapers.value.map(paper => paper.paper_id)),
        setMode: workspace.setMode,
        selectPaperById: workspace.selectPaperById,
      })
    })
    await nextTick()

    expect(workspace.mode.value).toBe('list')
    expect(workspace.currentPaperId.value).toBe('p3')

    workspace.setMode('card')
    workspace.selectPaperById('p2')
    await nextTick()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toMatchObject({ view: 'card', paper: 'p2' })
    })
    scope.stop()
  })

  it('restores and serializes the immersive return source', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/?view=immersive&paper=p2&source=list')
    await router.isReady()

    const workspace = useResearchWorkspace({
      papers: ref(samplePapers),
      supportedModes: ['card', 'list', 'immersive'],
    })
    const scope = effectScope()
    scope.run(() => {
      useWorkspaceRouteState({
        query: () => router.currentRoute.value.query,
        router,
        mode: workspace.mode,
        currentPaperId: workspace.currentPaperId,
        paperIds: computed(() => workspace.displayPapers.value.map(paper => paper.paper_id)),
        immersiveReturnMode: workspace.immersiveReturnMode,
        setMode: workspace.setMode,
        setImmersiveReturnMode: workspace.setImmersiveReturnMode,
        selectPaperById: workspace.selectPaperById,
      })
    })
    await nextTick()

    expect(workspace.mode.value).toBe('immersive')
    expect(workspace.immersiveReturnMode.value).toBe('list')
    expect(workspace.currentPaperId.value).toBe('p2')

    workspace.exitImmersive()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toMatchObject({ view: 'list', paper: 'p2' })
      expect(router.currentRoute.value.query.source).toBeUndefined()
    })
    scope.stop()
  })
})

describe('usePaperDecisionActions', () => {
  it('redirects anonymous collection attempts without advancing', async () => {
    const advance = vi.fn()
    const redirectToLogin = vi.fn()
    const actions = usePaperDecisionActions({
      currentPaper: computed(() => samplePapers[0]),
      isAuthenticated: ref(false),
      advance,
      redirectToLogin,
      dismissPaper: vi.fn(),
      collectPaper: vi.fn(),
      storage: null,
    })

    await expect(actions.collect()).resolves.toBe(false)
    expect(redirectToLogin).toHaveBeenCalledOnce()
    expect(advance).not.toHaveBeenCalled()
  })

  it('shares collect, dismiss and bookmark behavior across presentations', async () => {
    const advance = vi.fn()
    const collectPaper = vi.fn().mockResolvedValue(undefined)
    const dismissPaper = vi.fn().mockResolvedValue(undefined)
    const onCollect = vi.fn()
    const onDismiss = vi.fn()
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) },
    }
    const currentPaper = computed(() => samplePapers[0])
    const actions = usePaperDecisionActions({
      currentPaper,
      isAuthenticated: ref(true),
      advance,
      redirectToLogin: vi.fn(),
      dismissPaper,
      collectPaper,
      onCollect,
      onDismiss,
      storage,
    })

    await expect(actions.collect()).resolves.toBe(true)
    expect(advance).toHaveBeenCalledWith('right')
    expect(collectPaper).toHaveBeenCalledWith(samplePapers[0])
    expect(onCollect).toHaveBeenCalledWith(samplePapers[0])

    advance.mockClear()
    await expect(actions.collectTarget(samplePapers[1], false)).resolves.toBe(true)
    expect(advance).not.toHaveBeenCalled()
    expect(collectPaper).toHaveBeenCalledWith(samplePapers[1])

    expect(actions.skip()).toBe(true)
    expect(advance).toHaveBeenCalledWith('left')
    expect(dismissPaper).toHaveBeenCalledWith(samplePapers[0])
    expect(onDismiss).toHaveBeenCalledWith(samplePapers[0])

    expect(actions.toggleBookmark()).toBe(true)
    expect(actions.bookmarkedPaperIds.value.has('p1')).toBe(true)
    expect(JSON.parse(values.get('ai4p-bookmarks') ?? '[]')).toContain('p1')
    expect(actions.toggleBookmark()).toBe(false)
    expect(actions.bookmarkedPaperIds.value.has('p1')).toBe(false)

    advance.mockClear()
    expect(actions.toggleBookmarkTarget(samplePapers[1], false)).toBe(true)
    expect(advance).not.toHaveBeenCalled()
  })

  it('keeps the current paper visible and reports collection failures', async () => {
    const advance = vi.fn()
    const error = { response: { status: 403, data: { detail: '知识库论文已达上限' } } }
    const onCollect = vi.fn()
    const onCollectError = vi.fn()
    let resolveCollection: (() => void) | undefined
    const collectPaper = vi.fn(() => new Promise<void>((_resolve, reject) => {
      resolveCollection = () => reject(error)
    }))
    const actions = usePaperDecisionActions({
      currentPaper: computed(() => samplePapers[0]),
      isAuthenticated: ref(true),
      advance,
      redirectToLogin: vi.fn(),
      dismissPaper: vi.fn(),
      collectPaper,
      onCollect,
      onCollectError,
      storage: null,
    })

    const pending = actions.collect()
    expect(actions.collectingPaperIds.value.has('p1')).toBe(true)
    await expect(actions.collect()).resolves.toBe(false)

    resolveCollection?.()
    await expect(pending).resolves.toBe(false)
    expect(advance).not.toHaveBeenCalled()
    expect(onCollect).not.toHaveBeenCalled()
    expect(onCollectError).toHaveBeenCalledWith(error, samplePapers[0])
    expect(actions.collectingPaperIds.value.has('p1')).toBe(false)
  })
})
