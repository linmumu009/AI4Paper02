/**
 * useDigestControls
 *
 * Encapsulates all client-side digest view controls:
 * - View mode (card swipe vs list overview)
 * - Sort mode (default / relevance / institution / diversity)
 * - Topic/category filter
 * - Digest statistics display
 * - Bookmark management (localStorage-backed)
 *
 * Extracted from DailyDigest.vue to keep that component maintainable.
 */

import { ref, computed, watch } from 'vue'
import type { PaperSummary } from '@shared/types/paper'

export type DigestViewMode = 'card' | 'list'
export type DigestSortMode = 'default' | 'relevance' | 'institution' | 'diversity'

export interface DigestStatsData {
  total_papers: number
  avg_relevance_score: number | null
  large_institution_count: number
  institution_distribution: { name: string; count: number }[]
}

function loadBookmarks(): Set<string> {
  try {
    const raw = localStorage.getItem('ai4p-bookmarks')
    if (raw) return new Set(JSON.parse(raw) as string[])
  } catch { /* ignore */ }
  return new Set()
}

function saveBookmarks(ids: Set<string>) {
  try { localStorage.setItem('ai4p-bookmarks', JSON.stringify([...ids])) } catch { /* ignore */ }
}

function applyDiversitySort(list: PaperSummary[]): PaperSummary[] {
  const byScore = (a: PaperSummary, b: PaperSummary) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0)
  const high = list.filter(p => (p.institution_tier ?? 4) <= 2).sort(byScore)
  const low  = list.filter(p => (p.institution_tier ?? 4) >  2).sort(byScore)
  const result: PaperSummary[] = []
  let hi = 0, lo = 0
  while (hi < high.length || lo < low.length) {
    for (let i = 0; i < 2 && hi < high.length; i++, hi++) result.push(high[hi])
    if (lo < low.length) result.push(low[lo++])
  }
  return result
}

export function useDigestControls(
  papers: Readonly<{ value: PaperSummary[] }>,
  currentIndex: { value: number },
  history: { value: number[] },
  cardAnimClass: { value: string },
) {
  const digestViewMode = ref<DigestViewMode>('card')
  const sortMode = ref<DigestSortMode>('default')
  const topicFilter = ref<string>('')
  const digestStats = ref<DigestStatsData | null>(null)
  const bookmarkedPaperIds = ref<Set<string>>(loadBookmarks())

  // Onboarding hint
  const showRecommendHint = ref(false)

  // Sorted + filtered papers
  const displayPapers = computed<PaperSummary[]>(() => {
    let list = [...papers.value]
    if (sortMode.value === 'relevance') {
      list.sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
    } else if (sortMode.value === 'institution') {
      list.sort((a, b) => (a.institution_tier ?? 4) - (b.institution_tier ?? 4))
    } else if (sortMode.value === 'diversity') {
      list = applyDiversitySort(list)
    }
    if (topicFilter.value) {
      list = list.filter(p => p.categories?.includes(topicFilter.value))
    }
    return list
  })

  // All arXiv categories in current papers
  const availableCategories = computed<string[]>(() => {
    const cats = new Set<string>()
    papers.value.forEach(p => p.categories?.forEach(c => cats.add(c)))
    return [...cats].sort()
  })

  // Reset position when sort/filter changes
  watch([sortMode, topicFilter], () => {
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
  })

  function jumpToCard(index: number) {
    currentIndex.value = index
    digestViewMode.value = 'card'
    cardAnimClass.value = 'card-enter'
  }

  function toggleBookmark(paperId: string, advanceFn?: () => void) {
    const updated = new Set(bookmarkedPaperIds.value)
    if (updated.has(paperId)) {
      updated.delete(paperId)
    } else {
      updated.add(paperId)
      advanceFn?.()
    }
    bookmarkedPaperIds.value = updated
    saveBookmarks(updated)
  }

  function isBookmarked(paperId: string): boolean {
    return bookmarkedPaperIds.value.has(paperId)
  }

  function dismissRecommendHint() {
    showRecommendHint.value = false
    try { localStorage.setItem('ai4p-recommend-hint-dismissed', '1') } catch { /* ignore */ }
  }

  function initRecommendHint(isAuthenticated: boolean) {
    if (isAuthenticated && !localStorage.getItem('ai4p-recommend-hint-dismissed')) {
      showRecommendHint.value = true
    }
  }

  return {
    digestViewMode,
    sortMode,
    topicFilter,
    digestStats,
    bookmarkedPaperIds,
    showRecommendHint,
    displayPapers,
    availableCategories,
    jumpToCard,
    toggleBookmark,
    isBookmarked,
    dismissRecommendHint,
    initRecommendHint,
  }
}
