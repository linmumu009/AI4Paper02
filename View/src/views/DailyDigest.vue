<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import DatePill from '../components/DatePill.vue'
import PaperCard from '../components/PaperCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import WhyNotDrawer from '../components/WhyNotDrawer.vue'
import ContentLayout from '../components/ContentLayout.vue'
import type { ContentLayoutContext } from '../components/ContentLayout.vue'
import PdfPanel from '../components/panels/PdfPanel.vue'
import UserPaperUploadDialog from '../components/UserPaperUploadDialog.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import SidebarPageLayout from '../components/SidebarPageLayout.vue'
import UpgradePrompt from '../components/UpgradePrompt.vue'
import TodayMissionBar from '../components/TodayMissionBar.vue'
import type { TasklineItem } from '../components/DailyResearchTaskline.vue'
import { PANEL_IDS, STORAGE_PREFIX, type LayoutState, type PanelConfigItem } from '../composables/usePanelLayout'
import { fetchDates, fetchDigest, addKbPaper, removeKbPaper, updateKbPaperReadStatus, deleteNote, dismissPaper, fetchUserPapers, fetchUserPaperInstitutions, fetchUserPaperDetail, fetchPaperDetail, fetchResearchProject, processUserPaper, userPaperStepLabel, saveResearchSession } from '../api'
import { fetchResearchRadar, type ResearchRadarResponse } from '@shared/api/radar'
import { fetchReviewCards, recordReviewResponse, type ReviewCard } from '@shared/api/recap'
import { buildPdfViewerUrl, resolvePaperPdfUrl, buildKbPdfViewerUrl, buildKbFileUrl } from '../composables/usePdfUrl'
import { useAnnotationAdapter } from '../composables/useAnnotationAdapter'
import { openExternal } from '../utils/openExternal'
import type { KbScope } from '../api'
import type { KbPaper, PaperSummary, UserPaper, UserPaperViewMdPayload } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import { useGlobalChat } from '../composables/useGlobalChat'
import { useKbSidebarState } from '../composables/useKbSidebarState'
import { useEngagement } from '../composables/useEngagement'
import { trackKbAction, trackPaperCardView } from '../composables/useAnalytics'
import { useToast } from '../composables/useToast'
import { useResearchWorkspace } from '../composables/useResearchWorkspace'
import { useWorkspaceRouteState } from '../composables/useWorkspaceRouteState'
import { usePaperDecisionActions } from '../composables/usePaperDecisionActions'
import ResearchWorkspaceShell from '../components/workspace/ResearchWorkspaceShell.vue'
import WorkspaceModeSwitch from '../components/workspace/WorkspaceModeSwitch.vue'
import WorkspacePaperRow from '../components/workspace/WorkspacePaperRow.vue'
import PaperInspector from '../components/workspace/PaperInspector.vue'
import ImmersivePaperReader from '../components/workspace/ImmersivePaperReader.vue'
import KnowledgeWorkspace from '../components/workspace/KnowledgeWorkspace.vue'

const router = useRouter()
const route = useRoute()
const globalChat = useGlobalChat()
const engagement = useEngagement()
const { attachAnnotationAdapter, detachAnnotationAdapter } = useAnnotationAdapter()
const { showError } = useToast()

// Data
const dates = ref<string[]>([])
const selectedDate = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)
const error = ref('')
const errorType = ref<'proxy' | 'server' | 'unknown'>('unknown')
const totalAvailable = ref<number>(0)
const quotaLimit = ref<number | null>(null)
const responseTier = ref<string>('anonymous')

// Card navigation
const cardAnimClass = ref('card-enter')
const LIST_PAGE_SIZE = 15
const {
  mode: digestViewMode,
  sortMode,
  topicFilter,
  currentIndex,
  history,
  listPage,
  selectedPaperIds,
  displayPapers,
  currentPaper,
  currentPaperId,
  remaining,
  allSwiped,
  listTotalPages,
  pagedPapers,
  availableCategories,
  setMode: setDigestViewMode,
  selectIndex: selectDigestPaper,
  selectPaperById: selectDigestPaperById,
  rememberCurrentIndex,
  moveToNext,
  restorePreviousIndex,
  togglePaperSelection,
  selectPaperIds,
  clearPaperSelection,
} = useResearchWorkspace({
  papers,
  pageSize: LIST_PAGE_SIZE,
  supportedModes: ['card', 'list', 'immersive'],
})

useWorkspaceRouteState({
  query: () => route.query,
  router,
  mode: digestViewMode,
  currentPaperId,
  paperIds: computed(() => displayPapers.value.map(paper => paper.paper_id)),
  setMode: setDigestViewMode,
  selectPaperById: selectDigestPaperById,
  paperQueryKey: 'digest_paper',
})

// Digest statistics from API response (used in stats bar)
const digestStats = ref<{
  total_papers: number
  avg_relevance_score: number | null
  large_institution_count: number
  institution_distribution: { name: string; count: number }[]
} | null>(null)

// Onboarding hint: encourage authenticated users to set up paper_recommend
const showRecommendHint = ref(false)

// Missed papers panel: papers the recommendation engine scored lower than the user might prefer
const missedPapersOpen = ref(false)

// Reactivation panel: revisit + question items from the most recent successful recap
const reactivationOpen = ref(false)

// Review drawer: spaced-repetition cards due today
const reviewOpen = ref(false)
const reviewCards = ref<ReviewCard[]>([])
const reviewLoading = ref(false)

async function openReviewDrawer() {
  reviewOpen.value = true
  if (reviewCards.value.length > 0) return
  reviewLoading.value = true
  try {
    const res = await fetchReviewCards(5)
    reviewCards.value = res.cards
  } catch {
    // fall back to radar preview if API unavailable
    reviewCards.value = (radarData.value?.review?.preview ?? []) as ReviewCard[]
  } finally {
    reviewLoading.value = false
  }
}

async function handleReviewResponse(card: ReviewCard, response: 'remember' | 'reread' | 'dismiss_forever' | 'skip') {
  const pid = card.paper_id || card._paper_id
  if (pid) {
    try { await recordReviewResponse(pid, response) } catch { /* non-critical */ }
  }
  reviewCards.value = reviewCards.value.filter(c => (c.paper_id || c._paper_id) !== pid)
  if (response === 'reread' && pid) {
    reviewOpen.value = false
    router.push(`/papers/${pid}`)
  }
}

// ── Research Radar ────────────────────────────────────────────────────────
const radarData = ref<ResearchRadarResponse | null>(null)
const radarLoading = ref(false)

async function loadRadar(date: string) {
  if (!date) return
  radarLoading.value = true
  try {
    radarData.value = await fetchResearchRadar(date)
  } catch {
    // radar failure must not block the main paper feed
    radarData.value = null
  } finally {
    radarLoading.value = false
  }
}

// Knowledge base + sidebar shared state
const { kbTree, activeFolderId, compareTree, showSidebar, loadKbTree, loadCompareTree, collapseSidebarOnMobile, markPaperReadStatus } = useKbSidebarState()
const knowledgeWorkspaceActive = ref(false)

const sidebarWasOpenBeforeImmersive = ref(true)
watch(digestViewMode, (mode, previousMode) => {
  if (mode === 'immersive') {
    sidebarWasOpenBeforeImmersive.value = showSidebar.value
    showSidebar.value = false
  } else if (previousMode === 'immersive' && sidebarWasOpenBeforeImmersive.value) {
    showSidebar.value = true
  }
}, { immediate: true })

// List mode pagination derived state
const listScrollRef = ref<HTMLElement | null>(null)
function listGoPage(page: number) {
  listPage.value = page
  listScrollRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
}

// Track paper card views for funnel analytics
watch(currentPaper, (paper) => {
  if (paper?.paper_id) trackPaperCardView(paper.paper_id)
})
const isActuallyLimited = computed(() => {
  if (quotaLimit.value === null) return false
  return totalAvailable.value > papers.value.length
})

watch([sortMode, topicFilter], () => { cardAnimClass.value = 'card-enter' })

// Auto-advance across dates: becomes true only when all available dates are exhausted
const allDatesExhausted = ref(false)
// Brief toast shown when we silently advance to the previous day
const dateTransitionNotice = ref<string | null>(null)
let _dateNoticeTimer: ReturnType<typeof setTimeout> | null = null

// Count total KB papers for display
const kbPaperCount = computed(() => {
  let count = kbTree.value.papers.length
  function countInFolders(folders: typeof kbTree.value.folders) {
    for (const f of folders) {
      count += f.papers?.length ?? 0
      if (f.children?.length) countInFolders(f.children)
    }
  }
  countInFolders(kbTree.value.folders)
  return count
})

// Flat list of KB papers whose read_status is unread (or unset)
const kbUnreadPapers = computed(() => {
  const all: any[] = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function collect(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(collect)]
    }),
  ]
  return all.filter((p: any) => !p.read_status || p.read_status === 'unread')
})

// Flat list of all KB papers sorted by created_at desc (for "launch analysis" action)
const kbAllPapersRecent = computed(() => {
  const all: any[] = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function collect(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(collect)]
    }),
  ]
  return all.slice().sort((a: any, b: any) =>
    new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
  )
})

// Task-line items for the DailyResearchTaskline component
const researchTasklineItems = computed<TasklineItem[]>(() => {
  if (!isAuthenticated.value) return []
  const items: TasklineItem[] = []

  // 1. Today's progress + streak (always shown to authenticated users)
  const streak = engagement.status.value?.streak?.current ?? 0
  items.push({
    id: 'today_progress',
    label: '',
    status: engagement.allDone.value ? 'done' : 'active',
    isProgress: true,
    progressTasks: engagement.taskItems.value.map(t => ({ key: t.key, label: t.label, done: t.done })),
    streakDays: streak > 0 ? streak : undefined,
  })

  // 2. Continue browsing today's feed
  if (remaining.value > 0 && !loading.value && !error.value) {
    const viewDone = engagement.taskItems.value.find(t => t.key === 'view')?.done ?? false
    items.push({
      id: 'continue_browse',
      label: '继续浏览',
      sub: `还剩 ${remaining.value} 篇`,
      status: viewDone ? 'idle' : 'active',
      action: 'continue_browse',
      count: remaining.value,
    })
  }

  // 3. Unread KB papers (collected but not yet opened)
  const unreadCount = kbUnreadPapers.value.length
  if (unreadCount > 0) {
    items.push({
      id: 'open_unread',
      label: '待读收藏',
      status: 'active',
      action: 'open_unread',
      count: unreadCount,
    })
  }

  // 4. Suggest launching deep research/compare when ≥2 KB papers available
  if (kbPaperCount.value >= 2) {
    const analyzeDone = engagement.taskItems.value.find(t => t.key === 'analyze')?.done ?? false
    items.push({
      id: 'open_research',
      label: '可发起分析',
      sub: `${kbPaperCount.value} 篇`,
      status: analyzeDone ? 'done' : 'idle',
      action: analyzeDone ? undefined : 'open_research',
    })
  }

  // 5. Missed papers (suppressed by recommendation engine)
  const missedCount = radarData.value?.missed?.count ?? 0
  if (missedCount > 0) {
    items.push({
      id: 'open_missed',
      label: '可能错过',
      status: 'active',
      action: 'open_missed',
      count: missedCount,
      urgent: true,
    })
  }

  // 6. Spaced-review cards due today
  const reviewCount = radarData.value?.review?.count ?? 0
  if (reviewCount > 0) {
    items.push({
      id: 'open_review',
      label: '到期复习',
      status: 'active',
      action: 'open_review',
      count: reviewCount,
      urgent: true,
    })
  }

  // 7. Weekly recap / research outcomes (only when recap has been generated)
  if (radarData.value?.recap?.status === 'ok') {
    items.push({
      id: 'open_recap',
      label: '研究成果',
      sub: `本周 ${radarData.value.recap.paper_count} 篇`,
      status: 'active',
      action: 'open_recap',
    })
  }

  // 8. Reactivation suggestions (revisit + questions from most recent recap)
  const reactivationCount = radarData.value?.reactivation?.count ?? 0
  if (reactivationCount > 0) {
    items.push({
      id: 'open_reactivation',
      label: '旧收藏新线索',
      sub: `${reactivationCount} 条`,
      status: 'active',
      action: 'open_reactivation',
    })
  }

  return items
})

// 加载日期列表（可被 retryLoad 复用）
async function loadDates() {
  try {
    const res = await fetchDates()
    dates.value = res.dates
    allDatesExhausted.value = false
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch (e: any) {
    errorType.value = e?.errorType || 'unknown'
    error.value = e?.message || '获取日期失败'
  }
}

// ---------------------------------------------------------------------------
// Tool query dispatcher — triggered by Navbar "研究工具" menu navigation
// ---------------------------------------------------------------------------
async function applyToolQuery(tool: string | string[] | undefined) {
  const t = Array.isArray(tool) ? tool[0] : tool
  if (!t) return
  switch (t) {
    case 'knowledge':
      await handleGoToDigestClick()
      knowledgeWorkspaceActive.value = true
      showSidebar.value = true
      nextTick(() => sidebarRef.value?.switchToPapersTab?.())
      break
    case 'compare-library':
      showSidebar.value = true
      nextTick(() => sidebarRef.value?.switchToCompareTab?.())
      break
    case 'research-library':
      showSidebar.value = true
      nextTick(() => sidebarRef.value?.switchToResearchTab?.())
      break
    case 'research':
      handleTabChanged('research')
      {
        const rawProjectId = Array.isArray(route.query.project_id) ? route.query.project_id[0] : route.query.project_id
        const projectId = typeof rawProjectId === 'string' ? Number(rawProjectId) : NaN
        if (Number.isFinite(projectId)) {
          try {
            const project = await fetchResearchProject(projectId)
            researchProjectId.value = project.id
            researchPaperIds.value = project.paper_ids
            researchPaperTitles.value = Object.fromEntries(
              project.assets
                .filter(asset => asset.asset_type === 'paper' && !asset.missing)
                .map(asset => [asset.asset_id, asset.title]),
            )
            researchScope.value = 'kb'
            const rawQuestion = Array.isArray(route.query.question) ? route.query.question[0] : route.query.question
            researchInitialQuestion.value = typeof rawQuestion === 'string' && rawQuestion.trim()
              ? rawQuestion.trim()
              : project.objective
          } catch (err) {
            showError('打开课题研究失败，请稍后重试')
            console.error('[Research] project load failed', err)
          }
        }
      }
      break
    case 'compare':
      {
        const rawProjectId = Array.isArray(route.query.project_id) ? route.query.project_id[0] : route.query.project_id
        const projectId = typeof rawProjectId === 'string' ? Number(rawProjectId) : NaN
        if (Number.isFinite(projectId)) {
          try {
            const project = await fetchResearchProject(projectId)
            handleCompare(project.paper_ids, 'kb')
          } catch (err) {
            showError('打开课题对比失败，请稍后重试')
            console.error('[Compare] project load failed', err)
          }
        } else {
          handleCompare([])
        }
      }
      break
  }
}

async function applyAssetTargetQuery() {
  if (!isAuthenticated.value) return
  const paperId = Array.isArray(route.query.paper) ? route.query.paper[0] : route.query.paper
  const resultId = Array.isArray(route.query.result) ? route.query.result[0] : route.query.result
  const sessionId = Array.isArray(route.query.session) ? route.query.session[0] : route.query.session

  if (route.query.tab === 'mypapers' && typeof paperId === 'string' && paperId) {
    await openUserPaper(paperId)
    return
  }
  if (typeof resultId === 'string' && Number.isFinite(Number(resultId))) {
    await openCompareResult(Number(resultId))
    return
  }
  if (typeof sessionId === 'string' && Number.isFinite(Number(sessionId))) {
    await handleOpenResearchSession(Number(sessionId))
  }
}

// Load dates
onMounted(async () => {
  attachAnnotationAdapter()
  await ensureAuthInitialized()
  await loadDates()

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
    await engagement.loadStatus(true)
    // Show onboarding hint once for new authenticated users
    if (!localStorage.getItem('ai4p-recommend-hint-dismissed')) {
      showRecommendHint.value = true
    }
  }

  // Handle ?tab=mypapers redirect from /my-papers
  if (route.query.tab === 'mypapers' && isAuthenticated.value) {
    showSidebar.value = true
    sidebarRef.value?.switchToMyPapersTab?.()
  }

  // Handle ?tool= queries from the Navbar "研究工具" menu
  if (route.query.tool) {
    await nextTick()
    await applyToolQuery(route.query.tool)
  }

  await applyAssetTargetQuery()

  // Register keyboard shortcuts
  window.addEventListener('keydown', handleKeydown)
})

// Collapse KB sidebar when chat drawer opens on narrow viewports (< 1280px)
watch(
  () => globalChat.collapseSidebarSignal.value,
  () => { showSidebar.value = false },
)

// Watch global chat research/compare signals from PaperChat shortcuts
watch(
  () => globalChat.researchRequest.value,
  (req) => {
    if (!req) return
    handleResearch(req.paperIds, req.titles, req.scope)
    globalChat.consumeResearchRequest()
  },
)

watch(
  () => globalChat.compareRequest.value,
  (req) => {
    if (!req) return
    handleCompare(req.paperIds)
    globalChat.consumeCompareRequest()
  },
)

// Record analyze when user sends a message in the global chat drawer
watch(
  () => globalChat.messageSentSignal.value,
  (n, old) => {
    if (n > 0 && n !== old && isAuthenticated.value) {
      void engagement.record('analyze', 'daily-digest-chat', '')
    }
  },
)

// React to ?tool= query changes so repeated menu clicks (different tool) work
// even when already on the digest page
watch(
  () => route.query.tool,
  (tool) => {
    if (tool) void applyToolQuery(tool)
  },
)

watch(
  () => [route.query.paper, route.query.result, route.query.session],
  () => { void applyAssetTargetQuery() },
)

// Notice shown when pipeline ran but produced 0 papers
const dateNotice = ref<{ type: string; message: string } | null>(null)

// Fallback tracking: when the requested date has no unread papers, the backend
// returns papers from an earlier date and sets is_fallback + effective_date.
const effectiveDate = ref<string | null>(null)
const isFallback = ref(false)

async function loadDigestForDate(date: string, fallbackAuthed = isAuthenticated.value) {
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  dateNotice.value = null
  isFallback.value = false
  effectiveDate.value = null
  try {
    const res = await fetchDigest(date)
    const fetchedPapers = Array.isArray(res.papers) ? res.papers : []
    papers.value = fetchedPapers
    totalAvailable.value = res.total_available ?? fetchedPapers.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (fallbackAuthed ? currentTier.value : 'anonymous')
    dateNotice.value = res.notice ?? null
    digestStats.value = {
      total_papers: res.total_papers ?? fetchedPapers.length,
      avg_relevance_score: res.avg_relevance_score ?? null,
      large_institution_count: res.large_institution_count ?? 0,
      institution_distribution: res.institution_distribution ?? [],
    }
    // Fallback metadata from backend
    effectiveDate.value = (res.effective_date as string | undefined) ?? date
    isFallback.value = (res.is_fallback as boolean | undefined) ?? false
    currentIndex.value = 0
    listPage.value = 0
    history.value = []
    clearPaperSelection()
    listInspectorOpen.value = false
    cardAnimClass.value = 'card-enter'
    // When the backend fell back to an earlier date, sync the date selector so
    // that auto-advance (watch allSwiped) can navigate from the correct position.
    // The watcher below skips reloading when it detects this programmatic sync.
    if (isFallback.value && effectiveDate.value && effectiveDate.value !== date) {
      selectedDate.value = effectiveDate.value
    }
    if (import.meta.env.DEV) {
      console.debug('[DailyDigest] digest loaded', {
        date,
        effectiveDate: effectiveDate.value,
        isFallback: isFallback.value,
        papers: papers.value.length,
        totalAvailable: totalAvailable.value,
        quotaLimit: quotaLimit.value,
        tier: responseTier.value,
      })
    }
  } catch (e: any) {
    errorType.value = e?.errorType || (e?.response ? 'server' : 'unknown')
    error.value = e?.message || '加载失败'
    papers.value = []
    totalAvailable.value = 0
    quotaLimit.value = null
    responseTier.value = 'anonymous'
    isFallback.value = false
    effectiveDate.value = null
    digestStats.value = null
  } finally {
    loading.value = false
  }
}

// Load papers on date change
// 在深度研究面板激活时跳过，避免日期切换时意外触发论文推荐卡片加载。
// 当 loadDigestForDate 因 fallback 同步 selectedDate 时，跳过重复请求。
watch(selectedDate, async (date) => {
  if (!date) return
  if (researchPaperIds.value !== null) return
  // Skip reload triggered by our own programmatic sync of selectedDate to effectiveDate
  if (isFallback.value && date === effectiveDate.value) return
  await loadDigestForDate(date)
  void loadRadar(date)
})

// Auto-advance to the previous day when the current day is fully swiped.
// Skip when quota is exceeded — those users should see the upgrade prompt instead.
watch(allSwiped, (val) => {
  if (!val) return
  if (isQuotaExceeded.value && isActuallyLimited.value) return
  const currentIdx = dates.value.indexOf(selectedDate.value)
  const nextIdx = currentIdx + 1
  if (nextIdx < dates.value.length) {
    const nextDate = dates.value[nextIdx]
    if (_dateNoticeTimer) clearTimeout(_dateNoticeTimer)
    dateTransitionNotice.value = nextDate
    _dateNoticeTimer = setTimeout(() => { dateTransitionNotice.value = null }, 3500)
    selectedDate.value = nextDate
  } else {
    allDatesExhausted.value = true
  }
})

// 判断是否超限（用户已刷完所有允许的论文，且论文数等于配额上限）
const isQuotaExceeded = computed(() => {
  if (loading.value) return false
  const limit = quotaLimit.value
  const paperCount = papers.value.length
  if (limit === null || paperCount === 0) return false
  return currentIndex.value >= paperCount && paperCount >= limit
})

// 获取超限提示信息
const quotaExceededMessage = computed(() => {
  const tier = responseTier.value
  const limit = quotaLimit.value
  if (import.meta.env.DEV) {
    console.debug('[DailyDigest] quota message state', { tier, limit })
  }
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') {
    return `您已达到 Pro 账号上限（${limit ?? 15} 条）`
  }
  if (tier === 'anonymous') {
    return `您已达到未登录账号上限（${limit ?? 3} 条）`
  }
  return `您已达到普通账号上限（${limit ?? 3} 条）`
})

// 不再需要弹窗控制

watch(
  () => isAuthenticated.value,
  async (authed) => {
    if (authed) {
      await loadKbTree()
      await loadCompareTree()
      await engagement.loadStatus(true)
      if (!localStorage.getItem('ai4p-recommend-hint-dismissed')) {
        showRecommendHint.value = true
      }
    } else {
      kbTree.value = { folders: [], papers: [] }
      compareTree.value = null
      activeFolderId.value = null
      engagement.status.value = null
      engagement.loaded.value = false
    }
    // Login/logout changes user-scoped filtering and quota.
    // Reload digest to avoid stale index/quota state from previous session.
    if (selectedDate.value) {
      const date = selectedDate.value
      await loadDigestForDate(date, authed)
    }
  },
)

function onDateChange(event: Event) {
  selectedDate.value = (event.target as HTMLSelectElement).value
}

function retryLoad() {
  errorType.value = 'unknown'
  error.value = ''
  if (dates.value.length === 0) {
    loadDates()
  } else if (selectedDate.value) {
    loadDigestForDate(selectedDate.value)
  }
}

// Actions
function next(direction: 'left' | 'right') {
  if (!currentPaper.value) return
  cardAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  rememberCurrentIndex()
  setTimeout(() => {
    moveToNext()
    cardAnimClass.value = 'card-enter'
  }, 300)
}

const {
  bookmarkedPaperIds,
  skip,
  collect: like,
  collectTarget,
  toggleBookmark: bookmark,
  toggleBookmarkTarget,
} = usePaperDecisionActions({
  currentPaper,
  isAuthenticated,
  advance: next,
  redirectToLogin: () => {
    void router.push({ path: '/login', query: { redirect: route.fullPath } })
  },
  // Logged-in dismissals remain a silent background action.
  dismissPaper: paper => dismissPaper(paper.paper_id),
  collectPaper: paper => addKbPaper(paper.paper_id, paper, null).then(() => loadKbTree()),
  onDismiss: (paper) => {
    trackKbAction('dismiss', paper.paper_id)
  },
  onCollect: (paper) => {
    trackKbAction('save', paper.paper_id)
    void engagement.record('collect', 'daily-digest-like', paper.paper_id)
  },
})

const collectedPaperIds = ref<Set<string>>(new Set())
const listInspectorOpen = ref(false)
const selectedPaperCount = computed(() => selectedPaperIds.value.size)
const currentPagePaperIds = computed(() => pagedPapers.value.map(paper => paper.paper_id))
const isCurrentPageSelected = computed(() =>
  currentPagePaperIds.value.length > 0
  && currentPagePaperIds.value.every(paperId => selectedPaperIds.value.has(paperId)),
)

function toggleCurrentPageSelection() {
  if (isCurrentPageSelected.value) {
    const remainingSelection = new Set(selectedPaperIds.value)
    currentPagePaperIds.value.forEach(paperId => remainingSelection.delete(paperId))
    selectPaperIds(remainingSelection)
  } else {
    selectPaperIds([...selectedPaperIds.value, ...currentPagePaperIds.value])
  }
}

function collectListPaper(paper: PaperSummary) {
  if (!collectTarget(paper, false)) return
  collectedPaperIds.value = new Set([...collectedPaperIds.value, paper.paper_id])
}

function bookmarkListPaper(paper: PaperSummary) {
  toggleBookmarkTarget(paper, false)
}

function collectSelectedPapers() {
  const selected = displayPapers.value.filter(paper => selectedPaperIds.value.has(paper.paper_id))
  selected.forEach(collectListPaper)
}

function compareSelectedPapers() {
  const ids = [...selectedPaperIds.value]
  if (ids.length < 2) return
  handleCompare(ids, 'digest-list')
}

function startListResearch(paper: PaperSummary) {
  handleResearch(
    [paper.paper_id],
    { [paper.paper_id]: paper.short_title || paper['📖标题'] || paper.paper_id },
    'digest-list',
  )
}

const immersiveRelatedPapers = computed(() => {
  const active = currentPaper.value
  if (!active) return []
  const activeCategories = new Set(active.categories ?? [])
  const overlapScore = (paper: PaperSummary) =>
    (paper.categories ?? []).reduce((count, category) => count + (activeCategories.has(category) ? 1 : 0), 0)
  return displayPapers.value
    .filter(paper => paper.paper_id !== active.paper_id)
    .sort((a, b) => overlapScore(b) - overlapScore(a) || (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
    .slice(0, 3)
})

function navigateImmersive(delta: -1 | 1) {
  selectDigestPaper(Math.max(0, Math.min(currentIndex.value + delta, displayPapers.value.length - 1)))
}

function openImmersiveRelated(paperId: string) {
  selectDigestPaperById(paperId)
}

function compareImmersivePaper() {
  const active = currentPaper.value
  const related = immersiveRelatedPapers.value[0]
  if (!active || !related) {
    showError('当前筛选结果中暂无可对比论文')
    return
  }
  handleCompare([active.paper_id, related.paper_id], 'digest-immersive')
}

function undo() {
  if (!restorePreviousIndex()) return
  cardAnimClass.value = 'card-enter'
}

// Select a paper while keeping the list visible and updating the persistent inspector.
function openListDetail(paper: PaperSummary, idx: number) {
  selectDigestPaper(idx)
  listInspectorOpen.value = true
  collapseSidebarOnMobile()
  globalChat.setBrowsingContext({
    paperId: paper.paper_id,
    title: paper.short_title || paper['📖标题'] || paper.paper_id,
    summary: paper,
    source: 'paper-detail',
  })
  globalChat.applyBrowsingToPaperContext()
  void engagement.record('view', 'daily-digest-detail', paper.paper_id)
}

function openListPaper(paper: PaperSummary, idx: number) {
  selectDigestPaper(idx)
  openDetail()
}

// Keyboard shortcut handler for card navigation
function handleKeydown(e: KeyboardEvent) {
  const target = e.target as HTMLElement
  if (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  ) return
  if (isInPanelView.value) return

  // Immersive mode keeps reading navigation and research actions available without leaving the document.
  if (digestViewMode.value === 'immersive') {
    if (e.key === 'Escape' || e.key === 'l' || e.key === 'L') {
      e.preventDefault()
      setDigestViewMode('list')
      return
    }
    if (!currentPaper.value || loading.value) return
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'j' || e.key === 'J') {
      e.preventDefault()
      navigateImmersive(-1)
      return
    }
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'k' || e.key === 'K') {
      e.preventDefault()
      navigateImmersive(1)
      return
    }
    if (e.key === 'Enter' || e.key === 'd' || e.key === 'D') {
      e.preventDefault()
      openDetail()
      return
    }
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault()
      openPdf()
      return
    }
    if (e.key === 's' || e.key === 'S') {
      e.preventDefault()
      collectListPaper(currentPaper.value)
      return
    }
    if (e.key === 'b' || e.key === 'B') {
      e.preventDefault()
      bookmarkListPaper(currentPaper.value)
      return
    }
    if (e.key === 'c' || e.key === 'C') {
      e.preventDefault()
      compareImmersivePaper()
      return
    }
    if (e.key === 'r' || e.key === 'R') {
      e.preventDefault()
      startListResearch(currentPaper.value)
      return
    }
    if (e.key === 'x' || e.key === 'X') {
      e.preventDefault()
      skip()
    }
    return
  }
  // List mode keeps selection, the inspector and keyboard navigation in sync.
  if (digestViewMode.value === 'list') {
    if (e.key === 'i' || e.key === 'I') {
      e.preventDefault()
      setDigestViewMode('immersive')
      return
    }
    if (e.key === 'Escape' && listInspectorOpen.value) {
      e.preventDefault()
      listInspectorOpen.value = false
      return
    }
    if (e.key === 'Escape' || e.key === 'l' || e.key === 'L') {
      e.preventDefault()
      setDigestViewMode('card')
      return
    }
    if (!currentPaper.value || loading.value) return
    if (e.key === 'ArrowDown' || e.key === 'j' || e.key === 'J') {
      e.preventDefault()
      selectDigestPaper(Math.min(currentIndex.value + 1, displayPapers.value.length - 1))
      return
    }
    if (e.key === 'ArrowUp' || e.key === 'k' || e.key === 'K') {
      e.preventDefault()
      selectDigestPaper(Math.max(currentIndex.value - 1, 0))
      return
    }
    if (e.key === 'Enter' || e.key === 'd' || e.key === 'D') {
      e.preventDefault()
      openDetail()
      return
    }
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault()
      openPdf()
      return
    }
    if (e.key === 's' || e.key === 'S') {
      e.preventDefault()
      collectListPaper(currentPaper.value)
      return
    }
    if (e.key === 'b' || e.key === 'B') {
      e.preventDefault()
      bookmarkListPaper(currentPaper.value)
    }
    return
  }

  if (!currentPaper.value || loading.value) return

  switch (e.key) {
    case 'ArrowLeft':
    case 'j':
    case 'J':
      e.preventDefault()
      skip()
      break
    case 'ArrowRight':
    case 'k':
    case 'K':
      e.preventDefault()
      like()
      break
    case 'd':
    case 'D':
      e.preventDefault()
      openDetail()
      break
    case 'p':
    case 'P':
      e.preventDefault()
      openPdf()
      break
    case 'z':
    case 'Z':
      e.preventDefault()
      undo()
      break
    case 'b':
    case 'B':
      e.preventDefault()
      bookmark()
      break
    case 'l':
    case 'L':
      e.preventDefault()
      setDigestViewMode('list')
      break
    case 'i':
    case 'I':
      e.preventDefault()
      setDigestViewMode('immersive')
      break
  }
}

// Onboarding hint functions
function dismissRecommendHint() {
  showRecommendHint.value = false
  try { localStorage.setItem('ai4p-recommend-hint-dismissed', '1') } catch { /* ignore */ }
}

function openDetail() {
  const paper = currentPaper.value
  if (!paper) return
  globalChat.setBrowsingContext({
    paperId: paper.paper_id,
    title: paper.short_title || paper['📖标题'] || paper.paper_id,
    summary: paper,
    source: 'paper-detail',
  })
  globalChat.applyBrowsingToPaperContext()
  void engagement.record('view', 'daily-digest-detail', paper.paper_id)
  void router.push({
    name: 'paper-detail',
    params: { id: paper.paper_id },
    query: { from: 'digest' },
  })
}

function openPdf() {
  if (currentPaper.value) {
    openExternal(`https://arxiv.org/pdf/${currentPaper.value.paper_id}`)
    void engagement.record('view', 'daily-digest-pdf', currentPaper.value.paper_id)
  }
}

// Sidebar ref for refreshing notes
const sidebarRef = ref<InstanceType<typeof Sidebar> | null>(null)

// Inline note editor（携带 noteId + paperId，方便右侧显示详情）
const editingNote = ref<{ id: number; paperId: string } | null>(null)

// 从知识库点击的论文，在中间区域居中展示详情
const sidebarPaperId = ref<string | null>(null)
const viewingPdf = ref<{ paperId: string; filePath: string; title: string } | null>(null)
/** 我的论文：左侧 PDF + 右侧 Markdown 渲染 */
const viewingMd = ref<UserPaperViewMdPayload | null>(null)

/** 侧栏「我的论文」高亮：详情或子链接所属论文 */
const sidebarActiveUserPaperId = computed(
  () => viewingUserPaperId.value ?? viewingMd.value?.paperId ?? null,
)
/** 侧栏子链接选中：paperId:viewMode */
const sidebarActiveViewMdKey = computed(() => {
  const v = viewingMd.value
  if (!v?.paperId || v.viewMode == null) return null
  return `${v.paperId}:${v.viewMode}`
})

// 用户上传论文展示
const myPapersMode = ref(false)          // 「我的论文」Tab 是否激活
const myPapersCenter = ref<UserPaper[]>([])  // 中间区域展示的用户论文列表
const myPapersCenterLoading = ref(false)
const viewingUserPaperId = ref<string | null>(null)
const viewingUserPaper = ref<UserPaper | null>(null)
const userPaperLoading = ref(false)
let _userPaperPollTimer: ReturnType<typeof setInterval> | null = null
let _myPapersCenterPollTimer: ReturnType<typeof setInterval> | null = null
let _processingTickTimer: ReturnType<typeof setInterval> | null = null
const processingElapsedSeconds = ref(0)
const showUploadDialog = ref(false)

// 我的论文：搜索 / 筛选 / 排序 / 视图模式 / 分页
const myPapersSearch = ref('')
const myPapersSourceFilter = ref('')
const myPapersInstitutionFilter = ref('')
const myPapersInstitutions = ref<string[]>([])
const myPapersSort = ref<'date_desc' | 'date_asc' | 'title_asc'>('date_desc')
const myPapersViewMode = ref<'card' | 'compact'>('card')
const myPapersTotal = ref(0)
const myPapersPageSize = 20
const myPapersHasMore = ref(false)
let _myPapersSearchDebounce: ReturnType<typeof setTimeout> | null = null

async function loadMyPapersInstitutions() {
  try {
    myPapersInstitutions.value = await fetchUserPaperInstitutions()
  } catch (e) {
    console.warn('[MyPapers] 加载机构列表失败', e)
  }
}

// sorted view of the currently loaded page(s)
const myPapersCenterSorted = computed(() => {
  const list = myPapersCenter.value
  if (myPapersSort.value === 'title_asc') {
    return [...list].sort((a, b) =>
      (a.title || '').localeCompare(b.title || '', 'zh-CN')
    )
  }
  if (myPapersSort.value === 'date_asc') {
    return [...list].sort((a, b) => a.created_at.localeCompare(b.created_at))
  }
  return list // date_desc — default from backend
})

async function loadMyPapersCenter(opts?: { append?: boolean }) {
  myPapersCenterLoading.value = true
  try {
    const offset = opts?.append ? myPapersCenter.value.length : 0
    const res = await fetchUserPapers({
      limit: myPapersPageSize,
      offset,
      search: myPapersSearch.value.trim() || undefined,
      source_type: myPapersSourceFilter.value || undefined,
      institution: myPapersInstitutionFilter.value || undefined,
    })
    if (opts?.append) {
      myPapersCenter.value = [...myPapersCenter.value, ...res.papers]
    } else {
      myPapersCenter.value = res.papers
    }
    myPapersTotal.value = res.total
    // "has more" = we got a full page (filtered count unknown from backend)
    myPapersHasMore.value = res.papers.length >= myPapersPageSize
    // 若有处理中的论文，启动轮询刷新
    const hasProcessing = res.papers.some(
      p => p.process_status === 'processing' || p.process_status === 'pending'
    )
    if (hasProcessing) {
      _startMyPapersCenterPoll()
    } else {
      _stopMyPapersCenterPoll()
    }
  } catch (e) {
    showError('加载上传论文列表失败，请稍后重试')
    console.error('[MyPapers] loadMyPapersCenter 失败', e)
  } finally {
    myPapersCenterLoading.value = false
  }
}

function loadMoreMyPapers() {
  loadMyPapersCenter({ append: true })
}

// debounced reload when search / filter changes
watch([myPapersSearch, myPapersSourceFilter, myPapersInstitutionFilter], () => {
  if (_myPapersSearchDebounce) clearTimeout(_myPapersSearchDebounce)
  _myPapersSearchDebounce = setTimeout(() => {
    myPapersCenter.value = []
    loadMyPapersCenter()
  }, 300)
})

function _startMyPapersCenterPoll() {
  if (_myPapersCenterPollTimer) return
  _myPapersCenterPollTimer = setInterval(async () => {
    try {
      const loadedCount = Math.max(myPapersCenter.value.length, myPapersPageSize)
      const res = await fetchUserPapers({
        limit: loadedCount,
        offset: 0,
        search: myPapersSearch.value.trim() || undefined,
        source_type: myPapersSourceFilter.value || undefined,
        institution: myPapersInstitutionFilter.value || undefined,
      })
      // Merge: update statuses in-place, preserve pagination state
      const updatedMap = new Map(res.papers.map(p => [p.paper_id, p]))
      myPapersCenter.value = myPapersCenter.value.map(p => updatedMap.get(p.paper_id) ?? p)
      myPapersTotal.value = res.total
      myPapersHasMore.value = res.papers.length >= loadedCount && myPapersCenter.value.length < res.total
      const hasProcessing = res.papers.some(
        p => p.process_status === 'processing' || p.process_status === 'pending'
      )
      if (!hasProcessing) _stopMyPapersCenterPoll()
    } catch {}
  }, 3000)
}

function _stopMyPapersCenterPoll() {
  if (_myPapersCenterPollTimer) {
    clearInterval(_myPapersCenterPollTimer)
    _myPapersCenterPollTimer = null
  }
}

async function openKnowledgeWorkspace() {
  await handleGoToDigestClick()
  knowledgeWorkspaceActive.value = true
  showSidebar.value = true
}

function handleTabChanged(tab: string) {
  if (tab === 'papers') {
    void openKnowledgeWorkspace()
    return
  }
  knowledgeWorkspaceActive.value = false
  if (tab === 'mypapers') {
    // 切换到其他 Tab 时关闭研究面板（无论是否有活跃论文）
    researchPaperIds.value = null
    myPapersMode.value = true
    sidebarPaperId.value = null
    viewingPdf.value = null
    viewingMd.value = null
    comparingPaperIds.value = null
    viewingCompareResultId.value = null
    viewingUserPaperId.value = null
    viewingUserPaper.value = null
    _stopUserPaperPoll()
    globalChat.clearBrowsingContext()
    loadMyPapersCenter()
    loadMyPapersInstitutions()
  } else if (tab === 'research') {
    myPapersMode.value = false
    sidebarPaperId.value = null
    viewingPdf.value = null
    viewingMd.value = null
    comparingPaperIds.value = null
    viewingCompareResultId.value = null
    editingNote.value = null
    _stopMyPapersCenterPoll()
    globalChat.clearBrowsingContext()
    // 点击深度研究 Tab（含重复点击）时始终重置到空态首页
    researchPaperIds.value = []
    researchPaperTitles.value = {}
    researchInitialSessionId.value = null
    researchProjectId.value = null
    researchInitialQuestion.value = ''
  } else {
    // 切换到其他 Tab 时关闭研究面板（无论是否有活跃论文）
    researchPaperIds.value = null
    researchProjectId.value = null
    researchInitialQuestion.value = ''
    myPapersMode.value = false
    viewingMd.value = null
    _stopMyPapersCenterPoll()
    globalChat.clearBrowsingContext()
  }
}

async function openUserPaper(paperId: string) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  myPapersMode.value = true  // 保持在「我的论文」模式
  viewingUserPaperId.value = paperId
  await _loadUserPaper(paperId)
  const p = viewingUserPaper.value
  if (p) {
    globalChat.setBrowsingContext({
      paperId,
      title: p.title || paperId,
      summary: p.summary ?? undefined,
      source: 'user-paper',
    })
    globalChat.applyBrowsingToPaperContext()
  }
  collapseSidebarOnMobile()
}

function closeUserPaperDetail() {
  viewingUserPaperId.value = null
  viewingUserPaper.value = null
  _stopUserPaperPoll()
  globalChat.clearBrowsingContext()
  // 回到我的论文列表视图
  if (myPapersMode.value) loadMyPapersCenter()
}

async function _loadUserPaper(paperId: string) {
  userPaperLoading.value = true
  try {
    const p = await fetchUserPaperDetail(paperId)
    viewingUserPaper.value = p
    // If processing, start polling
    if (p.process_status === 'processing' || p.process_status === 'pending') {
      _startUserPaperPoll(paperId)
    } else {
      _stopUserPaperPoll()
    }
  } catch (e) {
    showError('加载论文详情失败，请稍后重试')
    console.error('[UserPaper] _loadUserPaper 失败', e)
  } finally {
    userPaperLoading.value = false
  }
}

function _startUserPaperPoll(paperId: string) {
  if (_userPaperPollTimer) return
  _userPaperPollTimer = setInterval(async () => {
    try {
      const p = await fetchUserPaperDetail(paperId)
      viewingUserPaper.value = p
      // Also refresh sidebar list
      sidebarRef.value?.refreshMyPapers()
      if (p.process_status !== 'processing' && p.process_status !== 'pending') {
        _stopUserPaperPoll()
      }
    } catch {}
  }, 3000)
  // Elapsed timer: tick every second to drive the "已耗时" display
  if (!_processingTickTimer) {
    const p = viewingUserPaper.value
    const startedAt = p?.process_started_at ? new Date(p.process_started_at).getTime() : Date.now()
    _processingTickTimer = setInterval(() => {
      processingElapsedSeconds.value = Math.floor((Date.now() - startedAt) / 1000)
    }, 1000)
  }
}

function _stopUserPaperPoll() {
  if (_userPaperPollTimer) {
    clearInterval(_userPaperPollTimer)
    _userPaperPollTimer = null
  }
  if (_processingTickTimer) {
    clearInterval(_processingTickTimer)
    _processingTickTimer = null
    processingElapsedSeconds.value = 0
  }
}

async function handleRetryUserPaper() {
  if (!viewingUserPaperId.value) return
  try {
    await processUserPaper(viewingUserPaperId.value)
    await _loadUserPaper(viewingUserPaperId.value)
  } catch (e) {
    showError('重新处理论文失败，请稍后重试')
    console.error('[UserPaper] handleRetryUserPaper 失败', e)
  }
}

async function handleUploadDialogUploaded(paperId: string) {
  showUploadDialog.value = false
  await openUserPaper(paperId)
  sidebarRef.value?.refreshMyPapers()
  // 也刷新中间区域的列表（如果正处于 myPapersMode）
  if (myPapersMode.value) {
    await loadMyPapersCenter()
    loadMyPapersInstitutions()
  }
}

onBeforeUnmount(() => {
  detachAnnotationAdapter()
  _stopUserPaperPoll()
  _stopMyPapersCenterPoll()
  if (_myPapersSearchDebounce) clearTimeout(_myPapersSearchDebounce)
  window.removeEventListener('keydown', handleKeydown)
})

// 笔记编辑器组件引用，便于外部触发保存/检查是否为空
/** 带笔记编辑的 ContentLayout，用于切换前 flush */
const digestContentLayoutRef = ref<InstanceType<typeof ContentLayout> | null>(null)

function getDigestNoteEditor() {
  return digestContentLayoutRef.value?.getNoteEditor?.() ?? null
}

// 深度研究 Q&A
const researchPaperIds = ref<string[] | null>(null)
const researchPaperTitles = ref<Record<string, string>>({})
const researchScope = ref<string>('kb')
const researchProjectId = ref<number | null>(null)

function handleResearch(paperIds: string[], paperTitles: Record<string, string>, scope?: string) {
  knowledgeWorkspaceActive.value = false
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchInitialSessionId.value = null
  researchProjectId.value = null
  researchInitialQuestion.value = ''
  researchPaperIds.value = paperIds
  researchPaperTitles.value = paperTitles
  researchScope.value = scope ?? 'kb'
  globalChat.clearBrowsingContext()
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'daily-digest-research', paperIds[0] || '')
}

async function handleOpenResearchSession(sessionId: number) {
  const { fetchResearchSession: fetchSession } = await import('../api')
  try {
    const session = await fetchSession(sessionId)
    editingNote.value = null
    sidebarPaperId.value = null
    viewingPdf.value = null
    viewingMd.value = null
    comparingPaperIds.value = null
    viewingCompareResultId.value = null
    researchPaperIds.value = session.paper_ids
    researchPaperTitles.value = {}
    researchScope.value = 'kb'
    researchInitialSessionId.value = sessionId
    researchProjectId.value = session.project_id ?? null
    researchInitialQuestion.value = ''
    globalChat.clearBrowsingContext()
    collapseSidebarOnMobile()
    void engagement.record('analyze', 'daily-digest-research-session', String(sessionId))
  } catch (e) {
    showError('打开深度研究会话失败，请稍后重试')
    console.error('[Research] handleOpenResearchSession 失败', e)
  }
}

function closeResearch() {
  researchPaperIds.value = null
  researchProjectId.value = null
  researchInitialQuestion.value = ''
  sidebarRef.value?.switchToPapersTab()
}

async function handleSaveToLibrary(sessionId: number) {
  try {
    await saveResearchSession(sessionId)
  } catch (e) {
    console.error('[Research] save failed', e)
  }
  sidebarRef.value?.switchToResearchTab()
}

function removeResearchPaper(paperId: string) {
  if (!researchPaperIds.value) return
  const next = researchPaperIds.value.filter((id) => id !== paperId)
  // Keep the panel open with empty state so the user can pick different papers
  researchPaperIds.value = next
  const titles = { ...researchPaperTitles.value }
  delete titles[paperId]
  researchPaperTitles.value = titles
}

// 对比分析
const comparingPaperIds = ref<string[] | null>(null)
const comparingResultIds = ref<number[]>([])
const compareScope = ref<KbScope>('kb')

// 查看已保存对比结果
const viewingCompareResultId = ref<number | null>(null)

// 构建 paper_id → short_title 映射，供 ComparePanel 显示标签
const comparePaperTitles = computed(() => {
  if (!comparingPaperIds.value) return {}
  const map: Record<string, string> = {}

  // 始终从我的论文列表中补充标题（跨库时可能包含 up_ 论文）
  for (const p of myPapersCenter.value) {
    map[p.paper_id] = p.title || p.paper_id
  }

  const allPapers = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function collectPapers(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(collectPapers)]
    }),
  ]
  for (const p of allPapers) {
    map[p.paper_id] = p.paper_data?.short_title || p.paper_id
  }
  return map
})

function handleCompare(paperIds: string[], scope?: string, resultIds?: number[]) {
  knowledgeWorkspaceActive.value = false
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  comparingPaperIds.value = paperIds
  comparingResultIds.value = resultIds ?? []
  compareScope.value = (scope as KbScope) ?? 'kb'
  globalChat.clearBrowsingContext()
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'daily-digest-compare', paperIds[0] || '')
}

function closeCompare() {
  comparingPaperIds.value = null
}

function handleCompareSaved(_resultId: number) {
  loadCompareTree()
}

function openCompareResult(resultId: number) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = resultId
  globalChat.clearBrowsingContext()
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'daily-digest-compare-result', String(resultId))
}

function closeCompareResult() {
  viewingCompareResultId.value = null
}

async function openPaperFromSidebar(paperId: string) {
  knowledgeWorkspaceActive.value = false
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  // 如果当前正在编辑笔记，优先处理笔记状态
  if (editingNote.value && getDigestNoteEditor()) {
    const isEmpty = getDigestNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      // 笔记无内容：不保留这条笔记，直接删除记录
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败，继续切换
      }
      editingNote.value = null
    } else {
      // 笔记有内容：先自动保存，再关闭编辑器
      try {
        await getDigestNoteEditor().flushSave()
      } catch {
        // 保存失败也不阻塞跳转
      }
      editingNote.value = null
    }
  }

  // 然后跳转到新点击论文的详情
  myPapersMode.value = false
  viewingUserPaperId.value = null
  viewingUserPaper.value = null
  _stopUserPaperPoll()
  _stopMyPapersCenterPoll()
  sidebarPaperId.value = paperId
  // 移动端：自动收起侧边栏，让用户立刻看到内容
  collapseSidebarOnMobile()
  void engagement.record('view', 'daily-digest-sidebar-paper', paperId)

  void (async () => {
    try {
      const d = await fetchPaperDetail(paperId)
      if (d?.summary) {
        globalChat.setBrowsingContext({
          paperId,
          title: d.summary.short_title || d.summary['📖标题'] || paperId,
          summary: d.summary,
          source: 'kb-paper',
        })
      } else {
        globalChat.setBrowsingContext({ paperId, title: paperId, source: 'kb-paper' })
      }
    } catch {
      globalChat.setBrowsingContext({ paperId, title: paperId, source: 'kb-paper' })
    }
    globalChat.applyBrowsingToPaperContext()
  })()
}

async function openNoteFromSidebar(payload: { id: number; paperId: string }) {
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  // 如果当前正在编辑笔记，先判断是否为空
  if (editingNote.value && getDigestNoteEditor()) {
    const isEmpty = getDigestNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      // 当前笔记为空：删除这条笔记记录，然后仅展示新点击论文的详情页
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
      editingNote.value = null
      sidebarPaperId.value = payload.paperId
      collapseSidebarOnMobile()
      return
    } else {
      // 当前笔记有内容：自动保存后再打开新点击笔记的详情编辑页
      try {
        await getDigestNoteEditor().flushSave()
      } catch {
        // 保存失败也不阻塞切换
      }
    }
  }

  editingNote.value = payload
  collapseSidebarOnMobile()
}

function openPdfFromSidebar(payload: { paperId: string; filePath: string; title: string }) {
  knowledgeWorkspaceActive.value = false
  editingNote.value = null
  sidebarPaperId.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  viewingMd.value = null
  researchPaperIds.value = null
  viewingPdf.value = payload
  globalChat.setBrowsingContext({
    paperId: payload.paperId,
    title: payload.title,
    source: 'kb-paper',
  })
  globalChat.applyBrowsingToPaperContext()
  collapseSidebarOnMobile()
  void engagement.record('view', 'daily-digest-sidebar-pdf', payload.paperId)
}

function openKnowledgePdf(paper: KbPaper) {
  const title = paper.paper_data.short_title || paper.paper_data['📖标题'] || paper.paper_id
  if (paper.pdf_static_url) {
    openPdfFromSidebar({ paperId: paper.paper_id, filePath: paper.pdf_static_url, title })
    return
  }
  openExternal(resolvePaperPdfUrl(paper.paper_id))
  void engagement.record('view', 'knowledge-workspace-pdf', paper.paper_id)
}

async function removeKnowledgePaper(paper: KbPaper) {
  const title = paper.paper_data.short_title || paper.paper_data['📖标题'] || paper.paper_id
  if (!confirm(`从知识库移除「${title}」？相关笔记不会被自动删除。`)) return
  try {
    await removeKbPaper(paper.paper_id, 'kb')
    await loadKbTree()
  } catch (err) {
    showError('从知识库移除论文失败，请稍后重试')
    console.error('[KnowledgeWorkspace] remove paper failed', err)
  }
}

async function updateKnowledgeReadStatus(paper: KbPaper, status: 'unread' | 'reading' | 'read') {
  markPaperReadStatus(paper.paper_id, status)
  try {
    await updateKbPaperReadStatus(paper.paper_id, status, 'kb')
  } catch (err) {
    await loadKbTree()
    showError('阅读状态更新失败，请稍后重试')
    console.error('[KnowledgeWorkspace] update read status failed', err)
  }
}

function openUserPaperViewMd(payload: UserPaperViewMdPayload) {
  try {
    const k = `${STORAGE_PREFIX}digest-md-${payload.paperId}-${payload.viewMode ?? 'default'}`
    localStorage.removeItem(k)
  } catch {
    /* ignore */
  }
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  viewingMd.value = payload
  myPapersMode.value = true
  viewingUserPaperId.value = null
  viewingUserPaper.value = null
  _stopUserPaperPoll()
  globalChat.setBrowsingContext({
    paperId: payload.paperId,
    title: payload.title,
    source: 'user-paper-md',
  })
  globalChat.applyBrowsingToPaperContext()
  collapseSidebarOnMobile()
}

function closeViewingMd() {
  viewingMd.value = null
  globalChat.clearBrowsingContext()
  if (myPapersMode.value) loadMyPapersCenter()
}

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  return buildKbPdfViewerUrl(viewingPdf.value.filePath, viewingPdf.value.paperId)
})

const pdfBareUrl = computed(() => {
  if (!viewingPdf.value) return ''
  return buildKbFileUrl(viewingPdf.value.filePath)
})

const viewingMdPdfIframeSrc = computed(() => {
  if (!viewingMd.value?.pdfUrl) return ''
  return buildPdfViewerUrl(viewingMd.value.pdfUrl, viewingMd.value.paperId)
})

function digestArxivPdfUrl(paperId: string): string {
  return resolvePaperPdfUrl(paperId)
}

function digestPdfJsSrc(pdfUrl: string, paperId: string): string {
  return buildPdfViewerUrl(pdfUrl, paperId)
}

const noteEditingLayoutKey = computed(() =>
  editingNote.value ? `digest-note-${editingNote.value.id}-${editingNote.value.paperId}` : 'digest-note',
)

const noteEditingPanelConfigs = computed<PanelConfigItem[]>(() => {
  if (!editingNote.value) return []
  const pid = editingNote.value.paperId
  const arxivOk = !pid.startsWith('up_')
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.NOTE_EDITOR, label: '笔记', icon: '📝', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: arxivOk },
    { id: PANEL_IDS.AI_CHAT, label: 'AI 问答', icon: '💬', available: !!isAuthenticated.value && !!pid },
  ]
})

const noteEditingDefaultLayout = computed<LayoutState>(() => ({
  mode: 'split',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.NOTE_EDITOR,
  splitRatio: 50,
}))

const noteEditingContext = computed<ContentLayoutContext>(() => {
  if (!editingNote.value) return {}
  const pid = editingNote.value.paperId
  const arxivOk = !pid.startsWith('up_')
  const pdfUrl = arxivOk ? digestArxivPdfUrl(pid) : undefined
  return {
    paperId: pid,
    noteEditor: { id: editingNote.value.id, paperId: pid },
    pdfUrl,
    pdfViewerSrc: pdfUrl ? digestPdfJsSrc(pdfUrl, pid) : '',
    pdfTitle: `${pid}.pdf`,
  }
})

const compareLayoutKey = computed(() =>
  comparingPaperIds.value?.length
    ? `digest-cmp-${comparingPaperIds.value.join(',')}`
    : 'digest-cmp',
)

const compareOnlyPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.COMPARE, label: '对比分析', icon: '⚖️', available: true },
])

const compareOnlyDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.COMPARE,
  rightPanel: PANEL_IDS.COMPARE,
  splitRatio: 60,
}))

const compareLayoutContext = computed<ContentLayoutContext>(() => ({
  comparingPaperIds: comparingPaperIds.value || [],
  comparingResultIds: comparingResultIds.value,
  compareScope: compareScope.value,
  comparePaperTitles: comparePaperTitles.value,
}))

// Deep Research layout
const researchLayoutKey = computed(() =>
  researchPaperIds.value?.length
    ? `digest-research-${researchProjectId.value ?? 'loose'}-${researchPaperIds.value.join(',')}`
    : 'digest-research',
)

const researchOnlyPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.RESEARCH, label: '深度研究', icon: '🔍', available: true },
])

const researchDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.RESEARCH,
  rightPanel: PANEL_IDS.RESEARCH,
  splitRatio: 60,
}))

const researchInitialSessionId = ref<number | null>(null)
const researchInitialQuestion = ref('')

const researchLayoutContext = computed<ContentLayoutContext>(() => ({
  researchPaperIds: researchPaperIds.value || [],
  researchPaperTitles: researchPaperTitles.value,
  researchScope: researchScope.value,
  researchInitialSessionId: researchInitialSessionId.value,
  researchProjectId: researchProjectId.value,
  researchInitialQuestion: researchInitialQuestion.value,
}))

const compareResultLayoutKey = computed(
  () => `digest-cmpres-${viewingCompareResultId.value ?? 0}`,
)

const compareResultPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.COMPARE_RESULT, label: '对比结果', icon: '📊', available: true },
])

const compareResultDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.COMPARE_RESULT,
  rightPanel: PANEL_IDS.COMPARE_RESULT,
  splitRatio: 60,
}))

const compareResultContext = computed<ContentLayoutContext>(() => ({
  compareResultId: viewingCompareResultId.value ?? undefined,
  comparePaperTitles: comparePaperTitles.value,
}))

const mdLayoutKey = computed(
  () =>
    viewingMd.value
      ? `digest-md-${viewingMd.value.paperId}-${viewingMd.value.viewMode ?? 'default'}`
      : 'digest-md',
)

const mdPanelConfigs = computed<PanelConfigItem[]>(() => {
  const pid = viewingMd.value?.paperId
  const vm = viewingMd.value?.viewMode
  const rows: PanelConfigItem[] = [
    {
      id: PANEL_IDS.PAPER_DETAIL,
      label: '论文详情',
      icon: '📄',
      available: !!pid && !pid.startsWith('up_'),
    },
    {
      id: PANEL_IDS.PDF_VIEWER,
      label: 'PDF',
      icon: '📕',
      available: !!viewingMdPdfIframeSrc.value,
    },
    {
      id: PANEL_IDS.MARKDOWN_VIEWER,
      label: '翻译 / Markdown',
      icon: '📖',
      available: !!viewingMd.value?.mdUrl && vm !== 'mineru' && vm !== 'zh' && vm !== 'bilingual',
    },
    {
      id: PANEL_IDS.MARKDOWN_MINERU,
      label: 'MinerU 解析',
      icon: '📋',
      available: !!viewingMd.value?.mineruUrl,
    },
    {
      id: PANEL_IDS.MARKDOWN_ZH,
      label: '中文翻译',
      icon: '🇨🇳',
      available: !!viewingMd.value?.zhUrl,
    },
    {
      id: PANEL_IDS.MARKDOWN_BILINGUAL,
      label: '中英对照',
      icon: '🔀',
      available: !!viewingMd.value?.bilingualUrl,
    },
  ]
  if (pid && isAuthenticated.value) {
    rows.push({
      id: PANEL_IDS.AI_CHAT,
      label: 'AI 问答',
      icon: '💬',
      available: true,
    })
  }
  return rows
})

/** 我的论文子链接：默认单栏，主面板与点击项一致；分栏可通过工具栏切换 */
const mdDefaultLayout = computed<LayoutState>(() => {
  const vm = viewingMd.value?.viewMode
  const hasPdf = !!viewingMdPdfIframeSrc.value
  const hasMd = !!viewingMd.value?.mdUrl

  let leftPanel: string
  if (vm === 'mineru') {
    leftPanel = PANEL_IDS.MARKDOWN_MINERU
  } else if (vm === 'zh') {
    leftPanel = PANEL_IDS.MARKDOWN_ZH
  } else if (vm === 'bilingual') {
    leftPanel = PANEL_IDS.MARKDOWN_BILINGUAL
  } else if (vm === 'pdf' || (!hasMd && hasPdf)) {
    leftPanel = PANEL_IDS.PDF_VIEWER
  } else {
    leftPanel = PANEL_IDS.MARKDOWN_VIEWER
  }

  let rightPanel =
    leftPanel === PANEL_IDS.PDF_VIEWER ? PANEL_IDS.MARKDOWN_VIEWER : PANEL_IDS.PDF_VIEWER
  if (leftPanel === PANEL_IDS.PDF_VIEWER && !hasMd) {
    rightPanel = isAuthenticated.value ? PANEL_IDS.AI_CHAT : PANEL_IDS.PDF_VIEWER
  }
  if (
    (leftPanel === PANEL_IDS.MARKDOWN_VIEWER ||
      leftPanel === PANEL_IDS.MARKDOWN_MINERU ||
      leftPanel === PANEL_IDS.MARKDOWN_ZH ||
      leftPanel === PANEL_IDS.MARKDOWN_BILINGUAL) &&
    !hasPdf
  ) {
    rightPanel = isAuthenticated.value ? PANEL_IDS.AI_CHAT : leftPanel
  }
  return {
    mode: 'single',
    leftPanel,
    rightPanel,
    splitRatio: 50,
  }
})

const mdLayoutContext = computed<ContentLayoutContext>(() => ({
  pdfViewerSrc: viewingMdPdfIframeSrc.value,
  pdfUrl: viewingMd.value?.pdfUrl ?? undefined,
  pdfTitle: viewingMd.value?.title,
  mdUrl: viewingMd.value?.mdUrl ?? undefined,
  mdMineruUrl: viewingMd.value?.mineruUrl ?? undefined,
  mdZhUrl: viewingMd.value?.zhUrl ?? undefined,
  mdBilingualUrl: viewingMd.value?.bilingualUrl ?? undefined,
  paperId: viewingMd.value?.paperId,
  paperViewScope: viewingMd.value?.scope,
  translateInProgress: viewingMd.value?.translateInProgress ?? false,
}))

const sidebarLayoutKey = computed(() =>
  sidebarPaperId.value ? `digest-kb-${sidebarPaperId.value}` : 'digest-kb',
)

const sidebarPanelConfigs = computed<PanelConfigItem[]>(() => {
  if (!sidebarPaperId.value) return []
  const pid = sidebarPaperId.value
  const arxivOk = !pid.startsWith('up_')
  // Find the KbPaper in kbTree to access derivative URLs
  const allKbPapers = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function walk(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(walk)]
    }),
  ]
  const kbPaper = allKbPapers.find(p => p.paper_id === pid)
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: arxivOk || !!kbPaper?.pdf_static_url },
    { id: PANEL_IDS.MARKDOWN_MINERU, label: 'MinerU 解析', icon: '📋', available: !!kbPaper?.mineru_static_url },
    { id: PANEL_IDS.MARKDOWN_ZH, label: '中文翻译', icon: '🇨🇳', available: !!kbPaper?.zh_static_url },
    { id: PANEL_IDS.MARKDOWN_BILINGUAL, label: '中英对照', icon: '🔀', available: !!kbPaper?.bilingual_static_url },
    { id: PANEL_IDS.AI_CHAT, label: 'AI 问答', icon: '💬', available: !!isAuthenticated.value },
  ]
})

const sidebarDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.PDF_VIEWER,
  splitRatio: 60,
}))

const sidebarLayoutContext = computed<ContentLayoutContext>(() => {
  if (!sidebarPaperId.value) return {}
  const pid = sidebarPaperId.value
  const arxivOk = !pid.startsWith('up_')
  // Find KB paper to get derivative URLs
  const allKbPapers = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function walk(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(walk)]
    }),
  ]
  const kbPaper = allKbPapers.find(p => p.paper_id === pid)
  const pdfUrl = arxivOk ? digestArxivPdfUrl(pid) : (kbPaper?.pdf_static_url ? buildKbFileUrl(kbPaper.pdf_static_url) : undefined)
  const mineruUrl = kbPaper?.mineru_static_url ? buildKbFileUrl(kbPaper.mineru_static_url) : undefined
  const zhUrl = kbPaper?.zh_static_url ? buildKbFileUrl(kbPaper.zh_static_url) : undefined
  const bilingualUrl = kbPaper?.bilingual_static_url ? buildKbFileUrl(kbPaper.bilingual_static_url) : undefined
  const mdUrl = bilingualUrl ?? zhUrl ?? mineruUrl
  return {
    paperId: pid,
    pdfUrl,
    pdfViewerSrc: pdfUrl ? digestPdfJsSrc(pdfUrl, pid) : '',
    pdfTitle: `${pid}.pdf`,
    mdUrl,
    mdMineruUrl: mineruUrl,
    mdZhUrl: zhUrl,
    mdBilingualUrl: bilingualUrl,
    translateInProgress: kbPaper?.translate_status === 'processing',
  }
})

const userPaperLayoutKey = computed(() =>
  viewingUserPaperId.value ? `digest-up-${viewingUserPaperId.value}` : 'digest-up',
)

const userPaperPanelConfigs = computed<PanelConfigItem[]>(() => {
  const p = viewingUserPaper.value
  if (!p?.summary) return []
  const hasPdf = !!p.pdf_static_url
  const pid = p.paper_id
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: hasPdf },
    { id: PANEL_IDS.MARKDOWN_MINERU, label: 'MinerU 解析', icon: '📋', available: !!p.mineru_static_url },
    { id: PANEL_IDS.MARKDOWN_ZH, label: '中文翻译', icon: '🇨🇳', available: !!p.zh_static_url },
    { id: PANEL_IDS.MARKDOWN_BILINGUAL, label: '中英对照', icon: '🔀', available: !!p.bilingual_static_url },
    { id: PANEL_IDS.AI_CHAT, label: 'AI 问答', icon: '💬', available: !!isAuthenticated.value && !!pid },
  ]
})

const userPaperDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.PDF_VIEWER,
  splitRatio: 60,
}))

const userPaperLayoutContext = computed<ContentLayoutContext>(() => {
  const p = viewingUserPaper.value
  const id = viewingUserPaperId.value
  if (!p || !id || !p.summary) return {}
  const pdfUrl = p.pdf_static_url || undefined
  const mineruUrl = p.mineru_static_url ? buildKbFileUrl(p.mineru_static_url) : undefined
  const zhUrl = p.zh_static_url ? buildKbFileUrl(p.zh_static_url) : undefined
  const bilingualUrl = p.bilingual_static_url ? buildKbFileUrl(p.bilingual_static_url) : undefined
  const mdUrl = bilingualUrl ?? zhUrl ?? mineruUrl
  return {
    paperId: id,
    userPaperData: p,
    pdfUrl,
    pdfViewerSrc: pdfUrl ? digestPdfJsSrc(pdfUrl, id) : '',
    pdfTitle: p.title || `${id}.pdf`,
    mdUrl,
    mdMineruUrl: mineruUrl,
    mdZhUrl: zhUrl,
    mdBilingualUrl: bilingualUrl,
    translateInProgress: p.translate_status === 'processing',
  }
})

// 全局“回到推荐”按钮事件处理：应用自动保存/删除规则，并回到推荐卡片视图
async function handleGoToDigestClick() {
  knowledgeWorkspaceActive.value = false
  if (editingNote.value && getDigestNoteEditor()) {
    const isEmpty = getDigestNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
    } else {
      try {
        await getDigestNoteEditor().flushSave()
      } catch {
        // 保存失败也不阻塞
      }
    }
    editingNote.value = null
    // 保存或删除之后，确保左侧知识库立即刷新
    await loadKbTree()
    sidebarRef.value?.refreshAllExpandedNotes()
  }
  // 清理所有侧面板状态，回到推荐刷卡视图
  myPapersMode.value = false
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  viewingUserPaperId.value = null
  viewingUserPaper.value = null
  _stopUserPaperPoll()
  _stopMyPapersCenterPoll()
  globalChat.clearBrowsingContext()
}

// ── Taskline action handler ────────────────────────────────────────────────
function handleTasklineAction(actionId: string) {
  switch (actionId) {
    case 'continue_browse':
      handleGoToDigestClick()
      break
    case 'open_unread': {
      const first = kbUnreadPapers.value[0]
      if (first) {
        openPaperFromSidebar(first.paper_id)
      } else {
        showSidebar.value = true
      }
      break
    }
    case 'open_research': {
      const recent = kbAllPapersRecent.value.slice(0, 5)
      if (recent.length > 0) {
        const ids = recent.map((p: any) => p.paper_id as string)
        const titles: Record<string, string> = {}
        recent.forEach((p: any) => {
          titles[p.paper_id] = (p.paper_data?.short_title as string) || (p.paper_id as string)
        })
        handleResearch(ids, titles, 'kb')
      }
      break
    }
    case 'open_missed':
      missedPapersOpen.value = true
      break
    case 'open_reactivation':
      reactivationOpen.value = true
      break
    case 'open_ideas':
      router.push('/workbench?tab=idea')
      break
    case 'open_review':
      openReviewDrawer()
      break
    case 'open_recap':
      router.push('/recap')
      break
  }
}

async function closeNoteEditor() {
  editingNote.value = null
  // 关闭笔记编辑时保留当前 sidebarPaperId，不打扰中间详情
  // Refresh sidebar notes to show updated titles
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

async function handleChatNoteSaved() {
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

async function handleNoteSaved(payload: { id: number; title: string }) {
  // 先本地更新当前论文下笔记列表的标题，立即反馈到左侧知识库
  if (editingNote.value) {
    sidebarRef.value?.updateNoteTitle(editingNote.value.paperId, payload.id, payload.title)
  }
  // 再刷新一次知识库树和已展开论文下的笔记，确保与后端完全同步
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

function resetCards() {
  currentIndex.value = 0
  history.value = []
  clearPaperSelection()
  listInspectorOpen.value = false
  cardAnimClass.value = 'card-enter'
  if (allDatesExhausted.value) {
    allDatesExhausted.value = false
    // Jump back to latest date and reload
    if (dates.value.length > 0 && selectedDate.value !== dates.value[0]) {
      selectedDate.value = dates.value[0]
    } else {
      loadDigestForDate(selectedDate.value)
    }
  }
}

const STEP_ORDER = ['pdf_prepare', 'pdf_download', 'pdf_extract', 'pdf_mineru', 'pdf_info', 'paper_summary', 'summary_limit', 'paper_assets', 'done']

function isStepDone(step: string, currentStep: string): boolean {
  const currentIdx = STEP_ORDER.indexOf(currentStep)
  const stepIdx = STEP_ORDER.indexOf(step)
  return stepIdx !== -1 && currentIdx !== -1 && stepIdx < currentIdx
}

function isStepCurrent(step: string, currentStep: string): boolean {
  if (currentStep === step) return true
  // pdf_prepare covers all PDF-acquisition sub-steps
  if (step === 'pdf_prepare' && (currentStep === 'pdf_download' || currentStep === 'pdf_extract' || currentStep === 'pdf_mineru')) return true
  // During parallel layer 1 (paper_summary), pdf_info is also running → show as current
  if (step === 'pdf_info' && currentStep === 'paper_summary') return true
  return false
}

// Welcome banner — shown once to first-time unauthenticated visitors
const showWelcomeBanner = ref(
  !isAuthenticated.value && !localStorage.getItem('ai4p-welcomed'),
)
watch(
  () => isAuthenticated.value,
  (authed) => {
    if (authed) showWelcomeBanner.value = false
  },
)
function dismissWelcomeBanner() {
  showWelcomeBanner.value = false
  try { localStorage.setItem('ai4p-welcomed', '1') } catch { /* ignore */ }
}

/** 任意详情面板打开时为 true，用于在中央区域顶部显示「回到推荐」入口 */
const isInPanelView = computed(() =>
  knowledgeWorkspaceActive.value ||
  editingNote.value !== null ||
  !!comparingPaperIds.value ||
  viewingCompareResultId.value !== null ||
  !!viewingPdf.value ||
  !!viewingMd.value ||
  !!sidebarPaperId.value ||
  myPapersMode.value ||
  !!viewingUserPaperId.value ||
  !!researchPaperIds.value,
)

// 将面板视图状态同步到全局，供右下角浮动按钮感知
watch(isInPanelView, (v) => { globalChat.setPageInPanelView(v) }, { immediate: true })

// 主卡片视图：将当前浏览的推荐论文自动同步到 AI 问答上下文
// 面板视图时跳过（面板内会由 openPaperFromSidebar 等函数精确设置）
// 同时监听 isInPanelView：面板关闭回到卡片时 currentPaper 不变，
// 但 isInPanelView 由 true → false，此时必须重新同步，否则 AI 问答丢失当前论文。
watch([currentPaper, isInPanelView], ([paper, inPanel]) => {
  if (inPanel) return
  if (paper) {
    globalChat.setBrowsingContext({
      paperId: paper.paper_id,
      title: paper.short_title || paper['📖标题'] || paper.paper_id,
      summary: paper,
      source: 'paper-detail',
    })
    globalChat.applyBrowsingToPaperContext()
  } else {
    globalChat.clearBrowsingContext()
  }
}, { immediate: true })

// 全局 AI 问答存入笔记时刷新知识库侧栏
watch(globalChat.noteSavedSignal, async () => {
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
})

// 浮动按钮请求"回到推荐"时执行清理
watch(globalChat.digestResetRequested, (requested) => {
  if (requested) {
    globalChat.digestResetRequested.value = false
    handleGoToDigestClick()
  }
})

// 离开推荐页路由时（例如切到列表页），也应用同样的自动保存/删除规则
onBeforeRouteLeave(async (_to, _from, next) => {
  if (editingNote.value && getDigestNoteEditor()) {
    const isEmpty = getDigestNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
    } else {
      try {
        await getDigestNoteEditor().flushSave()
      } catch {
        // 保存失败不阻塞导航
      }
    }
    editingNote.value = null
  }
  next()
})
</script>

<template>
  <SidebarPageLayout
    v-model:show-sidebar="showSidebar"
    :hide-open-button="digestViewMode === 'immersive' && !isInPanelView"
  >

    <h1 class="sr-only">AI4Papers 每日 AI 与机器学习论文推荐</h1>

    <!-- ===== Sidebar slot ===== -->
    <template #sidebar>

    <!-- ===== Authenticated sidebar ===== -->
    <template v-if="isAuthenticated">
      <Transition name="sidebar-slide">
        <div
          v-show="showSidebar"
          :class="[
            'shrink-0 z-30 h-full transition-transform duration-300 ease-in-out',
            'fixed lg:relative inset-y-0 left-0',
            showSidebar ? 'translate-x-0' : '-translate-x-full lg:-translate-x-full'
          ]"
        >
          <Sidebar
            ref="sidebarRef"
            :kb-tree="kbTree"
            :compare-tree="compareTree"
            v-model:active-folder-id="activeFolderId"
            v-model:selected-date="selectedDate"
            :dates="dates"
            scope="kb"
            :active-paper-id="sidebarPaperId"
            @open-paper="openPaperFromSidebar"
            @open-note="openNoteFromSidebar"
            @open-pdf="openPdfFromSidebar"
            @compare="handleCompare"
            @research="handleResearch"
            @refresh="loadKbTree"
            @open-compare-result="openCompareResult"
            @refresh-compare="loadCompareTree"
            @toggle-sidebar="showSidebar = false"
            @open-user-paper="openUserPaper"
            @open-upload-dialog="showUploadDialog = true"
            @tab-changed="handleTabChanged"
            @view-md="openUserPaperViewMd"
            @open-research-session="handleOpenResearchSession"
            @update-read-status="markPaperReadStatus"
            :active-user-paper-id="sidebarActiveUserPaperId"
            :active-view-md-key="sidebarActiveViewMdKey"
            :active-compare-result-id="viewingCompareResultId"
            :active-research-session-id="researchInitialSessionId"
          />
        </div>
      </Transition>
    </template>

    <!-- ===== Unauthenticated sidebar ===== -->
    <template v-else>
      <Transition name="sidebar-slide">
        <aside
          v-show="showSidebar"
          :class="[
            'z-30 w-[80vw] max-w-[340px] lg:w-[var(--sidebar-w)] h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300 ease-in-out relative',
            'fixed lg:relative inset-y-0 left-0',
            showSidebar ? 'translate-x-0' : '-translate-x-full lg:-translate-x-full'
          ]"
        >
          <div class="px-4 pt-5 pb-4 border-b border-border">
            <div class="flex items-center gap-3">
              <span
                class="inline-flex items-center px-3 py-1 rounded-lg text-xs font-bold text-white shrink-0 tracking-wide"
                style="background: linear-gradient(135deg, #fd267a, #ff6036);"
              >
                日报
              </span>
              <!-- Current date display (read-only for guests) -->
              <DatePill :date="selectedDate" class="flex-1 min-w-0" />
              <!-- Collapse button -->
              <button
                class="shrink-0 w-8 h-8 flex items-center justify-center rounded-md text-text-muted/50 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
                title="收起侧边栏"
                @click="showSidebar = false"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
                </svg>
              </button>
            </div>
          </div>
          <div class="flex-1 p-4 flex flex-col items-center justify-center text-center">
            <div class="w-14 h-14 rounded-xl bg-bg-elevated border border-border mb-3 flex items-center justify-center text-2xl">
              ✨
            </div>
            <h3 class="text-base font-semibold text-text-primary mb-1">免费注册，解锁全部功能</h3>
            <ul class="text-left text-xs text-text-muted mb-4 space-y-1.5 w-full px-1">
              <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>知识库 · 收藏 · 笔记</li>
              <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>AI 问答 · 论文对比</li>
              <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>灵感生成 · 中文翻译</li>
              <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>每日无限论文浏览</li>
            </ul>
            <div class="flex flex-col gap-2 w-full">
              <button
                class="px-4 py-2 rounded-full bg-brand-gradient text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
                @click="router.push({ path: '/register', query: { redirect: route.fullPath } })"
              >
                免费注册
              </button>
              <button
                class="px-4 py-2 rounded-full border border-border text-text-secondary text-sm font-medium cursor-pointer hover:bg-bg-hover transition-colors"
                @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
              >
                已有账号，登录
              </button>
            </div>
          </div>
        </aside>
      </Transition>
    </template>

    </template>
    <!-- End sidebar slot -->

    <!-- ===== Default slot: center content area ===== -->

      <KnowledgeWorkspace
        v-if="knowledgeWorkspaceActive && isAuthenticated"
        class="flex-1 min-h-0"
        :kb-tree="kbTree"
        :active-folder-id="activeFolderId"
        @open-paper="openPaperFromSidebar"
        @open-pdf="openKnowledgePdf"
        @compare="ids => handleCompare(ids, 'kb')"
        @research="(ids, titles) => handleResearch(ids, titles, 'kb')"
        @remove-paper="removeKnowledgePaper"
        @update-read-status="updateKnowledgeReadStatus"
        @show-sidebar="showSidebar = true"
      />

      <!-- 笔记 + 论文：统一 ContentLayout -->
      <ContentLayout
        v-else-if="editingNote !== null"
        ref="digestContentLayoutRef"
        class="flex-1 min-h-0 border-l border-border mt-1"
        :context-key="noteEditingLayoutKey"
        :panel-configs="noteEditingPanelConfigs"
        :default-layout="noteEditingDefaultLayout"
        :context="noteEditingContext"
        @note-saved="handleChatNoteSaved"
        @close-note="closeNoteEditor"
      />

      <ContentLayout
        v-else-if="researchPaperIds"
        class="flex-1 min-h-0 mt-1"
        :context-key="researchLayoutKey"
        :panel-configs="researchOnlyPanels"
        :default-layout="researchDefaultLayout"
        :context="researchLayoutContext"
        @close-research="closeResearch"
        @remove-research-paper="removeResearchPaper"
        @save-to-library="handleSaveToLibrary"
      />

      <ContentLayout
        v-else-if="comparingPaperIds"
        class="flex-1 min-h-0 mt-1"
        :context-key="compareLayoutKey"
        :panel-configs="compareOnlyPanels"
        :default-layout="compareOnlyDefaultLayout"
        :context="compareLayoutContext"
        @close-compare="closeCompare"
        @compare-saved="handleCompareSaved"
      />

      <ContentLayout
        v-else-if="viewingCompareResultId !== null"
        class="flex-1 min-h-0 mt-1"
        :context-key="compareResultLayoutKey"
        :panel-configs="compareResultPanels"
        :default-layout="compareResultDefaultLayout"
        :context="compareResultContext"
        @close-compare-result="closeCompareResult"
      />

      <div
        v-else-if="viewingPdf"
        class="flex-1 flex flex-col overflow-hidden mt-1 px-2 sm:px-4 pb-4 min-h-0"
      >
        <PdfPanel
          class="flex-1 min-h-0 rounded-xl border border-border overflow-hidden"
          :src="pdfViewerSrc"
          :title="viewingPdf.title || `${viewingPdf.paperId}.pdf`"
          :bare-url="pdfBareUrl"
          show-close
          @close="viewingPdf = null"
        />
      </div>

      <ContentLayout
        v-else-if="viewingMd"
        :key="mdLayoutKey"
        class="flex-1 min-h-0 mt-1"
        :context-key="mdLayoutKey"
        :panel-configs="mdPanelConfigs"
        :default-layout="mdDefaultLayout"
        :context="mdLayoutContext"
        :show-close="true"
        @close-view="closeViewingMd"
      />

      <ContentLayout
        v-else-if="sidebarPaperId"
        class="flex-1 min-h-0 mt-1"
        :context-key="sidebarLayoutKey"
        :panel-configs="sidebarPanelConfigs"
        :default-layout="sidebarDefaultLayout"
        :context="sidebarLayoutContext"
        @note-saved="handleChatNoteSaved"
      />

      <!-- 「我的论文」Tab 激活：展示用户论文列表（未选中具体论文时） -->
      <div
        v-else-if="myPapersMode && !viewingUserPaperId"
        class="flex-1 overflow-y-auto px-2 sm:px-4 py-4"
      >
        <!-- Initial loading (no data yet) -->
        <div v-if="myPapersCenterLoading && myPapersCenter.length === 0 && !myPapersSearch && !myPapersSourceFilter && !myPapersInstitutionFilter"
          class="flex items-center justify-center h-full"
        >
          <LoadingSpinner color="text-amber-500" />
        </div>

        <!-- 空状态（真正没有论文，且无搜索词） -->
        <div v-else-if="myPapersCenter.length === 0 && !myPapersSearch && !myPapersSourceFilter && !myPapersInstitutionFilter && !myPapersCenterLoading"
          class="flex flex-col items-center justify-center h-full gap-5 text-center px-8"
        >
          <div class="w-20 h-20 rounded-2xl bg-mypapers-gradient-br opacity-70 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <h2 class="text-xl font-bold text-text-primary mb-2">还没有上传论文</h2>
            <p class="text-sm text-text-muted max-w-xs leading-relaxed">在左侧点击「上传 / 导入论文」，支持 PDF 上传或 arXiv ID 导入，自动生成结构化摘要</p>
          </div>
          <button
            class="px-6 py-2.5 rounded-full bg-mypapers-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="showUploadDialog = true"
          >上传第一篇论文</button>
        </div>

        <!-- 论文列表区（有数据 OR 有搜索词） -->
        <div v-else class="max-w-2xl mx-auto">
          <!-- ── 顶部：标题行 + 上传按钮 ── -->
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-base font-semibold text-text-primary">
              我的论文
              <span class="text-sm font-normal text-text-muted ml-1">
                ({{ myPapersTotal > 0 ? myPapersTotal : myPapersCenter.length }})
              </span>
            </h2>
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-white bg-mypapers-gradient border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="showUploadDialog = true"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              上传论文
            </button>
          </div>

          <!-- ── 工具条：搜索 + 筛选 + 排序 + 视图切换 ── -->
          <div class="flex flex-col sm:flex-row gap-2 mb-3">
            <!-- 搜索框 -->
            <div class="relative flex-1 min-w-0">
              <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
              </svg>
              <input
                v-model="myPapersSearch"
                type="text"
                placeholder="搜索标题、摘要、机构…"
                class="w-full pl-8 pr-3 py-1.5 rounded-xl bg-bg-card border border-border text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-amber-500/60 transition-colors"
              />
              <button
                v-if="myPapersSearch"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer p-0 leading-none"
                @click="myPapersSearch = ''"
              >✕</button>
            </div>

            <!-- 来源筛选 -->
            <select
              v-model="myPapersSourceFilter"
              class="px-2.5 py-1.5 rounded-xl bg-bg-card border border-border text-xs text-text-primary focus:outline-none focus:border-amber-500/60 transition-colors cursor-pointer"
            >
              <option value="">全部来源</option>
              <option value="pdf">PDF</option>
              <option value="arxiv">arXiv</option>
              <option value="manual">手动</option>
            </select>

            <!-- 机构筛选 -->
            <select
              v-if="myPapersInstitutions.length > 0"
              v-model="myPapersInstitutionFilter"
              class="px-2.5 py-1.5 rounded-xl bg-bg-card border border-border text-xs text-text-primary focus:outline-none focus:border-amber-500/60 transition-colors cursor-pointer max-w-[120px]"
            >
              <option value="">全部机构</option>
              <option v-for="inst in myPapersInstitutions" :key="inst" :value="inst">{{ inst }}</option>
            </select>

            <!-- 排序 -->
            <select
              v-model="myPapersSort"
              class="px-2.5 py-1.5 rounded-xl bg-bg-card border border-border text-xs text-text-primary focus:outline-none focus:border-amber-500/60 transition-colors cursor-pointer"
            >
              <option value="date_desc">最新优先</option>
              <option value="date_asc">最早优先</option>
              <option value="title_asc">标题 A→Z</option>
            </select>

            <!-- 视图切换 -->
            <div class="flex rounded-xl overflow-hidden border border-border shrink-0">
              <button
                class="px-2.5 py-1.5 text-xs font-medium transition-colors border-none cursor-pointer"
                :class="myPapersViewMode === 'card'
                  ? 'bg-mypapers-gradient text-white'
                  : 'bg-bg-card text-text-muted hover:text-text-primary'"
                title="卡片视图"
                @click="myPapersViewMode = 'card'"
              >
                <svg viewBox="0 0 16 16" class="w-3.5 h-3.5" fill="currentColor">
                  <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
                  <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
                </svg>
              </button>
              <button
                class="px-2.5 py-1.5 text-xs font-medium transition-colors border-none border-l border-border cursor-pointer"
                :class="myPapersViewMode === 'compact'
                  ? 'bg-mypapers-gradient text-white'
                  : 'bg-bg-card text-text-muted hover:text-text-primary'"
                title="列表视图"
                @click="myPapersViewMode = 'compact'"
              >
                <svg viewBox="0 0 16 16" class="w-3.5 h-3.5" fill="currentColor">
                  <rect x="1" y="2" width="14" height="2" rx="1"/><rect x="1" y="7" width="14" height="2" rx="1"/>
                  <rect x="1" y="12" width="14" height="2" rx="1"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- 结果计数 / 搜索无结果提示 -->
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] text-text-muted">
              <template v-if="myPapersSearch || myPapersSourceFilter || myPapersInstitutionFilter">
                找到 {{ myPapersCenterSorted.length }} 篇
                <template v-if="myPapersHasMore"> · 还有更多</template>
              </template>
              <template v-else>
                已加载 {{ myPapersCenter.length }} 篇<template v-if="myPapersTotal > myPapersCenter.length"> · 共 {{ myPapersTotal }} 篇</template>
              </template>
            </span>
            <!-- 搜索中加载指示 -->
            <LoadingSpinner v-if="myPapersCenterLoading && myPapersCenter.length > 0" size="sm" color="text-amber-500" />
          </div>

          <!-- 搜索/筛选无结果 -->
          <div
            v-if="myPapersCenterSorted.length === 0 && !myPapersCenterLoading"
            class="flex flex-col items-center py-12 gap-2 text-center"
          >
            <svg class="w-10 h-10 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            <p class="text-sm text-text-muted">没有符合条件的论文</p>
            <button
              class="mt-1 text-xs text-amber-500 hover:text-amber-400 bg-transparent border-none cursor-pointer"
              @click="myPapersSearch = ''; myPapersSourceFilter = ''; myPapersInstitutionFilter = ''"
            >清除筛选</button>
          </div>

          <!-- ══ 卡片视图 ══ -->
          <div v-if="myPapersViewMode === 'card' && myPapersCenterSorted.length > 0" class="space-y-4">
            <div
              v-for="paper in myPapersCenterSorted"
              :key="paper.paper_id"
              class="bg-bg-card border border-border rounded-2xl p-4 sm:p-5 cursor-pointer hover:border-amber-500/40 hover:shadow-md transition-all"
              @click="openUserPaper(paper.paper_id)"
            >
              <!-- Header row -->
              <div class="flex items-start justify-between gap-3 mb-3">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="px-2.5 py-0.5 rounded-full bg-mypapers-gradient text-white text-xs font-semibold">
                    {{ paper.institution || '未知机构' }}
                  </span>
                  <span class="text-[10px] text-text-muted px-2 py-0.5 rounded-full bg-bg-elevated border border-border">
                    {{ paper.source_type === 'arxiv' ? 'arXiv' : paper.source_type === 'pdf' ? 'PDF' : '手动' }}
                  </span>
                </div>
                <!-- Status indicator -->
                <div class="shrink-0 flex items-center gap-1.5">
                  <span
                    v-if="paper.process_status === 'processing' || paper.process_status === 'pending'"
                    class="w-5 h-5 flex items-center justify-center text-amber-500 text-sm animate-spin"
                  >⟳</span>
                  <span v-else-if="paper.process_status === 'completed'" class="text-green-500 text-sm">✅</span>
                  <span v-else-if="paper.process_status === 'failed'" class="text-red-500 text-sm">❌</span>
                  <span v-else class="text-text-muted text-sm">○</span>
                </div>
              </div>

              <!-- Title -->
              <h3 class="text-base font-bold text-text-primary leading-snug mb-1.5">
                {{ paper.summary?.short_title || paper.title || '（未命名）' }}
              </h3>
              <p v-if="paper.summary?.['📖标题']" class="text-xs text-text-secondary mb-2 line-clamp-1">
                {{ paper.summary['📖标题'] }}
              </p>

              <!-- Summary excerpt (completed) -->
              <template v-if="paper.process_status === 'completed' && paper.summary">
                <div class="text-xs text-text-muted space-y-1">
                  <div v-if="paper.summary['🛎️文章简介']?.['🔸研究问题']" class="line-clamp-2">
                    <span class="font-medium text-text-secondary">研究问题：</span>{{ paper.summary['🛎️文章简介']['🔸研究问题'] }}
                  </div>
                  <div v-if="paper.summary['🛎️文章简介']?.['🔸主要贡献']" class="line-clamp-2">
                    <span class="font-medium text-text-secondary">主要贡献：</span>{{ paper.summary['🛎️文章简介']['🔸主要贡献'] }}
                  </div>
                </div>
              </template>
              <!-- Processing status (in progress) -->
              <template v-else-if="paper.process_status === 'processing' || paper.process_status === 'pending'">
                <p class="text-xs text-amber-500 flex items-center gap-1.5">
                  <span class="inline-block animate-spin">⟳</span>
                  {{ userPaperStepLabel(paper.process_step) }}
                </p>
              </template>
              <!-- Error (failed) -->
              <template v-else-if="paper.process_status === 'failed'">
                <p class="text-xs text-red-500 line-clamp-1">{{ paper.process_error || '处理失败' }}</p>
              </template>
              <!-- Not processed yet -->
              <template v-else>
                <p class="text-xs text-text-muted">尚未处理，点击查看并启动摘要生成</p>
              </template>

              <!-- Footer -->
              <div class="mt-3 pt-3 border-t border-border/60 flex items-center justify-between">
                <span class="text-[10px] text-text-muted">{{ new Date(paper.created_at).toLocaleDateString('zh-CN') }}</span>
                <span class="text-xs text-amber-500 hover:text-amber-400 font-medium">查看详情 →</span>
              </div>
            </div>
          </div>

          <!-- ══ 紧凑列表视图 ══ -->
          <div v-else-if="myPapersViewMode === 'compact' && myPapersCenterSorted.length > 0"
            class="bg-bg-card border border-border rounded-2xl overflow-hidden"
          >
            <div
              v-for="(paper, idx) in myPapersCenterSorted"
              :key="paper.paper_id"
              class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-bg-elevated transition-colors"
              :class="{ 'border-t border-border/50': idx > 0 }"
              @click="openUserPaper(paper.paper_id)"
            >
              <!-- Status dot -->
              <div class="shrink-0 w-5 text-center">
                <span v-if="paper.process_status === 'processing' || paper.process_status === 'pending'" class="text-amber-500 text-xs animate-spin inline-block">⟳</span>
                <span v-else-if="paper.process_status === 'completed'" class="text-green-500 text-xs">✓</span>
                <span v-else-if="paper.process_status === 'failed'" class="text-red-500 text-xs">✕</span>
                <span v-else class="text-text-muted/40 text-xs">○</span>
              </div>

              <!-- Title (main) -->
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-text-primary truncate leading-snug">
                  {{ paper.summary?.short_title || paper.title || '（未命名）' }}
                </p>
                <p v-if="paper.institution" class="text-[10px] text-text-muted truncate mt-0.5">{{ paper.institution }}</p>
              </div>

              <!-- Source badge -->
              <span class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-md bg-bg-elevated border border-border text-text-muted">
                {{ paper.source_type === 'arxiv' ? 'arXiv' : paper.source_type === 'pdf' ? 'PDF' : '手动' }}
              </span>

              <!-- Date -->
              <span class="shrink-0 text-[10px] text-text-muted hidden sm:block">
                {{ new Date(paper.created_at).toLocaleDateString('zh-CN') }}
              </span>

              <!-- Arrow -->
              <svg class="shrink-0 w-3.5 h-3.5 text-text-muted/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m9 18 6-6-6-6"/>
              </svg>
            </div>
          </div>

          <!-- ── 加载更多 ── -->
          <div v-if="myPapersHasMore" class="mt-4 flex flex-col items-center gap-1">
            <button
              class="px-6 py-2 rounded-full border border-border bg-bg-card text-xs font-medium text-text-secondary hover:border-amber-500/40 hover:text-amber-500 transition-colors cursor-pointer disabled:opacity-50"
              :disabled="myPapersCenterLoading"
              @click="loadMoreMyPapers"
            >
              <span v-if="myPapersCenterLoading" class="flex items-center gap-1.5">
                <LoadingSpinner size="sm" color="text-amber-500" />
                加载中…
              </span>
              <span v-else>
                <template v-if="!myPapersSearch && !myPapersSourceFilter && !myPapersInstitutionFilter && myPapersTotal > myPapersCenter.length">
                  加载更多（还有 {{ myPapersTotal - myPapersCenter.length }} 篇）
                </template>
                <template v-else>加载更多</template>
              </span>
            </button>
          </div>
        </div>
      </div>

      <!-- 用户上传论文展示（点击具体论文后的详情/进度面板） -->
      <div
        v-else-if="viewingUserPaperId"
        class="flex-1 flex flex-col overflow-hidden mt-1 px-2 sm:px-4 pb-4"
      >
        <!-- 返回列表按钮 -->
        <button
          class="inline-flex items-center gap-1 text-sm text-text-muted hover:text-amber-500 mb-3 cursor-pointer bg-transparent border-none transition-colors self-start"
          @click="closeUserPaperDetail"
        >← 返回我的论文</button>

        <!-- 处理中进度面板（尚无摘要时才显示完整等待页） -->
        <div
          v-if="viewingUserPaper && (viewingUserPaper.process_status === 'processing' || viewingUserPaper.process_status === 'pending') && !viewingUserPaper.summary"
          class="flex flex-col items-center justify-center flex-1 gap-6 text-center"
        >
          <div class="w-16 h-16 rounded-full bg-mypapers-gradient-br flex items-center justify-center animate-pulse">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <h3 class="text-lg font-semibold text-text-primary mb-1">正在处理论文</h3>
            <p class="text-sm text-text-muted mb-4">{{ viewingUserPaper.title }}</p>
          </div>
          <!-- Step progress -->
          <div class="w-full max-w-xs flex flex-col gap-2">
            <div
              v-for="(step, idx) in ['pdf_prepare', 'pdf_info', 'paper_summary', 'summary_limit', 'paper_assets']"
              :key="step"
              class="flex items-center gap-3"
            >
              <div
                class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                :class="isStepDone(step, viewingUserPaper.process_step)
                  ? 'bg-green-500 text-white'
                  : isStepCurrent(step, viewingUserPaper.process_step)
                    ? 'bg-amber-500 text-white animate-pulse'
                    : 'bg-bg-elevated border border-border text-text-muted'"
              >
                <span v-if="isStepDone(step, viewingUserPaper.process_step)">✓</span>
                <span v-else-if="isStepCurrent(step, viewingUserPaper.process_step)" class="inline-block animate-spin">⟳</span>
                <span v-else>{{ idx + 1 }}</span>
              </div>
              <span
                class="text-sm flex-1 text-left"
                :class="isStepCurrent(step, viewingUserPaper.process_step)
                  ? 'text-amber-500 font-medium'
                  : isStepDone(step, viewingUserPaper.process_step)
                    ? 'text-text-secondary'
                    : 'text-text-muted'"
              >{{ userPaperStepLabel(step) }}</span>
              <span v-if="isStepCurrent(step, viewingUserPaper.process_step)" class="text-[10px] text-text-muted shrink-0">
                {{ step === 'pdf_prepare' ? '~30-300s' : step === 'paper_summary' ? '~15-40s' : step === 'pdf_info' ? '~5-15s' : '~10-25s' }}
              </span>
            </div>
          </div>
          <!-- Elapsed time + hint -->
          <div class="flex flex-col items-center gap-1">
            <p v-if="processingElapsedSeconds > 0" class="text-xs text-text-muted">
              已耗时 {{ processingElapsedSeconds < 60 ? processingElapsedSeconds + ' 秒' : Math.floor(processingElapsedSeconds / 60) + ' 分 ' + (processingElapsedSeconds % 60) + ' 秒' }}
            </p>
            <p class="text-xs text-text-muted">预计需要 1–3 分钟，摘要生成后即可查看内容</p>
          </div>
        </div>

        <!-- 处理失败 -->
        <div
          v-else-if="viewingUserPaper && viewingUserPaper.process_status === 'failed'"
          class="flex flex-col items-center justify-center flex-1 gap-4 text-center"
        >
          <div class="text-5xl">❌</div>
          <h3 class="text-lg font-semibold text-text-primary">处理失败</h3>
          <p class="text-sm text-text-muted max-w-xs">{{ viewingUserPaper.process_error || '未知错误' }}</p>
          <div class="flex gap-3">
            <button
              class="px-5 py-2 rounded-full bg-mypapers-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="handleRetryUserPaper"
            >重新处理</button>
            <button
              class="px-5 py-2 rounded-full border border-border text-text-secondary text-sm font-semibold bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="closeUserPaperDetail"
            >关闭</button>
          </div>
        </div>

        <!-- 未处理（none）或加载中 -->
        <div
          v-else-if="!viewingUserPaper || viewingUserPaper.process_status === 'none'"
          class="flex flex-col items-center justify-center flex-1 gap-4 text-center"
        >
          <div class="text-5xl">📄</div>
          <h3 class="text-lg font-semibold text-text-primary">{{ viewingUserPaper?.title || '论文详情' }}</h3>
          <p class="text-sm text-text-muted">尚未处理，点击下方按钮开始生成摘要</p>
          <button
            class="px-5 py-2 rounded-full bg-mypapers-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="handleRetryUserPaper"
          >开始处理</button>
        </div>

        <!-- 处理完成 或 处理中已有摘要可预览：统一布局 -->
        <div
          v-else-if="viewingUserPaper && viewingUserPaper.summary"
          class="flex-1 flex flex-col min-h-0 overflow-hidden"
        >
          <!-- 分析仍在进行中时显示进度横幅 -->
          <div
            v-if="viewingUserPaper.process_status === 'processing' || viewingUserPaper.process_status === 'pending'"
            class="flex items-center gap-2 px-3 py-2 mb-2 rounded-lg text-xs text-amber-500 bg-amber-500/10 border border-amber-500/20 shrink-0"
          >
            <span class="inline-block animate-spin">⟳</span>
            <span class="font-medium">{{ userPaperStepLabel(viewingUserPaper.process_step) }}</span>
            <span class="text-text-muted ml-1">· 分析仍在进行，已生成内容可直接查看</span>
            <span v-if="processingElapsedSeconds > 0" class="ml-auto text-text-muted">
              {{ processingElapsedSeconds < 60 ? processingElapsedSeconds + 's' : Math.floor(processingElapsedSeconds / 60) + 'm' + (processingElapsedSeconds % 60) + 's' }}
            </span>
          </div>
          <ContentLayout
            class="flex-1 min-h-0 overflow-hidden"
            :key="viewingUserPaperId"
            :context-key="userPaperLayoutKey"
            :panel-configs="userPaperPanelConfigs"
            :default-layout="userPaperDefaultLayout"
            :context="userPaperLayoutContext"
            @note-saved="handleChatNoteSaved"
          />
        </div>
      </div>

      <!-- 默认卡片刷刷模式 -->
      <div v-else class="flex-1 flex flex-col min-h-0">

        <Teleport to="#navbar-page-controls">
          <WorkspaceModeSwitch
            :model-value="digestViewMode"
            :modes="['card', 'list', 'immersive']"
            @update:model-value="setDigestViewMode"
          />
        </Teleport>

        <!-- Today's mission bar — unified: progress + primary task + radar summary -->
        <TodayMissionBar
          v-if="digestViewMode !== 'immersive' && isAuthenticated && !error && (researchTasklineItems.length > 0 || radarData || radarLoading)"
          :items="researchTasklineItems"
          :radar="radarData"
          :radar-loading="radarLoading"
          :is-authenticated="isAuthenticated"
          @action="handleTasklineAction"
        />

        <!-- Main research workspace -->
        <ResearchWorkspaceShell
          :mode="digestViewMode"
          :show-toolbar="digestViewMode !== 'immersive' && !!(currentPaper || papers.length > 0)"
          class="flex-1 min-h-0"
        >
          <template #toolbar>
            <div class="digest-workspace-toolbar">
              <div class="digest-workspace-toolbar__context">
                <span class="digest-workspace-toolbar__title">今日论文</span>
                <span v-if="selectedDate" class="digest-workspace-toolbar__date">{{ selectedDate }}</span>
                <span class="digest-workspace-toolbar__count">
                  <template v-if="digestViewMode === 'list' && listTotalPages > 1">
                    {{ listPage * LIST_PAGE_SIZE + 1 }}-{{ Math.min((listPage + 1) * LIST_PAGE_SIZE, displayPapers.length) }} / {{ displayPapers.length }} 篇
                  </template>
                  <template v-else>{{ displayPapers.length }} 篇</template>
                </span>
              </div>

              <div class="digest-workspace-toolbar__filters">
                <label v-if="availableCategories.length > 0" class="digest-workspace-toolbar__field">
                  <span class="sr-only">论文分类</span>
                  <select v-model="topicFilter" aria-label="论文分类">
                    <option value="">全部分类</option>
                    <option v-for="cat in availableCategories" :key="cat" :value="cat">{{ cat }}</option>
                  </select>
                </label>

                <label class="digest-workspace-toolbar__field">
                  <span class="sr-only">论文排序</span>
                  <select v-model="sortMode" aria-label="论文排序">
                    <option value="default">默认排序</option>
                    <option value="relevance">相关性优先</option>
                    <option value="institution">机构优先</option>
                    <option value="diversity">多样性优先</option>
                  </select>
                </label>

                <button
                  v-if="topicFilter"
                  type="button"
                  class="digest-workspace-toolbar__clear"
                  @click="topicFilter = ''"
                >清除筛选</button>

                <button
                  v-if="isAuthenticated"
                  type="button"
                  class="digest-workspace-toolbar__secondary"
                  title="查看可能被低估的论文"
                  @click="missedPapersOpen = true"
                >可能错过</button>
              </div>
            </div>
          </template>

        <!-- Welcome Hero Banner — shown once to first-time unauthenticated visitors -->
        <Transition name="banner-slide">
          <div
            v-if="showWelcomeBanner"
            class="absolute inset-x-0 top-0 z-30 flex items-start justify-center pt-6 pb-8 px-4 bg-gradient-to-b from-bg-base via-bg-base/95 to-bg-base/0 backdrop-blur-[2px]"
          >
            <div class="w-full max-w-md bg-bg-card border border-border rounded-2xl shadow-xl px-6 py-5">
              <div class="flex items-start justify-between mb-3">
                <div>
                  <h2 class="text-base font-bold text-text-primary leading-snug">每天 10 分钟，掌握 AI/ML 最新研究</h2>
                  <p class="mt-1 text-xs text-text-muted">AI 自动筛选 arXiv 论文 · 中文摘要 · 知识库 · 灵感生成，核心功能免费</p>
                </div>
                <button
                  class="ml-3 shrink-0 text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                  @click="dismissWelcomeBanner"
                  aria-label="关闭"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                  </svg>
                </button>
              </div>
              <ul class="grid grid-cols-2 gap-x-4 gap-y-1.5 mb-4 text-xs text-text-secondary">
                <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>AI 主题相关性评分</li>
                <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>中文摘要一键生成</li>
                <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>AI 论文对比分析</li>
                <li class="flex items-center gap-1.5"><span class="text-tinder-pink">✦</span>知识库 + 灵感生成</li>
              </ul>
              <div class="flex items-center gap-2">
                <button
                  class="flex-1 px-4 py-2 rounded-full bg-brand-gradient text-white text-xs font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
                  @click="dismissWelcomeBanner"
                >
                  开始浏览论文
                </button>
                <RouterLink
                  to="/tutorial"
                  class="px-4 py-2 rounded-full border border-border text-text-secondary text-xs font-medium hover:bg-bg-hover transition-colors"
                  @click="dismissWelcomeBanner"
                >
                  了解更多
                </RouterLink>
              </div>
            </div>
          </div>
        </Transition>


        <!-- Loading -->
        <LoadingSpinner v-if="loading" :text="selectedDate ? `正在加载 ${selectedDate} 的论文…` : '加载论文中…'" />

        <!-- Error -->
        <ErrorState v-else-if="error" :message="error" :type="errorType" @retry="retryLoad" />

        <!-- 超限提示（卡片模式下刷完后显示，列表模式不触发此分支） -->
        <div v-else-if="digestViewMode !== 'list' && isQuotaExceeded && isActuallyLimited && quotaExceededMessage" class="flex flex-col items-center justify-center gap-4 text-center px-8 max-w-sm">
          <div class="text-5xl mb-1">🚀</div>
          <h2 class="text-xl font-bold text-text-primary">想看更多？免费注册解锁全部论文</h2>
          <p class="text-sm text-text-secondary">
            {{ quotaExceededMessage }}
          </p>
          <!-- 未登录用户：展示功能列表 + 注册/登录按钮 -->
          <template v-if="!isAuthenticated">
            <ul class="text-left text-sm text-text-secondary space-y-1.5 bg-bg-card border border-border rounded-xl px-5 py-4 w-full">
              <li class="flex items-center gap-2"><span class="text-tinder-pink font-bold">✦</span>每日全量 AI 论文推荐，无阅读上限</li>
              <li class="flex items-center gap-2"><span class="text-tinder-pink font-bold">✦</span>中文摘要 + AI 问答，快速读懂每篇</li>
              <li class="flex items-center gap-2"><span class="text-tinder-pink font-bold">✦</span>论文对比 · 知识库 · 灵感生成</li>
              <li class="flex items-center gap-2"><span class="text-tinder-pink font-bold">✦</span>核心功能免费，高级 AI 可自带 Key 无限使用</li>
            </ul>
            <div class="flex items-center gap-2 w-full">
              <button
                class="flex-1 mt-1 px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
                @click="router.push({ path: '/register', query: { redirect: route.fullPath } })"
              >
                免费注册
              </button>
              <button
                class="flex-1 mt-1 px-6 py-2.5 rounded-full border border-border text-text-secondary text-sm font-medium cursor-pointer hover:bg-bg-hover transition-colors"
                @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
              >
                已有账号，登录
              </button>
            </div>
          </template>
          <!-- 已登录用户：使用统一升级提示组件 -->
          <template v-else>
            <UpgradePrompt feature="browse" class="w-full max-w-sm" />
          </template>
        </div>

        <!-- All dates exhausted (true end state) -->
        <EmptyState
          v-else-if="allSwiped && allDatesExhausted"
          icon="🎉"
          title="所有论文已全部浏览"
          :description="`知识库已收藏 ${kbPaperCount} 篇，新论文将在明天更新`"
        >
          <button
            class="px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="resetCards"
          >重新浏览</button>
          <button
            v-if="isAuthenticated"
            class="px-5 py-2.5 rounded-full border border-border text-text-secondary text-sm font-medium cursor-pointer hover:bg-bg-hover transition-colors"
            @click="missedPapersOpen = true"
          >看看可能错过的论文</button>
        </EmptyState>

        <!-- Card / List view — shown when papers are available -->
        <template v-else-if="currentPaper || (papers.length > 0 && digestViewMode === 'list')">

          <!-- ===== LIST VIEW ===== -->
          <div v-if="digestViewMode === 'list'" class="digest-list-workspace">
            <section class="digest-list-pane" aria-label="论文列表">
              <div class="digest-list-commandbar">
                <label class="digest-list-commandbar__select-all">
                  <input
                    type="checkbox"
                    :checked="isCurrentPageSelected"
                    aria-label="选择当前页全部论文"
                    @change="toggleCurrentPageSelection"
                  >
                  <span>{{ selectedPaperCount > 0 ? `已选 ${selectedPaperCount} 篇` : '选择' }}</span>
                </label>

                <div v-if="selectedPaperCount > 0" class="digest-list-commandbar__bulk-actions">
                  <button type="button" @click="collectSelectedPapers">批量收藏</button>
                  <button type="button" :disabled="selectedPaperCount < 2" @click="compareSelectedPapers">加入对比</button>
                  <button type="button" @click="clearPaperSelection">清除选择</button>
                </div>
                <p v-else>单击查看详情，双击或按 Enter 精读</p>
              </div>

              <div class="digest-list-columns" aria-hidden="true">
                <span></span>
                <span>论文信息</span>
                <span>相关度</span>
                <span>作者</span>
                <span>日期</span>
                <span>操作</span>
              </div>

              <div ref="listScrollRef" class="digest-list-scroll" role="listbox" aria-label="论文结果">
                <div v-if="displayPapers.length === 0" class="digest-list-empty">
                  <p>没有符合 {{ topicFilter }} 分类的论文</p>
                  <button type="button" @click="topicFilter = ''">清除筛选</button>
                </div>

                <div v-else class="digest-list-rows">
                  <WorkspacePaperRow
                    v-for="(paper, idx) in pagedPapers"
                    :key="paper.paper_id"
                    :paper="paper"
                    :index="listPage * LIST_PAGE_SIZE + idx"
                    :active="listPage * LIST_PAGE_SIZE + idx === currentIndex"
                    :selected="selectedPaperIds.has(paper.paper_id)"
                    :collected="collectedPaperIds.has(paper.paper_id)"
                    :bookmarked="bookmarkedPaperIds.has(paper.paper_id)"
                    :publication-date="effectiveDate || selectedDate"
                    @select="openListDetail(paper, listPage * LIST_PAGE_SIZE + idx)"
                    @open="openListPaper(paper, listPage * LIST_PAGE_SIZE + idx)"
                    @toggle-selection="togglePaperSelection(paper.paper_id)"
                    @collect="collectListPaper(paper)"
                    @toggle-bookmark="bookmarkListPaper(paper)"
                  />
                </div>

                <div v-if="listTotalPages > 1" class="digest-list-pagination">
                  <button type="button" :disabled="listPage <= 0" @click="listGoPage(listPage - 1)">上一页</button>
                  <span>{{ listPage + 1 }} / {{ listTotalPages }}</span>
                  <button type="button" :disabled="listPage >= listTotalPages - 1" @click="listGoPage(listPage + 1)">下一页</button>
                </div>

                <div v-if="isActuallyLimited && totalAvailable > papers.length" class="digest-list-quota">
                  <p>还有 {{ totalAvailable - papers.length }} 篇论文因当前档位限制未显示（共 {{ totalAvailable }} 篇）</p>
                  <template v-if="!isAuthenticated">
                    <button type="button" class="digest-list-quota__primary" @click="router.push({ path: '/register', query: { redirect: route.fullPath } })">免费注册解锁全部</button>
                    <button type="button" @click="router.push({ path: '/login', query: { redirect: route.fullPath } })">已有账号，登录</button>
                  </template>
                  <UpgradePrompt v-else feature="browse" class="w-full" />
                </div>
              </div>
            </section>

            <button
              v-if="listInspectorOpen"
              type="button"
              class="digest-list-inspector-backdrop"
              aria-label="关闭论文检查器"
              @click="listInspectorOpen = false"
            />

            <section
              class="digest-list-inspector"
              :class="{ 'digest-list-inspector--open': listInspectorOpen }"
            >
              <button
                type="button"
                class="digest-list-inspector__close"
                @click="listInspectorOpen = false"
              >关闭</button>
              <PaperInspector
                :paper="currentPaper"
                :publication-date="effectiveDate || selectedDate"
                :collected="currentPaper ? collectedPaperIds.has(currentPaper.paper_id) : false"
                :bookmarked="currentPaper ? bookmarkedPaperIds.has(currentPaper.paper_id) : false"
                @open-detail="openDetail"
                @open-pdf="openPdf"
                @collect="currentPaper && collectListPaper(currentPaper)"
                @toggle-bookmark="currentPaper && bookmarkListPaper(currentPaper)"
                @start-research="currentPaper && startListResearch(currentPaper)"
              />
            </section>
          </div>

          <!-- ===== IMMERSIVE VIEW ===== -->
          <ImmersivePaperReader
            v-else-if="digestViewMode === 'immersive' && currentPaper"
            :key="currentPaper.paper_id"
            :paper="currentPaper"
            :related-papers="immersiveRelatedPapers"
            :publication-date="effectiveDate || selectedDate"
            :position="currentIndex + 1"
            :total="displayPapers.length"
            :collected="collectedPaperIds.has(currentPaper.paper_id)"
            :bookmarked="bookmarkedPaperIds.has(currentPaper.paper_id)"
            :can-go-previous="currentIndex > 0"
            :can-go-next="currentIndex < displayPapers.length - 1"
            @previous="navigateImmersive(-1)"
            @next="navigateImmersive(1)"
            @skip="skip"
            @compare="compareImmersivePaper"
            @collect="collectListPaper(currentPaper)"
            @open-pdf="openPdf"
            @open-detail="openDetail"
            @toggle-bookmark="bookmarkListPaper(currentPaper)"
            @start-research="startListResearch(currentPaper)"
            @select-related="openImmersiveRelated"
            @change-mode="setDigestViewMode"
            @login="router.push({ path: '/login', query: { redirect: route.fullPath } })"
          />
          <!-- ===== CARD VIEW ===== -->
          <!-- Wrap in own relative container so absolute children (counter pill, toasts) are scoped here -->
          <div v-else class="flex-1 relative w-full flex flex-col items-center justify-center">

            <!-- Date transition toast — shown briefly when auto-advancing to a previous day -->
            <Transition name="date-toast">
              <div
                v-if="dateTransitionNotice"
                class="absolute bottom-[160px] inset-x-0 z-30 pointer-events-none flex justify-center"
              >
                <div class="flex items-center gap-2 px-4 py-2 rounded-full bg-bg-card/95 backdrop-blur-sm border border-border shadow-lg">
                  <svg class="w-3.5 h-3.5 text-tinder-pink shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  <span class="text-[12px] text-text-secondary font-medium whitespace-nowrap">{{ dateTransitionNotice }} 的论文</span>
                </div>
              </div>
            </Transition>

            <!-- Onboarding hint for authenticated users (link to paper_recommend settings) -->
            <Transition name="date-toast">
              <div
                v-if="showRecommendHint && !isInPanelView"
                class="absolute top-[52px] inset-x-0 z-20 flex justify-center pointer-events-auto"
              >
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-tinder-blue/10 backdrop-blur-sm border border-tinder-blue/25 shadow-sm">
                  <span class="text-[11px]">💡</span>
                  <span class="text-[11px] text-tinder-blue whitespace-nowrap">自定义推荐主题偏好</span>
                  <RouterLink
                    to="/advanced-settings?tab=paper_recommend"
                    class="text-[11px] font-semibold text-tinder-blue hover:underline whitespace-nowrap"
                    @click="dismissRecommendHint"
                  >去设置 →</RouterLink>
                  <button
                    class="text-[11px] text-text-muted hover:text-text-primary ml-1 cursor-pointer bg-transparent border-none leading-none"
                    @click="dismissRecommendHint"
                  >✕</button>
                </div>
              </div>
            </Transition>

            <!-- The card — responsive width/height -->
            <div class="w-full px-3 sm:px-0 mx-auto" style="max-width: var(--card-max-w); height: clamp(var(--card-min-h), calc(100dvh - var(--card-height-offset)), var(--card-max-h))">
              <PaperCard
                :key="currentPaper.paper_id"
                :paper="currentPaper"
                :anim-class="cardAnimClass"
                :rec-date="effectiveDate || selectedDate"
              />
            </div>

            <!-- Action buttons — directly below card, no control row -->
            <ActionButtons
              @undo="undo"
              @skip="skip"
              @like="like"
              @detail="openDetail"
              @superlike="openPdf"
            />

          </div>
        </template>

        <!-- No data: with pipeline notice (e.g. weekend, no matching papers) -->
        <div
          v-else-if="!loading && selectedDate && dateNotice"
          class="flex flex-col items-center gap-4 text-center px-8 max-w-sm"
        >
          <span class="text-5xl">
            {{ dateNotice.type === 'no_papers_weekend' ? '📅' : dateNotice.type === 'no_matching_papers' ? '🔍' : '📭' }}
          </span>
          <h2 class="text-base font-semibold text-text-primary">
            {{ selectedDate }} 暂无论文推荐
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            {{ dateNotice.message }}
          </p>
        </div>

        <!-- No data: all historical papers have been read / collected / dismissed -->
        <div v-else-if="!loading && selectedDate" class="flex flex-col items-center gap-3 text-center px-8 max-w-sm">
          <span class="text-5xl">✅</span>
          <h2 class="text-base font-semibold text-text-primary">近期论文已全部浏览</h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            已收藏或跳过所有可用论文，新内容将在每个工作日更新
          </p>
          <button
            v-if="isAuthenticated"
            class="mt-1 px-5 py-2 rounded-full bg-bg-secondary border border-border text-sm text-text-secondary cursor-pointer hover:bg-bg-card transition-colors"
            @click="() => showSidebar = true"
          >查看知识库</button>
        </div>
        </ResearchWorkspaceShell><!-- /main research workspace -->
      </div><!-- /默认卡片刷刷模式 -->

  <!-- Upload dialog -->
  <UserPaperUploadDialog
    v-if="showUploadDialog"
    @close="showUploadDialog = false"
    @uploaded="handleUploadDialogUploaded"
  />

  <!-- Missed papers modal (triggered from navbar or completion state) -->
  <Teleport to="body">
    <Transition name="missed-fade">
      <div
        v-if="missedPapersOpen && isAuthenticated"
        class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
        style="background: rgba(0,0,0,0.45);"
        @click.self="missedPapersOpen = false"
      >
        <div class="bg-bg-card rounded-t-2xl sm:rounded-2xl w-full sm:max-w-[420px] shadow-xl overflow-hidden">
          <WhyNotDrawer
            :date="effectiveDate || selectedDate"
            :is-authenticated="isAuthenticated"
            :embedded="true"
            @close="missedPapersOpen = false"
          />
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- Review drawer: spaced-repetition cards due today -->
  <Teleport to="body">
    <Transition name="missed-fade">
      <div
        v-if="reviewOpen && isAuthenticated"
        class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
        style="background: rgba(0,0,0,0.45);"
        @click.self="reviewOpen = false"
      >
        <div class="bg-bg-card rounded-t-2xl sm:rounded-2xl w-full sm:max-w-[460px] shadow-xl overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border">
            <div>
              <p class="text-[14px] font-semibold text-text-primary">到期复习</p>
              <p class="text-[11px] text-text-muted mt-0.5">收藏一段时间后，趁热巩固记忆</p>
            </div>
            <button
              type="button"
              class="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-bg-elevated transition-colors"
              @click="reviewOpen = false"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <!-- Loading -->
          <div v-if="reviewLoading" class="flex items-center justify-center py-10">
            <div class="w-5 h-5 rounded-full border-2 border-tinder-purple border-t-transparent animate-spin" />
          </div>
          <!-- Cards -->
          <div v-else-if="reviewCards.length" class="divide-y divide-border max-h-[65vh] overflow-y-auto">
            <div
              v-for="card in reviewCards"
              :key="card.paper_id || card._paper_id"
              class="px-5 py-4 space-y-2"
            >
              <p class="text-[13px] font-medium text-text-primary leading-snug line-clamp-2">
                {{ card.short_title || card['📖标题'] || card.title || card.paper_id }}
              </p>
              <p class="text-[11px] text-text-muted">{{ card.review_reason }}（{{ card.days_since_saved }} 天前收藏）</p>
              <div class="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  class="text-[11px] px-3 py-1.5 rounded-lg font-medium bg-tinder-purple/10 text-tinder-purple border border-tinder-purple/20 hover:bg-tinder-purple/20 transition-colors"
                  @click="handleReviewResponse(card, 'reread')"
                >重读论文</button>
                <button
                  type="button"
                  class="text-[11px] px-3 py-1.5 rounded-lg bg-tinder-green/10 text-tinder-green border border-tinder-green/20 hover:bg-tinder-green/20 transition-colors"
                  @click="handleReviewResponse(card, 'remember')"
                >已记住</button>
                <button
                  type="button"
                  class="text-[11px] px-3 py-1.5 rounded-lg bg-bg-elevated text-text-muted border border-border hover:text-text-secondary transition-colors"
                  @click="handleReviewResponse(card, 'skip')"
                >稍后</button>
                <button
                  type="button"
                  class="ml-auto text-[11px] text-text-muted hover:text-text-secondary transition-colors"
                  @click="handleReviewResponse(card, 'dismiss_forever')"
                >不再提醒</button>
              </div>
            </div>
          </div>
          <!-- Empty: all cleared -->
          <div v-else class="flex flex-col items-center gap-2 py-10 text-center">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-green">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <p class="text-sm font-medium text-text-primary">今日复习已完成</p>
            <p class="text-xs text-text-muted">继续收藏论文，系统会适时提醒你复习。</p>
          </div>
          <!-- Footer -->
          <div class="px-5 py-3 border-t border-border">
            <button
              type="button"
              class="w-full text-[12px] text-text-muted hover:text-text-secondary transition-colors"
              @click="reviewOpen = false; router.push('/recap')"
            >查看完整周回顾 →</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- Reactivation drawer: revisit + question items from most recent recap -->
  <Teleport to="body">
    <Transition name="missed-fade">
      <div
        v-if="reactivationOpen && isAuthenticated"
        class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
        style="background: rgba(0,0,0,0.45);"
        @click.self="reactivationOpen = false"
      >
        <div class="bg-bg-card rounded-t-2xl sm:rounded-2xl w-full sm:max-w-[420px] shadow-xl overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border">
            <div>
              <p class="text-[14px] font-semibold text-text-primary">从收藏继续研究</p>
              <p class="text-[11px] text-text-muted mt-0.5">上周回顾提炼的追问方向与重读建议</p>
            </div>
            <button
              type="button"
              class="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-bg-elevated transition-colors"
              @click="reactivationOpen = false"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <!-- Items -->
          <div class="divide-y divide-border max-h-[60vh] overflow-y-auto">
            <div
              v-for="(item, idx) in radarData?.reactivation?.preview ?? []"
              :key="idx"
              class="flex items-start gap-3 px-5 py-3.5"
            >
              <!-- Kind icon -->
              <div class="shrink-0 mt-1">
                <svg v-if="item.kind === 'revisit'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-purple">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                </svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-blue">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <!-- Content -->
              <div class="flex-1 min-w-0">
                <p class="text-[13px] text-text-primary leading-snug">{{ item.title }}</p>
                <p class="text-[11px] text-text-muted mt-0.5 leading-snug">{{ item.reason }}</p>
              </div>
              <!-- Action: revisit → open paper; question → open paper in context or AI chat -->
              <button
                v-if="item.kind === 'revisit' && item.paper_id"
                type="button"
                class="shrink-0 text-[11px] px-2.5 py-1.5 rounded-lg bg-tinder-purple/10 text-tinder-purple border border-tinder-purple/20 hover:bg-tinder-purple/20 transition-colors"
                @click="reactivationOpen = false; router.push(`/papers/${item.paper_id}`)"
              >重读</button>
              <button
                v-else-if="item.paper_id"
                type="button"
                class="shrink-0 text-[11px] px-2.5 py-1.5 rounded-lg bg-tinder-blue/10 text-tinder-blue border border-tinder-blue/20 hover:bg-tinder-blue/20 transition-colors"
                @click="reactivationOpen = false; router.push(`/papers/${item.paper_id}`)"
              >去追问</button>
              <button
                v-else
                type="button"
                class="shrink-0 text-[11px] px-2.5 py-1.5 rounded-lg bg-tinder-blue/10 text-tinder-blue border border-tinder-blue/20 hover:bg-tinder-blue/20 transition-colors"
                @click="reactivationOpen = false; globalChat.open()"
              >问 AI</button>
            </div>
          </div>
          <!-- Footer -->
          <div class="px-5 py-3 border-t border-border flex items-center justify-between">
            <button
              type="button"
              class="text-[12px] text-text-muted hover:text-text-secondary transition-colors"
              @click="reactivationOpen = false; router.push('/recap')"
            >查看完整周回顾 →</button>
            <button
              type="button"
              class="text-[12px] px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary hover:text-text-primary transition-colors"
              @click="reactivationOpen = false; globalChat.open()"
            >发起 AI 对话</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  </SidebarPageLayout>
</template>

<style scoped>
.digest-list-workspace {
  position: relative;
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-columns: minmax(0, 1fr) clamp(380px, 34vw, 520px);
  overflow: hidden;
}

.digest-list-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg);
}

.digest-list-commandbar {
  display: flex;
  min-height: 44px;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  padding: 7px 14px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-card);
}

.digest-list-commandbar__select-all {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-text-secondary);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.digest-list-commandbar__select-all input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-tinder-pink);
}

.digest-list-commandbar > p {
  margin: 0 0 0 auto;
  color: var(--color-text-muted);
  font-size: 10px;
}

.digest-list-commandbar__bulk-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.digest-list-commandbar__bulk-actions button,
.digest-list-pagination button,
.digest-list-empty button,
.digest-list-quota button {
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font: inherit;
  font-size: 10px;
  cursor: pointer;
}

.digest-list-commandbar__bulk-actions button:hover,
.digest-list-pagination button:hover:not(:disabled),
.digest-list-empty button:hover,
.digest-list-quota button:hover {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 38%, var(--color-border));
  color: var(--color-text-primary);
}

.digest-list-commandbar__bulk-actions button:disabled,
.digest-list-pagination button:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.digest-list-columns {
  display: grid;
  grid-template-columns: 32px minmax(260px, 1fr) 76px 112px 92px 124px;
  gap: 12px;
  min-height: 34px;
  flex: 0 0 auto;
  align-items: center;
  padding: 0 14px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-muted);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.digest-list-columns span:nth-child(n + 3) {
  text-align: left;
}

.digest-list-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--color-bg);
}

.digest-list-rows {
  border-bottom: 1px solid var(--color-border);
}

.digest-list-empty {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  padding: 24px;
  text-align: center;
}

.digest-list-empty p {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 12px;
}

.digest-list-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 14px;
}

.digest-list-pagination span {
  color: var(--color-text-muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.digest-list-quota {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-gold) 24%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-tinder-gold) 7%, transparent);
}

.digest-list-quota p {
  min-width: 220px;
  flex: 1 1 auto;
  margin: 0;
  color: var(--color-tag-score-mid);
  font-size: 10px;
}

.digest-list-quota .digest-list-quota__primary {
  border-color: transparent;
  background: var(--color-tinder-pink);
  color: white;
}

.digest-list-inspector {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border-left: 1px solid var(--color-border);
  background: var(--color-bg-card);
}

.digest-list-inspector__close,
.digest-list-inspector-backdrop {
  display: none;
}

@media (max-width: 1599px) {
  .digest-list-columns {
    grid-template-columns: 30px minmax(200px, 1fr) 58px 76px 82px 96px;
  }
}

@media (max-width: 1279px) {
  .digest-list-workspace {
    display: block;
  }

  .digest-list-pane {
    width: 100%;
    height: 100%;
  }

  .digest-list-columns {
    grid-template-columns: 28px minmax(0, 1fr) 58px 102px;
  }

  .digest-list-columns span:nth-child(4),
  .digest-list-columns span:nth-child(5) {
    display: none;
  }

  .digest-list-inspector {
    position: absolute;
    z-index: 21;
    top: 0;
    right: 0;
    bottom: 0;
    display: none;
    width: min(460px, calc(100% - 24px));
    border-left: 1px solid var(--color-border);
    box-shadow: -16px 0 44px color-mix(in srgb, #000 25%, transparent);
  }

  .digest-list-inspector--open {
    display: block;
  }

  .digest-list-inspector-backdrop {
    position: absolute;
    z-index: 20;
    inset: 0;
    display: block;
    border: 0;
    background: color-mix(in srgb, #000 32%, transparent);
    cursor: default;
  }

  .digest-list-inspector__close {
    position: absolute;
    z-index: 2;
    top: 10px;
    right: 12px;
    display: inline-flex;
    min-height: 28px;
    align-items: center;
    padding: 0 9px;
    border: 1px solid var(--color-border);
    border-radius: 7px;
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
    font: inherit;
    font-size: 10px;
    cursor: pointer;
  }
}

@media (max-width: 767px) {
  .digest-list-commandbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .digest-list-commandbar > p {
    display: none;
  }

  .digest-list-commandbar__bulk-actions {
    width: 100%;
    overflow-x: auto;
  }

  .digest-list-columns {
    display: none;
  }

  .digest-list-inspector {
    width: 100%;
  }
}

.digest-workspace-toolbar {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px clamp(12px, 2vw, 24px);
}

.digest-workspace-toolbar__context,
.digest-workspace-toolbar__filters {
  display: flex;
  min-width: 0;
  align-items: center;
}

.digest-workspace-toolbar__context {
  gap: 8px;
  white-space: nowrap;
}

.digest-workspace-toolbar__filters {
  justify-content: flex-end;
  gap: 8px;
}

.digest-workspace-toolbar__title {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 700;
}

.digest-workspace-toolbar__date,
.digest-workspace-toolbar__count {
  color: var(--color-text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.digest-workspace-toolbar__date::after {
  margin-left: 8px;
  color: var(--color-border-light);
  content: '/';
}

.digest-workspace-toolbar__field select,
.digest-workspace-toolbar__secondary,
.digest-workspace-toolbar__clear {
  height: 30px;
  border-radius: 8px;
  font: inherit;
  font-size: 11px;
}

.digest-workspace-toolbar__field select {
  max-width: 128px;
  padding: 0 28px 0 10px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.digest-workspace-toolbar__field select:focus-visible,
.digest-workspace-toolbar__secondary:focus-visible,
.digest-workspace-toolbar__clear:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--color-tinder-pink) 68%, white);
  outline-offset: 2px;
}

.digest-workspace-toolbar__secondary {
  flex: 0 0 auto;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-card);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease, background-color 150ms ease;
}

.digest-workspace-toolbar__secondary:hover {
  border-color: var(--color-border-light);
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.digest-workspace-toolbar__clear {
  flex: 0 0 auto;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--color-tinder-pink);
  cursor: pointer;
}

@media (max-width: 767px) {
  .digest-workspace-toolbar {
    align-items: stretch;
    flex-direction: column;
    gap: 7px;
    padding-block: 7px;
  }

  .digest-workspace-toolbar__filters {
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 1px;
    scrollbar-width: none;
  }

  .digest-workspace-toolbar__filters::-webkit-scrollbar {
    display: none;
  }

  .digest-workspace-toolbar__date {
    display: none;
  }

  .digest-workspace-toolbar__field select {
    max-width: 116px;
  }
}

/* Sidebar slide transition */
.sidebar-slide-enter-active,
.sidebar-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}


/* Welcome banner slide-up transition */
.banner-slide-enter-active,
.banner-slide-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.banner-slide-enter-from,
.banner-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Date transition toast — fades in and slides up slightly */
.date-toast-enter-active,
.date-toast-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.date-toast-enter-from,
.date-toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* Missed papers modal overlay */
.missed-fade-enter-active,
.missed-fade-leave-active {
  transition: opacity 0.2s ease;
}
.missed-fade-enter-from,
.missed-fade-leave-to {
  opacity: 0;
}
</style>
