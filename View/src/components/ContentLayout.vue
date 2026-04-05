<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount, type ComponentPublicInstance } from 'vue'
import PanelToolbar from './PanelToolbar.vue'
import PanelRenderer from './PanelRenderer.vue'
import type { KbScope } from '../api'
import type { PaperDetailResponse, UserPaper, PaperSummary } from '../types/paper'
import {
  usePanelLayout,
  PANEL_IDS,
  type PanelConfigItem,
  type LayoutState,
} from '../composables/usePanelLayout'
import { useGlobalChat } from '../composables/useGlobalChat'

/** Context bag for dynamic panels (parent fills per scene). */
export interface ContentLayoutContext {
  paperId?: string
  paperDetail?: PaperDetailResponse | null
  userPaperData?: UserPaper
  paperSummary?: PaperSummary
  noteEditor?: { id: number; paperId: string }
  pdfViewerSrc?: string
  pdfUrl?: string
  pdfTitle?: string
  mdUrl?: string
  mdMineruUrl?: string
  mdZhUrl?: string
  mdBilingualUrl?: string
  comparingPaperIds?: string[]
  comparingResultIds?: number[]
  compareScope?: KbScope
  comparePaperTitles?: Record<string, string>
  compareResultId?: number
  ideaCandidateId?: number
  /** Scope used for download API calls on derivative Markdown panels. Defaults to 'kb'. */
  paperViewScope?: 'kb' | 'mypapers'
  /** When true, PdfPanel renders without its own title bar (use when the outer context already provides one). */
  hidePdfHeader?: boolean
}

const props = defineProps<{
  contextKey: string
  panelConfigs: PanelConfigItem[]
  defaultLayout: LayoutState
  context: ContentLayoutContext
  showClose?: boolean
}>()

const emit = defineEmits<{
  noteSaved: [payload?: { id: number; title: string }]
  closeNote: []
  closeCompare: []
  closeCompareResult: []
  closeIdea: []
  ideaOpenPaper: [paperId: string]
  compareSaved: [resultId: number]
  closeView: []
}>()

const globalChat = useGlobalChat()

const availableIds = computed(() =>
  props.panelConfigs.filter((p) => p.available).map((p) => p.id),
)

const {
  state: layout,
  toggleSplit,
  setLeftPanel,
  setRightPanel,
  swapPanels,
  setSplitRatio,
  openSplitWithRight,
  ensureValidPanels,
} = usePanelLayout(props.contextKey, props.defaultLayout, availableIds)

watch(
  () => props.contextKey,
  () => {
    ensureValidPanels()
  },
)

watch(
  () => props.panelConfigs,
  () => {
    ensureValidPanels()
  },
  { deep: true },
)

const isResizing = ref(false)
const splitContainerRef = ref<HTMLElement | null>(null)

const PANEL_PREFERRED_PX: Record<string, number> = {
  [PANEL_IDS.PAPER_DETAIL]: 700,
  [PANEL_IDS.PDF_VIEWER]: 800,
  [PANEL_IDS.MARKDOWN_VIEWER]: 700,
  [PANEL_IDS.MARKDOWN_MINERU]: 700,
  [PANEL_IDS.MARKDOWN_ZH]: 700,
  [PANEL_IDS.MARKDOWN_BILINGUAL]: 700,
  [PANEL_IDS.NOTE_EDITOR]: 600,
  [PANEL_IDS.AI_CHAT]: 484,
  [PANEL_IDS.COMPARE]: 700,
  [PANEL_IDS.COMPARE_RESULT]: 700,
  [PANEL_IDS.IDEA_DETAIL]: 600,
}

function getPanelPreferredPx(panelId: string): number {
  return PANEL_PREFERRED_PX[panelId] ?? 600
}

function calcDefaultLeftPercent(): number {
  if (!splitContainerRef.value) return layout.value.splitRatio
  const containerW = splitContainerRef.value.getBoundingClientRect().width
  if (containerW <= 0) return layout.value.splitRatio

  const leftId = layout.value.leftPanel
  const rightId = layout.value.rightPanel
  const leftIsPdf = leftId === PANEL_IDS.PDF_VIEWER
  const rightIsPdf = rightId === PANEL_IDS.PDF_VIEWER

  let leftPct: number

  if (leftIsPdf || rightIsPdf) {
    // 有一栏是 PDF：优先保证另一栏的首选宽度，剩余全给 PDF，PDF 最低 50%
    const nonPdfPx = leftIsPdf ? getPanelPreferredPx(rightId) : getPanelPreferredPx(leftId)
    const pdfPx = Math.max(containerW * 0.5, containerW - nonPdfPx)
    const nonPdfActualPx = containerW - pdfPx
    leftPct = leftIsPdf ? (pdfPx / containerW) * 100 : (nonPdfActualPx / containerW) * 100
  } else {
    // 两栏都不是 PDF：优先保证首选宽度较小的一栏，剩余给另一栏（不超过其首选宽度）
    const leftPrefPx = getPanelPreferredPx(leftId)
    const rightPrefPx = getPanelPreferredPx(rightId)

    if (leftPrefPx <= rightPrefPx) {
      const leftAlloc = Math.min(leftPrefPx, containerW - 200)
      const rightRemain = containerW - leftAlloc
      const rightAlloc = Math.min(rightRemain, rightPrefPx)
      const leftFinal = containerW - rightAlloc
      leftPct = (leftFinal / containerW) * 100
    } else {
      const rightAlloc = Math.min(rightPrefPx, containerW - 200)
      const leftRemain = containerW - rightAlloc
      const leftAlloc = Math.min(leftRemain, leftPrefPx)
      leftPct = (leftAlloc / containerW) * 100
    }
  }

  return Math.min(85, Math.max(20, leftPct))
}

function startResize(e: MouseEvent) {
  e.preventDefault()
  isResizing.value = true
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'

  function onMouseMove(ev: MouseEvent) {
    if (!splitContainerRef.value) return
    const rect = splitContainerRef.value.getBoundingClientRect()
    const rightMinPx = getPanelPreferredPx(layout.value.rightPanel)
    const maxLeftPct = rect.width > 0
      ? Math.min(85, ((rect.width - Math.min(rightMinPx, rect.width * 0.5)) / rect.width) * 100)
      : 85
    const newPercent = ((ev.clientX - rect.left) / rect.width) * 100
    setSplitRatio(Math.min(maxLeftPct, Math.max(20, newPercent)))
  }

  function onMouseUp() {
    isResizing.value = false
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function resetPanelWidth() {
  setSplitRatio(calcDefaultLeftPercent())
}

watch(
  () => layout.value.mode,
  (m) => {
    if (m === 'split') {
      nextTick(() => setSplitRatio(calcDefaultLeftPercent()))
    }
  },
)

watch(
  [() => layout.value.leftPanel, () => layout.value.rightPanel],
  () => {
    if (layout.value.mode === 'split') {
      nextTick(() => setSplitRatio(calcDefaultLeftPercent()))
    }
  },
)

const showToolbar = computed(() => availableIds.value.length > 1)

const isSplit = computed(() => layout.value.mode === 'split')

const activeDownloadParams = computed(() => {
  const scope = (props.context.paperViewScope ?? (props.context.userPaperData ? 'mypapers' : 'kb')) as 'kb' | 'mypapers'
  const pid = props.context.paperId

  const resolveForPanel = (panelId: string): { downloadParams?: { paperId: string; fileType: 'mineru' | 'zh' | 'bilingual'; scope: 'kb' | 'mypapers' }; downloadUrl?: string } | null => {
    if (panelId === PANEL_IDS.MARKDOWN_MINERU && pid) {
      return { downloadParams: { paperId: pid, fileType: 'mineru', scope } }
    }
    if (panelId === PANEL_IDS.MARKDOWN_ZH && pid) {
      return { downloadParams: { paperId: pid, fileType: 'zh', scope } }
    }
    if (panelId === PANEL_IDS.MARKDOWN_BILINGUAL && pid) {
      return { downloadParams: { paperId: pid, fileType: 'bilingual', scope } }
    }
    if (panelId === PANEL_IDS.MARKDOWN_VIEWER && props.context.mdUrl) {
      return { downloadUrl: props.context.mdUrl }
    }
    return null
  }

  // In split mode, prefer left panel; check right panel too
  const left = resolveForPanel(layout.value.leftPanel)
  if (left) return left
  if (layout.value.mode === 'split') {
    return resolveForPanel(layout.value.rightPanel)
  }
  return null
})

const toolbarHidden = ref(true)
let lastScrollTop = 0
let toolbarLeaveTimer: ReturnType<typeof setTimeout> | null = null
let introTimer: ReturnType<typeof setTimeout> | null = null

function showToolbarTemporarily() {
  toolbarHidden.value = false
}

function scheduleHideToolbar() {
  if (toolbarLeaveTimer) clearTimeout(toolbarLeaveTimer)
  toolbarLeaveTimer = setTimeout(() => {
    toolbarHidden.value = true
  }, 500)
}

function cancelHideToolbar() {
  if (toolbarLeaveTimer) {
    clearTimeout(toolbarLeaveTimer)
    toolbarLeaveTimer = null
  }
}

function onContentScroll(e: Event) {
  const el = e.target as HTMLElement
  const st = el.scrollTop
  if (st < 10) {
    toolbarHidden.value = false
  } else if (st - lastScrollTop > 30) {
    toolbarHidden.value = true
  } else if (st < lastScrollTop) {
    toolbarHidden.value = false
  }
  lastScrollTop = st
}

watch(
  () => layout.value.mode,
  () => {
    toolbarHidden.value = false
    lastScrollTop = 0
  },
)

onMounted(() => {
  // Show toolbar briefly on first mount so users discover it
  toolbarHidden.value = false
  introTimer = setTimeout(() => {
    toolbarHidden.value = true
  }, 2500)
})

onBeforeUnmount(() => {
  if (introTimer) clearTimeout(introTimer)
  if (toolbarLeaveTimer) clearTimeout(toolbarLeaveTimer)
})

function onNestedOpenPdf() {
  if (availableIds.value.includes(PANEL_IDS.PDF_VIEWER)) {
    openSplitWithRight(PANEL_IDS.PDF_VIEWER)
  }
}

function onNestedOpenChat() {
  const pid = props.context.paperId || props.context.paperDetail?.summary.paper_id
  const d = props.context.paperDetail
  if (pid && d) {
    globalChat.openWithPaper(
      pid,
      d.summary.short_title || d.summary['📖标题'] || pid,
      d.summary,
    )
  } else if (pid) {
    globalChat.openWithPaper(pid, pid)
  }
}

function leftMaxWidthClass(panelId: string) {
  if (panelId === PANEL_IDS.PAPER_DETAIL) {
    return 'max-w-3xl mx-auto'
  }
  if (
    panelId === PANEL_IDS.MARKDOWN_VIEWER ||
    panelId === PANEL_IDS.MARKDOWN_MINERU ||
    panelId === PANEL_IDS.MARKDOWN_ZH ||
    panelId === PANEL_IDS.MARKDOWN_BILINGUAL
  ) {
    return 'max-w-3xl mx-auto h-full min-h-0 flex flex-col'
  }
  return 'h-full min-h-0 flex flex-col'
}


/** 供父组件在切换视图前调用笔记自动保存（如 DailyDigest） */
type NoteEditorExposed = ComponentPublicInstance & {
  isEffectivelyEmpty: () => boolean
  flushSave: () => Promise<void>
}

const singlePanelRef = ref<InstanceType<typeof PanelRenderer> | null>(null)
const splitLeftPanelRef = ref<InstanceType<typeof PanelRenderer> | null>(null)
const splitRightPanelRef = ref<InstanceType<typeof PanelRenderer> | null>(null)

defineExpose({
  getNoteEditor: (): NoteEditorExposed | null =>
    (singlePanelRef.value?.getNoteEditor() as NoteEditorExposed | null)
    ?? (splitLeftPanelRef.value?.getNoteEditor() as NoteEditorExposed | null)
    ?? (splitRightPanelRef.value?.getNoteEditor() as NoteEditorExposed | null)
    ?? null,
})
</script>

<template>
  <div class="flex flex-col h-full min-h-0 overflow-hidden bg-bg">
    <!-- 鼠标热区：工具栏隐藏时悬停此区域可恢复显示 -->
    <div
      v-if="showToolbar"
      class="shrink-0 relative"
      :class="toolbarHidden ? 'h-4' : 'h-0'"
      @mouseenter="showToolbarTemporarily(); cancelHideToolbar()"
    >
      <!-- 视觉指示器：小横线，提示用户此处可悬浮展开 -->
      <div
        v-if="toolbarHidden"
        class="absolute left-1/2 -translate-x-1/2 top-1.5 w-14 h-1 rounded-full bg-border hover:bg-text-muted transition-colors duration-200"
      />
    </div>
    <!-- 工具栏容器：带折叠过渡；展开时 overflow-visible 允许下拉菜单溢出 -->
    <div
      v-if="showToolbar"
      class="shrink-0"
      :style="toolbarHidden
        ? { maxHeight: '0px', opacity: '0', overflow: 'hidden', transition: 'max-height 0.2s ease-in-out, opacity 0.2s ease-in-out' }
        : { maxHeight: '60px', opacity: '1', overflow: 'visible', transition: 'max-height 0.2s ease-in-out, opacity 0.2s ease-in-out' }"
      @mouseenter="cancelHideToolbar()"
      @mouseleave="scheduleHideToolbar()"
    >
      <PanelToolbar
        :mode="layout.mode"
        :left-panel="layout.leftPanel"
        :right-panel="layout.rightPanel"
        :panels="panelConfigs"
        :show-close="showClose"
        :download-params="activeDownloadParams?.downloadParams"
        :download-url="activeDownloadParams?.downloadUrl"
        @update:left-panel="setLeftPanel"
        @update:right-panel="setRightPanel"
        @toggle-split="toggleSplit"
        @swap="swapPanels"
        @close="emit('closeView')"
      />
    </div>

    <div
      ref="splitContainerRef"
      class="flex-1 min-h-0 flex flex-col md:flex-row items-stretch"
      :style="isSplit ? { '--left-width': layout.splitRatio + '%' } : {}"
    >
      <!-- 单栏 -->
      <template v-if="!isSplit">
        <div class="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-3 sm:px-6 pt-2 sm:pt-3 pb-6" @scroll="onContentScroll">
          <div :class="leftMaxWidthClass(layout.leftPanel)">
            <PanelRenderer
              ref="singlePanelRef"
              :panel-id="layout.leftPanel"
              :context="context"
              markdown-root-class="min-h-[200px]"
              @open-pdf="onNestedOpenPdf"
              @open-chat="onNestedOpenChat"
              @note-saved="emit('noteSaved', $event)"
              @close-note="emit('closeNote')"
              @close-compare="emit('closeCompare')"
              @close-compare-result="emit('closeCompareResult')"
              @close-idea="emit('closeIdea')"
              @idea-open-paper="emit('ideaOpenPaper', $event)"
              @compare-saved="emit('compareSaved', $event)"
            />
          </div>
        </div>
      </template>

      <!-- 分栏 -->
      <template v-else>
        <div
          class="split-left h-[45vh] md:h-full min-w-0 overflow-y-auto overflow-x-hidden px-2 sm:px-4 py-3 md:py-4"
          :style="isResizing ? { pointerEvents: 'none' } : {}"
          @scroll="onContentScroll"
        >
          <div :class="leftMaxWidthClass(layout.leftPanel)">
            <PanelRenderer
              ref="splitLeftPanelRef"
              :panel-id="layout.leftPanel"
              :context="context"
              markdown-root-class="min-h-[200px] md:min-h-0"
              @open-pdf="onNestedOpenPdf"
              @open-chat="onNestedOpenChat"
              @note-saved="emit('noteSaved', $event)"
              @close-note="emit('closeNote')"
              @close-compare="emit('closeCompare')"
              @close-compare-result="emit('closeCompareResult')"
              @close-idea="emit('closeIdea')"
              @idea-open-paper="emit('ideaOpenPaper', $event)"
              @compare-saved="emit('compareSaved', $event)"
            />
          </div>
        </div>

        <div
          class="hidden md:flex items-center justify-center w-2 shrink-0 self-stretch cursor-col-resize group z-10"
          @mousedown="startResize"
          @dblclick="resetPanelWidth"
          title="拖动调整宽度，双击重置"
        >
          <div
            class="w-[3px] h-10 rounded-full transition-all duration-200"
            :class="isResizing
              ? 'bg-tinder-pink h-full rounded-none'
              : 'bg-border group-hover:bg-tinder-pink/60 group-hover:h-full group-hover:rounded-none'"
          />
        </div>

        <div
          class="flex-1 min-w-0 h-[55vh] md:h-full border-t md:border-t-0 md:border-l border-border overflow-hidden flex flex-col"
          :style="isResizing ? { pointerEvents: 'none' } : {}"
        >
          <PanelRenderer
            ref="splitRightPanelRef"
            :panel-id="layout.rightPanel"
            :context="context"
            markdown-root-class="min-h-[200px] md:min-h-0"
            @open-pdf="onNestedOpenPdf"
            @open-chat="onNestedOpenChat"
            @note-saved="emit('noteSaved', $event)"
            @close-note="emit('closeNote')"
            @close-compare="emit('closeCompare')"
            @close-compare-result="emit('closeCompareResult')"
            @close-idea="emit('closeIdea')"
            @idea-open-paper="emit('ideaOpenPaper', $event)"
            @compare-saved="emit('compareSaved', $event)"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
@media (min-width: 768px) {
  .split-left {
    width: var(--left-width, 60%);
    flex-shrink: 0;
  }
}
</style>
