import { ref, watch, type ComputedRef, type Ref } from 'vue'
import type { LocationQuery, LocationQueryRaw, Router } from 'vue-router'
import {
  isResearchWorkspaceMode,
  type ResearchWorkspaceBaseMode,
  type ResearchWorkspaceMode,
} from './useResearchWorkspace'

interface UseWorkspaceRouteStateOptions {
  query: () => LocationQuery
  router: Router
  mode: Ref<ResearchWorkspaceMode>
  currentPaperId: ComputedRef<string | null>
  paperIds: ComputedRef<string[]>
  immersiveReturnMode?: Ref<ResearchWorkspaceBaseMode>
  setMode: (mode: ResearchWorkspaceMode) => boolean
  setImmersiveReturnMode?: (mode: ResearchWorkspaceBaseMode) => boolean
  selectPaperById: (paperId: string) => boolean
  modeQueryKey?: string
  paperQueryKey?: string
  sourceQueryKey?: string
  shouldSync?: (query: LocationQuery) => boolean
}

function singleQueryValue(value: LocationQuery[string]): string | null {
  if (Array.isArray(value)) return value[0] ?? null
  return value ?? null
}

export function useWorkspaceRouteState(options: UseWorkspaceRouteStateOptions) {
  const modeQueryKey = options.modeQueryKey ?? 'view'
  const paperQueryKey = options.paperQueryKey ?? 'paper'
  const sourceQueryKey = options.sourceQueryKey ?? 'source'
  const pendingPaperId = ref<string | null>(singleQueryValue(options.query()[paperQueryKey]))
  let applyingRouteState = false

  watch(
    () => [
      singleQueryValue(options.query()[modeQueryKey]),
      singleQueryValue(options.query()[paperQueryKey]),
      singleQueryValue(options.query()[sourceQueryKey]),
      options.paperIds.value.join('\u0000'),
      options.shouldSync?.(options.query()) ?? true,
    ] as const,
    ([routeMode, routePaperId, routeSource, _paperIds, shouldSync]) => {
      applyingRouteState = true
      if (!shouldSync) {
        pendingPaperId.value = null
        applyingRouteState = false
        return
      }
      if (isResearchWorkspaceMode(routeMode)) options.setMode(routeMode)
      if (
        routeMode === 'immersive'
        && (routeSource === 'card' || routeSource === 'list')
      ) {
        options.setImmersiveReturnMode?.(routeSource)
      }
      if (routePaperId) pendingPaperId.value = routePaperId
      if (pendingPaperId.value && options.selectPaperById(pendingPaperId.value)) {
        pendingPaperId.value = null
      }
      applyingRouteState = false
    },
    { immediate: true },
  )

  watch(
    () => [
      options.mode.value,
      options.currentPaperId.value,
      options.immersiveReturnMode?.value ?? null,
    ] as const,
    ([mode, paperId, immersiveReturnMode]) => {
      if (applyingRouteState || !paperId) return
      const currentQuery = options.query()
      if (options.shouldSync && !options.shouldSync(currentQuery)) return
      const routeMode = singleQueryValue(currentQuery[modeQueryKey])
      const routePaperId = singleQueryValue(currentQuery[paperQueryKey])
      const routeSource = singleQueryValue(currentQuery[sourceQueryKey])
      const nextSource = mode === 'immersive' ? immersiveReturnMode : null
      if (routeMode === mode && routePaperId === paperId && routeSource === nextSource) return

      pendingPaperId.value = null
      const query: LocationQueryRaw = {
        ...currentQuery,
        [modeQueryKey]: mode,
        [paperQueryKey]: paperId,
        [sourceQueryKey]: nextSource || undefined,
      }
      void options.router.replace({ query }).catch(() => {})
    },
    { flush: 'post' },
  )

  return { pendingPaperId }
}
