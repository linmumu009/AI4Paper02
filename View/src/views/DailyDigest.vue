<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import DatePill from '../components/DatePill.vue'
import PaperCard from '../components/PaperCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import ContentLayout from '../components/ContentLayout.vue'
import type { ContentLayoutContext } from '../components/ContentLayout.vue'
import PdfPanel from '../components/panels/PdfPanel.vue'
import UserPaperUploadDialog from '../components/UserPaperUploadDialog.vue'
import { PANEL_IDS, STORAGE_PREFIX, type LayoutState, type PanelConfigItem } from '../composables/usePanelLayout'
import { fetchDates, fetchDigest, addKbPaper, deleteNote, dismissPaper, fetchUserPapers, fetchUserPaperDetail, fetchPaperDetail, processUserPaper, userPaperStepLabel, API_ORIGIN } from '../api'
import { openExternal } from '../utils/openExternal'
import type { KbScope } from '../api'
import type { PaperSummary, UserPaper, UserPaperViewMdPayload } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import { useGlobalChat } from '../composables/useGlobalChat'
import { useKbSidebarState } from '../composables/useKbSidebarState'

const router = useRouter()
const route = useRoute()
const globalChat = useGlobalChat()

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
const currentIndex = ref(0)
const cardAnimClass = ref('card-enter')
const history = ref<number[]>([])

// Knowledge base + sidebar shared state
const { kbTree, activeFolderId, compareTree, showSidebar, loadKbTree, loadCompareTree, collapseSidebarOnMobile } = useKbSidebarState()

const currentPaper = computed(() => papers.value[currentIndex.value] ?? null)
const remaining = computed(() => papers.value.length - currentIndex.value)
const allSwiped = computed(() => papers.value.length > 0 && currentIndex.value >= papers.value.length)
const isActuallyLimited = computed(() => {
  if (quotaLimit.value === null) return false
  return totalAvailable.value > papers.value.length
})

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

// Load dates
onMounted(async () => {
  await ensureAuthInitialized()
  await loadDates()

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
  }

  // Handle ?tab=mypapers redirect from /my-papers
  if (route.query.tab === 'mypapers' && isAuthenticated.value) {
    showSidebar.value = true
    sidebarRef.value?.switchToMyPapersTab?.()
  }
})

// Notice shown when pipeline ran but produced 0 papers
const dateNotice = ref<{ type: string; message: string } | null>(null)

async function loadDigestForDate(date: string, fallbackAuthed = isAuthenticated.value) {
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  dateNotice.value = null
  try {
    const res = await fetchDigest(date)
    const fetchedPapers = Array.isArray(res.papers) ? res.papers : []
    papers.value = fetchedPapers
    totalAvailable.value = res.total_available ?? fetchedPapers.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (fallbackAuthed ? currentTier.value : 'anonymous')
    dateNotice.value = res.notice ?? null
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
    if (import.meta.env.DEV) {
      console.debug('[DailyDigest] digest loaded', {
        date,
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
  } finally {
    loading.value = false
  }
}

// Load papers on date change
watch(selectedDate, async (date) => {
  if (!date) return
  await loadDigestForDate(date)
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
    } else {
      kbTree.value = { folders: [], papers: [] }
      compareTree.value = null
      activeFolderId.value = null
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
  history.value.push(currentIndex.value)
  setTimeout(() => {
    currentIndex.value++
    cardAnimClass.value = 'card-enter'
  }, 300)
}

function skip() {
  const paper = currentPaper.value
  next('left')
  // 已登录用户：后台静默标记为"不感兴趣"，下次加载时不再展示
  if (paper && isAuthenticated.value) {
    dismissPaper(paper.paper_id).catch(() => {})
  }
}

function like() {
  const paper = currentPaper.value
  if (!paper) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  // Animate card immediately for snappy UX
  next('right')
  // Fire API in background — don't block the animation
  addKbPaper(paper.paper_id, paper, activeFolderId.value)
    .then(() => loadKbTree())
    .catch(() => {})
}

function undo() {
  if (history.value.length === 0) return
  const prevIdx = history.value.pop()!
  currentIndex.value = prevIdx
  cardAnimClass.value = 'card-enter'
}

function openDetail() {
  if (currentPaper.value) {
    sidebarPaperId.value = currentPaper.value.paper_id
    collapseSidebarOnMobile()
  }
}

function openPdf() {
  if (currentPaper.value) {
    openExternal(`https://arxiv.org/pdf/${currentPaper.value.paper_id}`)
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
const showUploadDialog = ref(false)

async function loadMyPapersCenter() {
  myPapersCenterLoading.value = true
  try {
    const res = await fetchUserPapers({ limit: 200 })
    myPapersCenter.value = res.papers
    // 若有处理中的论文，启动轮询刷新
    const hasProcessing = res.papers.some(
      p => p.process_status === 'processing' || p.process_status === 'pending'
    )
    if (hasProcessing) {
      _startMyPapersCenterPoll()
    } else {
      _stopMyPapersCenterPoll()
    }
  } catch {}
  finally {
    myPapersCenterLoading.value = false
  }
}

function _startMyPapersCenterPoll() {
  if (_myPapersCenterPollTimer) return
  _myPapersCenterPollTimer = setInterval(async () => {
    try {
      const res = await fetchUserPapers({ limit: 200 })
      myPapersCenter.value = res.papers
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

function handleTabChanged(tab: string) {
  if (tab === 'mypapers') {
    myPapersMode.value = true
    // 切换到我的论文 Tab 时，清空当前推荐卡片相关状态
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
  } else {
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
  } catch {}
  finally {
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
}

function _stopUserPaperPoll() {
  if (_userPaperPollTimer) {
    clearInterval(_userPaperPollTimer)
    _userPaperPollTimer = null
  }
}

async function handleRetryUserPaper() {
  if (!viewingUserPaperId.value) return
  try {
    await processUserPaper(viewingUserPaperId.value)
    await _loadUserPaper(viewingUserPaperId.value)
  } catch {}
}

async function handleUploadDialogUploaded(paperId: string) {
  showUploadDialog.value = false
  await openUserPaper(paperId)
  sidebarRef.value?.refreshMyPapers()
  // 也刷新中间区域的列表（如果正处于 myPapersMode）
  if (myPapersMode.value) await loadMyPapersCenter()
}

onBeforeUnmount(() => {
  _stopUserPaperPoll()
  _stopMyPapersCenterPoll()
})

// 笔记编辑器组件引用，便于外部触发保存/检查是否为空
/** 带笔记编辑的 ContentLayout，用于切换前 flush */
const digestContentLayoutRef = ref<InstanceType<typeof ContentLayout> | null>(null)

function getDigestNoteEditor() {
  return digestContentLayoutRef.value?.getNoteEditor?.() ?? null
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
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingMd.value = null
  viewingCompareResultId.value = null
  comparingPaperIds.value = paperIds
  comparingResultIds.value = resultIds ?? []
  compareScope.value = (scope as KbScope) ?? 'kb'
  globalChat.clearBrowsingContext()
  collapseSidebarOnMobile()
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
}

function closeCompareResult() {
  viewingCompareResultId.value = null
}

async function openPaperFromSidebar(paperId: string) {
  viewingPdf.value = null
  viewingMd.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
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
  editingNote.value = null
  sidebarPaperId.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  viewingMd.value = null
  viewingPdf.value = payload
  globalChat.setBrowsingContext({
    paperId: payload.paperId,
    title: payload.title,
    source: 'kb-paper',
  })
  globalChat.applyBrowsingToPaperContext()
  collapseSidebarOnMobile()
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

function digestArxivPdfUrl(paperId: string): string {
  return `${API_ORIGIN}/api/papers/${paperId}/pdf`
}

function digestPdfJsSrc(pdfUrl: string, paperId: string): string {
  const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  return `${viewerPath}?file=${encodeURIComponent(pdfUrl)}&paperId=${encodeURIComponent(paperId)}`
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
  const pdfUrl = arxivOk ? digestArxivPdfUrl(pid) : (kbPaper?.pdf_static_url ? `${API_ORIGIN}${kbPaper.pdf_static_url}` : undefined)
  const mineruUrl = kbPaper?.mineru_static_url ? `${API_ORIGIN}${kbPaper.mineru_static_url}` : undefined
  const zhUrl = kbPaper?.zh_static_url ? `${API_ORIGIN}${kbPaper.zh_static_url}` : undefined
  const bilingualUrl = kbPaper?.bilingual_static_url ? `${API_ORIGIN}${kbPaper.bilingual_static_url}` : undefined
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
  const mineruUrl = p.mineru_static_url ? `${API_ORIGIN}${p.mineru_static_url}` : undefined
  const zhUrl = p.zh_static_url ? `${API_ORIGIN}${p.zh_static_url}` : undefined
  const bilingualUrl = p.bilingual_static_url ? `${API_ORIGIN}${p.bilingual_static_url}` : undefined
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
  }
})

// 全局“回到推荐”按钮事件处理：应用自动保存/删除规则，并回到推荐卡片视图
async function handleGoToDigestClick() {
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
  viewingUserPaperId.value = null
  viewingUserPaper.value = null
  _stopUserPaperPoll()
  _stopMyPapersCenterPoll()
  globalChat.clearBrowsingContext()
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

const STEP_ORDER = ['pdf_prepare', 'pdf_download', 'pdf_extract', 'pdf_info', 'paper_summary', 'summary_limit', 'paper_assets', 'done']

function isStepDone(step: string, currentStep: string): boolean {
  const currentIdx = STEP_ORDER.indexOf(currentStep)
  const stepIdx = STEP_ORDER.indexOf(step)
  return stepIdx !== -1 && currentIdx !== -1 && stepIdx < currentIdx
}

function isStepCurrent(step: string, currentStep: string): boolean {
  if (currentStep === step) return true
  if (step === 'pdf_prepare' && (currentStep === 'pdf_download' || currentStep === 'pdf_extract')) return true
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
  editingNote.value !== null ||
  !!comparingPaperIds.value ||
  viewingCompareResultId.value !== null ||
  !!viewingPdf.value ||
  !!viewingMd.value ||
  !!sidebarPaperId.value ||
  myPapersMode.value ||
  !!viewingUserPaperId.value,
)

// 将面板视图状态同步到全局，供右下角浮动按钮感知
watch(isInPanelView, (v) => { globalChat.setDigestInPanelView(v) }, { immediate: true })

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
  <div class="h-full flex relative">

    <!-- Sidebar overlay backdrop (mobile only, when sidebar is open) -->
    <Transition name="fade">
      <div
        v-if="showSidebar"
        class="fixed inset-0 z-20 bg-black/60 lg:hidden"
        @click="showSidebar = false"
      />
    </Transition>

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
            @open-paper="openPaperFromSidebar"
            @open-note="openNoteFromSidebar"
            @open-pdf="openPdfFromSidebar"
            @compare="handleCompare"
            @refresh="loadKbTree"
            @open-compare-result="openCompareResult"
            @refresh-compare="loadCompareTree"
            @toggle-sidebar="showSidebar = false"
            @open-user-paper="openUserPaper"
            @open-upload-dialog="showUploadDialog = true"
            @tab-changed="handleTabChanged"
            @view-md="openUserPaperViewMd"
            :active-user-paper-id="sidebarActiveUserPaperId"
            :active-view-md-key="sidebarActiveViewMdKey"
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
            'z-30 w-[80vw] max-w-[320px] lg:w-72 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300 ease-in-out relative',
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

    <!-- Universal "open sidebar" button — visible whenever sidebar is collapsed -->
    <Transition name="fade">
      <button
        v-if="!showSidebar"
        class="fixed top-[100px] left-0 z-10 flex items-center justify-center w-9 h-9 bg-bg-card border border-border border-l-0 rounded-r-lg shadow-sm text-text-muted/60 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
        title="展开知识库"
        @click="showSidebar = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>
        </svg>
      </button>
    </Transition>

    <!-- Center content area -->
    <div class="flex-1 flex flex-col relative overflow-hidden min-w-0">

      <!-- 笔记 + 论文：统一 ContentLayout -->
      <ContentLayout
        v-if="editingNote !== null"
        ref="digestContentLayoutRef"
        class="flex-1 min-h-0 border-l border-border mt-3"
        :context-key="noteEditingLayoutKey"
        :panel-configs="noteEditingPanelConfigs"
        :default-layout="noteEditingDefaultLayout"
        :context="noteEditingContext"
        @note-saved="handleChatNoteSaved"
        @close-note="closeNoteEditor"
      />

      <ContentLayout
        v-else-if="comparingPaperIds"
        class="flex-1 min-h-0 mt-3"
        :context-key="compareLayoutKey"
        :panel-configs="compareOnlyPanels"
        :default-layout="compareOnlyDefaultLayout"
        :context="compareLayoutContext"
        @close-compare="closeCompare"
        @compare-saved="handleCompareSaved"
      />

      <ContentLayout
        v-else-if="viewingCompareResultId !== null"
        class="flex-1 min-h-0 mt-3"
        :context-key="compareResultLayoutKey"
        :panel-configs="compareResultPanels"
        :default-layout="compareResultDefaultLayout"
        :context="compareResultContext"
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

      <ContentLayout
        v-else-if="viewingMd"
        :key="mdLayoutKey"
        class="flex-1 min-h-0 mt-3"
        :context-key="mdLayoutKey"
        :panel-configs="mdPanelConfigs"
        :default-layout="mdDefaultLayout"
        :context="mdLayoutContext"
        :show-close="true"
        @close-view="closeViewingMd"
      />

      <ContentLayout
        v-else-if="sidebarPaperId"
        class="flex-1 min-h-0 mt-3"
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
        <!-- Loading -->
        <div v-if="myPapersCenterLoading && myPapersCenter.length === 0"
          class="flex items-center justify-center h-full"
        >
          <svg class="animate-spin h-8 w-8 text-amber-500" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
        </div>

        <!-- 空状态 -->
        <div v-else-if="myPapersCenter.length === 0"
          class="flex flex-col items-center justify-center h-full gap-5 text-center px-8"
        >
          <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-[#f59e0b] to-[#ef4444] opacity-70 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div>
            <h2 class="text-xl font-bold text-text-primary mb-2">还没有上传论文</h2>
            <p class="text-sm text-text-muted max-w-xs leading-relaxed">在左侧点击「上传 / 导入论文」，支持 PDF 上传或 arXiv ID 导入，自动生成结构化摘要</p>
          </div>
          <button
            class="px-6 py-2.5 rounded-full bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="showUploadDialog = true"
          >上传第一篇论文</button>
        </div>

        <!-- 论文卡片列表 -->
        <div v-else class="max-w-2xl mx-auto space-y-4">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold text-text-primary">
              我的论文
              <span class="text-sm font-normal text-text-muted ml-1">({{ myPapersCenter.length }})</span>
            </h2>
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-white bg-gradient-to-r from-[#f59e0b] to-[#ef4444] border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="showUploadDialog = true"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              上传论文
            </button>
          </div>

          <div
            v-for="paper in myPapersCenter"
            :key="paper.paper_id"
            class="bg-bg-card border border-border rounded-2xl p-4 sm:p-5 cursor-pointer hover:border-amber-500/40 hover:shadow-md transition-all"
            @click="openUserPaper(paper.paper_id)"
          >
            <!-- Header row -->
            <div class="flex items-start justify-between gap-3 mb-3">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="px-2.5 py-0.5 rounded-full bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white text-xs font-semibold">
                  {{ paper.institution || '未知机构' }}
                </span>
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-600 border border-amber-500/30">
                  我的上传
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
      </div>

      <!-- 用户上传论文展示（点击具体论文后的详情/进度面板） -->
      <div
        v-else-if="viewingUserPaperId"
        class="flex-1 flex flex-col overflow-hidden mt-3 px-2 sm:px-4 pb-4"
      >
        <!-- 返回列表按钮 -->
        <button
          class="inline-flex items-center gap-1 text-sm text-text-muted hover:text-amber-500 mb-3 cursor-pointer bg-transparent border-none transition-colors self-start"
          @click="closeUserPaperDetail"
        >← 返回我的论文</button>

        <!-- 处理中进度面板 -->
        <div
          v-if="viewingUserPaper && (viewingUserPaper.process_status === 'processing' || viewingUserPaper.process_status === 'pending')"
          class="flex flex-col items-center justify-center flex-1 gap-6 text-center"
        >
          <div class="w-16 h-16 rounded-full bg-gradient-to-br from-[#f59e0b] to-[#ef4444] flex items-center justify-center animate-pulse">
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
                class="text-sm"
                :class="isStepCurrent(step, viewingUserPaper.process_step)
                  ? 'text-amber-500 font-medium'
                  : isStepDone(step, viewingUserPaper.process_step)
                    ? 'text-text-secondary'
                    : 'text-text-muted'"
              >{{ userPaperStepLabel(step) }}</span>
            </div>
          </div>
          <p class="text-xs text-text-muted">预计需要 1.5–3 分钟，完成后自动更新</p>
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
              class="px-5 py-2 rounded-full bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
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
            class="px-5 py-2 rounded-full bg-gradient-to-r from-[#f59e0b] to-[#ef4444] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="handleRetryUserPaper"
          >开始处理</button>
        </div>

        <!-- 处理完成：统一布局 -->
        <ContentLayout
          v-else-if="viewingUserPaper && viewingUserPaper.process_status === 'completed' && viewingUserPaper.summary"
          class="flex-1 min-h-0 overflow-hidden"
          :key="viewingUserPaperId"
          :context-key="userPaperLayoutKey"
          :panel-configs="userPaperPanelConfigs"
          :default-layout="userPaperDefaultLayout"
          :context="userPaperLayoutContext"
          @note-saved="handleChatNoteSaved"
        />
      </div>

      <!-- 默认卡片刷刷模式 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center relative">

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
                  <p class="mt-1 text-xs text-text-muted">AI 自动筛选 arXiv 论文 · 中文摘要 · 知识库 · 灵感生成，完全免费</p>
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
        <div v-if="loading" class="flex flex-col items-center gap-3">
          <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-text-muted text-sm">
            {{ selectedDate ? `正在加载 ${selectedDate} 的论文…` : '加载论文中…' }}
          </span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex flex-col items-center gap-3 text-center px-8">
          <span class="text-tinder-pink text-lg">{{ error }}</span>
          <p v-if="errorType === 'proxy'" class="text-sm text-text-muted max-w-xs">
            检测到系统代理可能未启动，请关闭代理程序（如 Clash / V2Ray）或确保代理正常运行后重试
          </p>
          <p v-else-if="errorType === 'server'" class="text-sm text-text-muted">
            服务端出现异常，请稍后再试
          </p>
          <button
            class="px-4 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="retryLoad"
          >
            重试
          </button>
        </div>

        <!-- 超限提示（不显示卡片，显示背景文字） -->
        <div v-else-if="isQuotaExceeded && isActuallyLimited && quotaExceededMessage" class="flex flex-col items-center justify-center gap-4 text-center px-8 max-w-sm">
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
              <li class="flex items-center gap-2"><span class="text-tinder-pink font-bold">✦</span>完全免费，无需付费</li>
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
          <!-- 已登录用户：提示升级 -->
          <template v-else>
            <p class="text-sm text-text-muted mt-2">
              升级账号可查看更多论文
            </p>
          </template>
        </div>

        <!-- All dates exhausted (true end state) -->
        <div v-else-if="allSwiped && allDatesExhausted" class="flex flex-col items-center gap-4 text-center px-8">
          <div class="text-5xl mb-2">🎉</div>
          <h2 class="text-xl font-bold text-text-primary">所有论文已全部浏览</h2>
          <p class="text-sm text-text-muted">
            知识库已收藏 {{ kbPaperCount }} 篇，新论文将在明天更新
          </p>
          <button
            class="px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="resetCards"
          >
            重新浏览
          </button>
        </div>

        <!-- Card -->
        <template v-else-if="currentPaper">
          <!-- Counter pill with progress bar (hidden when total <= 5 to avoid "too few papers" signal) -->
          <div v-if="papers.length > 5" class="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-1.5">
            <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-bg-card/80 backdrop-blur-sm border border-border/60 shadow-sm">
              <span class="text-[11px] font-semibold text-text-primary tabular-nums">{{ currentIndex + 1 }}</span>
              <span class="text-[10px] text-text-muted">/</span>
              <span class="text-[11px] text-text-muted tabular-nums">{{ papers.length }}</span>
            </div>
            <!-- Mini progress bar -->
            <div class="w-16 h-0.5 rounded-full bg-border overflow-hidden">
              <div
                class="h-full rounded-full bg-brand-gradient transition-all duration-300"
                :style="{ width: `${((currentIndex + 1) / papers.length) * 100}%` }"
              />
            </div>
          </div>

          <!-- Date transition toast — shown briefly when auto-advancing to a previous day -->
          <Transition name="date-toast">
            <div
              v-if="dateTransitionNotice"
              class="absolute bottom-[130px] inset-x-0 z-30 pointer-events-none flex justify-center"
            >
              <div class="flex items-center gap-2 px-4 py-2 rounded-full bg-bg-card/95 backdrop-blur-sm border border-border shadow-lg">
                <svg class="w-3.5 h-3.5 text-tinder-pink shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <span class="text-[12px] text-text-secondary font-medium whitespace-nowrap">{{ dateTransitionNotice }} 的论文</span>
              </div>
            </div>
          </Transition>

          <!-- The card — responsive width/height -->
          <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(480px, calc(100dvh - 210px), 620px)">
            <PaperCard
              :key="currentPaper.paper_id"
              :paper="currentPaper"
              :anim-class="cardAnimClass"
            />
          </div>

          <!-- Action buttons -->
          <ActionButtons
            @undo="undo"
            @skip="skip"
            @like="like"
            @detail="openDetail"
            @superlike="openPdf"
          />
        </template>

        <!-- No data: with notice -->
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

        <!-- No data: without notice -->
        <div v-else-if="!loading && selectedDate" class="text-center text-text-muted text-sm">
          该日期暂无论文
        </div>
      </div>
    </div>

  <!-- Upload dialog -->
  <UserPaperUploadDialog
    v-if="showUploadDialog"
    @close="showUploadDialog = false"
    @uploaded="handleUploadDialogUploaded"
  />
  </div>
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

/* Fade transition for backdrop and open button */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
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
</style>
