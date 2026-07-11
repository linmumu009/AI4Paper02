<script setup lang="ts">
/**
 * Lightweight embedded paper detail for use inside pages that already have
 * their own left sidebar (e.g. task-center or research-preferences tabs inside
 * ProfileSettings). Renders the same ContentLayout panels as PaperDetail.vue
 * but does NOT include SidebarPageLayout / Sidebar — those belong to the host page.
 *
 * Props:
 *   paperId   — arXiv paper ID to load.
 *   backLabel — text shown on the back button (default: "返回").
 *
 * Emits:
 *   back — user clicked the back button; host should clear the selected paper.
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import ContentLayout from './ContentLayout.vue'
import type { ContentLayoutContext } from './ContentLayout.vue'
import LoadingSpinner from './LoadingSpinner.vue'
import { fetchPaperDetail } from '../api'
import type { PaperDetailResponse } from '../types/paper'
import { isAuthenticated } from '../stores/auth'
import { PANEL_IDS, type PanelConfigItem, type LayoutState } from '../composables/usePanelLayout'
import { useEngagement } from '../composables/useEngagement'
import { useGlobalChat } from '../composables/useGlobalChat'
import { trackPaperView, trackPaperViewDuration } from '../composables/useAnalytics'
import { recordPaperVisit } from '../utils/recentPapers'
import { buildPdfViewerUrl, warmPdfConnection } from '../composables/usePdfUrl'
import { useAnnotationAdapter } from '../composables/useAnnotationAdapter'

const props = withDefaults(defineProps<{
  paperId: string
  backLabel?: string
}>(), {
  backLabel: '返回',
})

const emit = defineEmits<{
  back: []
  noteSaved: []
}>()

const engagement = useEngagement()
const globalChat = useGlobalChat()
const { attachAnnotationAdapter, detachAnnotationAdapter } = useAnnotationAdapter()

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')

const layoutContextKey = computed(() => `embedded-paper:${props.paperId}`)

const defaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.PDF_VIEWER,
  splitRatio: 60,
}))

const panelConfigs = computed<PanelConfigItem[]>(() => {
  const d = detail.value
  if (!d) return []
  const pid = d.summary.paper_id
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: !!d.pdf_url },
    {
      id: PANEL_IDS.AI_CHAT,
      label: 'AI 问答',
      icon: '💬',
      available: !!isAuthenticated.value && !!pid,
    },
  ]
})

const contentLayoutContext = computed<ContentLayoutContext>(() => {
  const d = detail.value!
  const pid = d.summary.paper_id
  return {
    paperDetail: d,
    paperId: pid,
    pdfUrl: d.pdf_url || undefined,
    pdfViewerSrc: d.pdf_url ? buildPdfViewerUrl(d.pdf_url, pid) : '',
    pdfTitle: `${pid}.pdf`,
  }
})

let _viewStart = 0

async function load(paperId: string) {
  loading.value = true
  error.value = ''
  try {
    detail.value = await fetchPaperDetail(paperId)
    if (detail.value) {
      const s = detail.value.summary
      const title = s['📖标题'] || s.short_title || paperId
      recordPaperVisit({
        paperId,
        title,
        firstAuthor: Array.isArray(s.authors) ? (s.authors[0] as string) : undefined,
        source: 'arxiv',
      })
      // Pre-warm the PDF connection on idle so it's ready when user clicks PDF.
      const pdfUrl = detail.value.pdf_url
      if (pdfUrl) {
        const cb = () => warmPdfConnection(pdfUrl)
        if (typeof requestIdleCallback !== 'undefined') {
          requestIdleCallback(cb, { timeout: 5000 })
        } else {
          setTimeout(cb, 2000)
        }
      }
    }
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? '论文未找到' : (e?.message || '加载失败')
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  attachAnnotationAdapter()
  if (props.paperId) {
    await load(props.paperId)
    trackPaperView(props.paperId)
    _viewStart = Date.now()
    if (isAuthenticated.value) {
      void engagement.loadStatus()
      void engagement.record('view', 'paper-detail-embedded', props.paperId)
    }
  }
})

watch(() => props.paperId, async (pid) => {
  if (!pid) return
  if (_viewStart > 0) {
    trackPaperViewDuration(props.paperId, (Date.now() - _viewStart) / 1000)
  }
  await load(pid)
  trackPaperView(pid)
  _viewStart = Date.now()
})

watch(() => globalChat.messageSentSignal.value, (n, old) => {
  if (n > 0 && n !== old && isAuthenticated.value && detail.value) {
    void engagement.record('analyze', 'paper-detail-chat', detail.value.summary.paper_id)
  }
})

onUnmounted(() => {
  detachAnnotationAdapter()
  if (_viewStart > 0 && detail.value) {
    trackPaperViewDuration(detail.value.summary.paper_id, (Date.now() - _viewStart) / 1000)
  }
})
</script>

<template>
  <div class="h-full overflow-hidden flex flex-col">
    <!-- Back bar -->
    <div class="shrink-0 px-3 sm:px-5 pt-1 flex items-center">
      <button
        class="inline-flex items-center gap-1 text-xs text-text-muted hover:text-tinder-pink cursor-pointer bg-transparent border-none transition-colors"
        @click="emit('back')"
      >
        ← {{ backLabel }}
      </button>
    </div>

    <div v-if="loading" class="flex-1 flex justify-center py-20">
      <LoadingSpinner />
    </div>

    <div v-else-if="error" class="flex-1 text-center py-20 px-4">
      <p class="text-tinder-pink text-lg mb-4">{{ error }}</p>
      <button
        class="px-5 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none"
        @click="emit('back')"
      >
        返回
      </button>
    </div>

    <ContentLayout
      v-else-if="detail"
      class="flex-1 min-h-0"
      :context-key="layoutContextKey"
      :panel-configs="panelConfigs"
      :default-layout="defaultLayout"
      :context="contentLayoutContext"
      @note-saved="emit('noteSaved')"
    />
  </div>
</template>
