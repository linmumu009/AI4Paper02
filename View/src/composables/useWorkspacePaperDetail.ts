import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import { fetchPaperDetail } from '../api'
import type { PaperDetailResponse, PaperSummary } from '../types/paper'

const paperDetailCache = new Map<string, PaperDetailResponse>()

export function mergeWorkspacePaperSummary(
  base: PaperSummary | null,
  loaded: PaperSummary | null | undefined,
): PaperSummary | null {
  if (!base) return loaded ?? null
  if (!loaded) return base
  return {
    ...base,
    ...loaded,
    authors: loaded.authors?.length ? loaded.authors : base.authors,
    categories: loaded.categories?.length ? loaded.categories : base.categories,
  }
}

export function clearWorkspacePaperDetailCache() {
  paperDetailCache.clear()
}

export function useWorkspacePaperDetail(
  paper: Readonly<Ref<PaperSummary | null>>,
  detailOverride?: Readonly<Ref<PaperDetailResponse | null | undefined>>,
) {
  const detail = shallowRef<PaperDetailResponse | null>(null)
  const detailLoading = ref(false)
  const detailError = ref('')
  let loadVersion = 0

  const summary = computed(() => mergeWorkspacePaperSummary(paper.value, detail.value?.summary))

  watch(
    () => [paper.value?.paper_id, detailOverride?.value] as const,
    async ([paperId, override]) => {
      const version = ++loadVersion
      detail.value = null
      detailError.value = ''
      detailLoading.value = false
      if (!paperId) return

      if (override) {
        detail.value = override
        return
      }

      const cached = paperDetailCache.get(paperId)
      if (cached) {
        detail.value = cached
        return
      }

      detailLoading.value = true
      try {
        const response = await fetchPaperDetail(paperId)
        if (version !== loadVersion) return
        paperDetailCache.set(paperId, response)
        detail.value = response
      } catch (error: any) {
        if (version !== loadVersion) return
        detailError.value = error?.message || '详细证据暂时不可用'
      } finally {
        if (version === loadVersion) detailLoading.value = false
      }
    },
    { immediate: true },
  )

  return {
    detail,
    detailLoading,
    detailError,
    summary,
  }
}
