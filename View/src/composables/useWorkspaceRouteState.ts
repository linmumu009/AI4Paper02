import { ref, watch, type ComputedRef, type Ref } from 'vue'
import type { LocationQuery, LocationQueryRaw, Router } from 'vue-router'
import {
  isResearchWorkspaceMode,
  type ResearchWorkspaceMode,
} from './useResearchWorkspace'

interface UseWorkspaceRouteStateOptions {
  query: () => LocationQuery
  router: Router
  mode: Ref<ResearchWorkspaceMode>
  currentPaperId: ComputedRef<string | null>
  paperIds: ComputedRef<string[]>
  setMode: (mode: ResearchWorkspaceMode) => boolean
  selectPaperById: (paperId: string) => boolean
  modeQueryKey?: string
  paperQueryKey?: string
}

function singleQueryValue(value: LocationQuery[string]): string | null {
  if (Array.isArray(value)) return value[0] ?? null
  return value ?? null
}

export function useWorkspaceRouteState(options: UseWorkspaceRouteStateOptions) {
  const modeQueryKey = options.modeQueryKey ?? 'view'
  const paperQueryKey = options.paperQueryKey ?? 'paper'
  const pendingPaperId = ref<string | null>(singleQueryValue(options.query()[paperQueryKey]))
  let applyingRouteState = false

  watch(
    () => [
      singleQueryValue(options.query()[modeQueryKey]),
      singleQueryValue(options.query()[paperQueryKey]),
      options.paperIds.value.join('\u0000'),
    ] as const,
    ([routeMode, routePaperId]) => {
      applyingRouteState = true
      if (isResearchWorkspaceMode(routeMode)) options.setMode(routeMode)
      if (routePaperId) pendingPaperId.value = routePaperId
      if (pendingPaperId.value && options.selectPaperById(pendingPaperId.value)) {
        pendingPaperId.value = null
      }
      applyingRouteState = false
    },
    { immediate: true },
  )

  watch(
    [options.mode, options.currentPaperId],
    ([mode, paperId]) => {
      if (applyingRouteState || !paperId) return
      const currentQuery = options.query()
      const routeMode = singleQueryValue(currentQuery[modeQueryKey])
      const routePaperId = singleQueryValue(currentQuery[paperQueryKey])
      if (routeMode === mode && routePaperId === paperId) return

      pendingPaperId.value = null
      const query: LocationQueryRaw = {
        ...currentQuery,
        [modeQueryKey]: mode,
        [paperQueryKey]: paperId,
      }
      void options.router.replace({ query }).catch(() => {})
    },
    { flush: 'post' },
  )

  return { pendingPaperId }
}
