import { computed, ref, watch, type Ref } from 'vue'

export const RESEARCH_WORKSPACE_MODES = ['card', 'list', 'immersive'] as const

export type ResearchWorkspaceMode = typeof RESEARCH_WORKSPACE_MODES[number]
export type DigestSortMode = 'default' | 'relevance' | 'institution' | 'diversity'

export interface ResearchWorkspacePaper {
  paper_id: string
  categories?: string[]
  relevance_score?: number | null
  institution_tier?: number | null
}

export interface UseResearchWorkspaceOptions<T extends ResearchWorkspacePaper> {
  papers: Ref<T[]>
  initialMode?: ResearchWorkspaceMode
  supportedModes?: readonly ResearchWorkspaceMode[]
  pageSize?: number
}

export function isResearchWorkspaceMode(value: unknown): value is ResearchWorkspaceMode {
  return typeof value === 'string'
    && RESEARCH_WORKSPACE_MODES.includes(value as ResearchWorkspaceMode)
}

export function applyDiversitySort<T extends ResearchWorkspacePaper>(papers: T[]): T[] {
  const byScore = (a: T, b: T) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0)
  const high = papers.filter(paper => (paper.institution_tier ?? 4) <= 2).sort(byScore)
  const low = papers.filter(paper => (paper.institution_tier ?? 4) > 2).sort(byScore)
  const result: T[] = []
  let highIndex = 0
  let lowIndex = 0

  while (highIndex < high.length || lowIndex < low.length) {
    for (let count = 0; count < 2 && highIndex < high.length; count++, highIndex++) {
      result.push(high[highIndex])
    }
    if (lowIndex < low.length) result.push(low[lowIndex++])
  }

  return result
}

export function useResearchWorkspace<T extends ResearchWorkspacePaper>(
  options: UseResearchWorkspaceOptions<T>,
) {
  const supportedModes = options.supportedModes ?? RESEARCH_WORKSPACE_MODES
  const fallbackMode = supportedModes[0] ?? 'card'
  const requestedMode = options.initialMode ?? fallbackMode
  const mode = ref<ResearchWorkspaceMode>(
    supportedModes.includes(requestedMode) ? requestedMode : fallbackMode,
  )
  const sortMode = ref<DigestSortMode>('default')
  const topicFilter = ref('')
  const currentIndex = ref(0)
  const history = ref<number[]>([])
  const listPage = ref(0)
  const pageSize = options.pageSize ?? 15

  const displayPapers = computed<T[]>(() => {
    let list = [...options.papers.value]
    if (sortMode.value === 'relevance') {
      list.sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
    } else if (sortMode.value === 'institution') {
      list.sort((a, b) => (a.institution_tier ?? 4) - (b.institution_tier ?? 4))
    } else if (sortMode.value === 'diversity') {
      list = applyDiversitySort(list)
    }
    if (topicFilter.value) {
      list = list.filter(paper => paper.categories?.includes(topicFilter.value))
    }
    return list
  })

  const currentPaper = computed<T | null>(() => displayPapers.value[currentIndex.value] ?? null)
  const currentPaperId = computed(() => currentPaper.value?.paper_id ?? null)
  const remaining = computed(() => Math.max(0, displayPapers.value.length - currentIndex.value))
  const allSwiped = computed(
    () => displayPapers.value.length > 0 && currentIndex.value >= displayPapers.value.length,
  )
  const listTotalPages = computed(
    () => Math.max(1, Math.ceil(displayPapers.value.length / pageSize)),
  )
  const pagedPapers = computed(() => {
    const start = listPage.value * pageSize
    return displayPapers.value.slice(start, start + pageSize)
  })
  const availableCategories = computed(() => {
    const categories = new Set<string>()
    options.papers.value.forEach((paper) => {
      paper.categories?.forEach(category => categories.add(category))
    })
    return [...categories].sort()
  })

  function setMode(nextMode: ResearchWorkspaceMode): boolean {
    if (!supportedModes.includes(nextMode)) return false
    mode.value = nextMode
    return true
  }

  function selectIndex(index: number): boolean {
    if (!Number.isInteger(index) || index < 0 || index >= displayPapers.value.length) return false
    currentIndex.value = index
    listPage.value = Math.floor(index / pageSize)
    return true
  }

  function selectPaperById(paperId: string): boolean {
    const index = displayPapers.value.findIndex(paper => paper.paper_id === paperId)
    return index >= 0 && selectIndex(index)
  }

  function rememberCurrentIndex() {
    history.value.push(currentIndex.value)
  }

  function moveToNext() {
    currentIndex.value += 1
  }

  function restorePreviousIndex(): boolean {
    const previousIndex = history.value.pop()
    if (previousIndex === undefined) return false
    currentIndex.value = previousIndex
    listPage.value = Math.floor(previousIndex / pageSize)
    return true
  }

  function resetPosition() {
    currentIndex.value = 0
    history.value = []
    listPage.value = 0
  }

  watch([sortMode, topicFilter], resetPosition)

  return {
    mode,
    sortMode,
    topicFilter,
    currentIndex,
    history,
    listPage,
    displayPapers,
    currentPaper,
    currentPaperId,
    remaining,
    allSwiped,
    listTotalPages,
    pagedPapers,
    availableCategories,
    setMode,
    selectIndex,
    selectPaperById,
    rememberCurrentIndex,
    moveToNext,
    restorePreviousIndex,
    resetPosition,
  }
}
