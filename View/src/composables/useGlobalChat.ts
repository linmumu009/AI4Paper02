import { ref, computed, watch } from 'vue'
import type { PaperSummary } from '../types/paper'

export type GlobalChatDrawerMode = 'paper' | 'general'

export type BrowsingPaperSource =
  | 'paper-detail'
  | 'user-paper'
  | 'user-paper-md'
  | 'kb-paper'

/** 当前主区浏览的论文上下文（首页 / 灵感等内嵌视图上报） */
export interface BrowsingPaperContext {
  paperId: string
  title: string
  summary?: PaperSummary
  source: BrowsingPaperSource
}

const DRAWER_WIDTH_STORAGE_KEY = 'global-chat-drawer-width-px:v1'
/** 与侧栏 lg:w-72 (288px) 对齐的默认倍数 */
const SIDEBAR_BASE_PX = 288
const SIDEBAR_WIDTH_MULTIPLIER = 1.68
const DRAWER_MIN_PX = 320

function defaultDrawerWidthPx(viewportW: number): number {
  const fromSidebar = Math.round(SIDEBAR_BASE_PX * SIDEBAR_WIDTH_MULTIPLIER)
  const fromViewport = Math.round(viewportW * 0.92)
  return Math.min(fromSidebar, fromViewport)
}

function maxDrawerWidthPx(viewportW: number): number {
  return Math.round(viewportW * 0.92)
}

function clampDrawerWidth(px: number, viewportW: number): number {
  const max = maxDrawerWidthPx(viewportW)
  return Math.min(max, Math.max(DRAWER_MIN_PX, Math.round(px)))
}

function loadStoredDrawerWidth(viewportW: number): number | null {
  if (typeof localStorage === 'undefined') return null
  try {
    const raw = localStorage.getItem(DRAWER_WIDTH_STORAGE_KEY)
    if (raw == null) return null
    const n = Number.parseInt(raw, 10)
    if (!Number.isFinite(n)) return null
    return clampDrawerWidth(n, viewportW)
  } catch {
    return null
  }
}

function persistDrawerWidth(px: number) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(DRAWER_WIDTH_STORAGE_KEY, String(px))
  } catch {
    // ignore
  }
}

const isOpen = ref(false)
const drawerMode = ref<GlobalChatDrawerMode>('general')

/** DailyDigest 当前是否处于面板视图（查看论文详情、编辑笔记、对比等） */
const isDigestInPanelView = ref(false)

/** 浮动按钮请求"回到推荐"时置 true，DailyDigest watch 后消费并重置为 false */
const digestResetRequested = ref(false)

const paperContext = ref<{
  paperId: string
  title: string
  summary?: PaperSummary
} | null>(null)

/** 手动选择的论文 ID（抽屉内输入），用于无路由上下文时 */
const manualPaperId = ref('')

const browsingContext = ref<BrowsingPaperContext | null>(null)

const windowInnerWidth = ref(
  typeof window !== 'undefined' ? window.innerWidth : 1200,
)

const chatDrawerWidthPx = ref(
  (() => {
    const w = typeof window !== 'undefined' ? window.innerWidth : 1200
    return loadStoredDrawerWidth(w) ?? defaultDrawerWidthPx(w)
  })(),
)

let resizeBound = false

function ensureResizeListener() {
  if (typeof window === 'undefined' || resizeBound) return
  resizeBound = true
  window.addEventListener('resize', () => {
    windowInnerWidth.value = window.innerWidth
  })
}

export function useGlobalChat() {
  ensureResizeListener()

  watch(windowInnerWidth, (w) => {
    const clamped = clampDrawerWidth(chatDrawerWidthPx.value, w)
    if (clamped !== chatDrawerWidthPx.value) {
      chatDrawerWidthPx.value = clamped
      persistDrawerWidth(clamped)
    }
  })

  function setDrawerWidth(px: number) {
    const next = clampDrawerWidth(px, windowInnerWidth.value)
    chatDrawerWidthPx.value = next
    persistDrawerWidth(next)
  }

  function resetDrawerWidthToDefault() {
    const next = defaultDrawerWidthPx(windowInnerWidth.value)
    chatDrawerWidthPx.value = next
    persistDrawerWidth(next)
  }

  function setBrowsingContext(ctx: BrowsingPaperContext | null) {
    browsingContext.value = ctx
  }

  /** 清除首页/灵感等上报的浏览上下文，并清空抽屉内论文关联（独立详情页路由由路由同步负责） */
  function clearBrowsingContext() {
    browsingContext.value = null
    paperContext.value = null
    manualPaperId.value = ''
  }

  /** 将浏览上下文写入论文问答用的 paperContext（供路由同步等调用） */
  function applyBrowsingToPaperContext() {
    const b = browsingContext.value
    if (!b?.paperId) return
    paperContext.value = {
      paperId: b.paperId,
      title: b.title,
      summary: b.summary,
    }
    manualPaperId.value = b.paperId
  }

  function openWithPaper(paperId: string, title: string, summary?: PaperSummary) {
    paperContext.value = { paperId, title, summary }
    drawerMode.value = 'paper'
    manualPaperId.value = paperId
    isOpen.value = true
  }

  function openGeneral() {
    drawerMode.value = 'general'
    isOpen.value = true
  }

  function open() {
    const b = browsingContext.value
    if (b?.paperId) {
      paperContext.value = {
        paperId: b.paperId,
        title: b.title,
        summary: b.summary,
      }
      manualPaperId.value = b.paperId
      drawerMode.value = 'paper'
    }
    isOpen.value = true
  }

  function close() {
    isOpen.value = false
  }

  function setDrawerMode(m: GlobalChatDrawerMode) {
    drawerMode.value = m
  }

  /** 仅更新当前论文上下文（不打开抽屉），供路由同步 */
  function setPaperContext(ctx: { paperId: string; title: string; summary?: PaperSummary } | null) {
    paperContext.value = ctx
    if (ctx?.paperId) manualPaperId.value = ctx.paperId
  }

  function clearPaperContext() {
    paperContext.value = null
    manualPaperId.value = ''
  }

  /** 论文模式下实际用于 PaperChat 的 paperId：优先手动输入，否则上下文 */
  const effectivePaperId = computed(() => {
    const m = manualPaperId.value.trim()
    if (m) return m
    return paperContext.value?.paperId ?? ''
  })

  function setDigestInPanelView(inPanel: boolean) {
    isDigestInPanelView.value = inPanel
  }

  function requestDigestReset() {
    digestResetRequested.value = true
  }

  return {
    isOpen,
    drawerMode,
    paperContext,
    manualPaperId,
    effectivePaperId,
    browsingContext,
    chatDrawerWidthPx,
    isDigestInPanelView,
    digestResetRequested,
    setDrawerWidth,
    resetDrawerWidthToDefault,
    open,
    close,
    openWithPaper,
    openGeneral,
    setDrawerMode,
    setPaperContext,
    clearPaperContext,
    setBrowsingContext,
    clearBrowsingContext,
    applyBrowsingToPaperContext,
    setDigestInPanelView,
    requestDigestReset,
  }
}
