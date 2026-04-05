import { ref, watch, computed, type Ref } from 'vue'

export type PanelLayoutMode = 'single' | 'split'

export interface LayoutState {
  mode: PanelLayoutMode
  leftPanel: string
  rightPanel: string
  splitRatio: number
}

export interface PanelConfigItem {
  id: string
  label: string
  icon: string
  available: boolean
}

/** localStorage key prefix for panel layout persistence (used when resetting on navigation). */
export const STORAGE_PREFIX = 'panel-layout:v1:'

export const PANEL_IDS = {
  PAPER_DETAIL: 'paper-detail',
  PDF_VIEWER: 'pdf-viewer',
  NOTE_EDITOR: 'note-editor',
  MARKDOWN_VIEWER: 'markdown-viewer',
  MARKDOWN_MINERU: 'markdown-mineru',
  MARKDOWN_ZH: 'markdown-zh',
  MARKDOWN_BILINGUAL: 'markdown-bilingual',
  COMPARE: 'compare',
  COMPARE_RESULT: 'compare-result',
  IDEA_DETAIL: 'idea-detail',
  AI_CHAT: 'ai-chat',
} as const

function loadState(key: string, fallback: LayoutState): LayoutState {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key)
    if (!raw) return { ...fallback }
    const p = JSON.parse(raw) as Partial<LayoutState>
    return {
      mode: p.mode === 'split' ? 'split' : 'single',
      leftPanel: typeof p.leftPanel === 'string' ? p.leftPanel : fallback.leftPanel,
      rightPanel: typeof p.rightPanel === 'string' ? p.rightPanel : fallback.rightPanel,
      splitRatio:
        typeof p.splitRatio === 'number' && p.splitRatio >= 20 && p.splitRatio <= 85
          ? p.splitRatio
          : fallback.splitRatio,
    }
  } catch {
    return { ...fallback }
  }
}

function saveState(key: string, state: LayoutState) {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(state))
  } catch {
    // ignore
  }
}

/**
 * Per-context panel layout (single/split, which panel left/right, ratio).
 */
export function usePanelLayout(
  contextKey: string,
  defaultState: LayoutState,
  availablePanelIds: Ref<string[]>,
) {
  const state = ref<LayoutState>(loadState(contextKey, defaultState))

  watch(
    () => contextKey,
    (k) => {
      state.value = loadState(k, defaultState)
    },
  )

  watch(
    state,
    (s) => {
      saveState(contextKey, s)
    },
    { deep: true },
  )

  const availableSet = computed(() => new Set(availablePanelIds.value))

  function ensureValidPanels() {
    const ids = availablePanelIds.value
    if (!ids.length) return
    if (!availableSet.value.has(state.value.leftPanel)) {
      state.value.leftPanel = ids[0]!
    }
    if (!availableSet.value.has(state.value.rightPanel)) {
      state.value.rightPanel = ids.find((id) => id !== state.value.leftPanel) ?? ids[0]!
    }
    if (state.value.mode === 'split' && state.value.leftPanel === state.value.rightPanel) {
      const other = ids.find((id) => id !== state.value.leftPanel)
      if (other) state.value.rightPanel = other
    }
  }

  watch(availablePanelIds, ensureValidPanels, { immediate: true })

  function toggleSplit() {
    if (state.value.mode === 'single') {
      state.value.mode = 'split'
      ensureValidPanels()
    } else {
      state.value.mode = 'single'
    }
  }

  function setMode(m: PanelLayoutMode) {
    state.value.mode = m
    if (m === 'split') ensureValidPanels()
  }

  function setLeftPanel(id: string) {
    if (!availableSet.value.has(id)) return
    state.value.leftPanel = id
    if (state.value.mode === 'split' && state.value.rightPanel === id) {
      const other = availablePanelIds.value.find((x) => x !== id)
      if (other) state.value.rightPanel = other
    }
  }

  function setRightPanel(id: string) {
    if (!availableSet.value.has(id)) return
    state.value.rightPanel = id
    if (state.value.mode === 'split' && state.value.leftPanel === id) {
      const other = availablePanelIds.value.find((x) => x !== id)
      if (other) state.value.leftPanel = other
    }
  }

  function swapPanels() {
    if (state.value.mode !== 'split') return
    const t = state.value.leftPanel
    state.value.leftPanel = state.value.rightPanel
    state.value.rightPanel = t
  }

  function setSplitRatio(pct: number) {
    state.value.splitRatio = Math.min(85, Math.max(20, pct))
  }

  /** Open split view with a given right panel (e.g. PDF). */
  function openSplitWithRight(panelId: string) {
    if (!availableSet.value.has(panelId)) return
    state.value.mode = 'split'
    if (!availableSet.value.has(state.value.leftPanel)) {
      state.value.leftPanel = PANEL_IDS.PAPER_DETAIL
    }
    state.value.rightPanel = panelId
    ensureValidPanels()
  }

  return {
    state,
    toggleSplit,
    setMode,
    setLeftPanel,
    setRightPanel,
    swapPanels,
    setSplitRatio,
    openSplitWithRight,
    ensureValidPanels,
  }
}
