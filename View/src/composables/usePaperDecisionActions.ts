import { ref, type ComputedRef, type Ref } from 'vue'

export interface PaperDecisionTarget {
  paper_id: string
}

interface UsePaperDecisionActionsOptions<T extends PaperDecisionTarget> {
  currentPaper: ComputedRef<T | null>
  isAuthenticated: Readonly<Ref<boolean>>
  advance: (direction: 'left' | 'right') => void
  redirectToLogin: () => void
  dismissPaper: (paper: T) => Promise<unknown>
  collectPaper: (paper: T) => Promise<unknown>
  onDismiss?: (paper: T) => void
  onCollect?: (paper: T) => void
  bookmarkStorageKey?: string
  storage?: Pick<Storage, 'getItem' | 'setItem'> | null
}

function loadBookmarks(
  storage: Pick<Storage, 'getItem' | 'setItem'> | null,
  storageKey: string,
): Set<string> {
  try {
    const raw = storage?.getItem(storageKey)
    if (raw) return new Set(JSON.parse(raw) as string[])
  } catch { /* Ignore unavailable or malformed local storage. */ }
  return new Set()
}

export function usePaperDecisionActions<T extends PaperDecisionTarget>(
  options: UsePaperDecisionActionsOptions<T>,
) {
  const storageKey = options.bookmarkStorageKey ?? 'ai4p-bookmarks'
  const storage = options.storage === undefined
    ? (typeof window === 'undefined' ? null : window.localStorage)
    : options.storage
  const bookmarkedPaperIds = ref(loadBookmarks(storage, storageKey))

  function saveBookmarks(ids: Set<string>) {
    try { storage?.setItem(storageKey, JSON.stringify([...ids])) } catch { /* Ignore storage failures. */ }
  }

  function skip(): boolean {
    const paper = options.currentPaper.value
    if (!paper) return false
    options.advance('left')
    if (options.isAuthenticated.value) {
      void options.dismissPaper(paper).catch(() => {})
      options.onDismiss?.(paper)
    }
    return true
  }

  function collectTarget(paper: T, advance = false): boolean {
    if (!options.isAuthenticated.value) {
      options.redirectToLogin()
      return false
    }
    if (advance) options.advance('right')
    void options.collectPaper(paper).catch(() => {})
    options.onCollect?.(paper)
    return true
  }

  function collect(): boolean {
    const paper = options.currentPaper.value
    return paper ? collectTarget(paper, true) : false
  }

  function toggleBookmarkTarget(paper: T, advanceOnAdd = false): boolean {
    const updated = new Set(bookmarkedPaperIds.value)
    if (updated.has(paper.paper_id)) {
      updated.delete(paper.paper_id)
    } else {
      updated.add(paper.paper_id)
      if (advanceOnAdd) options.advance('right')
    }
    bookmarkedPaperIds.value = updated
    saveBookmarks(updated)
    return updated.has(paper.paper_id)
  }

  function toggleBookmark(): boolean {
    const paper = options.currentPaper.value
    return paper ? toggleBookmarkTarget(paper, true) : false
  }

  return {
    bookmarkedPaperIds,
    skip,
    collect,
    collectTarget,
    toggleBookmark,
    toggleBookmarkTarget,
  }
}
