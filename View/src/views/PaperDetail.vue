<script setup lang="ts">
/**
 * 独立路由 /papers/:id — 统一 ContentLayout，无嵌入模式（嵌入请用 PaperDetailEmbed）。
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ContentLayout from '../components/ContentLayout.vue'
import type { ContentLayoutContext } from '../components/ContentLayout.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import Sidebar from '../components/Sidebar.vue'
import SidebarPageLayout from '../components/SidebarPageLayout.vue'
import { fetchPaperDetail, fetchDates } from '../api'
import type { PaperDetailResponse } from '../types/paper'
import { setPageMeta } from '../router'
import { isAuthenticated } from '../stores/auth'
import { PANEL_IDS, type PanelConfigItem, type LayoutState } from '../composables/usePanelLayout'
import { useEngagement } from '../composables/useEngagement'
import { useGlobalChat } from '../composables/useGlobalChat'
import { trackPaperView, trackPaperViewDuration } from '../composables/useAnalytics'
import { recordPaperVisit } from '../utils/recentPapers'
import { buildPdfViewerUrl, warmPdfConnection } from '../composables/usePdfUrl'
import { useAnnotationAdapter } from '../composables/useAnnotationAdapter'
import { useKbSidebarState } from '../composables/useKbSidebarState'

const emit = defineEmits<{
  noteSaved: []
}>()

const route = useRoute()
const router = useRouter()
const engagement = useEngagement()
const globalChat = useGlobalChat()
const { attachAnnotationAdapter, detachAnnotationAdapter } = useAnnotationAdapter()

// Sidebar state (knowledge-base sidebar, same as DailyDigest / PaperList)
const {
  kbTree,
  activeFolderId,
  compareTree,
  showSidebar,
  loadKbTree,
  loadCompareTree,
  markPaperReadStatus,
} = useKbSidebarState('kb')

const dates = ref<string[]>([])
const selectedDate = ref('')

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')

// Inject modulepreload hints for PDF.js viewer resources as early as possible
// so the browser can fetch them in parallel while we await the paper API.
function preloadPdfResources() {
  const hints = [
    '/static/pdfjs/build/pdf.min.mjs',
    '/static/pdfjs/build/pdf.worker.min.mjs',
    '/static/pdfjs/web/pdf_viewer.mjs',
    '/static/pdfjs/web/pdf_viewer.css',
  ]
  for (const href of hints) {
    if (document.head.querySelector(`link[href="${href}"]`)) continue
    const link = document.createElement('link')
    link.rel = href.endsWith('.css') ? 'preload' : 'modulepreload'
    link.href = href
    if (href.endsWith('.css')) link.setAttribute('as', 'style')
    document.head.appendChild(link)
  }
}

let _jsonLdEl: HTMLScriptElement | null = null

function injectPaperJsonLd(d: PaperDetailResponse) {
  if (_jsonLdEl) {
    _jsonLdEl.remove()
    _jsonLdEl = null
  }

  const s = d.summary
  const title = s['📖标题'] || s.short_title || ''
  const abstract = s.abstract || s['🛎️文章简介']?.['🔸研究问题'] || ''
  const institution = s.institution || ''
  const paperId = s.paper_id || ''
  const arxivUrl = d.arxiv_url || `https://arxiv.org/abs/${paperId}`
  const pageUrl = `https://ai4papers.com/papers/${paperId}`

  const ld = {
    '@context': 'https://schema.org',
    '@type': 'ScholarlyArticle',
    headline: title,
    abstract,
    identifier: { '@type': 'PropertyValue', propertyID: 'arXiv', value: paperId },
    url: pageUrl,
    sameAs: arxivUrl,
    datePublished: d.date || undefined,
    publisher: {
      '@type': 'Organization',
      name: institution || 'arXiv',
    },
    isPartOf: {
      '@type': 'WebSite',
      name: 'AI4Papers',
      url: 'https://ai4papers.com',
    },
  }

  _jsonLdEl = document.createElement('script')
  _jsonLdEl.type = 'application/ld+json'
  _jsonLdEl.textContent = JSON.stringify(ld)
  document.head.appendChild(_jsonLdEl)
}

function removePaperJsonLd() {
  if (_jsonLdEl) {
    _jsonLdEl.remove()
    _jsonLdEl = null
  }
}

const buildPdfViewerSrc = buildPdfViewerUrl

const effectiveDetail = computed(() => detail.value)

const resolvedPaperId = computed(
  () => (route.params.id as string) || effectiveDetail.value?.summary.paper_id || '',
)

const layoutContextKey = computed(() => `paper-route:${resolvedPaperId.value}`)

const defaultStandaloneLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.PDF_VIEWER,
  splitRatio: 60,
}))

const panelConfigsStandalone = computed<PanelConfigItem[]>(() => {
  const d = effectiveDetail.value
  if (!d) return []
  const pid = d.summary.paper_id
  const hasPdf = !!d.pdf_url
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: hasPdf },
    {
      id: PANEL_IDS.AI_CHAT,
      label: 'AI 问答',
      icon: '💬',
      available: !!isAuthenticated.value && !!pid,
    },
  ]
})

const contentLayoutContext = computed<ContentLayoutContext>(() => {
  const d = effectiveDetail.value!
  const pid = d.summary.paper_id
  return {
    paperDetail: d,
    paperId: pid,
    pdfUrl: d.pdf_url || undefined,
    pdfViewerSrc: d.pdf_url ? buildPdfViewerSrc(d.pdf_url, pid) : '',
    pdfTitle: `${pid}.pdf`,
  }
})

async function load(paperId: string) {
  loading.value = true
  error.value = ''
  try {
    detail.value = await fetchPaperDetail(paperId)
    if (detail.value) {
      const s = detail.value.summary
      const title = s['📖标题'] || s.short_title || paperId
      setPageMeta(`${title} - AI4Papers`, s.abstract || s['🛎️文章简介']?.['🔸研究问题'] || '')
      injectPaperJsonLd(detail.value)
      recordPaperVisit({
        paperId,
        title,
        firstAuthor: Array.isArray(s.authors) ? (s.authors[0] as string) : undefined,
        source: 'arxiv',
      })
      // Pre-warm the PDF connection while the user reads the abstract.
      // Uses requestIdleCallback so it never competes with the initial render.
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
    removePaperJsonLd()
  } finally {
    loading.value = false
  }
}

let _paperViewStart = 0
let _currentTrackedPaperId = ''

onMounted(async () => {
  // Kick off PDF.js resource preloads immediately — they run in parallel with
  // the paper API call so the viewer starts rendering sooner after the user
  // clicks the PDF panel button.
  preloadPdfResources()
  attachAnnotationAdapter()

  // Load KB sidebar data in parallel with paper detail
  if (isAuthenticated.value) {
    void loadKbTree()
    void loadCompareTree()
  }
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) selectedDate.value = dates.value[0]
  } catch { /* non-critical */ }

  const id = route.params.id as string
  if (id) {
    await load(id)
    trackPaperView(id)
    _paperViewStart = Date.now()
    _currentTrackedPaperId = id
    if (isAuthenticated.value) {
      void engagement.loadStatus()
      void engagement.record('view', 'paper-detail-page', id)
    }
  }
})

watch(
  () => route.params.id,
  (id) => {
    if (id) {
      // Flush duration for previous paper before loading next
      if (_currentTrackedPaperId && _paperViewStart > 0) {
        const dur = (Date.now() - _paperViewStart) / 1000
        trackPaperViewDuration(_currentTrackedPaperId, dur)
      }
      load(id as string).then(() => {
        trackPaperView(id as string)
        _paperViewStart = Date.now()
        _currentTrackedPaperId = id as string
        if (isAuthenticated.value) {
          void engagement.record('view', 'paper-detail-page', id as string)
        }
      })
    }
  },
)

// Record analyze when user sends a chat message from this page
watch(
  () => globalChat.messageSentSignal.value,
  (n, old) => {
    if (n > 0 && n !== old && isAuthenticated.value) {
      void engagement.record('analyze', 'paper-detail-chat', resolvedPaperId.value)
    }
  },
)

onUnmounted(() => {
  detachAnnotationAdapter()
  removePaperJsonLd()
  if (_currentTrackedPaperId && _paperViewStart > 0) {
    const dur = (Date.now() - _paperViewStart) / 1000
    trackPaperViewDuration(_currentTrackedPaperId, dur)
  }
})
</script>

<template>
  <SidebarPageLayout v-model:show-sidebar="showSidebar" open-button-title="展开知识库">

    <!-- ===== Sidebar slot ===== -->
    <template #sidebar>
      <template v-if="isAuthenticated">
        <Transition name="sidebar-slide">
          <div
            v-show="showSidebar"
            :class="[
              'shrink-0 z-30 h-full transition-transform duration-300 ease-in-out',
              'fixed lg:relative inset-y-0 left-0',
              showSidebar ? 'translate-x-0' : '-translate-x-full lg:-translate-x-full',
            ]"
          >
            <Sidebar
              :kb-tree="kbTree"
              :compare-tree="compareTree"
              v-model:active-folder-id="activeFolderId"
              v-model:selected-date="selectedDate"
              :dates="dates"
              scope="kb"
              :active-paper-id="resolvedPaperId"
              @open-paper="(pid: string) => router.push(`/papers/${pid}`)"
              @open-note="(payload: { id: number; paperId: string }) => router.push(`/notes/${payload.id}`)"
              @open-pdf="() => {}"
              @open-user-paper="() => router.push('/?tab=mypapers')"
              @compare="() => router.push('/')"
              @research="() => router.push('/')"
              @refresh="loadKbTree"
              @open-compare-result="() => router.push('/')"
              @refresh-compare="loadCompareTree"
              @toggle-sidebar="showSidebar = false"
              @open-upload-dialog="() => {}"
              @open-research-session="() => router.push('/')"
              @tab-changed="() => {}"
              @view-md="() => {}"
              @update-read-status="markPaperReadStatus"
            />
          </div>
        </Transition>
      </template>
    </template>

    <!-- ===== Main content ===== -->
    <div class="h-full overflow-hidden flex flex-col">
      <div class="shrink-0 px-3 sm:px-5 pt-1 flex items-center">
        <button
          class="inline-flex items-center gap-1 text-xs text-text-muted hover:text-tinder-pink cursor-pointer bg-transparent border-none transition-colors"
          @click="router.back()"
        >
          ← 返回
        </button>
      </div>

      <div v-if="loading" class="flex-1 flex justify-center py-20">
        <LoadingSpinner />
      </div>
      <div v-else-if="error" class="flex-1 text-center py-20 px-4">
        <p class="text-tinder-pink text-lg mb-4">{{ error }}</p>
        <button
          class="px-5 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none"
          @click="router.back()"
        >
          返回
        </button>
      </div>
      <ContentLayout
        v-else-if="effectiveDetail"
        class="flex-1 min-h-0"
        :context-key="layoutContextKey"
        :panel-configs="panelConfigsStandalone"
        :default-layout="defaultStandaloneLayout"
        :context="contentLayoutContext"
        @note-saved="emit('noteSaved')"
      />
    </div>

  </SidebarPageLayout>
</template>
