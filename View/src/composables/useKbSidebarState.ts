import { ref, onBeforeUnmount } from 'vue'
import { fetchKbTree, fetchCompareResultsTree, type KbScope } from '../api'
import { isAuthenticated } from '../stores/auth'
import type { KbTree, KbCompareResultsTree } from '../types/paper'

/**
 * Shared state and logic for pages that show the KB/compare sidebar
 * (DailyDigest and PaperList). Encapsulates:
 * - kbTree / compareTree / activeFolderId reactive state
 * - loadKbTree / loadCompareTree data-fetch functions
 * - showSidebar responsive toggle (auto-opens on lg breakpoint)
 */
export function useKbSidebarState(kbScope?: KbScope) {
  const kbTree = ref<KbTree>({ folders: [], papers: [] })
  const activeFolderId = ref<number | null>(null)
  const compareTree = ref<KbCompareResultsTree | null>(null)

  async function loadKbTree() {
    if (!isAuthenticated.value) {
      kbTree.value = { folders: [], papers: [] }
      return
    }
    try {
      kbTree.value = await fetchKbTree(kbScope)
    } catch {}
  }

  async function loadCompareTree() {
    if (!isAuthenticated.value) {
      compareTree.value = null
      return
    }
    try {
      compareTree.value = await fetchCompareResultsTree()
    } catch {}
  }

  // Sidebar responsive state: open on lg+ screens, closed on mobile
  const mql = window.matchMedia('(min-width: 1024px)')
  const showSidebar = ref(mql.matches)

  function onMqlChange(e: MediaQueryListEvent) {
    showSidebar.value = e.matches
  }

  mql.addEventListener('change', onMqlChange)

  onBeforeUnmount(() => {
    mql.removeEventListener('change', onMqlChange)
  })

  /** Collapse the sidebar when on a narrow (mobile) screen. */
  function collapseSidebarOnMobile() {
    if (!mql.matches) showSidebar.value = false
  }

  return {
    kbTree,
    activeFolderId,
    compareTree,
    showSidebar,
    loadKbTree,
    loadCompareTree,
    collapseSidebarOnMobile,
  }
}
