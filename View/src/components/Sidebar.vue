<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import type { KbTree, KbFolder, KbPaper, KbMenuItem, KbNote, KbCompareResult, KbCompareResultsTree, UserPaper, UserPaperTree, UserPaperFolder, CompareCartItem, UserPaperFileViewMode, UserPaperViewMdPayload } from '../types/paper'
import type { UserPaperDerivativeType } from '../api'
import { useEntitlements } from '../composables/useEntitlements'
import KbContextMenu from './KbContextMenu.vue'
import FolderPickerDialog from './FolderPickerDialog.vue'
import SidebarFolder from './SidebarFolder.vue'
import UserPaperFolderItem from './UserPaperFolderItem.vue'
import TranslateProgressRing from './TranslateProgressRing.vue'
import UserBar from './UserBar.vue'
import DatePill from './DatePill.vue'
import DatePicker from './DatePicker.vue'
import SidebarResearchTab from './sidebar/SidebarResearchTab.vue'
import SidebarCompareTab from './sidebar/SidebarCompareTab.vue'
import {
  createKbFolder,
  renameKbFolder,
  deleteKbFolder,
  moveKbFolder,
  removeKbPaper,
  moveKbPapers,
  renameKbPaper,
  fetchNotes,
  createNote,
  uploadNoteFile,
  addNoteLink,
  deleteNote as apiDeleteNote,
  moveCompareResult as apiMoveCompare,
  fetchUserPapers,
  fetchUserPaperTree,
  deleteUserPaper,
  deleteUserPaperDerivative,
  processUserPaper,
  translateUserPaper,
  retranslateUserPaper,
  moveUserPapers,
  userPaperStepLabel,
  kbPaperStepLabel,
  processKbPaper,
  translateKbPaper,
  retranslateKbPaper,
  deleteKbPaperDerivative,
  downloadPaperFile,
  downloadNote,
  downloadBatch,
  fetchAutoClassifyPendingCount,
  fetchAutoClassifyUnclassifiedCount,
  updateKbPaperReadStatus,
  API_ORIGIN,
} from '../api'
import type { KbScope, BatchDownloadItem } from '../api'
import { openExternal } from '../utils/openExternal'
import { trackEvent } from '../composables/useAnalytics'

const props = withDefaults(defineProps<{
  kbTree: KbTree
  compareTree: KbCompareResultsTree | null
  activeFolderId: number | null
  selectedDate: string
  dates: string[]
  title?: string
  emptyTitle?: string
  emptyDesc?: string
  scope?: KbScope
  /** 第三个 Tab 的模式：'mypapers'（默认）| 'paper-inspiration'（灵感页用）| 'none'（隐藏） */
  thirdTab?: 'mypapers' | 'paper-inspiration' | 'none'
  /** 第四个 Tab：'research'（默认）| 'none'（隐藏） */
  fourthTab?: 'research' | 'none'
  /** 主区正在查看的用户论文 ID（详情或子链接所属论文） */
  activeUserPaperId?: string | null
  /** 主区正在查看的子链接，格式 paperId:pdf|mineru|zh|bilingual */
  activeViewMdKey?: string | null
}>(), {
  title: '知识库',
  emptyTitle: '开始浏览',
  emptyDesc: '当你对论文点赞后，它们会在这里出现。',
  scope: 'kb',
  thirdTab: 'mypapers',
  fourthTab: 'research',
  compareTree: null,
  activeUserPaperId: null,
  activeViewMdKey: null,
})

// ---- Tab switching ----
type SidebarTab = 'papers' | 'compare' | 'mypapers' | 'paper-inspiration' | 'research'
const activeTab = ref<SidebarTab>('papers')

const router = useRouter()

// ---- Entitlements (for KB storage indicator) ----
const ent = useEntitlements()
const kbStorageNearLimit = computed(() => {
  const s = ent.kbPaperStorage.value
  if (s.limit === null) return false
  return s.remaining !== null && s.remaining <= 5
})

// ---- Date jump dropdown (secondary control; primary UX is auto-advance) ----
const showDateJump = ref(false)

const emit = defineEmits<{
  'update:selectedDate': [value: string]
  'update:activeFolderId': [value: number | null]
  openPaper: [paperId: string]
  openNote: [payload: { id: number; paperId: string }]
  openPdf: [payload: { paperId: string; filePath: string; title: string }]
  compare: [paperIds: string[], scope?: string, compareResultIds?: number[]]
  research: [paperIds: string[], paperTitles: Record<string, string>, scope?: string]
  refresh: []
  openCompareResult: [resultId: number]
  refreshCompare: []
  toggleSidebar: []
  openUserPaper: [paperId: string]
  openUploadDialog: []
  tabChanged: [tab: 'papers' | 'compare' | 'mypapers' | 'paper-inspiration' | 'research']
  /** 论文灵感：生成指定论文的灵感候选卡片 */
  paperInspiration: [paperId: string, title: string]
  /** 论文灵感：点击条目标题区域，直接展示该论文当前灵感候选的详情面板 */
  paperInspirationDetail: [paperId: string, title: string]
  /** 我的论文：主区 PDF + Markdown 分栏 */
  viewMd: [payload: UserPaperViewMdPayload]
  /** 深度研究库：打开某个研究会话 */
  openResearchSession: [sessionId: number]
  /** 知识库论文阅读状态变更，供父组件就地更新 kbTree */
  'update-read-status': [paperId: string, status: 'unread' | 'reading' | 'read']
}>()

// ---- My Papers tab state ----
const myPaperTree = ref<UserPaperTree | null>(null)
const myPapersLoading = ref(false)
const myPapersError = ref('')
let _pollTimer: ReturnType<typeof setInterval> | null = null

// ---- Paper Inspiration tab state ----
/** 正在生成灵感候选的论文 ID 集合 */
const generatingPaperIds = ref<Set<string>>(new Set())

function openPaperInspiration(paperId: string, title?: string) {
  // 即便正在生成中也允许重新触发：后端有幂等缓存不会重复 LLM 调用；
  // 避免因首次出错或状态未释放导致后续点击静默无效
  generatingPaperIds.value = new Set(generatingPaperIds.value).add(paperId)
  emit('paperInspiration', paperId, title ?? paperId)
}

function onPaperInspirationDone(paperId: string) {
  const next = new Set(generatingPaperIds.value)
  next.delete(paperId)
  generatingPaperIds.value = next
}

// Folder state for mypapers
const myPaperExpandedFolders = ref<Set<number>>(new Set())
const myPaperActiveFolderId = ref<number | null>(null)
/** 我的论文：展开显示 PDF / MinerU / 翻译链接 */
const myPaperExpandedPaperLinks = ref<Set<string>>(new Set())
const showMyPaperNewFolderInput = ref(false)
const myPaperNewFolderName = ref('')
const myPaperNewFolderParentId = ref<number | null>(null)
let _creatingMyPaperFolder = false
const renamingMyPaperFolderId = ref<number | null>(null)
const renamingMyPaperFolderName = ref('')
let _renamingMyPaperFolder = false

function _collectAllMyPapers(tree: UserPaperTree): UserPaper[] {
  const papers: UserPaper[] = [...(tree.papers ?? [])]
  function collect(folders: UserPaperFolder[]) {
    for (const f of folders) {
      papers.push(...(f.papers ?? []))
      if (f.children?.length) collect(f.children)
    }
  }
  collect(tree.folders ?? [])
  return papers
}

async function loadMyPapers() {
  myPapersLoading.value = true
  myPapersError.value = ''
  try {
    myPaperTree.value = await fetchUserPaperTree()
    _startOrStopPolling()
  } catch (e: any) {
    myPapersError.value = e?.message || '加载失败'
  } finally {
    myPapersLoading.value = false
  }
}

function _hasProcessing() {
  if (!myPaperTree.value) return false
  return _collectAllMyPapers(myPaperTree.value).some(
    p => p.process_status === 'processing' || p.process_status === 'pending',
  )
}

function _hasTranslating() {
  if (!myPaperTree.value) return false
  return _collectAllMyPapers(myPaperTree.value).some(
    p => p.translate_status === 'processing',
  )
}

function _shouldPollMyPapers() {
  return _hasProcessing() || _hasTranslating()
}

function _startOrStopPolling() {
  if (_shouldPollMyPapers()) {
    if (!_pollTimer) {
      _pollTimer = setInterval(async () => {
        try {
          myPaperTree.value = await fetchUserPaperTree()
          if (!_shouldPollMyPapers()) {
            _stopPolling()
          }
        } catch {}
      }, 3000)
    }
  } else {
    _stopPolling()
  }
}

function _stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer)
    _pollTimer = null
  }
}

// ---- mypapers folder management ----
function toggleMyPaperFolder(folderId: number) {
  const next = new Set(myPaperExpandedFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  myPaperExpandedFolders.value = next
}

function startMyPaperNewFolder(parentId: number | null = null) {
  myPaperNewFolderParentId.value = parentId
  myPaperNewFolderName.value = ''
  _creatingMyPaperFolder = false
  showMyPaperNewFolderInput.value = true
  if (parentId !== null) {
    const next = new Set(myPaperExpandedFolders.value)
    next.add(parentId)
    myPaperExpandedFolders.value = next
  }
}

async function confirmMyPaperNewFolder() {
  if (_creatingMyPaperFolder) return
  _creatingMyPaperFolder = true
  const name = myPaperNewFolderName.value.trim()
  showMyPaperNewFolderInput.value = false
  if (!name) { _creatingMyPaperFolder = false; return }
  try {
    await createKbFolder(name, myPaperNewFolderParentId.value, 'mypapers')
    await loadMyPapers()
  } catch {}
  _creatingMyPaperFolder = false
}

function startRenameMyPaperFolder(folder: UserPaperFolder) {
  renamingMyPaperFolderId.value = folder.id
  renamingMyPaperFolderName.value = folder.name
  _renamingMyPaperFolder = false
}

async function confirmRenameMyPaperFolder() {
  if (_renamingMyPaperFolder) return
  _renamingMyPaperFolder = true
  const folderId = renamingMyPaperFolderId.value
  if (folderId === null) return
  const name = renamingMyPaperFolderName.value.trim()
  renamingMyPaperFolderId.value = null
  if (!name) { _renamingMyPaperFolder = false; return }
  try {
    await renameKbFolder(folderId, name, 'mypapers')
    await loadMyPapers()
  } catch {}
  _renamingMyPaperFolder = false
}

watch(activeTab, (tab) => {
  if (tab === 'mypapers' || tab === 'paper-inspiration') {
    emit('tabChanged', tab as 'mypapers' | 'paper-inspiration')
    loadMyPapers()
  } else if (tab === 'research') {
    emit('tabChanged', 'research')
    _stopPolling()
    loadResearchSessions()
  } else {
    emit('tabChanged', tab as 'papers' | 'compare')
    _stopPolling()
  }
})

// Research tab state is owned by SidebarResearchTab
const researchTabRef = ref<InstanceType<typeof SidebarResearchTab> | null>(null)

function loadResearchSessions() {
  researchTabRef.value?.load()
}

onBeforeUnmount(() => {
  _stopPolling()
  _stopKbPolling()
})

/** Called by parent after an upload to refresh the list */
async function refreshMyPapers() {
  await loadMyPapers()
}

async function handleRetryProcess(paper: UserPaper) {
  try {
    await processUserPaper(paper.paper_id)
    await loadMyPapers()
  } catch {}
}

function toggleMyPaperPaperLinks(paperId: string) {
  const next = new Set(myPaperExpandedPaperLinks.value)
  if (next.has(paperId)) next.delete(paperId)
  else next.add(paperId)
  myPaperExpandedPaperLinks.value = next
}

function userPaperStaticFullUrl(path: string | null | undefined): string | null {
  if (!path) return null
  return `${API_ORIGIN}${path}`
}

function emitViewUserPaperMd(paper: UserPaper, mode: UserPaperFileViewMode) {
  const pdfUrl = userPaperStaticFullUrl(paper.pdf_static_url)
  let mdUrl: string | null = null
  const baseTitle = paper.title || paper.paper_id
  let title = baseTitle
  if (mode === 'pdf') {
    title = `${baseTitle} · 原 PDF`
  } else if (mode === 'mineru') {
    mdUrl = userPaperStaticFullUrl(paper.mineru_static_url)
    title = `${baseTitle} · MinerU 解析`
  } else if (mode === 'zh') {
    mdUrl = userPaperStaticFullUrl(paper.zh_static_url)
    title = `${baseTitle} · 中文翻译`
  } else if (mode === 'bilingual') {
    mdUrl = userPaperStaticFullUrl(paper.bilingual_static_url)
    title = `${baseTitle} · 中英对照`
  }
  emit('viewMd', {
    paperId: paper.paper_id,
    title,
    pdfUrl,
    mdUrl,
    viewMode: mode,
    mineruUrl: userPaperStaticFullUrl(paper.mineru_static_url),
    zhUrl: userPaperStaticFullUrl(paper.zh_static_url),
    bilingualUrl: userPaperStaticFullUrl(paper.bilingual_static_url),
    scope: 'mypapers',
    translateInProgress: paper.translate_status === 'processing',
  })
}

function myPaperMdSubLinkClass(paperId: string, mode: UserPaperFileViewMode): string {
  const active = props.activeViewMdKey === `${paperId}:${mode}`
  const base =
    'flex items-center gap-2 py-1.5 px-2 rounded transition-colors group/note cursor-pointer'
  if (active) {
    return `${base} bg-amber-500/8 text-amber-600 dark:text-amber-400`
  }
  return `${base} hover:bg-bg-hover`
}

async function handleTranslateMyPaper(paper: UserPaper) {
  if (ent.isGated('translate')) {
    myPapersError.value = '论文全文翻译需要 Pro 套餐，请升级后使用。'
    return
  }
  try {
    const r = await translateUserPaper(paper.paper_id)
    if (!r.ok) {
      myPapersError.value = r.message || '无法启动翻译'
      return
    }
    await loadMyPapers()
    _startOrStopPolling()
  } catch (e: any) {
    myPapersError.value = e?.message || '翻译请求失败'
  }
}

async function handleDeleteMyPaper(paper: UserPaper) {
  try {
    await deleteUserPaper(paper.paper_id)
    await loadMyPapers()
  } catch {}
}

// mypapers context menu — shared for both papers and folders
const myPaperContextMenu = ref<{
  x: number; y: number
  type: 'paper' | 'folder'
  paper?: UserPaper
  folder?: UserPaperFolder
} | null>(null)

/** 子链接（MinerU / 中文 / 中英）三点菜单 */
const myPaperDerivativeMenu = ref<{
  x: number
  y: number
  paper: UserPaper
  derivative: UserPaperDerivativeType
} | null>(null)

function openMyPaperDerivativeMenu(e: MouseEvent, paper: UserPaper, derivative: UserPaperDerivativeType) {
  e.stopPropagation()
  myPaperDerivativeMenu.value = { x: e.clientX, y: e.clientY, paper, derivative }
}

function myPaperDerivativeMenuItems(): KbMenuItem[] {
  return [
    { key: 'download-md', label: '下载 MD' },
    { key: 'download-docx', label: '下载 DOCX' },
    { key: 'download-pdf', label: '下载 PDF' },
    { key: 'regenerate', label: '重新生成' },
    { key: 'delete', label: '删除', danger: true },
  ]
}

async function handleMyPaperDerivativeMenuSelect(key: string) {
  const ctx = myPaperDerivativeMenu.value
  myPaperDerivativeMenu.value = null
  if (!ctx) return
  const { paper, derivative } = ctx
  if (key === 'download-md' || key === 'download-docx' || key === 'download-pdf') {
    const fmt = key.replace('download-', '') as 'md' | 'docx' | 'pdf'
    try {
      await downloadPaperFile(paper.paper_id, derivative, 'mypapers', fmt)
    } catch (e: any) {
      alert(`下载失败：${e?.message ?? '未知错误'}`)
    }
    return
  }
  if (key === 'delete') {
    try {
      await deleteUserPaperDerivative(paper.paper_id, derivative)
      await loadMyPapers()
    } catch {}
    return
  }
  if (key === 'regenerate') {
    try {
      if (derivative === 'mineru') {
        await processUserPaper(paper.paper_id)
      } else {
        await retranslateUserPaper(paper.paper_id)
      }
      await loadMyPapers()
      _startOrStopPolling()
    } catch {}
  }
}

function openMyPaperMenu(e: MouseEvent, paper: UserPaper) {
  e.stopPropagation()
  myPaperContextMenu.value = {
    x: e.clientX, y: e.clientY,
    type: 'paper',
    paper,
  }
}

function openMyPaperFolderMenu(e: MouseEvent, folder: UserPaperFolder) {
  e.stopPropagation()
  myPaperContextMenu.value = {
    x: e.clientX, y: e.clientY,
    type: 'folder',
    folder,
  }
}

async function handleMyPaperMenuSelect(key: string) {
  const ctx = myPaperContextMenu.value
  myPaperContextMenu.value = null
  if (!ctx) return

  if (ctx.type === 'paper' && ctx.paper) {
    const paper = ctx.paper
    if (key === 'retry') await handleRetryProcess(paper)
    else if (key === 'delete') await handleDeleteMyPaper(paper)
    else if (key === 'move') {
      movingPaperIds.value = [paper.paper_id]
      movingFolderId.value = null
      batchMoveContext.value = 'mypapers'
      folderPickerTitle.value = '移动论文到文件夹'
      showFolderPicker.value = true
    } else if (key === 'cart-add') {
      addToCompareCart({
        id: paper.paper_id,
        title: paper.title || paper.paper_id,
        source: 'mypapers',
        type: 'paper',
      })
    } else if (key === 'cart-remove') {
      removeFromCompareCart(paper.paper_id)
    } else if (key === 'research') {
      const titleMap: Record<string, string> = {}
      titleMap[paper.paper_id] = paper.title || paper.paper_id
      emit('research', [paper.paper_id], titleMap, 'mypapers')
    }
  }

  if (ctx.type === 'folder' && ctx.folder) {
    const folder = ctx.folder
    if (key === 'rename') {
      startRenameMyPaperFolder(folder)
    } else if (key === 'delete') {
      try {
        await deleteKbFolder(folder.id, 'mypapers')
        await loadMyPapers()
      } catch {}
    } else if (key === 'new-subfolder') {
      startMyPaperNewFolder(folder.id)
    } else if (key === 'move-folder') {
      movingFolderId.value = folder.id
      movingFolderScope.value = 'mypapers'
      movingPaperIds.value = []
      folderPickerTitle.value = `移动"${folder.name}"到...`
      showFolderPicker.value = true
    }
  }
}

function myPaperMenuItems(): KbMenuItem[] {
  const ctx = myPaperContextMenu.value
  if (!ctx) return []
  if (ctx.type === 'folder') {
    return [
      { key: 'new-subfolder', label: '新建子文件夹' },
      { key: 'rename', label: '重命名' },
      { key: 'move-folder', label: '移动到...' },
      { key: 'delete', label: '删除文件夹', danger: true },
    ]
  }
  const paper = ctx.paper
  if (!paper) return []
  const id = paper.paper_id
  const inCart = isInCart(id)
  const cartFull = compareCart.value.length >= 5
  const canAdd = paper.process_status === 'completed'
  return [
    { key: 'move', label: '移动到文件夹...' },
    { key: 'retry', label: '重新处理' },
    ...(canAdd
      ? [
          { key: 'research', label: '深度研究', icon: 'research' as const },
          {
            key: inCart ? 'cart-remove' : 'cart-add',
            label: inCart ? '已在对比清单' : cartFull ? '对比清单已满(5篇)' : '加入对比清单',
            danger: inCart,
            icon: (!inCart && !cartFull ? 'compare' : undefined) as 'compare' | undefined,
          },
        ]
      : []),
    { key: 'delete', label: '删除', danger: true },
  ]
}

function processStatusIcon(status: string): string {
  if (status === 'completed') return '✅'
  if (status === 'failed') return '❌'
  if (status === 'processing' || status === 'pending') return '⏳'
  return '○'
}

function processStatusColor(status: string): string {
  if (status === 'completed') return 'text-green-500'
  if (status === 'failed') return 'text-red-500'
  if (status === 'processing' || status === 'pending') return 'text-amber-500'
  return 'text-text-muted'
}

// ---- Folder expand/collapse state ----
const expandedFolders = ref<Set<number>>(new Set())

function toggleFolder(folderId: number) {
  const next = new Set(expandedFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedFolders.value = next
}

function selectFolder(folderId: number | null) {
  emit('update:activeFolderId', folderId)
  if (folderId !== null) {
    const next = new Set(expandedFolders.value)
    next.add(folderId)
    expandedFolders.value = next
  }
}

// ---- New folder ----
const showNewFolderInput = ref(false)
const newFolderName = ref('')
const newFolderParentId = ref<number | null>(null)
let _creatingFolder = false

function startNewFolder(parentId: number | null = null) {
  newFolderParentId.value = parentId
  newFolderName.value = ''
  _creatingFolder = false
  showNewFolderInput.value = true
  if (parentId !== null) {
    const next = new Set(expandedFolders.value)
    next.add(parentId)
    expandedFolders.value = next
  }
}

async function confirmNewFolder() {
  if (_creatingFolder) return
  _creatingFolder = true
  const name = newFolderName.value.trim()
  showNewFolderInput.value = false
  if (!name) return
  try {
    await createKbFolder(name, newFolderParentId.value, props.scope)
    emit('refresh')
  } catch {}
}

// ---- Rename folder ----
const renamingFolderId = ref<number | null>(null)
const renamingFolderName = ref('')
let _renamingFolder = false

function startRenameFolder(folder: KbFolder) {
  renamingFolderId.value = folder.id
  renamingFolderName.value = folder.name
  _renamingFolder = false
}

async function confirmRenameFolder() {
  if (_renamingFolder) return
  _renamingFolder = true
  const folderId = renamingFolderId.value
  if (folderId === null) return
  const name = renamingFolderName.value.trim()
  renamingFolderId.value = null
  if (!name) return
  try {
    await renameKbFolder(folderId, name, props.scope)
    emit('refresh')
  } catch {}
}

// ---- Rename paper ----
const renamingPaperId = ref<string | null>(null)
const renamingPaperTitle = ref('')
let _renamingPaper = false

function startRenamePaper(paper: KbPaper) {
  renamingPaperId.value = paper.paper_id
  renamingPaperTitle.value = paper.paper_data.short_title || paper.paper_id
  _renamingPaper = false
}

async function confirmRenamePaper() {
  if (_renamingPaper) return
  _renamingPaper = true
  const paperId = renamingPaperId.value
  if (!paperId) return
  const title = renamingPaperTitle.value.trim()
  renamingPaperId.value = null
  if (!title) return
  try {
    await renameKbPaper(paperId, title, props.scope)
    emit('refresh')
  } catch {}
}

// Compare tab state is owned by SidebarCompareTab
const compareTabRef = ref<InstanceType<typeof SidebarCompareTab> | null>(null)

function startRenameCompare(result: KbCompareResult) {
  compareTabRef.value?.startRename(result)
}

async function deleteCompareResult(id: number) {
  await compareTabRef.value?.handleDelete(id)
}

function handleCompareMenu(e: MouseEvent, result: KbCompareResult) {
  openCompareResultMenu(e, result)
}

// ---- Context menu ----
const contextMenu = ref<{ x: number; y: number; items: KbMenuItem[]; target: any } | null>(null)

function openFolderMenu(e: MouseEvent, folder: KbFolder) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'new-subfolder', label: '新建子文件夹' },
      { key: 'rename', label: '重命名' },
      { key: 'move-folder', label: '移动到...' },
      { key: 'delete', label: '删除文件夹', danger: true },
    ],
    target: { type: 'folder' as const, folder },
  }
}

// Mark KB paper as reading when opened (fire-and-forget)
function handleOpenKbPaper(paperId: string, scope: string = 'kb') {
  emit('openPaper', paperId)
  // Immediately reflect status change in parent's kbTree, then persist to backend
  emit('update-read-status', paperId, 'reading')
  updateKbPaperReadStatus(paperId, 'reading', scope).catch(() => {})
}

function openPaperMenu(e: MouseEvent, paper: KbPaper) {
  e.stopPropagation()
  const inCart = isInCart(paper.paper_id)
  const cartFull = compareCart.value.length >= 5
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'rename-paper', label: '重命名' },
      { key: 'move', label: '移动到文件夹...' },
      { key: 'research', label: '深度研究', icon: 'research' as const },
      {
        key: inCart ? 'cart-remove' : 'cart-add',
        label: inCart ? '已在对比清单' : cartFull ? '对比清单已满(5篇)' : '加入对比清单',
        danger: inCart,
        icon: (!inCart && !cartFull ? 'compare' : undefined) as 'compare' | undefined,
      },
      { key: 'delete', label: '从知识库删除', danger: true },
    ],
    target: { type: 'paper' as const, paper },
  }
}

function openCompareResultMenu(e: MouseEvent, result: KbCompareResult) {
  e.stopPropagation()
  const id = String(result.id)
  const inCart = isInCart(id)
  const cartFull = compareCart.value.length >= 5
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'rename-compare', label: '重命名' },
      {
        key: inCart ? 'cart-remove' : 'cart-add',
        label: inCart ? '已在对比清单' : cartFull ? '对比清单已满(5篇)' : '加入对比清单',
        danger: inCart,
        icon: (!inCart && !cartFull ? 'compare' : undefined) as 'compare' | undefined,
      },
      { key: 'delete-compare', label: '删除', danger: true },
    ],
    target: { type: 'compare-result' as const, result },
  }
}

async function handleContextMenuSelect(key: string) {
  if (!contextMenu.value) return
  const { target } = contextMenu.value

  if (target.type === 'folder') {
    const folder = target.folder as KbFolder
    if (key === 'rename') {
      startRenameFolder(folder)
    } else if (key === 'delete') {
      try {
        await deleteKbFolder(folder.id, props.scope)
        if (props.activeFolderId === folder.id) {
          emit('update:activeFolderId', null)
        }
        emit('refresh')
      } catch {}
    } else if (key === 'new-subfolder') {
      startNewFolder(folder.id)
    } else if (key === 'move-folder') {
      movingFolderId.value = folder.id
      movingPaperIds.value = []
      folderPickerTitle.value = `移动"${folder.name}"到...`
      showFolderPicker.value = true
    }
  }

  if (target.type === 'paper') {
    const paper = target.paper as KbPaper
    if (key === 'delete') {
      try {
        await removeKbPaper(paper.paper_id, props.scope)
        emit('refresh')
      } catch {}
    } else if (key === 'move') {
      movingPaperIds.value = [paper.paper_id]
      showFolderPicker.value = true
    } else if (key === 'rename-paper') {
      startRenamePaper(paper)
    } else if (key === 'cart-add') {
      addToCompareCart({
        id: paper.paper_id,
        title: paper.paper_data.short_title || paper.paper_id,
        source: 'kb',
        type: 'paper',
      })
    } else if (key === 'cart-remove') {
      removeFromCompareCart(paper.paper_id)
    } else if (key === 'research') {
      const titleMap: Record<string, string> = {}
      titleMap[paper.paper_id] = paper.paper_data?.short_title || (paper.paper_data as any)?.['📖标题'] || paper.paper_id
      emit('research', [paper.paper_id], titleMap)
    }
  }

  if (target.type === 'note') {
    const note = target.note as KbNote
    if (key === 'delete') {
      await handleDeleteNote(note.id)
    } else if (key === 'download-note') {
      downloadNote(note.id)
    }
  }

  if (target.type === 'mypapers-note') {
    const note = target.note as KbNote
    if (key === 'delete-mp-note') {
      await handleDeleteMyPaperNote(note.id, note.paper_id)
    } else if (key === 'download-note') {
      downloadNote(note.id)
    }
  }

  if (target.type === 'compare-result') {
    const result = target.result as KbCompareResult
    if (key === 'rename-compare') {
      startRenameCompare(result)
    } else if (key === 'delete-compare') {
      await deleteCompareResult(result.id)
    } else if (key === 'cart-add') {
      addToCompareCart({
        id: String(result.id),
        title: result.title,
        source: 'compare',
        type: 'compare_result',
      })
    } else if (key === 'cart-remove') {
      removeFromCompareCart(String(result.id))
    }
  }
}

// ---- Batch mode toggle ----
const batchMode = ref(false)

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    checkedPapers.value = new Set()
  }
}

// ---- Checkbox multi-select ----
const checkedPapers = ref<Set<string>>(new Set())

function toggleCheck(paperId: string) {
  const next = new Set(checkedPapers.value)
  if (next.has(paperId)) next.delete(paperId)
  else next.add(paperId)
  checkedPapers.value = next
}

const hasChecked = computed(() => checkedPapers.value.size > 0)
const canCompare = computed(() => checkedPapers.value.size >= 2 && checkedPapers.value.size <= 5)
const canResearch = computed(() => checkedPapers.value.size >= 1 && checkedPapers.value.size <= 20)

function startCompare() {
  if (!canCompare.value) return
  const ids = [...checkedPapers.value]
  const scope = activeTab.value === 'mypapers' ? 'mypapers' : undefined
  batchMode.value = false
  checkedPapers.value = new Set()
  emit('compare', ids, scope)
}

function startResearch() {
  if (!canResearch.value) return
  const ids = [...checkedPapers.value]
  const scope = activeTab.value === 'mypapers' ? 'mypapers' : undefined
  // Build a title map from all available paper sources
  const titleMap: Record<string, string> = {}
  function collectKbTitles(papers: Array<{ paper_id: string; paper_data?: { short_title?: string; '📖标题'?: string } }>) {
    for (const p of papers) {
      titleMap[p.paper_id] = p.paper_data?.short_title || p.paper_data?.['📖标题'] || p.paper_id
    }
  }
  if (props.kbTree) {
    collectKbTitles(props.kbTree.papers ?? [])
    function walkKbFolders(folders: typeof props.kbTree.folders) {
      for (const f of folders) {
        collectKbTitles(f.papers ?? [])
        if (f.children?.length) walkKbFolders(f.children)
      }
    }
    walkKbFolders(props.kbTree.folders ?? [])
  }
  // Also include titles from the "我的论文" tree (myPaperTree)
  if (myPaperTree.value) {
    function collectMyPaperTitles(papers: Array<{ paper_id: string; title?: string }>) {
      for (const p of papers) {
        if (!titleMap[p.paper_id]) {
          titleMap[p.paper_id] = p.title || p.paper_id
        }
      }
    }
    collectMyPaperTitles(myPaperTree.value.papers ?? [])
    function walkMyFolders(folders: UserPaperFolder[]) {
      for (const f of folders) {
        collectMyPaperTitles(f.papers ?? [])
        if (f.children?.length) walkMyFolders(f.children)
      }
    }
    walkMyFolders(myPaperTree.value.folders ?? [])
  }
  batchMode.value = false
  checkedPapers.value = new Set()
  emit('research', ids, titleMap, scope)
}

function handleStartNewResearchFromTab() {
  activeTab.value = 'papers'
  batchMode.value = true
  checkedPapers.value = new Set()
}

function handleStartNewCompareFromTab() {
  activeTab.value = 'papers'
  batchMode.value = true
  checkedPapers.value = new Set()
}

// ---- Compare Cart (跨库对比清单) ----
const compareCart = ref<CompareCartItem[]>([])
const compareCartExpanded = ref(false)

const compareCartPaperIds = computed(() =>
  compareCart.value.filter((i) => i.type === 'paper').map((i) => i.id),
)
const compareCartResultIds = computed(() =>
  compareCart.value.filter((i) => i.type === 'compare_result').map((i) => Number(i.id)),
)
const canCompareCart = computed(
  () => compareCart.value.length >= 2 && compareCart.value.length <= 5,
)

function isInCart(id: string): boolean {
  return compareCart.value.some((i) => i.id === id)
}

function addToCompareCart(item: CompareCartItem) {
  if (isInCart(item.id)) return
  if (compareCart.value.length >= 5) return
  compareCart.value = [...compareCart.value, item]
  compareCartExpanded.value = true
}

function removeFromCompareCart(id: string) {
  compareCart.value = compareCart.value.filter((i) => i.id !== id)
}

function clearCompareCart() {
  compareCart.value = []
  compareCartExpanded.value = false
}

function startCompareFromCart() {
  if (!canCompareCart.value) return
  const paperIds = compareCartPaperIds.value
  const resultIds = compareCartResultIds.value
  // 决定 scope：如果有用户论文则 undefined（后端按 up_ 前缀判断），否则 kb
  const scope = undefined
  clearCompareCart()
  emit('compare', paperIds, scope, resultIds.length > 0 ? resultIds : undefined)
}

// ---- Move (folder picker dialog) ----
const showFolderPicker = ref(false)
const movingPaperIds = ref<string[]>([])
const movingFolderId = ref<number | null>(null)
const movingFolderScope = ref<string>('kb')
const batchMoveContext = ref<'kb' | 'mypapers'>('kb')
const folderPickerTitle = ref('')

function startBatchMove() {
  movingPaperIds.value = [...checkedPapers.value]
  movingFolderId.value = null
  batchMoveContext.value = activeTab.value === 'mypapers' ? 'mypapers' : 'kb'
  folderPickerTitle.value = '移动论文到文件夹'
  showFolderPicker.value = true
}

async function handleMoveTo(targetId: number | null) {
  showFolderPicker.value = false

  if (movingFolderId.value !== null) {
    try {
      await moveKbFolder(movingFolderId.value, targetId, movingFolderScope.value as KbScope)
      if (movingFolderScope.value === 'mypapers') {
        await loadMyPapers()
      } else {
        emit('refresh')
      }
    } catch {}
    movingFolderId.value = null
    return
  }

  if (movingPaperIds.value.length === 0) return

  if (batchMoveContext.value === 'mypapers') {
    try {
      await moveUserPapers(movingPaperIds.value, targetId)
      checkedPapers.value = new Set()
      await loadMyPapers()
    } catch {}
  } else {
    try {
      await moveKbPapers(movingPaperIds.value, targetId, props.scope)
      checkedPapers.value = new Set()
      emit('refresh')
    } catch {}
  }
  movingPaperIds.value = []
}

// ---- Color helper ----
function avatarColor(paperId: string): string {
  let hash = 0
  for (let i = 0; i < paperId.length; i++) {
    hash = paperId.charCodeAt(i) + ((hash << 5) - hash)
  }
  return `hsl(${Math.abs(hash % 360)}, 60%, 35%)`
}

const allFolders = computed(() => props.kbTree?.folders ?? [])
const myPaperAllFolders = computed(() => myPaperTree.value?.folders ?? [])
const folderPickerFolders = computed(() =>
  batchMoveContext.value === 'mypapers' || movingFolderScope.value === 'mypapers'
    ? myPaperAllFolders.value
    : allFolders.value,
)

function countPapersInFolders(folders: typeof allFolders.value): number {
  let count = 0
  for (const f of folders) {
    count += f.papers?.length ?? 0
    if (f.children?.length) count += countPapersInFolders(f.children)
  }
  return count
}

const totalPaperCount = computed(() => {
  const rootPapers = props.kbTree?.papers?.length ?? 0
  return rootPapers + countPapersInFolders(allFolders.value)
})

// ---- Auto-classify pending badge ----
const pendingClassifyCount = ref(0)
const unclassifiedCount = ref(0)
let _pendingPollTimer: ReturnType<typeof setInterval> | null = null

/** Brief toast shown when the last pending classification finishes. */
const classifyDoneToast = ref(false)

async function refreshPendingClassify() {
  try {
    const prev = pendingClassifyCount.value
    const res = await fetchAutoClassifyPendingCount('kb')
    pendingClassifyCount.value = res.pending
    // When all pending jobs finish, refresh the tree and show a toast
    if (prev > 0 && res.pending === 0) {
      emit('refresh')
      classifyDoneToast.value = true
      setTimeout(() => { classifyDoneToast.value = false }, 4000)
      // Also refresh unclassified count after tree settles
      setTimeout(async () => {
        try {
          const u = await fetchAutoClassifyUnclassifiedCount('kb')
          unclassifiedCount.value = u.unclassified
        } catch { /* ignore */ }
      }, 1500)
    }
  } catch { /* ignore */ }
}

// Poll every 5s while there are pending items; also called after addPaper
function _startPendingPoll() {
  if (_pendingPollTimer) return
  _pendingPollTimer = setInterval(async () => {
    await refreshPendingClassify()
    if (pendingClassifyCount.value === 0 && _pendingPollTimer) {
      clearInterval(_pendingPollTimer)
      _pendingPollTimer = null
    }
  }, 5000)
}

watch(pendingClassifyCount, (val) => {
  if (val > 0) _startPendingPoll()
})

// Also refresh when kbTree is updated (i.e. after a paper is added)
watch(() => props.kbTree, () => {
  refreshPendingClassify()
})

onMounted(async () => {
  refreshPendingClassify()
  try {
    const u = await fetchAutoClassifyUnclassifiedCount('kb')
    unclassifiedCount.value = u.unclassified
  } catch { /* ignore */ }
})
onBeforeUnmount(() => {
  if (_pendingPollTimer) clearInterval(_pendingPollTimer)
})

// ---- Paper expand / notes ----
const expandedPapers = ref<Set<string>>(new Set())
const paperNotes = ref<Map<string, KbNote[]>>(new Map())

async function togglePaper(paperId: string) {
  const next = new Set(expandedPapers.value)
  if (next.has(paperId)) {
    next.delete(paperId)
  } else {
    next.add(paperId)
    // load notes if not cached
    if (!paperNotes.value.has(paperId)) {
      await loadPaperNotes(paperId)
    }
  }
  expandedPapers.value = next
}

async function loadPaperNotes(paperId: string) {
  try {
    const res = await fetchNotes(paperId, props.scope)
    const next = new Map(paperNotes.value)
    next.set(paperId, res.notes)
    paperNotes.value = next
  } catch {}
}

// ---- KB paper derivative menu ----
const kbDerivativeMenu = ref<{
  x: number; y: number
  paper: KbPaper
  derivative: 'mineru' | 'zh' | 'bilingual'
} | null>(null)

function openKbDerivativeMenu(e: MouseEvent, paper: KbPaper, derivative: 'mineru' | 'zh' | 'bilingual') {
  e.stopPropagation()
  kbDerivativeMenu.value = { x: e.clientX, y: e.clientY, paper, derivative }
}

function kbDerivativeMenuItems(): KbMenuItem[] {
  return [
    { key: 'download-md', label: '下载 MD' },
    { key: 'download-docx', label: '下载 DOCX' },
    { key: 'download-pdf', label: '下载 PDF' },
    { key: 'regenerate', label: '重新生成' },
    { key: 'delete', label: '删除', danger: true },
  ]
}

async function handleKbDerivativeMenuSelect(key: string) {
  const ctx = kbDerivativeMenu.value
  kbDerivativeMenu.value = null
  if (!ctx) return
  const { paper, derivative } = ctx
  if (key === 'download-md' || key === 'download-docx' || key === 'download-pdf') {
    const fmt = key.replace('download-', '') as 'md' | 'docx' | 'pdf'
    try {
      await downloadPaperFile(paper.paper_id, derivative, props.scope as 'kb' | 'mypapers', fmt)
    } catch (e: any) {
      alert(`下载失败：${e?.message ?? '未知错误'}`)
    }
    return
  }
  if (key === 'delete') {
    try {
      await deleteKbPaperDerivative(paper.paper_id, derivative, props.scope)
      emit('refresh')
    } catch {}
    return
  }
  if (key === 'regenerate') {
    try {
      if (derivative === 'mineru') {
        await processKbPaper(paper.paper_id, props.scope)
      } else {
        await retranslateKbPaper(paper.paper_id, props.scope)
      }
      emit('refresh')
      _startKbPolling()
    } catch {}
  }
}

// ---- KB paper process/translate polling ----
let _kbPollTimer: ReturnType<typeof setInterval> | null = null

function _kbPapersHaveActivity(): boolean {
  const allPapers = [
    ...(props.kbTree?.papers ?? []),
    ...(() => {
      const out: KbPaper[] = []
      function walk(folders: typeof props.kbTree.folders) {
        for (const f of folders) {
          out.push(...(f.papers ?? []))
          if (f.children?.length) walk(f.children)
        }
      }
      walk(props.kbTree?.folders ?? [])
      return out
    })(),
  ]
  return allPapers.some(
    p =>
      p.process_status === 'processing' ||
      p.process_status === 'pending' ||
      p.translate_status === 'processing',
  )
}

function _startKbPolling() {
  if (!_kbPollTimer) {
    _kbPollTimer = setInterval(() => {
      if (!_kbPapersHaveActivity()) {
        _stopKbPolling()
      }
      emit('refresh')
    }, 3000)
  }
}

function _stopKbPolling() {
  if (_kbPollTimer) {
    clearInterval(_kbPollTimer)
    _kbPollTimer = null
  }
}

async function handleKbPaperProcess(paper: KbPaper) {
  try {
    await processKbPaper(paper.paper_id, props.scope)
    emit('refresh')
    _startKbPolling()
  } catch {}
}

async function handleKbPaperTranslate(paper: KbPaper) {
  if (ent.isGated('translate')) {
    void router.push('/profile?tab=subscription')
    return
  }
  try {
    await translateKbPaper(paper.paper_id, props.scope)
    emit('refresh')
    _startKbPolling()
  } catch {}
}

// ---- My Papers notes (for "+" button) ----
const myPaperNotes = ref<Map<string, KbNote[]>>(new Map())
// Track which mypapers have their notes loaded
const myPaperNotesLoaded = ref<Set<string>>(new Set())

async function loadMyPaperNotes(paperId: string) {
  try {
    const res = await fetchNotes(paperId, 'mypapers')
    const next = new Map(myPaperNotes.value)
    next.set(paperId, res.notes)
    myPaperNotes.value = next
    const loaded = new Set(myPaperNotesLoaded.value)
    loaded.add(paperId)
    myPaperNotesLoaded.value = loaded
  } catch {}
}

// When expanding mypapers links, also load notes
const _origToggleMyPaperPaperLinks = toggleMyPaperPaperLinks

// Override toggleMyPaperPaperLinks to also load notes
function toggleMyPaperPaperLinksWithNotes(paperId: string) {
  const wasExpanded = myPaperExpandedPaperLinks.value.has(paperId)
  _origToggleMyPaperPaperLinks(paperId)
  if (!wasExpanded && !myPaperNotesLoaded.value.has(paperId)) {
    loadMyPaperNotes(paperId)
  }
}

// My Papers "+" add menu
const myPaperAddMenuPaperId = ref<string | null>(null)
function toggleMyPaperAddMenu(paperId: string) {
  myPaperAddMenuPaperId.value = myPaperAddMenuPaperId.value === paperId ? null : paperId
}

async function handleMyPaperCreateNote(paperId: string) {
  myPaperAddMenuPaperId.value = null
  try {
    const note = await createNote(paperId, '未命名笔记', '', 'mypapers')
    const next = new Set(myPaperExpandedPaperLinks.value)
    next.add(paperId)
    myPaperExpandedPaperLinks.value = next
    await loadMyPaperNotes(paperId)
    emit('openNote', { id: note.id, paperId })
  } catch {}
}

const myPaperFileInputRef = ref<HTMLInputElement | null>(null)
const myPaperUploadTargetPaperId = ref<string>('')

function handleMyPaperUploadFile(paperId: string) {
  myPaperAddMenuPaperId.value = null
  if (ent.isGated('note_file_upload')) {
    myPapersError.value = '笔记文件附件需要 Pro 套餐，请升级后使用。'
    return
  }
  myPaperUploadTargetPaperId.value = paperId
  myPaperFileInputRef.value?.click()
}

async function onMyPaperFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !myPaperUploadTargetPaperId.value) return
  try {
    await uploadNoteFile(myPaperUploadTargetPaperId.value, file, 'mypapers')
    const next = new Set(myPaperExpandedPaperLinks.value)
    next.add(myPaperUploadTargetPaperId.value)
    myPaperExpandedPaperLinks.value = next
    await loadMyPaperNotes(myPaperUploadTargetPaperId.value)
  } catch {}
  input.value = ''
}

async function handleMyPaperAddLink(paperId: string) {
  myPaperAddMenuPaperId.value = null
  const url = window.prompt('请输入链接 URL')
  if (!url) return
  const title = window.prompt('链接标题（可选）') || url
  try {
    await addNoteLink(paperId, title, url, 'mypapers')
    const next = new Set(myPaperExpandedPaperLinks.value)
    next.add(paperId)
    myPaperExpandedPaperLinks.value = next
    await loadMyPaperNotes(paperId)
  } catch {}
}

async function handleDeleteMyPaperNote(noteId: number, paperId: string) {
  try {
    await apiDeleteNote(noteId)
    await loadMyPaperNotes(paperId)
  } catch {}
}

function openMyPaperNoteMenu(e: MouseEvent, note: KbNote) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'download-note', label: '下载/导出' },
      { key: 'delete-mp-note', label: '删除笔记', danger: true },
    ],
    target: { type: 'mypapers-note' as const, note },
  }
}

// Batch download state
const showBatchDownloadDialog = ref(false)
const batchDownloadFileTypes = ref<('pdf' | 'mineru' | 'zh' | 'bilingual')[]>(['pdf', 'mineru', 'zh', 'bilingual'])
const batchDownloadIncludeNotes = ref(false)
let _batchDownloading = false

async function startBatchDownload() {
  if (_batchDownloading) return
  _batchDownloading = true
  showBatchDownloadDialog.value = false
  try {
    const scope = activeTab.value === 'mypapers' ? 'mypapers' : 'kb'
    const items: BatchDownloadItem[] = [...checkedPapers.value].map(pid => ({
      paper_id: pid,
      file_types: [...batchDownloadFileTypes.value],
      scope: scope as 'kb' | 'mypapers',
      include_notes: batchDownloadIncludeNotes.value,
    }))
    await downloadBatch(items)
  } catch {}
  _batchDownloading = false
}

// ---- Note actions ----
async function handleCreateNote(paperId: string) {
  try {
    const note = await createNote(paperId, '未命名笔记', '', props.scope)
    trackEvent('kb_note_create', { targetType: 'paper', targetId: paperId })
    // expand and refresh notes
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    emit('refresh')
    // 打开右侧笔记编辑，同时携带所属论文 ID
    emit('openNote', { id: note.id, paperId })
  } catch {}
}

// Hidden file input ref
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetPaperId = ref<string>('')

function handleUploadFile(paperId: string) {
  if (ent.isGated('note_file_upload')) {
    void router.push('/profile?tab=subscription')
    return
  }
  uploadTargetPaperId.value = paperId
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !uploadTargetPaperId.value) return
  try {
    await uploadNoteFile(uploadTargetPaperId.value, file, props.scope)
    const next = new Set(expandedPapers.value)
    next.add(uploadTargetPaperId.value)
    expandedPapers.value = next
    await loadPaperNotes(uploadTargetPaperId.value)
    emit('refresh')
  } catch {}
  // reset input
  input.value = ''
}

async function handleAddLink(paperId: string) {
  const url = window.prompt('请输入链接 URL')
  if (!url) return
  const title = window.prompt('链接标题（可选）') || url
  try {
    await addNoteLink(paperId, title, url, props.scope)
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    emit('refresh')
  } catch {}
}

async function handleDeleteNote(noteId: number) {
  try {
    await apiDeleteNote(noteId)
    // refresh all expanded papers' notes
    for (const pid of expandedPapers.value) {
      await loadPaperNotes(pid)
    }
    emit('refresh')
  } catch {}
}

function noteIcon(type: string): string {
  if (type === 'file') return '📎'
  if (type === 'link') return '🔗'
  return '📝'
}

function openNoteMenu(e: MouseEvent, note: KbNote) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'download-note', label: '下载/导出' },
      { key: 'delete', label: '删除笔记', danger: true },
    ],
    target: { type: 'note' as const, note },
  }
}

function onNoteClick(note: KbNote) {
  if (note.type === 'link' && note.file_url) {
    // 检测内部论文链接（/papers/xxx），在右侧面板打开而非新标签页
    const internalPaperMatch = note.file_url.match(/^\/papers\/(.+)$/)
    if (internalPaperMatch) {
      emit('openPaper', internalPaperMatch[1])
      return
    }
    openExternal(note.file_url)
  } else if (note.type === 'file' && note.file_path) {
    const isPdf =
      (note.mime_type || '').toLowerCase() === 'application/pdf' ||
      note.file_path.toLowerCase().endsWith('.pdf') ||
      (note.title || '').toLowerCase().endsWith('.pdf')
    if (isPdf) {
      emit('openPdf', {
        paperId: note.paper_id,
        filePath: note.file_path,
        title: note.title,
      })
      return
    }
    openExternal(`${API_ORIGIN}/static/kb_files/${note.file_path}`)
  } else {
    emit('openNote', { id: note.id, paperId: note.paper_id })
  }
}

// Root-level paper add menu
const rootAddMenuPaperId = ref<string | null>(null)
function toggleRootAddMenu(paperId: string) {
  rootAddMenuPaperId.value = rootAddMenuPaperId.value === paperId ? null : paperId
}

// Expose method for parent to refresh notes after editing
async function refreshAllExpandedNotes() {
  for (const pid of expandedPapers.value) {
    await loadPaperNotes(pid)
  }
}

// 供父组件直接更新某条笔记的标题，避免必须依赖重新拉取列表
function updateNoteTitle(paperId: string, noteId: number, title: string) {
  const current = paperNotes.value.get(paperId)
  if (!current) return
  const nextNotes = current.map((n) =>
    n.id === noteId
      ? { ...n, title }
      : n,
  )
  const nextMap = new Map(paperNotes.value)
  nextMap.set(paperId, nextNotes)
  paperNotes.value = nextMap
}

function switchToMyPapersTab() {
  activeTab.value = 'mypapers'
}

function switchToPapersTab() {
  activeTab.value = 'papers'
}

function switchToResearchTab() {
  if (activeTab.value === 'research') {
    // 已在 research tab，watch 不会重新触发，需手动刷新列表
    loadResearchSessions()
    researchTabRef.value?.switchToSaved()
  } else {
    activeTab.value = 'research'
    // SidebarResearchTab 在下一 tick 挂载后再调用 load，避免 ref 为 null
    nextTick(() => {
      loadResearchSessions()
      researchTabRef.value?.switchToSaved()
    })
  }
}

function handleResearchTabClick() {
  if (activeTab.value === 'research') {
    // 已在 research tab：再次点击时仍然通知父组件重置到深度研究首页
    emit('tabChanged', 'research')
  }
  activeTab.value = 'research'
}

defineExpose({ refreshAllExpandedNotes, updateNoteTitle, refreshMyPapers, switchToMyPapersTab, loadMyPapers, onPaperInspirationDone, switchToResearchTab, switchToPapersTab })
</script>

<template>
  <aside class="w-[80vw] max-w-[340px] lg:w-[var(--sidebar-w)] h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0">
    <!-- Hidden file input for uploads -->
    <input
      ref="fileInputRef"
      type="file"
      class="hidden"
      @change="onFileSelected"
    />

    <!-- ============ Nav Menu ============ -->
    <div class="px-3 pt-2.5 pb-3 flex flex-col shrink-0 space-y-0.5">
      <!-- Minimal header: context label + collapse button -->
      <div class="flex items-center justify-between px-1 h-8 mb-1">
        <span class="text-[10.5px] font-semibold text-text-muted/45 tracking-widest uppercase select-none">研究空间</span>
        <button
          class="w-[42px] h-[42px] flex items-center justify-center rounded-md text-text-muted/35 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer shrink-0"
          title="收起侧边栏"
          @click="emit('toggleSidebar')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
          </svg>
        </button>
      </div>

      <!-- 知识库 / 灵感涌现 (tab: papers) -->
      <button
        class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-lg text-[15px] transition-all duration-150 cursor-pointer border-none text-left"
        :class="activeTab === 'papers'
          ? 'bg-tinder-pink/8 text-tinder-pink font-semibold'
          : 'text-text-primary/75 font-medium hover:bg-bg-hover/70 hover:text-text-primary'"
        @click="activeTab = 'papers'; selectFolder(null)"
      >
        <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
        <span>{{ title }}</span>
        <!-- Auto-classify pending badge -->
        <span
          v-if="pendingClassifyCount > 0"
          class="ml-auto flex items-center gap-1 text-[10px] font-medium text-amber-400 bg-amber-400/10 border border-amber-400/25 px-1.5 py-0.5 rounded-full leading-none"
          title="AI 正在自动分类这些论文"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse inline-block"></span>
          {{ pendingClassifyCount }}
        </span>
        <!-- Classify-done flash badge -->
        <Transition enter-from-class="opacity-0 scale-90" leave-to-class="opacity-0 scale-90" enter-active-class="transition-all duration-300" leave-active-class="transition-all duration-300">
          <span
            v-if="classifyDoneToast && pendingClassifyCount === 0"
            class="ml-auto flex items-center gap-1 text-[10px] font-medium text-tinder-green bg-tinder-green/10 border border-tinder-green/25 px-1.5 py-0.5 rounded-full leading-none"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            分类完成
          </span>
        </Transition>
      </button>

      <!-- 对比库 (tab: compare) -->
      <button
        class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-lg text-[15px] transition-all duration-150 cursor-pointer border-none text-left"
        :class="activeTab === 'compare'
          ? 'bg-tinder-pink/8 text-tinder-pink font-semibold'
          : 'text-text-primary/75 font-medium hover:bg-bg-hover/70 hover:text-text-primary'"
        @click="activeTab = 'compare'"
      >
        <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/>
        </svg>
        <span>对比库</span>
      </button>

      <!-- 我的论文 (tab: mypapers) -->
      <button
        v-if="thirdTab === 'mypapers'"
        class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-lg text-[15px] transition-all duration-150 cursor-pointer border-none text-left"
        :class="activeTab === 'mypapers'
          ? 'bg-tinder-pink/8 text-tinder-pink font-semibold'
          : 'text-text-primary/75 font-medium hover:bg-bg-hover/70 hover:text-text-primary'"
        @click="activeTab = 'mypapers'"
      >
        <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
        </svg>
        <span>我的论文</span>
      </button>

      <!-- 论文灵感 (tab: paper-inspiration) -->
      <button
        v-else-if="thirdTab === 'paper-inspiration'"
        class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-lg text-[15px] transition-all duration-150 cursor-pointer border-none text-left"
        :class="activeTab === 'paper-inspiration'
          ? 'bg-tinder-pink/8 text-tinder-pink font-semibold'
          : 'text-text-primary/75 font-medium hover:bg-bg-hover/70 hover:text-text-primary'"
        @click="activeTab = 'paper-inspiration'"
      >
        <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
        </svg>
        <span>论文灵感</span>
      </button>

      <!-- 深度研究 (tab: research) -->
      <button
        v-if="fourthTab === 'research'"
        class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-lg text-[15px] transition-all duration-150 cursor-pointer border-none text-left"
        :class="activeTab === 'research'
          ? 'bg-tinder-pink/8 text-tinder-pink font-semibold'
          : 'text-text-primary/75 font-medium hover:bg-bg-hover/70 hover:text-text-primary'"
        @click="handleResearchTabClick"
      >
        <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v11m0 0H5a2 2 0 0 1-2-2V7m6 7h10m0 0a2 2 0 0 0 2-2V7m-12 7v4m0 0h4m-4 0H5"/>
          <circle cx="17" cy="18" r="3"/><path d="m21 22-1.5-1.5"/>
        </svg>
        <span>深度研究</span>
      </button>
    </div>

    <!-- ============ Sidebar Content Area ============ -->
    <div class="flex-1 min-w-0 flex flex-col h-full overflow-hidden">

    <!-- Header: date selector -->
    <div class="px-3 pt-3 pb-2 border-t border-b border-border">

      <!-- Date display + optional jump dropdown -->
      <div class="relative" :class="(activeTab === 'papers' || activeTab === 'mypapers') ? 'mb-2' : ''">
        <!-- Transparent overlay to close dropdown on outside click -->
        <div v-if="showDateJump" class="fixed inset-0 z-40" @click="showDateJump = false" />

        <!-- Current date pill (read-only display, with optional jump button) -->
        <DatePill :date="selectedDate">
          <button
            v-if="dates.length > 1"
            class="shrink-0 flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] text-text-muted/70 hover:text-text-primary hover:bg-bg-hover transition-colors cursor-pointer border-none bg-transparent"
            :title="showDateJump ? '关闭日期跳转' : '跳转到其他日期'"
            @click.stop="showDateJump = !showDateJump"
          >
            <span class="leading-none">跳转</span>
            <svg class="w-3 h-3 transition-transform duration-200" :class="showDateJump ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
        </DatePill>

        <!-- Calendar date picker -->
        <div
          v-if="showDateJump && dates.length > 1"
          class="absolute top-full left-0 right-0 mt-1 z-50 bg-bg-card border border-border rounded-xl shadow-xl overflow-hidden"
        >
          <DatePicker
            :model-value="selectedDate"
            :available-dates="dates"
            @update:model-value="(d) => { $emit('update:selectedDate', d); showDateJump = false }"
          />
        </div>
      </div>

      <!-- Toolbar row: merged for papers + mypapers tabs -->
      <div v-if="activeTab === 'papers' || activeTab === 'mypapers'" class="flex items-center justify-between gap-2">
        <span class="text-[11px] text-text-muted/50 select-none flex items-center gap-1.5">
          <template v-if="totalPaperCount > 0">{{ totalPaperCount }} 篇</template>
          <template v-else>AI 前沿</template>
          <!-- Pending classify indicator in toolbar -->
          <span
            v-if="pendingClassifyCount > 0 && activeTab === 'papers'"
            class="flex items-center gap-1 text-[10px] text-amber-400/80"
            title="AI 正在后台自动分类这些论文"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-amber-400/70 animate-pulse inline-block"></span>
            {{ pendingClassifyCount }} 篇待分类
          </span>
        </span>
        <!-- KB storage indicator (shows when near or at limit) -->
        <span
          v-if="ent.loaded.value && ent.kbPaperStorage.value.limit !== null"
          class="text-[10px] select-none ml-1"
          :class="kbStorageNearLimit ? 'text-amber-400' : 'text-text-muted/40'"
          :title="`知识库：${ent.kbPaperStorage.value.used}/${ent.kbPaperStorage.value.limit} 篇`"
        >{{ ent.kbPaperStorage.value.used }}/{{ ent.kbPaperStorage.value.limit }}</span>
        <div class="flex items-center gap-1.5">
          <button
            class="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-transparent border cursor-pointer transition-colors"
            :class="batchMode
              ? 'border-tinder-pink/60 text-tinder-pink bg-tinder-pink/5'
              : 'border-border text-text-muted hover:text-text-secondary hover:border-border-light'"
            title="批量选择论文，可发起对比分析或深度研究 Q&A"
            @click="toggleBatchMode"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="5" width="4" height="4" rx="1"/><rect x="3" y="11" width="4" height="4" rx="1"/><rect x="3" y="17" width="4" height="4" rx="1"/><line x1="10" y1="7" x2="21" y2="7"/><line x1="10" y1="13" x2="21" y2="13"/><line x1="10" y1="19" x2="21" y2="19"/>
            </svg>
            批量
          </button>
          <button
            class="flex items-center gap-1 text-[11px] px-2 py-1 rounded-md bg-transparent border border-border text-text-muted hover:text-tinder-pink hover:border-tinder-pink/40 cursor-pointer transition-colors"
            title="新建文件夹"
            @click="activeTab === 'papers' ? startNewFolder(activeFolderId) : startMyPaperNewFolder(myPaperActiveFolderId)"
          >
            <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
            </svg>
            新建
          </button>
        </div>
      </div>
    </div>

    <!-- ============ Papers tab ============ -->
    <div v-if="activeTab === 'papers'" class="flex-1 overflow-y-auto p-2" @click="selectFolder(null)">
      <!-- New folder input (root level) -->
      <div v-if="showNewFolderInput && newFolderParentId === null" class="flex items-center gap-2 px-2 py-2 mb-1">
        <svg class="shrink-0 text-text-muted" style="width:18px;height:18px;"
             viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <input
          v-model="newFolderName"
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-tinder-blue/50"
          placeholder="文件夹名称..."
          autofocus
          @keydown.enter="confirmNewFolder"
          @keydown.escape="showNewFolderInput = false"
          @blur="confirmNewFolder"
        />
      </div>

      <!-- Folders -->
      <SidebarFolder
        v-for="folder in kbTree.folders"
        :key="folder.id"
        :folder="folder"
        :depth="0"
        :expanded-folders="expandedFolders"
        :active-folder-id="activeFolderId"
        :renaming-folder-id="renamingFolderId"
        :renaming-folder-name="renamingFolderName"
        :show-new-folder-input="showNewFolderInput"
        :new-folder-parent-id="newFolderParentId"
        :checked-papers="checkedPapers"
        :batch-mode="batchMode"
        :expanded-papers="expandedPapers"
        :paper-notes="paperNotes"
        :renaming-paper-id="renamingPaperId"
        :renaming-paper-title="renamingPaperTitle"
        @toggle-folder="toggleFolder"
        @select-folder="selectFolder"
        @open-folder-menu="openFolderMenu"
        @open-paper-menu="openPaperMenu"
        @open-paper="(id: string) => handleOpenKbPaper(id)"
        @toggle-check="toggleCheck"
        @update:renaming-name="renamingFolderName = $event"
        @confirm-rename="confirmRenameFolder"
        @cancel-rename="renamingFolderId = null"
        @update:new-folder-name="newFolderName = $event"
        @confirm-new-folder="confirmNewFolder"
        @cancel-new-folder="showNewFolderInput = false"
        @toggle-paper="togglePaper"
        @create-note="handleCreateNote"
        @upload-file="handleUploadFile"
        @add-link="handleAddLink"
        @open-note="(payload) => emit('openNote', payload)"
        @open-pdf="(payload) => emit('openPdf', payload)"
        @delete-note="handleDeleteNote"
        @update:renaming-paper-title="renamingPaperTitle = $event"
        @confirm-rename-paper="confirmRenamePaper"
        @cancel-rename-paper="renamingPaperId = null"
      />

      <!-- Unclassified nudge: shown when ≥10 papers are in 「未分类」 -->
      <div
        v-if="unclassifiedCount >= 10 && activeTab === 'papers'"
        class="mx-2 mt-2 mb-1 flex items-start gap-2 px-2.5 py-2 rounded-lg bg-sky-500/8 border border-sky-500/20 cursor-pointer hover:bg-sky-500/12 transition-colors"
        title="前往自动分类设置"
        @click="$router.push('/settings?nav=auto_classify')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span class="text-[10px] text-sky-400 leading-tight">
          「未分类」有 {{ unclassifiedCount }} 篇，可在<strong> 设置 → 自动分类 </strong>添加目录并重新分类
        </span>
      </div>

      <!-- Root papers -->
      <div v-if="kbTree.papers.length > 0" class="mt-1">
        <div
          v-for="paper in kbTree.papers"
          :key="paper.paper_id"
          class="border-b border-border/30 last:border-b-0"
        >
          <!-- Paper row -->
          <div
            class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors group border-l-2"
            :class="(!paper.read_status || paper.read_status === 'unread') ? 'border-tinder-green/60' : 'border-transparent'"
          >
            <!-- Checkbox (only in batch mode) -->
            <label
              v-if="batchMode"
              class="kb-checkbox shrink-0"
              @click.stop
            >
              <input
                type="checkbox"
                :checked="checkedPapers.has(paper.paper_id)"
                @change="toggleCheck(paper.paper_id)"
              />
              <span class="kb-checkbox-mark"></span>
            </label>

            <!-- Expand arrow -->
            <button
              v-if="(paper.note_count ?? 0) > 0"
              class="w-4 h-4 flex items-center justify-center text-[8px] text-text-muted bg-transparent border-none cursor-pointer shrink-0 transition-transform duration-150"
              :class="expandedPapers.has(paper.paper_id) ? 'rotate-90' : ''"
              @click.stop="togglePaper(paper.paper_id)"
            >▶</button>
            <div v-else class="w-4 shrink-0"></div>

            <!-- Paper content (inline rename or normal) -->
            <template v-if="renamingPaperId === paper.paper_id">
              <div
                class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
                :style="{ background: avatarColor(paper.paper_id) }"
              >
                {{ (paper.paper_data.institution || '?').slice(0, 2) }}
              </div>
              <input
                v-model="renamingPaperTitle"
                class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-tinder-pink/50 min-w-0"
                autofocus
                @keydown.enter="confirmRenamePaper"
                @keydown.escape="renamingPaperId = null"
                @blur="confirmRenamePaper"
                @click.stop
              />
            </template>
            <button
              v-else
              class="flex-1 flex items-center gap-2 min-w-0 bg-transparent border-none cursor-pointer text-left p-0"
              @click="handleOpenKbPaper(paper.paper_id)"
            >
              <div
                class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
                :style="{ background: avatarColor(paper.paper_id) }"
              >
                {{ (paper.paper_data.institution || '?').slice(0, 2) }}
              </div>
              <div class="min-w-0 flex-1">
                <div
                  class="text-xs truncate"
                  :class="(!paper.read_status || paper.read_status === 'unread') ? 'font-semibold text-text-primary' : 'font-medium text-text-secondary'"
                >
                  {{ paper.paper_data.short_title }}
                </div>
                <div class="text-[10px] text-text-muted truncate">
                  {{ paper.paper_data.institution }} · {{ paper.paper_id }}
                </div>
              </div>
            </button>

            <!-- + Add button -->
            <div class="relative shrink-0">
              <button
                class="w-6 h-6 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
                @click.stop="toggleRootAddMenu(paper.paper_id)"
                title="添加笔记/文件"
              >+</button>

              <div
                v-if="rootAddMenuPaperId === paper.paper_id"
                class="absolute right-0 top-6 z-50 w-36 bg-bg-elevated border border-border rounded-lg shadow-lg py-1 text-xs"
                @click.stop
              >
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleCreateNote(paper.paper_id)"
                >
                  <span>📝</span> 新建笔记
                </button>
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleUploadFile(paper.paper_id)"
                >
                  <span>📎</span> 上传文件
                </button>
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleAddLink(paper.paper_id)"
                >
                  <span>🔗</span> 添加链接
                </button>
              </div>
            </div>

            <!-- Menu button -->
            <button
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
              @click.stop="openPaperMenu($event, paper)"
            >⋯</button>
          </div>

          <!-- Expanded area for root paper: file links + notes -->
          <div v-if="expandedPapers.has(paper.paper_id)" class="pb-1">
            <!-- PDF link -->
            <div
              v-if="paper.pdf_static_url"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors cursor-pointer"
              style="padding-left: 50px; padding-right: 8px;"
              @click="emit('openPdf', { paperId: paper.paper_id, filePath: paper.pdf_static_url!.replace(/^\/static\/kb_files\//, ''), title: paper.paper_data.short_title || paper.paper_id })"
            >
              <span class="text-xs shrink-0">📄</span>
              <span class="text-xs text-text-secondary truncate flex-1">原 PDF</span>
              <button type="button" class="shrink-0 w-5 h-5 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded text-[10px] opacity-0 group-hover:opacity-100 transition-opacity" title="下载" @click.stop="downloadPaperFile(paper.paper_id, 'pdf', props.scope as 'kb' | 'mypapers')">↓</button>
            </div>
            <!-- MinerU link -->
            <div
              v-if="paper.mineru_static_url"
              class="flex items-center gap-1 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/der"
              style="padding-left: 50px; padding-right: 8px;"
            >
              <div class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer" @click="emit('viewMd', { paperId: paper.paper_id, title: (paper.paper_data.short_title || paper.paper_id) + ' · MinerU 解析', pdfUrl: paper.pdf_static_url ? `${API_ORIGIN}${paper.pdf_static_url}` : null, mdUrl: `${API_ORIGIN}${paper.mineru_static_url}`, viewMode: 'mineru', mineruUrl: paper.mineru_static_url ? `${API_ORIGIN}${paper.mineru_static_url}` : null, zhUrl: paper.zh_static_url ? `${API_ORIGIN}${paper.zh_static_url}` : null, bilingualUrl: paper.bilingual_static_url ? `${API_ORIGIN}${paper.bilingual_static_url}` : null })">
                <span class="text-xs shrink-0">📋</span>
                <span class="text-xs text-text-secondary truncate flex-1">MinerU 解析 (Markdown)</span>
              </div>
              <button type="button" class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded text-[10px] opacity-0 group-hover/der:opacity-100 transition-opacity" title="更多" @click.stop="openKbDerivativeMenu($event, paper, 'mineru')">⋯</button>
            </div>
            <!-- MinerU not yet processed -->
            <div
              v-else-if="paper.process_status === 'none' || !paper.process_status"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors cursor-pointer"
              style="padding-left: 50px; padding-right: 8px;"
              @click="handleKbPaperProcess(paper)"
            >
              <span class="text-xs shrink-0">✨</span>
              <span class="text-xs text-tinder-pink truncate flex-1 font-medium">生成 MinerU 解析</span>
            </div>
            <!-- Processing in progress -->
            <div
              v-else-if="paper.process_status === 'processing' || paper.process_status === 'pending'"
              class="flex items-center gap-2 py-1.5 px-2 rounded"
              style="padding-left: 50px; padding-right: 8px;"
            >
              <span class="inline-block text-amber-500 animate-spin text-xs leading-none">⟳</span>
              <span class="text-xs text-amber-500 truncate flex-1">{{ kbPaperStepLabel(paper.process_step || '') }}</span>
            </div>
            <!-- Process failed -->
            <div
              v-else-if="paper.process_status === 'failed'"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover cursor-pointer"
              style="padding-left: 50px; padding-right: 8px;"
              @click="handleKbPaperProcess(paper)"
            >
              <span class="text-xs shrink-0">❌</span>
              <span class="text-xs text-red-500 truncate flex-1" :title="paper.process_error">{{ paper.process_error || '处理失败，点击重试' }}</span>
            </div>
            <!-- Chinese translation -->
            <div
              v-if="paper.zh_static_url"
              class="flex items-center gap-1 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/der"
              style="padding-left: 50px; padding-right: 8px;"
            >
              <div class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer" @click="emit('viewMd', { paperId: paper.paper_id, title: (paper.paper_data.short_title || paper.paper_id) + ' · 中文翻译', pdfUrl: paper.pdf_static_url ? `${API_ORIGIN}${paper.pdf_static_url}` : null, mdUrl: `${API_ORIGIN}${paper.zh_static_url}`, viewMode: 'zh', mineruUrl: paper.mineru_static_url ? `${API_ORIGIN}${paper.mineru_static_url}` : null, zhUrl: paper.zh_static_url ? `${API_ORIGIN}${paper.zh_static_url}` : null, bilingualUrl: paper.bilingual_static_url ? `${API_ORIGIN}${paper.bilingual_static_url}` : null, translateInProgress: paper.translate_status === 'processing' })">
                <span class="text-xs shrink-0">🇨🇳</span>
                <span class="text-xs text-text-secondary truncate flex-1">中文翻译版</span>
              </div>
              <button type="button" class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded text-[10px] opacity-0 group-hover/der:opacity-100 transition-opacity" title="更多" @click.stop="openKbDerivativeMenu($event, paper, 'zh')">⋯</button>
            </div>
            <!-- Bilingual -->
            <div
              v-if="paper.bilingual_static_url"
              class="flex items-center gap-1 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/der"
              style="padding-left: 50px; padding-right: 8px;"
            >
              <div class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer" @click="emit('viewMd', { paperId: paper.paper_id, title: (paper.paper_data.short_title || paper.paper_id) + ' · 中英对照', pdfUrl: paper.pdf_static_url ? `${API_ORIGIN}${paper.pdf_static_url}` : null, mdUrl: `${API_ORIGIN}${paper.bilingual_static_url}`, viewMode: 'bilingual', mineruUrl: paper.mineru_static_url ? `${API_ORIGIN}${paper.mineru_static_url}` : null, zhUrl: paper.zh_static_url ? `${API_ORIGIN}${paper.zh_static_url}` : null, bilingualUrl: paper.bilingual_static_url ? `${API_ORIGIN}${paper.bilingual_static_url}` : null, translateInProgress: paper.translate_status === 'processing' })">
                <span class="text-xs shrink-0">🔀</span>
                <span class="text-xs text-text-secondary truncate flex-1">中英文对照版</span>
              </div>
              <button type="button" class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded text-[10px] opacity-0 group-hover/der:opacity-100 transition-opacity" title="更多" @click.stop="openKbDerivativeMenu($event, paper, 'bilingual')">⋯</button>
            </div>
            <!-- Generate translation button -->
            <div
              v-if="paper.mineru_static_url && !paper.zh_static_url && paper.translate_status !== 'processing'"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors cursor-pointer"
              style="padding-left: 50px; padding-right: 8px;"
              @click="handleKbPaperTranslate(paper)"
            >
              <span class="text-xs shrink-0">✨</span>
              <span class="text-xs text-tinder-pink truncate flex-1 font-medium">生成中文翻译与对照</span>
            </div>
            <!-- Translating in progress -->
            <!-- Translating in progress (show even when partial zh already exists) -->
            <div
              v-if="paper.mineru_static_url && paper.translate_status === 'processing'"
              class="flex items-center gap-2 py-1.5 px-2 rounded"
              style="padding-left: 50px; padding-right: 8px;"
            >
              <span class="text-xs shrink-0">⏳</span>
              <span class="text-xs text-amber-500 truncate flex-1">
                {{ paper.zh_static_url ? '翻译中（已可预览）' : '翻译中…' }}
              </span>
              <TranslateProgressRing :percent="paper.translate_progress ?? 0" />
            </div>
            <!-- Notes (exclude the auto-attached PDF note when the hardcoded 原 PDF link is already shown) -->
            <div
              v-for="note in (paperNotes.get(paper.paper_id) || []).filter(n => !(paper.pdf_static_url && n.type === 'file' && (n.title || '').toLowerCase().endsWith('.pdf')))"
              :key="note.id"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/note cursor-pointer"
              style="padding-left: 50px;"
              @click="onNoteClick(note)"
            >
              <span class="text-xs shrink-0">{{ noteIcon(note.type) }}</span>
              <span class="text-xs text-text-secondary truncate flex-1">{{ note.title }}</span>
              <button
                class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/note:opacity-100 transition-opacity"
                @click.stop="openNoteMenu($event, note)"
              >⋯</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="kbTree.folders.length === 0 && kbTree.papers.length === 0" class="text-center py-8">
        <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-brand-gradient-br opacity-60"></div>
        <p class="text-sm font-semibold text-text-primary mb-1">{{ emptyTitle }}</p>
        <p class="text-xs text-text-muted leading-relaxed px-4">
          {{ emptyDesc }}
        </p>
      </div>
    </div>

    <!-- ============ Compare tab ============ -->
    <SidebarCompareTab
      v-if="activeTab === 'compare'"
      ref="compareTabRef"
      :compare-tree="compareTree"
      @open-compare-result="emit('openCompareResult', $event)"
      @refresh-compare="emit('refreshCompare')"
      @open-menu="handleCompareMenu"
      @start-new-compare="handleStartNewCompareFromTab"
    />

    <!-- ============ My Papers tab ============ -->
    <div v-if="activeTab === 'mypapers'" class="flex-1 overflow-y-auto flex flex-col">
      <!-- Upload button -->
      <div class="px-3 pt-2 pb-1 shrink-0">
        <button
          class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold text-white bg-mypapers-gradient border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="emit('openUploadDialog')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          上传 / 导入论文
        </button>
      </div>

      <!-- Loading / error -->
      <div v-if="myPapersLoading && !myPaperTree" class="flex-1 flex items-center justify-center text-xs text-text-muted">
        加载中...
      </div>
      <div v-else-if="myPapersError" class="flex-1 flex items-center justify-center text-xs text-red-500 px-4 text-center">
        {{ myPapersError }}
      </div>

      <!-- Tree view -->
      <div v-else class="flex-1 overflow-y-auto p-2" @click="myPaperActiveFolderId = null">
        <!-- Empty state -->
        <div v-if="!myPaperTree || (myPaperTree.folders.length === 0 && myPaperTree.papers.length === 0)" class="text-center py-8">
          <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-mypapers-gradient-br opacity-60 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <p class="text-sm font-semibold text-text-primary mb-1">暂无论文</p>
          <p class="text-xs text-text-muted leading-relaxed px-4">上传 PDF 或导入 arXiv 链接，即可自动生成摘要</p>
        </div>

        <template v-else>
          <!-- Root new folder input -->
          <div v-if="showMyPaperNewFolderInput && myPaperNewFolderParentId === null" class="flex items-center gap-2 px-2 py-2 mb-1">
            <svg class="shrink-0 text-text-muted" style="width:18px;height:18px;"
                 viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <input
              v-model="myPaperNewFolderName"
              class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-tinder-blue/50"
              placeholder="文件夹名称..."
              autofocus
              @keydown.enter="confirmMyPaperNewFolder"
              @keydown.escape="showMyPaperNewFolderInput = false"
              @blur="confirmMyPaperNewFolder"
            />
          </div>

          <!-- Folders (tree) -->
          <UserPaperFolderItem
            v-for="folder in myPaperTree.folders"
            :key="folder.id"
            :folder="folder"
            :depth="0"
            :expanded-folders="myPaperExpandedFolders"
            :active-folder-id="myPaperActiveFolderId"
            :active-user-paper-id="activeUserPaperId"
            :active-view-md-key="activeViewMdKey"
            :renaming-folder-id="renamingMyPaperFolderId"
            :renaming-folder-name="renamingMyPaperFolderName"
            :show-new-folder-input="showMyPaperNewFolderInput"
            :new-folder-parent-id="myPaperNewFolderParentId"
            :new-folder-name="myPaperNewFolderName"
            :checked-papers="checkedPapers"
            :batch-mode="batchMode"
            :expanded-paper-links="myPaperExpandedPaperLinks"
            :paper-notes="myPaperNotes"
            :add-menu-paper-id="myPaperAddMenuPaperId"
            @toggle-folder="toggleMyPaperFolder"
            @select-folder="(id) => { myPaperActiveFolderId = id }"
            @open-folder-menu="openMyPaperFolderMenu"
            @open-paper-menu="openMyPaperMenu"
            @open-paper="(id) => emit('openUserPaper', id)"
            @toggle-check="toggleCheck"
            @toggle-paper-links="toggleMyPaperPaperLinksWithNotes"
            @view-user-paper-md="emitViewUserPaperMd"
            @open-paper-derivative-menu="(e, paper, d) => openMyPaperDerivativeMenu(e, paper, d)"
            @translate-paper="handleTranslateMyPaper"
            @update:renamingFolderName="(v) => { renamingMyPaperFolderName = v }"
            @confirm-rename="confirmRenameMyPaperFolder"
            @cancel-rename="renamingMyPaperFolderId = null"
            @update:newFolderName="(v) => { myPaperNewFolderName = v }"
            @confirm-new-folder="confirmMyPaperNewFolder"
            @cancel-new-folder="showMyPaperNewFolderInput = false"
            @toggle-add-menu="toggleMyPaperAddMenu"
            @create-note="handleMyPaperCreateNote"
            @upload-file="handleMyPaperUploadFile"
            @add-link="handleMyPaperAddLink"
            @open-note="onNoteClick"
            @open-note-menu="openMyPaperNoteMenu"
          />

          <!-- Root-level papers -->
          <div
            v-for="paper in myPaperTree.papers"
            :key="paper.paper_id"
            class="border-b border-border/30 last:border-b-0 flex flex-col transition-colors group"
            :class="[
              batchMode ? '' : 'hover:bg-bg-hover',
              !batchMode && activeUserPaperId === paper.paper_id ? 'bg-amber-500/8' : '',
            ]"
          >
            <div
              class="flex items-center gap-2 px-2 py-2 cursor-pointer"
              @click="batchMode ? toggleCheck(paper.paper_id) : emit('openUserPaper', paper.paper_id)"
            >
              <!-- Checkbox (batch mode) -->
              <input
                v-if="batchMode"
                type="checkbox"
                :checked="checkedPapers.has(paper.paper_id)"
                class="w-3.5 h-3.5 shrink-0 cursor-pointer rounded accent-tinder-pink"
                @click.stop
                @change="toggleCheck(paper.paper_id)"
              />
              <!-- Expand links (completed only, not batch) -->
              <button
                v-else-if="!batchMode && paper.process_status === 'completed'"
                type="button"
                class="shrink-0 w-4 h-4 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded p-0"
                title="展开文件链接"
                @click.stop="toggleMyPaperPaperLinksWithNotes(paper.paper_id)"
              >
                <svg
                  class="w-3 h-3 transition-transform"
                  :class="myPaperExpandedPaperLinks.has(paper.paper_id) ? 'rotate-90' : ''"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
              <div v-else class="shrink-0 w-4" />

              <!-- Avatar with status badge -->
              <div class="relative shrink-0">
                <div
                  class="w-8 h-8 rounded-full flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
                  :style="{ background: avatarColor(paper.paper_id) }"
                >
                  {{ (paper.title || '?').slice(0, 2) }}
                </div>
                <!-- Status badge -->
                <span
                  v-if="paper.process_status === 'processing' || paper.process_status === 'pending'"
                  class="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-bg-card flex items-center justify-center"
                >
                  <span class="inline-block text-amber-500 animate-spin text-[9px] leading-none">⟳</span>
                </span>
                <span
                  v-else-if="paper.process_status === 'failed'"
                  class="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-bg-card flex items-center justify-center text-[9px] leading-none text-red-500"
                >✕</span>
                <span
                  v-else-if="paper.process_status === 'completed'"
                  class="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-bg-card flex items-center justify-center text-[9px] leading-none text-green-500"
                >✓</span>
              </div>

              <!-- Paper info -->
              <div class="flex-1 min-w-0">
                <div class="text-xs font-medium text-text-primary truncate">
                  {{ paper.title || '（未命名）' }}
                </div>
                <div class="text-[10px] text-text-muted truncate">
                  <template v-if="paper.process_status === 'processing' || paper.process_status === 'pending'">
                    <span class="text-amber-500">{{ userPaperStepLabel(paper.process_step) }}</span>
                  </template>
                  <template v-else-if="paper.process_status === 'failed'">
                    <span class="text-red-500 truncate">{{ paper.process_error || '处理失败' }}</span>
                  </template>
                  <template v-else-if="paper.process_status === 'completed'">
                    <span>{{ paper.institution || paper.paper_id }}</span>
                  </template>
                  <template v-else>
                    <span>{{ paper.source_type === 'arxiv' ? `arXiv: ${paper.source_ref}` : paper.source_type === 'pdf' ? 'PDF 上传' : '手动录入' }}</span>
                  </template>
                </div>
              </div>

              <!-- Compare button (completed papers) -->
              <button
                v-if="!batchMode && paper.process_status === 'completed'"
                class="w-6 h-6 flex items-center justify-center bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                :class="isInCart(paper.paper_id) ? 'text-indigo-400' : 'text-text-muted hover:text-indigo-400'"
                :title="isInCart(paper.paper_id) ? '已在对比清单（点击移除）' : '加入对比清单'"
                @click.stop="isInCart(paper.paper_id) ? removeFromCompareCart(paper.paper_id) : addToCompareCart({ id: paper.paper_id, title: paper.title || paper.paper_id, source: 'mypapers', type: 'paper' })"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
                </svg>
              </button>
              <!-- + Add button (notes/file/link) -->
              <div v-if="!batchMode" class="relative shrink-0">
                <button
                  class="w-6 h-6 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  @click.stop="toggleMyPaperAddMenu(paper.paper_id)"
                  title="添加笔记/文件"
                >+</button>
                <div
                  v-if="myPaperAddMenuPaperId === paper.paper_id"
                  class="absolute right-0 top-6 z-50 w-36 bg-bg-elevated border border-border rounded-lg shadow-lg py-1 text-xs"
                  @click.stop
                >
                  <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="handleMyPaperCreateNote(paper.paper_id)"><span>📝</span> 新建笔记</button>
                  <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="handleMyPaperUploadFile(paper.paper_id)"><span>📎</span> 上传文件</button>
                  <button class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors" @click="handleMyPaperAddLink(paper.paper_id)"><span>🔗</span> 添加链接</button>
                </div>
              </div>
              <!-- Menu button -->
              <button
                class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
                @click.stop="openMyPaperMenu($event, paper)"
              >⋯</button>
            </div>

            <!-- Sub-links（样式对齐知识库笔记行） -->
            <div
              v-if="!batchMode && paper.process_status === 'completed' && myPaperExpandedPaperLinks.has(paper.paper_id)"
              class="pb-1"
              @click.stop
            >
              <div
                v-if="paper.pdf_static_url"
                :class="myPaperMdSubLinkClass(paper.paper_id, 'pdf')"
                style="padding-left: 50px; padding-right: 8px;"
                @click="emitViewUserPaperMd(paper, 'pdf')"
              >
                <span class="text-xs shrink-0">📄</span>
                <span class="text-xs text-text-secondary truncate flex-1">原 PDF</span>
              </div>
              <div
                v-if="paper.mineru_static_url"
                :class="[myPaperMdSubLinkClass(paper.paper_id, 'mineru'), 'group !gap-1']"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <div
                  class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
                  @click="emitViewUserPaperMd(paper, 'mineru')"
                >
                  <span class="text-xs shrink-0">📋</span>
                  <span class="text-xs text-text-secondary truncate flex-1">MinerU 解析 (Markdown)</span>
                </div>
                <button
                  type="button"
                  class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
                  title="更多"
                  @click.stop="openMyPaperDerivativeMenu($event, paper, 'mineru')"
                >⋯</button>
              </div>
              <div
                v-else
                class="flex items-center gap-2 py-1.5 px-2 rounded"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <span class="text-xs shrink-0 text-text-muted">📋</span>
                <span class="text-xs text-text-muted truncate flex-1">MinerU：请重新「处理」生成</span>
              </div>
              <div
                v-if="paper.zh_static_url"
                :class="[myPaperMdSubLinkClass(paper.paper_id, 'zh'), 'group !gap-1']"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <div
                  class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
                  @click="emitViewUserPaperMd(paper, 'zh')"
                >
                  <span class="text-xs shrink-0">🇨🇳</span>
                  <span class="text-xs text-text-secondary truncate flex-1">中文翻译版</span>
                </div>
                <button
                  type="button"
                  class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
                  title="更多"
                  @click.stop="openMyPaperDerivativeMenu($event, paper, 'zh')"
                >⋯</button>
              </div>
              <div
                v-if="paper.bilingual_static_url"
                :class="[myPaperMdSubLinkClass(paper.paper_id, 'bilingual'), 'group !gap-1']"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <div
                  class="flex flex-1 min-w-0 items-center gap-2 cursor-pointer"
                  @click="emitViewUserPaperMd(paper, 'bilingual')"
                >
                  <span class="text-xs shrink-0">🔀</span>
                  <span class="text-xs text-text-secondary truncate flex-1">中英文对照版</span>
                </div>
                <button
                  type="button"
                  class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-[10px]"
                  title="更多"
                  @click.stop="openMyPaperDerivativeMenu($event, paper, 'bilingual')"
                >⋯</button>
              </div>
              <div
                v-if="paper.mineru_static_url && !paper.zh_static_url && paper.translate_status !== 'processing'"
                class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/note cursor-pointer"
                style="padding-left: 50px; padding-right: 8px;"
                @click="handleTranslateMyPaper(paper)"
              >
                <span class="text-xs shrink-0">✨</span>
                <span class="text-xs text-tinder-pink truncate flex-1 font-medium">生成中文翻译与对照</span>
              </div>
              <!-- Translating in progress (show even when partial zh already exists) -->
              <div
                v-if="paper.mineru_static_url && paper.translate_status === 'processing'"
                class="flex items-center gap-2 py-1.5 px-2 rounded"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <span class="text-xs shrink-0">⏳</span>
                <span class="text-xs text-amber-500 truncate flex-1">
                  {{ paper.zh_static_url ? '翻译中（已可预览）' : '翻译中…' }}
                </span>
                <TranslateProgressRing :percent="paper.translate_progress ?? 0" />
              </div>
              <div
                v-if="paper.translate_status === 'failed' && paper.translate_error"
                class="flex items-center gap-2 py-1.5 px-2"
                style="padding-left: 50px; padding-right: 8px;"
              >
                <span class="text-xs text-red-500 truncate">{{ paper.translate_error }}</span>
              </div>
              <!-- My Papers notes section -->
              <div
                v-for="note in (myPaperNotes.get(paper.paper_id) || [])"
                :key="note.id"
                class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/mpnote cursor-pointer"
                style="padding-left: 50px;"
                @click="onNoteClick(note)"
              >
                <span class="text-xs shrink-0">{{ noteIcon(note.type) }}</span>
                <span class="text-xs text-text-secondary truncate flex-1">{{ note.title }}</span>
                <button
                  class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/mpnote:opacity-100 transition-opacity"
                  @click.stop="openMyPaperNoteMenu($event, note)"
                >⋯</button>
              </div>
            </div>
          </div>
        </template>
      </div>
      <!-- Hidden file input for mypapers uploads -->
      <input
        ref="myPaperFileInputRef"
        type="file"
        class="hidden"
        @change="onMyPaperFileSelected"
      />
    </div>

    <!-- My Papers context menu -->
    <KbContextMenu
      v-if="myPaperContextMenu"
      :items="myPaperMenuItems()"
      :x="myPaperContextMenu.x"
      :y="myPaperContextMenu.y"
      @select="handleMyPaperMenuSelect"
      @close="myPaperContextMenu = null"
    />

    <KbContextMenu
      v-if="myPaperDerivativeMenu"
      :items="myPaperDerivativeMenuItems()"
      :x="myPaperDerivativeMenu.x"
      :y="myPaperDerivativeMenu.y"
      @select="handleMyPaperDerivativeMenuSelect"
      @close="myPaperDerivativeMenu = null"
    />

    <!-- KB derivative menu -->
    <KbContextMenu
      v-if="kbDerivativeMenu"
      :items="kbDerivativeMenuItems()"
      :x="kbDerivativeMenu.x"
      :y="kbDerivativeMenu.y"
      @select="handleKbDerivativeMenuSelect"
      @close="kbDerivativeMenu = null"
    />

    <!-- Batch action bar (papers tab and mypapers tab) -->
    <div
      v-if="batchMode && (activeTab === 'papers' || activeTab === 'mypapers')"
      class="px-3 py-2.5 border-t border-border bg-bg-elevated flex flex-col gap-2"
    >
      <div class="flex items-center justify-between">
        <span class="text-xs text-text-muted">已选 {{ checkedPapers.size }} 篇</span>
        <button
          class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="toggleBatchMode"
        >取消</button>
      </div>
      <div class="flex items-center gap-2">
        <button
          :disabled="!hasChecked"
          class="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity"
          :class="hasChecked
            ? 'text-white bg-brand-gradient hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          @click="startBatchMove"
        >移动到...</button>
        <button
          :disabled="!hasChecked"
          class="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="hasChecked
            ? 'text-white bg-gradient-to-r from-[#10b981] to-[#059669] hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          title="批量下载选中论文的数据"
          @click="showBatchDownloadDialog = true"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          批量下载
        </button>
        <button
          :disabled="!canCompare"
          class="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="canCompare
            ? 'text-white bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          :title="checkedPapers.size < 2 ? '请至少选择 2 篇论文' : checkedPapers.size > 5 ? '最多选择 5 篇论文' : '对比分析选中论文'"
          @click="startCompare"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          对比分析
        </button>
      </div>
      <button
        :disabled="!canResearch"
        class="w-full px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
        :class="canResearch
          ? 'text-white bg-gradient-to-r from-[#0ea5e9] to-[#6366f1] hover:opacity-90'
          : 'text-text-muted bg-bg-hover cursor-not-allowed'"
        :title="checkedPapers.size < 1 ? '请至少选择 1 篇论文' : checkedPapers.size > 20 ? '最多选择 20 篇论文' : `深度研究（${checkedPapers.size} 篇）`"
        @click="startResearch"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>
        </svg>
        深度研究 ({{ checkedPapers.size }}/20)
      </button>
    </div>

    <!-- ============ Paper Inspiration tab ============ -->
    <div v-if="activeTab === 'paper-inspiration'" class="flex-1 overflow-y-auto flex flex-col">
      <!-- Header -->
      <div class="px-3 pt-3 pb-2 shrink-0">
        <p class="text-xs text-text-muted leading-relaxed">
          选择一篇已处理完成的论文，AI 将基于其内容为你生成研究灵感方向。
        </p>
      </div>

      <!-- Loading / error -->
      <div v-if="myPapersLoading && !myPaperTree" class="flex-1 flex items-center justify-center text-xs text-text-muted">
        加载中...
      </div>
      <div v-else-if="myPapersError" class="flex-1 flex items-center justify-center text-xs text-red-500 px-4 text-center">
        {{ myPapersError }}
      </div>

      <template v-else>
        <!-- Collect all completed papers from tree -->
        <template v-if="myPaperTree">
          <!-- Empty state -->
          <div
            v-if="myPaperTree.papers.filter(p => p.process_status === 'completed').length === 0 && myPaperTree.folders.every(f => f.papers.filter(p => p.process_status === 'completed').length === 0)"
            class="flex-1 flex flex-col items-center justify-center text-center px-4 py-8"
          >
            <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-mypapers-gradient-br opacity-60 flex items-center justify-center">
              <svg class="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
              </svg>
            </div>
            <p class="text-sm font-semibold text-text-primary mb-1">暂无可用论文</p>
            <p class="text-xs text-text-muted leading-relaxed">
              请先在「发现」页上传并处理你的论文，<br/>完成后即可在此生成灵感。
            </p>
          </div>

          <!-- Paper list (root + folders, only completed) -->
          <div v-else class="flex-1 overflow-y-auto p-2">
            <!-- Root-level completed papers -->
            <div
              v-for="paper in myPaperTree.papers.filter(p => p.process_status === 'completed')"
              :key="paper.paper_id"
              class="border-b border-border/30 last:border-b-0"
            >
              <div class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors group">
                <!-- Avatar -->
                <div
                  class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
                  :style="{ background: avatarColor(paper.paper_id) }"
                >
                  {{ (paper.title || '?').slice(0, 2) }}
                </div>
                <!-- Info (clickable: open idea detail) -->
                <div
                  class="flex-1 min-w-0 cursor-pointer"
                  title="查看灵感详情"
                  @click="emit('paperInspirationDetail', paper.paper_id, paper.title)"
                >
                  <div class="text-xs font-medium text-text-primary truncate">{{ paper.title }}</div>
                  <div class="text-[10px] text-text-muted truncate">{{ paper.institution || paper.paper_id }}</div>
                </div>
                <!-- Inspiration button -->
                <button
                  class="shrink-0 flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border-none cursor-pointer transition-all font-medium"
                  :class="generatingPaperIds.has(paper.paper_id)
                    ? 'text-amber-600 bg-amber-500/10 cursor-not-allowed'
                    : 'text-white bg-brand-gradient hover:opacity-90'"
                  :disabled="generatingPaperIds.has(paper.paper_id)"
                  title="基于此论文生成灵感候选"
                  @click.stop="openPaperInspiration(paper.paper_id, paper.title)"
                >
                  <span v-if="generatingPaperIds.has(paper.paper_id)" class="animate-spin">⟳</span>
                  <svg v-else class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
                  </svg>
                  <span>{{ generatingPaperIds.has(paper.paper_id) ? '生成中' : '灵感涌现' }}</span>
                </button>
              </div>
            </div>

            <!-- Folder papers (only completed) -->
            <template v-for="folder in myPaperTree.folders" :key="folder.id">
              <template v-for="paper in folder.papers.filter(p => p.process_status === 'completed')" :key="paper.paper_id">
                <div class="border-b border-border/30 last:border-b-0">
                  <div class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors group">
                    <div
                      class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
                      :style="{ background: avatarColor(paper.paper_id) }"
                    >
                      {{ (paper.title || '?').slice(0, 2) }}
                    </div>
                    <!-- Info (clickable: open idea detail) -->
                    <div
                      class="flex-1 min-w-0 cursor-pointer"
                      title="查看灵感详情"
                      @click="emit('paperInspirationDetail', paper.paper_id, paper.title)"
                    >
                      <div class="text-xs font-medium text-text-primary truncate">{{ paper.title }}</div>
                      <div class="text-[10px] text-text-muted truncate">{{ folder.name }} · {{ paper.institution || paper.paper_id }}</div>
                    </div>
                    <button
                      class="shrink-0 flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border-none cursor-pointer transition-all font-medium"
                      :class="generatingPaperIds.has(paper.paper_id)
                        ? 'text-amber-600 bg-amber-500/10 cursor-not-allowed'
                        : 'text-white bg-brand-gradient hover:opacity-90'"
                      :disabled="generatingPaperIds.has(paper.paper_id)"
                      title="基于此论文生成灵感候选"
                      @click.stop="openPaperInspiration(paper.paper_id, paper.title)"
                    >
                      <span v-if="generatingPaperIds.has(paper.paper_id)" class="animate-spin">⟳</span>
                      <svg v-else class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
                      </svg>
                      <span>{{ generatingPaperIds.has(paper.paper_id) ? '生成中' : '灵感涌现' }}</span>
                    </button>
                  </div>
                </div>
              </template>
            </template>
          </div>
        </template>

        <div v-else class="flex-1 flex items-center justify-center text-xs text-text-muted">
          加载中...
        </div>
      </template>
    </div>

    <!-- Batch download dialog -->
    <div
      v-if="showBatchDownloadDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      @click.self="showBatchDownloadDialog = false"
    >
      <div class="bg-bg-elevated border border-border rounded-xl shadow-2xl p-5 w-72 flex flex-col gap-3">
        <div class="text-sm font-semibold text-text-primary">批量下载（{{ checkedPapers.size }} 篇）</div>
        <div class="text-xs text-text-muted">选择要下载的文件类型：</div>
        <div class="flex flex-col gap-1.5">
          <label v-for="ft in (['pdf', 'mineru', 'zh', 'bilingual'] as const)" :key="ft" class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              :checked="batchDownloadFileTypes.includes(ft)"
              class="rounded accent-tinder-green"
              @change="batchDownloadFileTypes.includes(ft) ? batchDownloadFileTypes = batchDownloadFileTypes.filter(t => t !== ft) : batchDownloadFileTypes = [...batchDownloadFileTypes, ft]"
            />
            <span class="text-xs text-text-primary">{{ { pdf: 'PDF 原文', mineru: 'MinerU 解析 (.md)', zh: '中文翻译 (.md)', bilingual: '中英对照 (.md)' }[ft] }}</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer mt-1">
            <input
              type="checkbox"
              v-model="batchDownloadIncludeNotes"
              class="rounded accent-tinder-green"
            />
            <span class="text-xs text-text-primary">包含笔记/附件</span>
          </label>
        </div>
        <div class="flex gap-2 pt-1">
          <button
            class="flex-1 py-1.5 rounded-lg text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="showBatchDownloadDialog = false"
          >取消</button>
          <button
            :disabled="batchDownloadFileTypes.length === 0 && !batchDownloadIncludeNotes"
            class="flex-1 py-1.5 rounded-lg text-xs font-semibold border-none cursor-pointer transition-opacity"
            :class="batchDownloadFileTypes.length > 0 || batchDownloadIncludeNotes
              ? 'text-white bg-gradient-to-r from-[#10b981] to-[#059669] hover:opacity-90'
              : 'text-text-muted bg-bg-hover cursor-not-allowed'"
            @click="startBatchDownload"
          >下载 zip</button>
        </div>
      </div>
    </div>

    <!-- Context menu -->
    <KbContextMenu
      v-if="contextMenu"
      :items="contextMenu.items"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @select="handleContextMenuSelect"
      @close="contextMenu = null"
    />

    <!-- Folder picker dialog -->
    <FolderPickerDialog
      v-if="showFolderPicker"
      :folders="folderPickerFolders"
      :title="folderPickerTitle"
      @select="handleMoveTo"
      @cancel="showFolderPicker = false"
    />

    <!-- Compare Cart (对比清单 - 跨库购物车) -->
    <Transition name="cart-slide">
      <div
        v-if="compareCart.length > 0 && activeTab !== 'research'"
        class="border-t border-border bg-bg-elevated"
      >
        <!-- Cart header bar -->
        <div class="flex items-center justify-between px-3 py-2">
          <button
            class="flex items-center gap-1.5 flex-1 min-w-0 bg-transparent border-none cursor-pointer text-left p-0 group"
            @click="compareCartExpanded = !compareCartExpanded"
          >
            <svg
              class="w-3.5 h-3.5 text-indigo-400 shrink-0 transition-transform duration-200"
              :class="compareCartExpanded ? 'rotate-180' : ''"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="18 15 12 9 6 15"/>
            </svg>
            <span class="text-xs font-semibold text-text-primary truncate">对比清单</span>
            <span class="ml-1 inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-400 shrink-0">
              {{ compareCart.length }}
            </span>
          </button>
          <button
            class="text-[10px] text-text-muted hover:text-red-400 bg-transparent border-none cursor-pointer transition-colors shrink-0 ml-2"
            title="清空清单"
            @click="clearCompareCart"
          >清空</button>
        </div>

        <!-- Cart items (expanded) -->
        <div v-if="compareCartExpanded" class="px-2 pb-1 max-h-36 overflow-y-auto">
          <div
            v-for="item in compareCart"
            :key="item.id"
            class="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-bg-hover group/item"
          >
            <!-- Source badge -->
            <span
              class="shrink-0 text-[9px] font-bold px-1 py-0.5 rounded leading-none"
              :class="{
                'bg-blue-500/15 text-blue-400': item.source === 'kb',
                'bg-green-500/15 text-green-400': item.source === 'mypapers',
                'bg-purple-500/15 text-purple-400': item.source === 'compare',
              }"
            >
              {{ item.source === 'kb' ? '知识库' : item.source === 'mypapers' ? '我的论文' : '对比库' }}
            </span>
            <!-- Title -->
            <span class="flex-1 text-[11px] text-text-secondary truncate min-w-0" :title="item.title">
              {{ item.title }}
            </span>
            <!-- Remove -->
            <button
              class="shrink-0 w-4 h-4 flex items-center justify-center text-text-muted hover:text-red-400 bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/item:opacity-100 transition-opacity"
              title="移出清单"
              @click="removeFromCompareCart(item.id)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="w-3 h-3">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Start compare button -->
        <div class="px-3 pb-2.5 pt-1">
          <button
            :disabled="!canCompareCart"
            class="w-full py-1.5 rounded-full text-xs font-semibold border-none cursor-pointer transition-all flex items-center justify-center gap-1.5"
            :class="canCompareCart
              ? 'text-white bg-gradient-to-r from-indigo-500 to-purple-500 hover:opacity-90 shadow-sm'
              : 'text-text-muted bg-bg-hover cursor-not-allowed'"
            :title="compareCart.length < 2 ? '请至少添加 2 项' : compareCart.length > 5 ? '最多 5 项' : '发起跨库对比分析'"
            @click="startCompareFromCart"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
            开始对比 ({{ compareCart.length }}/5)
          </button>
          <p v-if="compareCart.length < 2" class="text-[10px] text-text-muted text-center mt-1">
            再添加 {{ 2 - compareCart.length }} 项可发起对比
          </p>
        </div>
      </div>
    </Transition>

    <!-- ============ Research tab ============ -->
    <SidebarResearchTab
      v-if="activeTab === 'research'"
      ref="researchTabRef"
      @open-research-session="emit('openResearchSession', $event)"
      @start-new-research="handleStartNewResearchFromTab"
    />

    <!-- ============ User bar (bottom) ============ -->
    <UserBar />

    </div><!-- /sidebar-content -->

  </aside>
</template>
