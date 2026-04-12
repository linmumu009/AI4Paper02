<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import IdeaCard from '../components/idea/IdeaCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import ContentLayout from '../components/ContentLayout.vue'
import type { ContentLayoutContext } from '../components/ContentLayout.vue'
import PdfPanel from '../components/panels/PdfPanel.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import SidebarPageLayout from '../components/SidebarPageLayout.vue'
import UpgradePrompt from '../components/UpgradePrompt.vue'
import { PANEL_IDS, STORAGE_PREFIX, type LayoutState, type PanelConfigItem } from '../composables/usePanelLayout'
import { fetchDates, addKbPaper, deleteNote, fetchIdeaDigest, createIdeaFeedback, addNoteLink, fetchIdeaAtom, fetchPaperDetail, generateCandidatesForPaper, API_ORIGIN } from '../api'
import type { IdeaCandidate, UserPaperViewMdPayload } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import { useGlobalChat } from '../composables/useGlobalChat'
import { useKbSidebarState } from '../composables/useKbSidebarState'
import { useEngagement } from '../composables/useEngagement'
import { useEntitlements } from '../composables/useEntitlements'
import { trackKbAction } from '../composables/useAnalytics'

const router = useRouter()
const route = useRoute()
const globalChat = useGlobalChat()
const engagement = useEngagement()
const ent = useEntitlements()
const ideaGenQuotaBlocked = computed(() => !ent.canUse('idea_gen'))

// Dates
const dates = ref<string[]>([])
const selectedDate = ref('')

// Knowledge base + sidebar shared state
const { kbTree, activeFolderId, compareTree, showSidebar, loadKbTree, loadCompareTree, collapseSidebarOnMobile, markPaperReadStatus } = useKbSidebarState('inspiration')

// Sidebar ref
const sidebarRef = ref<InstanceType<typeof Sidebar> | null>(null)

// ---- 侧栏 Tab 状态 ----
const sidebarActiveTab = ref<'papers' | 'compare' | 'mypapers' | 'paper-inspiration' | 'research'>('papers')

// ---- 论文灵感：生成候选卡片 ----
const paperInspirationPaperId = ref<string | null>(null)
const paperInspirationTitle = ref('')
const paperCandidates = ref<IdeaCandidate[]>([])
const paperCandidateIndex = ref(0)
const paperInspirationLoading = ref(false)
const paperInspirationError = ref('')
const paperCandidateAnimClass = ref('card-enter')

const currentPaperCandidate = computed(() => paperCandidates.value[paperCandidateIndex.value] ?? null)
const paperAllSwiped = computed(
  () => paperCandidates.value.length > 0 && paperCandidateIndex.value >= paperCandidates.value.length,
)

async function handlePaperInspiration(paperId: string, title: string, force = false) {
  // 清除其他互斥视图（包括 editingNote，否则其优先级高于 paperInspirationPaperId 会导致点击无反应）
  editingNote.value = null
  viewingIdeaId.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null

  paperInspirationPaperId.value = paperId
  paperInspirationTitle.value = title
  paperCandidates.value = []
  paperCandidateIndex.value = 0
  paperCandidateAnimClass.value = 'card-enter'
  paperInspirationError.value = ''

  // Guard: block generation (quota is consumed on each call) when exhausted
  if (ideaGenQuotaBlocked.value && ent.loaded.value) {
    paperInspirationError.value = '本月灵感生成次数已用完，请升级套餐继续使用。'
    return
  }

  paperInspirationLoading.value = true

  collapseSidebarOnMobile()

  try {
    // 后端负责检查 DB 中是否已有候选：force=false 时直接返回已有记录，无需重新生成
    const res = await generateCandidatesForPaper(paperId, force)
    paperCandidates.value = res.candidates
    // Refresh quota after generation (quota is consumed on new generation)
    void ent.refreshEntitlements(true)
  } catch (e: any) {
    paperInspirationError.value = e?.response?.data?.detail || e?.message || '灵感生成失败'
  } finally {
    paperInspirationLoading.value = false
    sidebarRef.value?.onPaperInspirationDone(paperId)
  }
}

function paperCandidateNext(direction: 'left' | 'right') {
  paperCandidateAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  setTimeout(() => {
    paperCandidateIndex.value++
    paperCandidateAnimClass.value = 'card-enter'
  }, 300)
}

function paperCandidateSkip() {
  const c = currentPaperCandidate.value
  paperCandidateNext('left')
  if (c) createIdeaFeedback({ candidate_id: c.id, action: 'discard' }).catch(() => {})
}

function paperCandidateLike() {
  const c = currentPaperCandidate.value
  if (!c) return
  paperCandidateNext('right')
  createIdeaFeedback({ candidate_id: c.id, action: 'collect' }).catch(() => {})
  void engagement.record('collect', 'inspiration-paper-candidate-like', String(c.id))
}

function paperCandidateOpenDetail() {
  if (currentPaperCandidate.value) {
    // 不清空 paperInspirationPaperId，以便详情关闭后能回到论文灵感卡片视图
    viewingIdeaId.value = currentPaperCandidate.value.id
  }
}

async function handlePaperInspirationDetail(paperId: string, title: string) {
  // 若该论文候选已加载，直接打开当前候选的详情面板
  if (paperInspirationPaperId.value === paperId && paperCandidates.value.length > 0) {
    paperCandidateOpenDetail()
    return
  }
  // 否则先生成候选，生成完毕后自动打开第一个的详情
  await handlePaperInspiration(paperId, title)
  if (paperCandidates.value.length > 0) {
    viewingIdeaId.value = paperCandidates.value[0].id
  }
}

function paperCandidateReset() {
  paperCandidateIndex.value = 0
  paperCandidateAnimClass.value = 'card-enter'
}

// Load dates
onMounted(async () => {
  await ensureAuthInitialized()
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch {}

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
    await engagement.loadStatus(true)
  }
})

// Watch sidebar tab changes to show/hide empty research panel
watch(sidebarActiveTab, (tab) => {
  if (tab === 'research') {
    // 点击深度研究 Tab（含重复点击）时始终重置到空态首页
    researchPaperIds.value = []
    researchPaperTitles.value = {}
    inspireResearchInitialSessionId.value = null
  } else {
    // 若在空态研究面板，切换到其他 tab 时收起
    if (researchPaperIds.value !== null && researchPaperIds.value.length === 0) {
      researchPaperIds.value = null
    }
  }
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
      void engagement.record('analyze', 'inspiration-chat', '')
    }
  },
)

watch(
  () => isAuthenticated.value,
  async (authed) => {
    if (authed) {
      await loadKbTree()
      await loadCompareTree()
      await engagement.loadStatus(true)
      if (selectedDate.value) {
        await loadIdeaDigest(selectedDate.value)
      }
    } else {
      kbTree.value = { folders: [], papers: [] }
      compareTree.value = null
      activeFolderId.value = null
      ideaCandidates.value = []
      ideaTotalAvailable.value = 0
      ideaQuotaLimit.value = null
      ideaResponseTier.value = 'free'
      engagement.status.value = null
      engagement.loaded.value = false
    }
  },
)

// 全局 AI 问答存入笔记时刷新知识库侧栏
watch(globalChat.noteSavedSignal, async () => {
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
})

// ==================== 灵感推荐（日期驱动，类 DailyDigest）====================
const ideaCandidates = ref<IdeaCandidate[]>([])
const ideaLoading = ref(false)
const ideaError = ref('')
const ideaErrorType = ref<'proxy' | 'server' | 'unknown'>('unknown')
const ideaCurrentIndex = ref(0)
const ideaCardAnimClass = ref('card-enter')
const ideaHistory = ref<number[]>([])
const ideaTotalAvailable = ref(0)
const ideaQuotaLimit = ref<number | null>(null)
const ideaResponseTier = ref<string>('free')

const currentCandidate = computed(() => ideaCandidates.value[ideaCurrentIndex.value] ?? null)
const ideaAllSwiped = computed(
  () => ideaCandidates.value.length > 0 && ideaCurrentIndex.value >= ideaCandidates.value.length,
)
const isIdeaQuotaExceeded = computed(() => {
  if (ideaLoading.value) return false
  const limit = ideaQuotaLimit.value
  const count = ideaCandidates.value.length
  if (limit === null || count === 0) return false
  return ideaCurrentIndex.value >= count && count >= limit
})
const isIdeaActuallyLimited = computed(() => {
  if (ideaQuotaLimit.value === null) return false
  return ideaTotalAvailable.value > ideaCandidates.value.length
})
const ideaQuotaExceededMessage = computed(() => {
  const tier = ideaResponseTier.value
  const limit = ideaQuotaLimit.value
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') return `您已达到 Pro 账号上限（${limit ?? 15} 条）`
  return `您已达到普通账号上限（${limit ?? 3} 条）`
})

async function loadIdeaDigest(date: string) {
  if (!isAuthenticated.value || !date) {
    ideaCandidates.value = []
    return
  }
  ideaLoading.value = true
  ideaError.value = ''
  ideaErrorType.value = 'unknown'
  try {
    const res = await fetchIdeaDigest(date)
    ideaCandidates.value = res.candidates
    ideaTotalAvailable.value = res.total_available
    ideaQuotaLimit.value = res.quota_limit
    ideaResponseTier.value = res.tier ?? currentTier.value
    ideaCurrentIndex.value = 0
    ideaHistory.value = []
    ideaCardAnimClass.value = 'card-enter'
  } catch (e: any) {
    ideaErrorType.value = e?.errorType || (e?.response ? 'server' : 'unknown')
    ideaError.value = e?.response?.data?.detail || e?.message || '加载灵感失败'
    ideaCandidates.value = []
  } finally {
    ideaLoading.value = false
  }
}

// Reload ideas when date changes
watch(selectedDate, async (date) => {
  if (date && isAuthenticated.value) {
    await loadIdeaDigest(date)
  }
})

function ideaNext(direction: 'left' | 'right') {
  if (!currentCandidate.value) return
  ideaCardAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  ideaHistory.value.push(ideaCurrentIndex.value)
  setTimeout(() => {
    ideaCurrentIndex.value++
    ideaCardAnimClass.value = 'card-enter'
  }, 300)
}

function ideaSkip() {
  const candidate = currentCandidate.value
  ideaNext('left')
  if (candidate) {
    createIdeaFeedback({ candidate_id: candidate.id, action: 'discard' }).catch(() => {})
  }
}

function ideaLike() {
  const candidate = currentCandidate.value
  if (!candidate) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  ideaNext('right')
  // 1. 记录 collect 反馈（用于排除已看过的候选，后台静默）
  createIdeaFeedback({ candidate_id: candidate.id, action: 'collect' }).catch(() => {})
  // 2. 把灵感候选本身作为条目加入灵感知识库（与论文 like 逻辑完全一致）
  const paperData = {
    paper_id: `idea_${candidate.id}`,
    short_title: candidate.title,
    institution: candidate.strategy || '灵感',
    '📖标题': candidate.title,
    '🌐来源': '灵感推荐',
    '🛎️文章简介': {
      '🔸研究问题': candidate.goal || '',
      '🔸主要贡献': candidate.mechanism || '',
    },
    '📝重点思路': [] as string[],
    '🔎分析总结': [] as string[],
    '💡个人观点': candidate.risks || '',
  }
  trackKbAction('save', `idea_${candidate.id}`)
  addKbPaper(`idea_${candidate.id}`, paperData as any, null, 'inspiration')
    .then(async () => {
      await loadKbTree()
      // 3. 将关联的来源论文作为链接子项添加到此灵感条目下（后台静默）
      if (candidate.input_atom_ids?.length) {
        try {
          const atomResults = await Promise.all(
            candidate.input_atom_ids.slice(0, 10).map((aid) =>
              fetchIdeaAtom(aid).then((r) => r.atom.paper_id).catch(() => null),
            ),
          )
          const uniquePaperIds = [...new Set(atomResults.filter(Boolean) as string[])]
          for (const pid of uniquePaperIds) {
            await addNoteLink(`idea_${candidate.id}`, pid, `/papers/${pid}`, 'inspiration').catch(() => {})
          }
          await loadKbTree()
        } catch {}
      }
    })
    .catch(() => {})
  void engagement.record('collect', 'inspiration-idea-like', String(candidate.id))
}

function ideaUndo() {
  if (ideaHistory.value.length === 0) return
  const prevIdx = ideaHistory.value.pop()!
  ideaCurrentIndex.value = prevIdx
  ideaCardAnimClass.value = 'card-enter'
}

function ideaOpenDetail() {
  if (currentCandidate.value) {
    // 与点击左侧灵感涌现库的效果一致：内嵌展示 IdeaDetailPanel
    viewingIdeaId.value = currentCandidate.value.id
    collapseSidebarOnMobile()
  }
}

function ideaResetCards() {
  ideaCurrentIndex.value = 0
  ideaHistory.value = []
  ideaCardAnimClass.value = 'card-enter'
}

async function ideaRefresh() {
  if (selectedDate.value) {
    await loadIdeaDigest(selectedDate.value)
  }
}

// ==================== 侧边栏交互（知识库详情） ====================

// 从知识库点击论文 → 中间展示详情
const sidebarPaperId = ref<string | null>(null)

// 从知识库点击灵感条目 → 中间展示灵感详情面板
const viewingIdeaId = ref<number | null>(null)

// 笔记编辑
const editingNote = ref<{ id: number; paperId: string } | null>(null)
const inspirationContentLayoutRef = ref<InstanceType<typeof ContentLayout> | null>(null)
function getInspirationNoteEditor() {
  return inspirationContentLayoutRef.value?.getNoteEditor?.() ?? null
}

// PDF 查看
const viewingPdf = ref<{ paperId: string; filePath: string; title: string } | null>(null)
/** 我的论文：左侧 PDF + 右侧 Markdown 渲染 */
const viewingMd = ref<UserPaperViewMdPayload | null>(null)

const inspirationActiveUserPaperId = computed(() => viewingMd.value?.paperId ?? null)
const inspirationActiveViewMdKey = computed(() => {
  const v = viewingMd.value
  if (!v?.paperId || v.viewMode == null) return null
  return `${v.paperId}:${v.viewMode}`
})

// 对比分析
const comparingPaperIds = ref<string[] | null>(null)

// 查看已保存对比结果
const viewingCompareResultId = ref<number | null>(null)

// 深度研究
const researchPaperIds = ref<string[] | null>(null)
const researchPaperTitles = ref<Record<string, string>>({})
const researchScope = ref<string>('kb')

/** 任意详情面板打开时为 true，供右下角浮动按钮感知 */
const isInPanelView = computed(() =>
  editingNote.value !== null ||
  !!comparingPaperIds.value ||
  viewingCompareResultId.value !== null ||
  !!viewingPdf.value ||
  !!viewingMd.value ||
  !!sidebarPaperId.value ||
  !!researchPaperIds.value,
)

// 将面板视图状态同步到全局，供右下角浮动按钮感知
watch(isInPanelView, (v) => { globalChat.setPageInPanelView(v) }, { immediate: true })

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  const relPath = viewingPdf.value.filePath.replace(/^\/static\/kb_files\//, '')
  const fileUrl = `${API_ORIGIN}/static/kb_files/${relPath}`
  return `${viewerPath}?file=${encodeURIComponent(fileUrl)}&paperId=${encodeURIComponent(viewingPdf.value.paperId)}`
})

const pdfBareUrl = computed(() => {
  if (!viewingPdf.value) return ''
  const relPath = viewingPdf.value.filePath.replace(/^\/static\/kb_files\//, '')
  return `${API_ORIGIN}/static/kb_files/${relPath}`
})

const viewingMdPdfIframeSrc = computed(() => {
  if (!viewingMd.value?.pdfUrl) return ''
  const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  return `${viewerPath}?file=${encodeURIComponent(viewingMd.value.pdfUrl)}&paperId=${encodeURIComponent(viewingMd.value.paperId)}`
})

function inspireArxivPdfUrl(paperId: string): string {
  return `${API_ORIGIN}/api/papers/${paperId}/pdf`
}

function inspirePdfJsSrc(pdfUrl: string, paperId: string): string {
  const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  return `${viewerPath}?file=${encodeURIComponent(pdfUrl)}&paperId=${encodeURIComponent(paperId)}`
}

const inspireNoteLayoutKey = computed(() =>
  editingNote.value ? `inspire-note-${editingNote.value.id}-${editingNote.value.paperId}` : 'inspire-note',
)

const inspireNotePanelConfigs = computed<PanelConfigItem[]>(() => {
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

const inspireNoteDefaultLayout = computed<LayoutState>(() => ({
  mode: 'split',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.NOTE_EDITOR,
  splitRatio: 50,
}))

const inspireNoteContext = computed<ContentLayoutContext>(() => {
  if (!editingNote.value) return {}
  const pid = editingNote.value.paperId
  const arxivOk = !pid.startsWith('up_')
  const pdfUrl = arxivOk ? inspireArxivPdfUrl(pid) : undefined
  return {
    paperId: pid,
    noteEditor: { id: editingNote.value.id, paperId: pid },
    pdfUrl,
    pdfViewerSrc: pdfUrl ? inspirePdfJsSrc(pdfUrl, pid) : '',
    pdfTitle: `${pid}.pdf`,
  }
})

const inspireMdKey = computed(
  () =>
    viewingMd.value
      ? `inspire-md-${viewingMd.value.paperId}-${viewingMd.value.viewMode ?? 'default'}`
      : 'inspire-md',
)

const inspireMdPanels = computed<PanelConfigItem[]>(() => {
  const pid = viewingMd.value?.paperId
  const vm = viewingMd.value?.viewMode
  const rows: PanelConfigItem[] = [
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

const inspireMdDefaultLayout = computed<LayoutState>(() => {
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

const inspireMdContext = computed<ContentLayoutContext>(() => ({
  pdfViewerSrc: viewingMdPdfIframeSrc.value,
  pdfUrl: viewingMd.value?.pdfUrl,
  pdfTitle: viewingMd.value?.title,
  mdUrl: viewingMd.value?.mdUrl,
  mdMineruUrl: viewingMd.value?.mineruUrl,
  mdZhUrl: viewingMd.value?.zhUrl,
  mdBilingualUrl: viewingMd.value?.bilingualUrl,
  paperId: viewingMd.value?.paperId,
  paperViewScope: viewingMd.value?.scope,
}))

const inspireIdeaKey = computed(
  () => `inspire-idea-${viewingIdeaId.value ?? 0}`,
)

const inspireIdeaPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.IDEA_DETAIL, label: '灵感详情', icon: '💡', available: true },
])

const inspireIdeaDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.IDEA_DETAIL,
  rightPanel: PANEL_IDS.IDEA_DETAIL,
  splitRatio: 60,
}))

const inspireIdeaContext = computed<ContentLayoutContext>(() => ({
  ideaCandidateId: viewingIdeaId.value ?? undefined,
}))

const inspireSidebarKey = computed(() =>
  sidebarPaperId.value ? `inspire-kb-${sidebarPaperId.value}` : 'inspire-kb',
)

const inspireSidebarPanels = computed<PanelConfigItem[]>(() => {
  if (!sidebarPaperId.value) return []
  const pid = sidebarPaperId.value
  const arxivOk = !pid.startsWith('up_')
  return [
    { id: PANEL_IDS.PAPER_DETAIL, label: '论文详情', icon: '📄', available: true },
    { id: PANEL_IDS.PDF_VIEWER, label: 'PDF', icon: '📕', available: arxivOk },
    { id: PANEL_IDS.AI_CHAT, label: 'AI 问答', icon: '💬', available: !!isAuthenticated.value },
  ]
})

const inspireSidebarDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.PAPER_DETAIL,
  rightPanel: PANEL_IDS.PDF_VIEWER,
  splitRatio: 60,
}))

const inspireSidebarContext = computed<ContentLayoutContext>(() => {
  if (!sidebarPaperId.value) return {}
  const pid = sidebarPaperId.value
  const arxivOk = !pid.startsWith('up_')
  const pdfUrl = arxivOk ? inspireArxivPdfUrl(pid) : undefined
  return {
    paperId: pid,
    pdfUrl,
    pdfViewerSrc: pdfUrl ? inspirePdfJsSrc(pdfUrl, pid) : '',
    pdfTitle: `${pid}.pdf`,
  }
})

// 构建 paper_id → short_title 映射，供 ComparePanel 显示标签
const comparePaperTitles = computed(() => {
  if (!comparingPaperIds.value) return {}
  const map: Record<string, string> = {}
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

const inspireCompareLayoutKey = computed(() =>
  comparingPaperIds.value?.length
    ? `inspire-cmp-${comparingPaperIds.value.join(',')}`
    : 'inspire-cmp',
)

const inspireComparePanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.COMPARE, label: '对比分析', icon: '⚖️', available: true },
])

const inspireCompareDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.COMPARE,
  rightPanel: PANEL_IDS.COMPARE,
  splitRatio: 60,
}))

const inspireCompareContext = computed<ContentLayoutContext>(() => ({
  comparingPaperIds: comparingPaperIds.value || [],
  compareScope: 'inspiration',
  comparePaperTitles: comparePaperTitles.value,
}))

const inspireCompareResultKey = computed(
  () => `inspire-cmpres-${viewingCompareResultId.value ?? 0}`,
)

const inspireCompareResultPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.COMPARE_RESULT, label: '对比结果', icon: '📊', available: true },
])

const inspireCompareResultDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.COMPARE_RESULT,
  rightPanel: PANEL_IDS.COMPARE_RESULT,
  splitRatio: 60,
}))

const inspireCompareResultContext = computed<ContentLayoutContext>(() => ({
  compareResultId: viewingCompareResultId.value ?? undefined,
  comparePaperTitles: comparePaperTitles.value,
}))

const inspireResearchLayoutKey = computed(() =>
  researchPaperIds.value?.length
    ? `inspire-research-${researchPaperIds.value.join(',')}`
    : 'inspire-research',
)

const inspireResearchPanels = computed<PanelConfigItem[]>(() => [
  { id: PANEL_IDS.RESEARCH, label: '深度研究', icon: '🔍', available: true },
])

const inspireResearchDefaultLayout = computed<LayoutState>(() => ({
  mode: 'single',
  leftPanel: PANEL_IDS.RESEARCH,
  rightPanel: PANEL_IDS.RESEARCH,
  splitRatio: 60,
}))

const inspireResearchInitialSessionId = ref<number | null>(null)

const inspireResearchContext = computed<ContentLayoutContext>(() => ({
  researchPaperIds: researchPaperIds.value || [],
  researchPaperTitles: researchPaperTitles.value,
  researchScope: researchScope.value,
  researchInitialSessionId: inspireResearchInitialSessionId.value,
}))

function handleCompare(paperIds: string[]) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  paperInspirationPaperId.value = null
  comparingPaperIds.value = paperIds
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'inspiration-compare', paperIds[0] || '')
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
  researchPaperIds.value = null
  paperInspirationPaperId.value = null
  viewingCompareResultId.value = resultId
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'inspiration-compare-result', String(resultId))
}

function closeCompareResult() {
  viewingCompareResultId.value = null
}

function handleResearch(paperIds: string[], paperTitles: Record<string, string>, scope?: string) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  paperInspirationPaperId.value = null
  inspireResearchInitialSessionId.value = null
  researchPaperIds.value = paperIds
  researchPaperTitles.value = paperTitles
  researchScope.value = scope ?? 'kb'
  collapseSidebarOnMobile()
  void engagement.record('analyze', 'inspiration-research', paperIds[0] || '')
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
    paperInspirationPaperId.value = null
    researchPaperIds.value = session.paper_ids
    researchPaperTitles.value = {}
    researchScope.value = 'kb'
    inspireResearchInitialSessionId.value = sessionId
    collapseSidebarOnMobile()
    void engagement.record('analyze', 'inspiration-research-session', String(sessionId))
  } catch {
    // silently ignore
  }
}

function closeResearch() {
  researchPaperIds.value = null
  sidebarRef.value?.switchToPapersTab()
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

async function openPaperFromSidebar(paperId: string) {
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  paperInspirationPaperId.value = null
  if (editingNote.value && getInspirationNoteEditor()) {
    const isEmpty = getInspirationNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
      editingNote.value = null
    } else {
      try { await getInspirationNoteEditor().flushSave() } catch {}
      editingNote.value = null
    }
  }

  // 若是灵感条目（paper_id = idea_XXX），展示灵感详情面板
  if (paperId.startsWith('idea_')) {
    const ideaId = parseInt(paperId.replace('idea_', ''), 10)
    if (!isNaN(ideaId)) {
      viewingIdeaId.value = ideaId
      sidebarPaperId.value = null
      globalChat.clearBrowsingContext()
      collapseSidebarOnMobile()
      return
    }
  }

  sidebarPaperId.value = paperId
  viewingIdeaId.value = null
  collapseSidebarOnMobile()
  void engagement.record('view', 'inspiration-open-paper', paperId)

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
  paperInspirationPaperId.value = null
  if (editingNote.value && getInspirationNoteEditor()) {
    const isEmpty = getInspirationNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
      editingNote.value = null
      sidebarPaperId.value = payload.paperId
      collapseSidebarOnMobile()
      return
    } else {
      try { await getInspirationNoteEditor().flushSave() } catch {}
    }
  }
  editingNote.value = payload
  collapseSidebarOnMobile()
}

function openPdfFromSidebar(payload: { paperId: string; filePath: string; title: string }) {
  editingNote.value = null
  sidebarPaperId.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  viewingMd.value = null
  paperInspirationPaperId.value = null
  viewingPdf.value = payload
  collapseSidebarOnMobile()
  void engagement.record('view', 'inspiration-open-pdf', payload.paperId)
}

function openUserPaperViewMd(payload: UserPaperViewMdPayload) {
  try {
    const k = `${STORAGE_PREFIX}inspire-md-${payload.paperId}-${payload.viewMode ?? 'default'}`
    localStorage.removeItem(k)
  } catch {
    /* ignore */
  }
  editingNote.value = null
  sidebarPaperId.value = null
  viewingIdeaId.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  paperInspirationPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = payload
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
}

async function handleBackToInspiration() {
  if (editingNote.value && getInspirationNoteEditor()) {
    const isEmpty = getInspirationNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
    } else {
      try { await getInspirationNoteEditor().flushSave() } catch {}
    }
    editingNote.value = null
    await loadKbTree()
    sidebarRef.value?.refreshAllExpandedNotes()
  }
  sidebarPaperId.value = null
  viewingIdeaId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  researchPaperIds.value = null
  globalChat.clearBrowsingContext()
}

async function handleIdeaOpenPaper(pid: string) {
  sidebarPaperId.value = pid
  viewingIdeaId.value = null
  paperInspirationPaperId.value = null
  void (async () => {
    try {
      const d = await fetchPaperDetail(pid)
      if (d?.summary) {
        globalChat.setBrowsingContext({
          paperId: pid,
          title: d.summary.short_title || d.summary['📖标题'] || pid,
          summary: d.summary,
          source: 'kb-paper',
        })
      } else {
        globalChat.setBrowsingContext({ paperId: pid, title: pid, source: 'kb-paper' })
      }
    } catch {
      globalChat.setBrowsingContext({ paperId: pid, title: pid, source: 'kb-paper' })
    }
    globalChat.applyBrowsingToPaperContext()
  })()
}

async function closeNoteEditor() {
  editingNote.value = null
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

async function handleNoteSaved(payload: { id: number; title: string }) {
  if (editingNote.value) {
    sidebarRef.value?.updateNoteTitle(editingNote.value.paperId, payload.id, payload.title)
  }
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

function onDateChange(event: Event) {
  selectedDate.value = (event.target as HTMLSelectElement).value
}


// 路由离开时自动保存笔记
onBeforeRouteLeave(async (_to, _from, next) => {
  if (editingNote.value && getInspirationNoteEditor()) {
    const isEmpty = getInspirationNoteEditor().isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
    } else {
      try { await getInspirationNoteEditor().flushSave() } catch {}
    }
    editingNote.value = null
  }
  next()
})
</script>

<template>
  <SidebarPageLayout v-model:show-sidebar="showSidebar">

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
            scope="inspiration"
            title="灵感涌现"
            empty-title="收藏灵感"
            empty-desc="当你收藏灵感中关联的论文后，它们会在这里出现。"
            third-tab="paper-inspiration"
            @open-paper="openPaperFromSidebar"
            @open-note="openNoteFromSidebar"
            @open-pdf="openPdfFromSidebar"
            @compare="handleCompare"
            @research="handleResearch"
            @refresh="loadKbTree"
            @open-compare-result="openCompareResult"
            @refresh-compare="loadCompareTree"
            @toggle-sidebar="showSidebar = false"
            @view-md="openUserPaperViewMd"
            @paper-inspiration="handlePaperInspiration"
            @paper-inspiration-detail="handlePaperInspirationDetail"
            @tab-changed="(tab: string) => sidebarActiveTab = tab as any"
            @open-research-session="handleOpenResearchSession"
            @update-read-status="markPaperReadStatus"
            :active-user-paper-id="inspirationActiveUserPaperId"
            :active-view-md-key="inspirationActiveViewMdKey"
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
          <div class="p-4 border-b border-border">
            <div class="bg-brand-gradient rounded-xl p-3 mb-3">
              <div class="flex items-center justify-between mb-1">
                <div class="text-xs font-bold text-white/80">灵感日报</div>
                <!-- Collapse button -->
                <button
                  class="w-10 h-10 flex items-center justify-center rounded text-white/60 hover:text-white hover:bg-white/15 transition-colors cursor-pointer"
                  title="收起侧边栏"
                  @click="showSidebar = false"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
                  </svg>
                </button>
              </div>
              <!-- Current date display (read-only for guests) -->
              <div class="flex items-center gap-2 px-2 py-1.5">
                <svg class="w-3.5 h-3.5 shrink-0 text-white/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span class="text-sm font-medium text-white">{{ selectedDate || '—' }}</span>
              </div>
            </div>
          </div>
          <div class="flex-1 p-4 flex flex-col items-center justify-center text-center">
            <div class="w-14 h-14 rounded-xl bg-bg-elevated border border-border mb-3 flex items-center justify-center text-2xl">
              🔒
            </div>
            <h3 class="text-base font-semibold text-text-primary mb-2">登录后浏览灵感推荐</h3>
            <p class="text-xs text-text-muted mb-4 leading-relaxed">
              灵感推荐、收藏和管理功能需要先登录
            </p>
            <button
              class="px-4 py-2 rounded-full bg-brand-gradient text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
            >
              去登录
            </button>
          </div>
        </aside>
      </Transition>
    </template>

    </template>
    <!-- End sidebar slot -->

    <!-- ==================== 主内容区 ==================== -->


      <ContentLayout
        v-if="editingNote !== null"
        ref="inspirationContentLayoutRef"
        class="flex-1 min-h-0 border-l border-border mt-3"
        :context-key="inspireNoteLayoutKey"
        :panel-configs="inspireNotePanelConfigs"
        :default-layout="inspireNoteDefaultLayout"
        :context="inspireNoteContext"
        @close-note="closeNoteEditor"
        @note-saved="handleNoteSaved"
      />

      <!-- ==================== 灵感详情面板（优先级最高：论文灵感/知识库均可触发）==================== -->
      <!-- 放在 paperInspirationPaperId 之前，以便从论文灵感点「详情」后关闭可自然回到卡片视图 -->
      <ContentLayout
        v-else-if="viewingIdeaId !== null"
        class="flex-1 min-h-0 mt-3"
        :context-key="inspireIdeaKey"
        :panel-configs="inspireIdeaPanels"
        :default-layout="inspireIdeaDefaultLayout"
        :context="inspireIdeaContext"
        @close-idea="viewingIdeaId = null"
        @idea-open-paper="handleIdeaOpenPaper"
      />

      <!-- ==================== 论文灵感候选卡片视图 ==================== -->
      <div
        v-else-if="paperInspirationPaperId"
        class="flex-1 flex flex-col overflow-hidden min-h-0"
      >
        <!-- 顶部栏 -->
        <div class="shrink-0 flex items-center justify-between px-4 py-2 gap-3">
          <div class="flex items-center gap-2 min-w-0">
            <svg class="w-4 h-4 text-[#fd267a] shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
            </svg>
            <span class="text-sm font-semibold text-text-primary truncate">{{ paperInspirationTitle }}</span>
          </div>
          <button
            class="shrink-0 px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="paperInspirationPaperId = null"
          >
            关闭
          </button>
        </div>

        <!-- 主内容区：复用灵感涌现卡片区布局 -->
        <div class="flex-1 flex flex-col items-center justify-center relative min-h-0">

          <!-- 加载中 -->
          <LoadingSpinner v-if="paperInspirationLoading" text="正在生成灵感候选..." />

          <!-- 出错 -->
          <ErrorState
            v-else-if="paperInspirationError"
            :message="paperInspirationError"
            @retry="handlePaperInspiration(paperInspirationPaperId!, paperInspirationTitle, true)"
          />

          <!-- 全部浏览完 -->
          <div v-else-if="paperAllSwiped" class="flex flex-col items-center gap-4 text-center px-8">
            <div class="text-5xl mb-2">🎉</div>
            <h2 class="text-xl font-bold text-text-primary">本文灵感已全部浏览</h2>
            <p class="text-sm text-text-muted">共 {{ paperCandidates.length }} 条灵感候选</p>
            <div class="flex items-center gap-3 mt-2">
              <button
                class="px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
                @click="paperCandidateReset"
              >
                重新浏览
              </button>
              <button
                class="px-4 py-2.5 rounded-full border border-border bg-transparent text-sm text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
                @click="handlePaperInspiration(paperInspirationPaperId!, paperInspirationTitle, true)"
              >
                重新生成
              </button>
              <button
                class="px-4 py-2.5 rounded-full border border-border bg-transparent text-sm text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
                @click="router.push('/workbench')"
              >
                前往工作台
              </button>
            </div>
          </div>

          <!-- 灵感候选卡片 -->
          <template v-else-if="currentPaperCandidate">
            <!-- 计数 -->
            <div class="absolute top-4 left-1/2 -translate-x-1/2 text-xs text-text-muted z-20">
              {{ paperCandidateIndex + 1 }} / {{ paperCandidates.length }}
            </div>

            <!-- 卡片 -->
            <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(320px, calc(100dvh - 210px), 620px)">
              <IdeaCard
                :key="currentPaperCandidate.id"
                :candidate="currentPaperCandidate"
                :anim-class="paperCandidateAnimClass"
              />
            </div>

            <!-- 操作按钮 -->
            <ActionButtons
              @undo="paperCandidateIndex > 0 ? paperCandidateIndex-- : undefined"
              @skip="paperCandidateSkip"
              @like="paperCandidateLike"
              @detail="paperCandidateOpenDetail"
              @superlike="paperCandidateOpenDetail"
            />
          </template>

          <!-- 暂无候选 -->
          <div v-else-if="!paperInspirationLoading" class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
            <div class="relative w-28 h-28 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse" />
              <span class="text-6xl relative z-10">💡</span>
            </div>
            <h2 class="text-lg font-bold text-text-primary">暂无灵感候选</h2>
            <p class="text-sm text-text-secondary leading-relaxed">
              请确保论文已处理完成，并在「灵感生成」中配置好 LLM 参数后重试。
            </p>
            <button
              class="mt-2 px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="handlePaperInspiration(paperInspirationPaperId!, paperInspirationTitle, true)"
            >
              重新生成
            </button>
          </div>
        </div>
      </div>

      <ContentLayout
        v-else-if="researchPaperIds"
        class="flex-1 min-h-0 mt-3"
        :context-key="inspireResearchLayoutKey"
        :panel-configs="inspireResearchPanels"
        :default-layout="inspireResearchDefaultLayout"
        :context="inspireResearchContext"
        @close-research="closeResearch"
        @remove-research-paper="removeResearchPaper"
      />

      <ContentLayout
        v-else-if="comparingPaperIds"
        class="flex-1 min-h-0 mt-3"
        :context-key="inspireCompareLayoutKey"
        :panel-configs="inspireComparePanels"
        :default-layout="inspireCompareDefaultLayout"
        :context="inspireCompareContext"
        @close-compare="closeCompare"
        @compare-saved="handleCompareSaved"
      />

      <ContentLayout
        v-else-if="viewingCompareResultId !== null"
        class="flex-1 min-h-0 mt-3"
        :context-key="inspireCompareResultKey"
        :panel-configs="inspireCompareResultPanels"
        :default-layout="inspireCompareResultDefaultLayout"
        :context="inspireCompareResultContext"
        @close-compare-result="closeCompareResult"
      />

      <div
        v-else-if="viewingPdf"
        class="flex-1 flex flex-col overflow-hidden mt-3 px-2 sm:px-4 pb-4 min-h-0"
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

      <div
        v-else-if="viewingMd"
        class="flex-1 flex flex-col overflow-hidden mt-3 px-2 sm:px-4 pb-4 min-h-0"
      >
        <div class="shrink-0 flex items-center justify-between rounded-t-xl border border-border border-b-0 bg-bg-card px-4 py-2">
          <div class="text-sm text-text-secondary truncate pr-4">{{ viewingMd.title }}</div>
          <button
            class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="closeViewingMd"
          >
            关闭
          </button>
        </div>
        <ContentLayout
          :key="inspireMdKey"
          class="flex-1 min-h-0 rounded-b-xl border border-border border-t-0 overflow-hidden"
          :context-key="inspireMdKey"
          :panel-configs="inspireMdPanels"
          :default-layout="inspireMdDefaultLayout"
          :context="inspireMdContext"
        />
      </div>

      <ContentLayout
        v-else-if="sidebarPaperId"
        class="flex-1 min-h-0 mt-3"
        :context-key="inspireSidebarKey"
        :panel-configs="inspireSidebarPanels"
        :default-layout="inspireSidebarDefaultLayout"
        :context="inspireSidebarContext"
      />

      <!-- ==================== 论文灵感 Tab 激活但未选论文 ==================== -->
      <div
        v-else-if="sidebarActiveTab === 'paper-inspiration'"
        class="flex-1 flex flex-col items-center justify-center relative"
      >
        <div class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
          <div class="relative w-28 h-28 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/15 to-[#ff6036]/15" />
            <span class="text-6xl relative z-10">💡</span>
          </div>
          <h2 class="text-lg font-bold text-text-primary">论文灵感</h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            从左侧选择一篇已处理完成的论文，AI 将基于其内容为你生成研究灵感方向。
          </p>
        </div>
      </div>

      <!-- ==================== 灵感推荐主界面（刷卡模式）==================== -->
      <div v-else class="flex-1 flex flex-col items-center justify-center relative">


        <!-- 未登录 -->
        <div v-if="!isAuthenticated" class="flex flex-col items-center gap-4 text-center px-8">
          <div class="w-16 h-16 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-3xl">🔒</div>
          <h3 class="text-base font-semibold text-text-primary">登录后浏览灵感推荐</h3>
          <p class="text-xs text-text-muted">灵感推荐、收藏等功能需要登录</p>
          <button
            class="px-5 py-2 rounded-full bg-brand-gradient text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
          >
            去登录
          </button>
        </div>

        <!-- 加载中 -->
        <LoadingSpinner v-else-if="ideaLoading" text="加载灵感中..." />

        <!-- 加载出错 -->
        <ErrorState v-else-if="ideaError" :message="ideaError" :type="ideaErrorType" @retry="ideaRefresh" />

        <!-- 配额超限 -->
        <div
          v-else-if="isIdeaQuotaExceeded && isIdeaActuallyLimited && ideaQuotaExceededMessage"
          class="flex flex-col items-center justify-center gap-4 text-center px-8 max-w-sm"
        >
          <div class="text-5xl mb-1">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">灵感已达上限</h2>
          <p class="text-sm text-text-secondary">{{ ideaQuotaExceededMessage }}</p>
          <UpgradePrompt feature="idea_gen" class="w-full" />
        </div>

        <!-- 全部浏览完 -->
        <EmptyState
          v-else-if="ideaAllSwiped"
          icon="🎉"
          title="今日灵感已全部浏览"
          :description="`共浏览 ${ideaCandidates.length} 条灵感`"
        >
          <button
            class="px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="ideaResetCards"
          >重新浏览</button>
          <button
            class="px-4 py-2.5 rounded-full border border-border bg-transparent text-sm text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
            @click="router.push('/idea')"
          >🧪 前往工作台</button>
        </EmptyState>

        <!-- 灵感卡片 -->
        <template v-else-if="currentCandidate">
          <!-- 计数 -->
          <div class="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5">
            <span
              class="text-xs tabular-nums px-2.5 py-0.5 rounded-full backdrop-blur-sm"
              :class="isIdeaActuallyLimited
                ? 'text-amber-400 bg-amber-500/15 border border-amber-500/25'
                : 'text-text-muted bg-bg-card/70 border border-border/50'"
            >
              {{ ideaCurrentIndex + 1 }} / {{ ideaCandidates.length }}
              <template v-if="isIdeaActuallyLimited && ideaTotalAvailable > ideaCandidates.length">
                <span class="opacity-70">· 共 {{ ideaTotalAvailable }} 条</span>
                <span class="ml-0.5 text-[10px]">🔒</span>
              </template>
            </span>
          </div>

          <!-- 卡片 -->
          <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(320px, calc(100dvh - 210px), 620px)">
            <IdeaCard
              :key="currentCandidate.id"
              :candidate="currentCandidate"
              :anim-class="ideaCardAnimClass"
            />
          </div>

          <!-- 操作按钮 -->
          <ActionButtons
            @undo="ideaUndo"
            @skip="ideaSkip"
            @like="ideaLike"
            @detail="ideaOpenDetail"
            @superlike="ideaOpenDetail"
          />
        </template>

        <!-- 暂无灵感 -->
        <div v-else-if="!ideaLoading" class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
          <div class="relative w-28 h-28 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse" />
            <span class="text-6xl relative z-10">💡</span>
          </div>
          <h2 class="text-lg font-bold text-text-primary">
            {{ selectedDate ? `${selectedDate} 暂无灵感` : '还没有灵感' }}
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            灵感由管理员从当日论文中生成。请先确认已选择正确的日期，或等待管理员运行流水线。
          </p>
          <button
            class="mt-2 px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2 shadow-lg shadow-[#fd267a]/20"
            @click="ideaRefresh"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
            </svg>
            刷新
          </button>
        </div>
      </div>
  </SidebarPageLayout>
</template>

<style scoped>
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
</style>
