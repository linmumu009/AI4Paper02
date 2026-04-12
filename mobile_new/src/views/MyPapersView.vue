<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import FloatingButton from '@/components/FloatingButton.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SearchBar from '@/components/SearchBar.vue'
import {
  fetchUserPapers,
  importUserPaperPdf,
  importUserPaperArxiv,
  importUserPaperManual,
  deleteUserPaper,
  processUserPaper,
  translateUserPaper,
  retranslateUserPaper,
  fetchUserPaperProcessStatus,
  fetchUserPaperFiles,
  userPaperStepLabel,
} from '@shared/api/user-papers'
import type { UserPaper, UserPaperFilesResponse } from '@shared/types/user-papers'
import { showToast, showDialog } from 'vant'

const router = useRouter()

// State
const papers = ref<UserPaper[]>([])
const total = ref(0)
const loading = ref(true)
const loadError = ref('')
const searchQuery = ref('')

// Import bottom sheet
const importVisible = ref(false)
const importTab = ref<'pdf' | 'arxiv' | 'manual'>('pdf')
const importing = ref(false)
const importError = ref('')

// PDF import
const pdfFile = ref<File | null>(null)
const pdfInput = ref<HTMLInputElement | null>(null)

// arXiv import
const arxivId = ref('')

// Manual import
const manualTitle = ref('')
const manualAuthors = ref('')
const manualAbstract = ref('')

// Paper action sheet
const actionPaper = ref<UserPaper | null>(null)
const actionVisible = ref(false)

// Status sheet
const statusPaper = ref<UserPaper | null>(null)
const statusVisible = ref(false)
const statusData = ref<{ process_status?: string; process_step?: string; process_error?: string } | null>(null)
const loadingStatus = ref(false)
let statusPollTimer: ReturnType<typeof setInterval> | null = null

// Files sheet
const filesVisible = ref(false)
const filesData = ref<UserPaperFilesResponse | null>(null)
const filesLoading = ref(false)
const filesError = ref('')
const processingAction = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

const processingCount = computed(() => papers.value.filter(p => p.process_status === 'processing' || p.process_status === 'pending').length)

const filteredPapers = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return papers.value
  return papers.value.filter(p =>
    (p.title || '').toLowerCase().includes(q) ||
    (p.institution || '').toLowerCase().includes(q) ||
    (p.source_ref || '').toLowerCase().includes(q),
  )
})

function statusLabel(status?: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'processing') return '处理中'
  if (status === 'pending') return '等待处理'
  if (status === 'failed') return '处理失败'
  if (status === 'none') return '未处理'
  return status ?? '未知'
}

function statusClass(status?: string): string {
  if (status === 'completed') return 'bg-tinder-green/15 text-tinder-green'
  if (status === 'processing') return 'bg-tinder-blue/15 text-tinder-blue'
  if (status === 'pending') return 'bg-tinder-gold/15 text-tinder-gold'
  if (status === 'failed') return 'bg-tinder-pink/15 text-tinder-pink'
  return 'bg-bg-elevated text-text-muted'
}

function sourceLabel(source?: string): string {
  if (source === 'pdf') return 'PDF 上传'
  if (source === 'arxiv') return 'arXiv'
  if (source === 'manual') return '手动录入'
  return source ?? ''
}

async function loadPapers() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchUserPapers({ limit: 100, offset: 0 })
    papers.value = res.papers
    total.value = res.total
  } catch (e: any) {
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openPdfPicker() {
  pdfInput.value?.click()
}

function onPdfChange(e: Event) {
  const input = e.target as HTMLInputElement
  pdfFile.value = input.files?.[0] ?? null
}

async function doImport() {
  importing.value = true
  importError.value = ''
  try {
    if (importTab.value === 'pdf') {
      if (!pdfFile.value) { importError.value = '请选择 PDF 文件'; return }
      await importUserPaperPdf(pdfFile.value)
    } else if (importTab.value === 'arxiv') {
      if (!arxivId.value.trim()) { importError.value = '请输入 arXiv ID'; return }
      await importUserPaperArxiv(arxivId.value.trim())
    } else {
      if (!manualTitle.value.trim()) { importError.value = '请输入论文标题'; return }
      await importUserPaperManual({
        title: manualTitle.value.trim(),
        authors: manualAuthors.value.trim() ? [manualAuthors.value.trim()] : undefined,
        abstract: manualAbstract.value.trim() || undefined,
      })
    }
    importVisible.value = false
    resetImportForm()
    showToast('导入成功')
    await loadPapers()
    if (processingCount.value > 0) startPolling()
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || e?.message || '导入失败，请重试'
  } finally {
    importing.value = false
  }
}

function resetImportForm() {
  pdfFile.value = null
  arxivId.value = ''
  manualTitle.value = ''
  manualAuthors.value = ''
  manualAbstract.value = ''
  importError.value = ''
  if (pdfInput.value) pdfInput.value.value = ''
}

// ── Action sheet ──

function openActionSheet(paper: UserPaper) {
  actionPaper.value = paper
  actionVisible.value = true
}

function openDetail(paper: UserPaper) {
  actionVisible.value = false
  router.push({ path: `/paper/${paper.paper_id}`, query: { source: 'user-paper' } })
}

function openChat(paper: UserPaper) {
  actionVisible.value = false
  router.push({ name: 'chat', query: { paperId: paper.paper_id, title: paper.title } })
}

function openReader(paper: UserPaper) {
  actionVisible.value = false
  router.push({ path: `/paper/${paper.paper_id}/read`, query: { mode: 'bilingual', source: 'user-paper', paperId: String(paper.id), title: paper.title || '论文阅读' } })
}

function openStatus(paper: UserPaper) {
  actionVisible.value = false
  showStatusSheet(paper)
}

async function showStatusSheet(paper: UserPaper) {
  statusPaper.value = paper
  statusVisible.value = true
  statusData.value = null
  loadingStatus.value = true
  try {
    const res = await fetchUserPaperProcessStatus(paper.paper_id)
    statusData.value = res as any
  } catch { /* best-effort */ }
  loadingStatus.value = false
  if (paper.process_status === 'processing' || paper.process_status === 'pending') {
    startStatusPolling()
  }
}

function startStatusPolling() {
  if (statusPollTimer) return
  statusPollTimer = setInterval(async () => {
    const paper = statusPaper.value
    if (!paper || !statusVisible.value) { stopStatusPolling(); return }
    try {
      const res = await fetchUserPaperProcessStatus(paper.paper_id)
      statusData.value = res as any
      const idx = papers.value.findIndex(p => p.paper_id === paper.paper_id)
      if (idx >= 0 && res.process_status) {
        papers.value[idx] = { ...papers.value[idx], process_status: res.process_status as any }
      }
      if (res.process_status !== 'processing' && res.process_status !== 'pending') {
        stopStatusPolling()
      }
    } catch { /* best-effort */ }
  }, 5000)
}

function stopStatusPolling() {
  if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
}

async function openFiles(paper: UserPaper) {
  actionVisible.value = false
  actionPaper.value = paper
  filesVisible.value = true
  filesData.value = null
  filesLoading.value = true
  filesError.value = ''
  try {
    filesData.value = await fetchUserPaperFiles(paper.paper_id)
  } catch {
    filesError.value = '加载失败'
  } finally {
    filesLoading.value = false
  }
}

async function triggerProcess(paper: UserPaper) {
  actionVisible.value = false
  processingAction.value = 'process'
  try {
    await processUserPaper(paper.paper_id)
    showToast('已提交处理任务')
    const p = papers.value.find(p => p.paper_id === paper.paper_id)
    if (p) p.process_status = 'pending'
    startPolling()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '触发失败，请重试')
  } finally {
    processingAction.value = null
  }
}

async function triggerTranslate(paper: UserPaper) {
  actionVisible.value = false
  processingAction.value = 'translate'
  try {
    await translateUserPaper(paper.paper_id)
    showToast('已提交翻译任务')
    await loadPapers()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '触发失败，请重试')
  } finally {
    processingAction.value = null
  }
}

async function triggerRetranslate(paper: UserPaper) {
  actionVisible.value = false
  processingAction.value = 'retranslate'
  try {
    await retranslateUserPaper(paper.paper_id)
    showToast('已提交重新翻译任务')
    await loadPapers()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '触发失败，请重试')
  } finally {
    processingAction.value = null
  }
}

async function deletePaperAction(paper: UserPaper) {
  actionVisible.value = false
  try {
    await showDialog({
      title: '删除论文',
      message: `确定删除「${paper.title?.slice(0, 30) ?? '此论文'}」？此操作不可恢复。`,
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteUserPaper(paper.paper_id)
    papers.value = papers.value.filter(p => p.paper_id !== paper.paper_id)
    total.value = Math.max(0, total.value - 1)
    showToast('已删除')
  } catch { /* cancelled */ }
}

// ── Files sheet actions ──

async function filesProcess() {
  const paper = actionPaper.value
  if (!paper || processingAction.value) return
  processingAction.value = 'process'
  try {
    await processUserPaper(paper.paper_id)
    showToast('已提交处理任务')
    filesData.value = await fetchUserPaperFiles(paper.paper_id)
    await loadPapers()
    startPolling()
  } catch { showToast('操作失败') } finally { processingAction.value = null }
}

async function filesTranslate() {
  const paper = actionPaper.value
  if (!paper || processingAction.value) return
  processingAction.value = 'translate'
  try {
    await translateUserPaper(paper.paper_id)
    showToast('已提交翻译任务')
    filesData.value = await fetchUserPaperFiles(paper.paper_id)
  } catch { showToast('操作失败') } finally { processingAction.value = null }
}

async function filesRetranslate() {
  const paper = actionPaper.value
  if (!paper || processingAction.value) return
  processingAction.value = 'retranslate'
  try {
    await retranslateUserPaper(paper.paper_id)
    showToast('已提交重新翻译任务')
    filesData.value = await fetchUserPaperFiles(paper.paper_id)
  } catch { showToast('操作失败') } finally { processingAction.value = null }
}

// ── Polling ──

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (processingCount.value > 0) await loadPapers()
    else stopPolling()
  }, 8000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onMounted(async () => {
  await loadPapers()
  if (processingCount.value > 0) startPolling()
})

onUnmounted(() => {
  stopPolling()
  stopStatusPolling()
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="我的论文" @back="router.back()">
      <template #right>
        <span v-if="total > 0" class="text-[12px] text-text-muted pr-1">{{ total }} 篇</span>
      </template>
    </PageHeader>

    <!-- Search bar -->
    <div class="px-4 pb-2 pt-1 shrink-0">
      <SearchBar v-model="searchQuery" placeholder="搜索论文标题、机构…" />
    </div>

    <LoadingState v-if="loading" class="flex-1" message="加载中…" />
    <ErrorState v-else-if="loadError" class="flex-1" :message="loadError" @retry="loadPapers" />

    <div v-else-if="!papers.length" class="flex-1 relative">
      <EmptyState
        icon="📄"
        title="还没有导入的论文"
        description="点击右下角的 + 按钮导入 PDF 或 arXiv 论文"
      />
    </div>

    <div v-else class="flex-1 overflow-y-auto min-h-0 pb-6 px-4 pt-2 space-y-2">
      <!-- No search results -->
      <div v-if="filteredPapers.length === 0" class="py-12 text-center text-[13px] text-text-muted">
        没有匹配的论文
      </div>
      <div
        v-for="paper in filteredPapers"
        :key="paper.id"
        class="card-section active:bg-bg-hover transition-colors cursor-pointer"
        @click="openActionSheet(paper)"
      >
        <div class="flex items-start gap-3">
          <div class="flex-1 min-w-0">
            <p class="text-[13px] font-semibold text-text-primary leading-snug mb-1 line-clamp-2">
              {{ paper.title || '无标题' }}
            </p>
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-[11px] text-text-muted">{{ sourceLabel(paper.source_type) }}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium" :class="statusClass(paper.process_status)">
                {{ statusLabel(paper.process_status) }}
              </span>
              <span v-if="paper.translate_status === 'completed'" class="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-tinder-purple/15 text-tinder-purple">
                已翻译
              </span>
              <span v-if="paper.translate_status === 'processing'" class="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-tinder-blue/15 text-tinder-blue">
                翻译中
              </span>
            </div>
          </div>
          <button
            type="button"
            class="shrink-0 w-8 h-8 flex items-center justify-center text-text-muted active:text-tinder-pink rounded-xl"
            @click.stop="deletePaperAction(paper)"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Floating import button -->
    <FloatingButton label="导入论文" @click="importVisible = true" />

    <!-- Hidden file input -->
    <input ref="pdfInput" type="file" accept=".pdf" class="hidden" @change="onPdfChange" />

    <!-- ── Action sheet: paper operations ── -->
    <BottomSheet
      :visible="actionVisible"
      :title="actionPaper?.title?.slice(0, 40) ?? '论文操作'"
      @close="actionVisible = false"
    >
      <div class="pb-4" v-if="actionPaper">
        <!-- View detail (completed only) -->
        <button
          v-if="actionPaper.process_status === 'completed'"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="openDetail(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">查看详情</p>
            <p class="text-[12px] text-text-muted mt-0.5">AI 摘要与结构化分析</p>
          </div>
        </button>

        <!-- AI Chat -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="openChat(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-purple/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-purple">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">AI 对话</p>
            <p class="text-[12px] text-text-muted mt-0.5">与 AI 讨论这篇论文</p>
          </div>
        </button>

        <!-- Bilingual reading (completed with translate) -->
        <button
          v-if="actionPaper.process_status === 'completed'"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="openReader(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-green/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-green">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">阅读</p>
            <p class="text-[12px] text-text-muted mt-0.5">双语对照、中文译文</p>
          </div>
        </button>

        <div class="h-px bg-border mx-4 my-1" />

        <!-- Trigger process (none / failed) -->
        <button
          v-if="actionPaper.process_status === 'none' || actionPaper.process_status === 'failed'"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          :disabled="!!processingAction"
          @click="triggerProcess(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-gold/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-gold">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">{{ processingAction === 'process' ? '提交中…' : '触发处理' }}</p>
            <p class="text-[12px] text-text-muted mt-0.5">生成 AI 摘要与结构化分析</p>
          </div>
        </button>

        <!-- Trigger translate (completed but not translated) -->
        <button
          v-if="actionPaper.process_status === 'completed' && (!actionPaper.translate_status || actionPaper.translate_status === 'none' || actionPaper.translate_status === 'failed')"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          :disabled="!!processingAction"
          @click="triggerTranslate(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue">
              <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">{{ processingAction === 'translate' ? '提交中…' : '触发翻译' }}</p>
            <p class="text-[12px] text-text-muted mt-0.5">生成中文翻译与双语对照</p>
          </div>
        </button>

        <!-- Re-translate (already translated) -->
        <button
          v-if="actionPaper.process_status === 'completed' && actionPaper.translate_status === 'completed'"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          :disabled="!!processingAction"
          @click="triggerRetranslate(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-gold/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-gold">
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">{{ processingAction === 'retranslate' ? '提交中…' : '重新翻译' }}</p>
            <p class="text-[12px] text-text-muted mt-0.5">重新生成中文翻译</p>
          </div>
        </button>

        <!-- View status (processing / pending) -->
        <button
          v-if="actionPaper.process_status === 'processing' || actionPaper.process_status === 'pending'"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="openStatus(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">查看处理状态</p>
            <p class="text-[12px] text-text-muted mt-0.5">查看当前步骤与进度</p>
          </div>
        </button>

        <!-- Manage files -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="openFiles(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-text-muted/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-text-secondary">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">衍生文件管理</p>
            <p class="text-[12px] text-text-muted mt-0.5">处理状态与文件管理</p>
          </div>
        </button>

        <div class="h-px bg-border mx-4 my-1" />

        <!-- Delete -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="deletePaperAction(actionPaper)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-pink/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-pink">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-tinder-pink">删除</p>
            <p class="text-[12px] text-text-muted mt-0.5">永久删除此论文及文件</p>
          </div>
        </button>
      </div>
    </BottomSheet>

    <!-- Import sheet -->
    <BottomSheet :visible="importVisible" title="导入论文" @close="importVisible = false; resetImportForm()">
      <div class="px-4 pb-6 pt-1">
        <!-- Tab switch -->
        <div class="flex gap-1 mb-4 p-1 bg-bg rounded-xl border border-border">
          <button
            v-for="tab in [{ key: 'pdf', label: 'PDF 上传' }, { key: 'arxiv', label: 'arXiv ID' }, { key: 'manual', label: '手动录入' }]"
            :key="tab.key"
            type="button"
            class="flex-1 py-1.5 rounded-lg text-[12px] font-medium transition-all"
            :class="importTab === tab.key ? 'bg-tinder-blue/15 text-tinder-blue' : 'text-text-muted'"
            @click="importTab = tab.key as typeof importTab; importError = ''"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- PDF tab -->
        <div v-if="importTab === 'pdf'" class="space-y-3">
          <button
            type="button"
            class="w-full py-4 rounded-2xl border-2 border-dashed border-border flex flex-col items-center gap-2 active:bg-bg-elevated transition-colors"
            @click="openPdfPicker"
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <span class="text-[13px] text-text-muted">{{ pdfFile ? pdfFile.name : '点击选择 PDF 文件' }}</span>
          </button>
        </div>

        <!-- arXiv tab -->
        <div v-else-if="importTab === 'arxiv'" class="space-y-3">
          <div>
            <label class="text-[12px] text-text-muted mb-1 block">arXiv ID</label>
            <input
              v-model="arxivId"
              type="text"
              class="input-field"
              placeholder="例：2301.00001 或 https://arxiv.org/abs/2301.00001"
              inputmode="text"
            />
          </div>
        </div>

        <!-- Manual tab -->
        <div v-else class="space-y-3">
          <div>
            <label class="text-[12px] text-text-muted mb-1 block">论文标题 <span class="text-tinder-pink">*</span></label>
            <input v-model="manualTitle" type="text" class="input-field" placeholder="输入论文标题" maxlength="300" />
          </div>
          <div>
            <label class="text-[12px] text-text-muted mb-1 block">作者（可选）</label>
            <input v-model="manualAuthors" type="text" class="input-field" placeholder="例：张三, 李四" />
          </div>
          <div>
            <label class="text-[12px] text-text-muted mb-1 block">摘要（可选）</label>
            <textarea v-model="manualAbstract" class="input-field resize-none" rows="4" placeholder="输入摘要" />
          </div>
        </div>

        <!-- Error -->
        <p v-if="importError" class="mt-2 text-[12px] text-tinder-pink">{{ importError }}</p>

        <button
          type="button"
          class="btn-primary mt-4"
          :disabled="importing"
          @click="doImport"
        >
          {{ importing ? '导入中…' : '确认导入' }}
        </button>
      </div>
    </BottomSheet>

    <!-- Status sheet -->
    <BottomSheet :visible="statusVisible" :title="statusPaper?.title?.slice(0, 30) ?? '处理状态'" @close="statusVisible = false; stopStatusPolling()">
      <div class="px-5 pb-6 pt-2">
        <div v-if="loadingStatus" class="flex justify-center py-6">
          <div class="w-6 h-6 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
        </div>
        <div v-else-if="statusPaper" class="space-y-3">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-[11px] px-2 py-0.5 rounded-full font-medium" :class="statusClass(statusData?.process_status || statusPaper.process_status)">
              {{ statusLabel(statusData?.process_status || statusPaper.process_status) }}
            </span>
            <span v-if="statusData?.process_step" class="text-[12px] text-text-muted">
              {{ userPaperStepLabel(statusData.process_step) }}
            </span>
          </div>
          <p class="text-[13px] text-text-primary font-medium">{{ statusPaper.title || '无标题' }}</p>
          <p class="text-[12px] text-text-muted">来源：{{ sourceLabel(statusPaper.source_type) }}</p>
          <p v-if="(statusData?.process_status || statusPaper.process_status) === 'processing'" class="text-[12px] text-tinder-blue">
            系统正在自动处理，通常需要 1-5 分钟，请稍候…
          </p>
          <p v-else-if="(statusData?.process_status || statusPaper.process_status) === 'failed'" class="text-[12px] text-tinder-pink">
            处理失败{{ statusData?.process_error ? `：${statusData.process_error}` : '' }}，请尝试重新触发处理。
          </p>
          <p v-else-if="(statusData?.process_status || statusPaper.process_status) === 'pending'" class="text-[12px] text-tinder-gold">
            已加入处理队列，等待系统处理中…
          </p>
        </div>
      </div>
    </BottomSheet>

    <!-- Files management sheet -->
    <BottomSheet :visible="filesVisible" title="衍生文件管理" @close="filesVisible = false">
      <div class="px-4 pb-6 pt-2">
        <div v-if="filesLoading" class="flex justify-center py-8">
          <div class="w-6 h-6 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
        </div>
        <div v-else-if="filesError" class="py-6 text-center text-[13px] text-tinder-pink">{{ filesError }}</div>
        <div v-else-if="filesData" class="space-y-3">
          <!-- PDF -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">PDF 原文</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full" :class="filesData.exists.pdf ? 'bg-tinder-green/15 text-tinder-green' : 'bg-text-muted/15 text-text-muted'">
                  {{ filesData.exists.pdf ? '存在' : '未找到' }}
                </span>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">原始论文 PDF 文件</p>
          </div>

          <!-- MinerU -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">结构化文本</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                  :class="{
                    'bg-tinder-green/15 text-tinder-green': filesData.exists.mineru,
                    'bg-tinder-blue/15 text-tinder-blue': !filesData.exists.mineru && filesData.translate_status === 'processing',
                    'bg-text-muted/15 text-text-muted': !filesData.exists.mineru && filesData.translate_status !== 'processing',
                  }"
                >
                  {{ filesData.exists.mineru ? '已生成' : '未生成' }}
                </span>
              </div>
              <button
                v-if="!filesData.exists.mineru"
                type="button"
                class="text-[11px] px-2 py-1 rounded-lg bg-tinder-blue/10 text-tinder-blue active:bg-tinder-blue/20 disabled:opacity-40"
                :disabled="!!processingAction"
                @click="filesProcess"
              >
                {{ processingAction === 'process' ? '提交中…' : '触发处理' }}
              </button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">MinerU 版面解析后的正文结构</p>
          </div>

          <!-- Chinese translation -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">中文翻译</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                  :class="{
                    'bg-tinder-green/15 text-tinder-green': filesData.exists.zh,
                    'bg-tinder-blue/15 text-tinder-blue': !filesData.exists.zh && filesData.translate_status === 'processing',
                    'bg-text-muted/15 text-text-muted': !filesData.exists.zh && filesData.translate_status !== 'processing',
                  }"
                >
                  {{ filesData.exists.zh ? '已生成' : filesData.translate_status === 'processing' ? '翻译中' : '未生成' }}
                </span>
              </div>
              <div class="flex items-center gap-1.5">
                <button
                  v-if="!filesData.exists.zh"
                  type="button"
                  class="text-[11px] px-2 py-1 rounded-lg bg-tinder-blue/10 text-tinder-blue active:bg-tinder-blue/20 disabled:opacity-40"
                  :disabled="!!processingAction"
                  @click="filesTranslate"
                >
                  {{ processingAction === 'translate' ? '提交中…' : '触发翻译' }}
                </button>
                <button
                  v-if="filesData.exists.zh"
                  type="button"
                  class="text-[11px] px-2 py-1 rounded-lg bg-tinder-gold/10 text-tinder-gold active:bg-tinder-gold/20 disabled:opacity-40"
                  :disabled="!!processingAction"
                  @click="filesRetranslate"
                >
                  {{ processingAction === 'retranslate' ? '提交中…' : '重新翻译' }}
                </button>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">论文中文翻译，用于双语阅读</p>
          </div>

          <!-- Bilingual -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">双语对照</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full" :class="filesData.exists.bilingual ? 'bg-tinder-green/15 text-tinder-green' : 'bg-text-muted/15 text-text-muted'">
                  {{ filesData.exists.bilingual ? '已生成' : '未生成' }}
                </span>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">中英对照文件，需先完成翻译</p>
          </div>
        </div>
      </div>
    </BottomSheet>
  </div>
</template>
