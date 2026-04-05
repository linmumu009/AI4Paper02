<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  fetchUserPapers,
  importUserPaperManual,
  importUserPaperArxiv,
  importUserPaperPdf,
  updateUserPaper,
  uploadUserPaperPdf,
  deleteUserPaper,
  API_ORIGIN,
} from '../api'
import type { UserPaper } from '../types/paper'
import { openExternal } from '../utils/openExternal'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const papers = ref<UserPaper[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')

// Import dialog
const showImportDialog = ref(false)
const importTab = ref<'pdf' | 'arxiv' | 'manual'>('pdf')
const importLoading = ref(false)
const importError = ref('')
const importSuccess = ref('')

// Edit dialog
const editingPaper = ref<UserPaper | null>(null)
const showEditDialog = ref(false)
const editLoading = ref(false)
const editError = ref('')

// Upload PDF supplement dialog
const pdfSupplementPaper = ref<UserPaper | null>(null)
const showPdfSupplementDialog = ref(false)
const pdfSupplementLoading = ref(false)
const pdfSupplementError = ref('')

// Delete confirmation
const deletingPaperId = ref<string | null>(null)

// Search & filter
const searchQuery = ref('')
const filterSource = ref<string>('')

// PDF import form
const pdfFile = ref<File | null>(null)
const pdfMeta = ref({ title: '', authors: '', abstract: '', institution: '', year: '', external_url: '' })

// arXiv import form
const arxivId = ref('')

// Manual form
const manualForm = ref({ title: '', authors: '', abstract: '', institution: '', year: '', external_url: '' })

// Edit form
const editForm = ref({ title: '', authors: '', abstract: '', institution: '', year: '', external_url: '' })

// PDF supplement form
const pdfSupplementFile = ref<File | null>(null)
const pdfInputRef = ref<HTMLInputElement | null>(null)
const pdfSupplementInputRef = ref<HTMLInputElement | null>(null)

function safeText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normalizeUserPaper(raw: unknown): UserPaper {
  const item = (raw && typeof raw === 'object') ? raw as Partial<UserPaper> : {}
  return {
    id: typeof item.id === 'number' ? item.id : 0,
    paper_id: safeText(item.paper_id),
    user_id: typeof item.user_id === 'number' ? item.user_id : 0,
    source_type: item.source_type === 'pdf' || item.source_type === 'arxiv' || item.source_type === 'manual'
      ? item.source_type
      : 'manual',
    source_ref: safeText(item.source_ref),
    title: safeText(item.title),
    authors: Array.isArray(item.authors) ? item.authors.filter((v): v is string => typeof v === 'string') : [],
    abstract: safeText(item.abstract),
    institution: safeText(item.institution),
    year: typeof item.year === 'number' ? item.year : null,
    pdf_path: typeof item.pdf_path === 'string' ? item.pdf_path : null,
    pdf_static_url: typeof item.pdf_static_url === 'string' ? item.pdf_static_url : null,
    external_url: safeText(item.external_url),
    arxiv_pdf_url: typeof item.arxiv_pdf_url === 'string' ? item.arxiv_pdf_url : null,
    summary_json: typeof item.summary_json === 'string' ? item.summary_json : null,
    paper_assets_json: typeof item.paper_assets_json === 'string' ? item.paper_assets_json : null,
    created_at: safeText(item.created_at),
    updated_at: safeText(item.updated_at),
  }
}

function openPdfInput() {
  pdfInputRef.value?.click()
}

function openPdfSupplementInput() {
  pdfSupplementInputRef.value?.click()
}

function upsertPaper(raw: unknown) {
  const next = normalizeUserPaper(raw)
  const idx = papers.value.findIndex(p => p.paper_id === next.paper_id)
  if (idx >= 0) {
    papers.value.splice(idx, 1, next)
  } else {
    papers.value.unshift(next)
  }
  total.value = papers.value.length
  loadError.value = ''
}

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------
const filteredPapers = computed(() => {
  let list = Array.isArray(papers.value) ? papers.value : []
  if (filterSource.value) {
    list = list.filter(p => p.source_type === filterSource.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(p =>
      safeText(p.title).toLowerCase().includes(q) ||
      safeText(p.abstract).toLowerCase().includes(q) ||
      safeText(p.institution).toLowerCase().includes(q)
    )
  }
  return list
})

const sourceLabel: Record<string, string> = {
  pdf: 'PDF 上传',
  arxiv: 'arXiv 导入',
  manual: '手动录入',
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadPapers() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchUserPapers({ limit: 500 })
    const rawPapers = Array.isArray(res?.papers) ? res.papers : []
    papers.value = rawPapers.map(normalizeUserPaper)
    total.value = typeof res?.total === 'number' ? res.total : papers.value.length
  } catch (e: any) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    if (status === 401 || detail === '请先登录') {
      loadError.value = '请先登录后再查看论文'
    } else {
      console.error('[MyUploadedPapers] loadPapers error:', e)
      console.error('[MyUploadedPapers] response status:', status, 'data:', e?.response?.data)
      loadError.value = detail || e?.message || '加载失败'
    }
    papers.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(loadPapers)

// ---------------------------------------------------------------------------
// Import: PDF
// ---------------------------------------------------------------------------
function onPdfFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  pdfFile.value = input.files?.[0] ?? null
}

async function submitPdfImport() {
  if (!pdfFile.value) {
    importError.value = '请选择 PDF 文件'
    return
  }
  importLoading.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const authors = pdfMeta.value.authors
      ? pdfMeta.value.authors.split(/[,，]\s*/).map(s => s.trim()).filter(Boolean)
      : []
    const created = await importUserPaperPdf(pdfFile.value, {
      title: pdfMeta.value.title,
      authors,
      abstract: pdfMeta.value.abstract,
      institution: pdfMeta.value.institution,
      year: pdfMeta.value.year ? parseInt(pdfMeta.value.year) : undefined,
      external_url: pdfMeta.value.external_url,
    })
    upsertPaper(created)
    importSuccess.value = '论文已成功导入！'
    pdfFile.value = null
    pdfMeta.value = { title: '', authors: '', abstract: '', institution: '', year: '', external_url: '' }
    setTimeout(() => {
      importSuccess.value = ''
      showImportDialog.value = false
    }, 1500)
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || e?.message || '导入失败'
  } finally {
    importLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Import: arXiv
// ---------------------------------------------------------------------------
async function submitArxivImport() {
  if (!arxivId.value.trim()) {
    importError.value = '请输入 arXiv ID 或链接'
    return
  }
  importLoading.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const created = await importUserPaperArxiv(arxivId.value.trim())
    upsertPaper(created)
    importSuccess.value = '论文已成功导入！'
    arxivId.value = ''
    setTimeout(() => {
      importSuccess.value = ''
      showImportDialog.value = false
    }, 1500)
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || e?.message || '导入失败'
  } finally {
    importLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Import: Manual
// ---------------------------------------------------------------------------
async function submitManualImport() {
  if (!manualForm.value.title.trim()) {
    importError.value = '标题不能为空'
    return
  }
  importLoading.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const authors = manualForm.value.authors
      ? manualForm.value.authors.split(/[,，]\s*/).map(s => s.trim()).filter(Boolean)
      : []
    const created = await importUserPaperManual({
      title: manualForm.value.title,
      authors,
      abstract: manualForm.value.abstract,
      institution: manualForm.value.institution,
      year: manualForm.value.year ? parseInt(manualForm.value.year) : undefined,
      external_url: manualForm.value.external_url,
    })
    upsertPaper(created)
    importSuccess.value = '论文已成功录入！'
    manualForm.value = { title: '', authors: '', abstract: '', institution: '', year: '', external_url: '' }
    setTimeout(() => {
      importSuccess.value = ''
      showImportDialog.value = false
    }, 1500)
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || e?.message || '录入失败'
  } finally {
    importLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Edit
// ---------------------------------------------------------------------------
function openEdit(paper: UserPaper) {
  editingPaper.value = paper
  editForm.value = {
    title: paper.title,
    authors: paper.authors.join(', '),
    abstract: paper.abstract,
    institution: paper.institution,
    year: paper.year ? String(paper.year) : '',
    external_url: paper.external_url,
  }
  editError.value = ''
  showEditDialog.value = true
}

async function submitEdit() {
  if (!editingPaper.value) return
  if (!editForm.value.title.trim()) {
    editError.value = '标题不能为空'
    return
  }
  editLoading.value = true
  editError.value = ''
  try {
    const authors = editForm.value.authors
      ? editForm.value.authors.split(/[,，]\s*/).map(s => s.trim()).filter(Boolean)
      : []
    const updated = await updateUserPaper(editingPaper.value.paper_id, {
      title: editForm.value.title,
      authors,
      abstract: editForm.value.abstract,
      institution: editForm.value.institution,
      year: editForm.value.year ? parseInt(editForm.value.year) : null,
      external_url: editForm.value.external_url,
    })
    upsertPaper(updated)
    showEditDialog.value = false
    editingPaper.value = null
  } catch (e: any) {
    editError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally {
    editLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// PDF supplement upload
// ---------------------------------------------------------------------------
function openPdfSupplement(paper: UserPaper) {
  pdfSupplementPaper.value = paper
  pdfSupplementFile.value = null
  pdfSupplementError.value = ''
  showPdfSupplementDialog.value = true
}

function onPdfSupplementFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  pdfSupplementFile.value = input.files?.[0] ?? null
}

async function submitPdfSupplement() {
  if (!pdfSupplementPaper.value || !pdfSupplementFile.value) {
    pdfSupplementError.value = '请选择 PDF 文件'
    return
  }
  pdfSupplementLoading.value = true
  pdfSupplementError.value = ''
  try {
    const updated = await uploadUserPaperPdf(pdfSupplementPaper.value.paper_id, pdfSupplementFile.value)
    upsertPaper(updated)
    showPdfSupplementDialog.value = false
    pdfSupplementPaper.value = null
  } catch (e: any) {
    pdfSupplementError.value = e?.response?.data?.detail || e?.message || '上传失败'
  } finally {
    pdfSupplementLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
async function confirmDelete(paperId: string) {
  deletingPaperId.value = paperId
}

async function doDelete() {
  if (!deletingPaperId.value) return
  try {
    await deleteUserPaper(deletingPaperId.value)
    papers.value = papers.value.filter(p => p.paper_id !== deletingPaperId.value)
    total.value -= 1
  } catch {
    // ignore
  } finally {
    deletingPaperId.value = null
  }
}

// ---------------------------------------------------------------------------
// Dialog helpers
// ---------------------------------------------------------------------------
function openImportDialog() {
  importError.value = ''
  importSuccess.value = ''
  showImportDialog.value = true
}

watch(importTab, () => {
  importError.value = ''
  importSuccess.value = ''
})

// PDF viewer URL builder
function buildPdfUrl(paper: UserPaper): string | null {
  if (paper.pdf_static_url) {
    const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
    const fileUrl = `${API_ORIGIN}${paper.pdf_static_url}`
    return `${viewerPath}?file=${encodeURIComponent(fileUrl)}&paperId=${encodeURIComponent(paper.paper_id)}`
  }
  if (paper.source_type === 'arxiv' && paper.source_ref) {
    return `https://arxiv.org/pdf/${paper.source_ref}`
  }
  if (paper.external_url && paper.external_url.toLowerCase().endsWith('.pdf')) {
    return paper.external_url
  }
  return null
}

function openPdf(paper: UserPaper) {
  const url = buildPdfUrl(paper)
  if (url) openExternal(url)
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return iso.slice(0, 10)
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-4xl mx-auto px-3 sm:px-6 py-6 pb-24">

      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-xl sm:text-2xl font-bold text-text-primary">我的论文</h1>
          <p class="text-sm text-text-muted mt-0.5">上传或导入论文，建立个人论文库</p>
        </div>
        <button
          class="flex items-center gap-1.5 px-4 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="openImportDialog"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          导入论文
        </button>
      </div>

      <!-- Search & Filter bar -->
      <div class="flex flex-col sm:flex-row gap-2 mb-4">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索标题、摘要、机构…"
          class="flex-1 px-3 py-2 rounded-xl bg-bg-card border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
        />
        <select
          v-model="filterSource"
          class="px-3 py-2 rounded-xl bg-bg-card border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors cursor-pointer"
        >
          <option value="">全部来源</option>
          <option value="pdf">PDF 上传</option>
          <option value="arxiv">arXiv 导入</option>
          <option value="manual">手动录入</option>
        </select>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-16">
        <svg class="animate-spin h-7 w-7 text-tinder-pink" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
      </div>

      <!-- Error -->
      <div v-else-if="loadError" class="text-center py-12 text-tinder-pink">{{ loadError }}</div>

      <!-- Empty state -->
      <div v-else-if="filteredPapers.length === 0" class="flex flex-col items-center py-16 gap-3 text-center">
        <div class="text-5xl">📄</div>
        <p class="text-base font-semibold text-text-primary">
          {{ papers.length === 0 ? '还没有论文' : '没有符合条件的论文' }}
        </p>
        <p class="text-sm text-text-muted max-w-xs">
          {{ papers.length === 0 ? '点击右上角「导入论文」开始添加你的第一篇论文' : '尝试清除搜索或筛选条件' }}
        </p>
        <button
          v-if="papers.length === 0"
          class="mt-2 px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="openImportDialog"
        >导入论文</button>
      </div>

      <!-- Paper list -->
      <div v-else class="space-y-3">
        <!-- Stats -->
        <div class="text-xs text-text-muted mb-1">共 {{ total }} 篇 · 显示 {{ filteredPapers.length }} 篇</div>

        <div
          v-for="paper in filteredPapers"
          :key="paper.paper_id"
          class="bg-bg-card border border-border rounded-2xl p-4 sm:p-5 transition-colors hover:border-tinder-pink/40"
        >
          <!-- Top row: source badge + year + date -->
          <div class="flex items-center gap-2 mb-2 flex-wrap">
            <span class="px-2 py-0.5 rounded-full text-xs font-semibold"
              :class="{
                'bg-tinder-pink/15 text-tinder-pink': paper.source_type === 'pdf',
                'bg-tinder-blue/15 text-tinder-blue': paper.source_type === 'arxiv',
                'bg-tinder-gold/15 text-tinder-gold': paper.source_type === 'manual',
              }"
            >
              {{ sourceLabel[paper.source_type] || paper.source_type }}
            </span>
            <span v-if="paper.year" class="text-xs text-text-muted">{{ paper.year }}</span>
            <span v-if="paper.institution" class="px-2 py-0.5 rounded-full bg-bg-elevated text-xs text-text-secondary">
              {{ paper.institution }}
            </span>
            <span class="ml-auto text-xs text-text-muted">{{ formatDate(paper.created_at) }}</span>
          </div>

          <!-- Title -->
          <h3 class="text-base font-semibold text-text-primary leading-snug mb-1">
            {{ paper.title || '（无标题）' }}
          </h3>

          <!-- Authors -->
          <p v-if="paper.authors.length" class="text-xs text-text-muted mb-1">
            {{ paper.authors.slice(0, 4).join(', ') }}{{ paper.authors.length > 4 ? ` 等 ${paper.authors.length} 人` : '' }}
          </p>

          <!-- Abstract (truncated) -->
          <p v-if="paper.abstract" class="text-sm text-text-secondary leading-relaxed line-clamp-2 mb-3">
            {{ paper.abstract }}
          </p>

          <!-- arXiv ref -->
          <p v-if="paper.source_type === 'arxiv' && paper.source_ref" class="text-xs font-mono text-text-muted mb-2">
            arXiv: {{ paper.source_ref }}
          </p>

          <!-- Actions -->
          <div class="flex flex-wrap gap-2 mt-2">
            <!-- PDF button -->
            <button
              v-if="paper.pdf_static_url || paper.source_type === 'arxiv' || (paper.external_url && paper.external_url.endsWith('.pdf'))"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-tinder-pink cursor-pointer hover:bg-bg-hover transition-colors"
              @click="openPdf(paper)"
            >
              📕 PDF
            </button>

            <!-- External link -->
            <a
              v-if="paper.external_url && !paper.external_url.endsWith('.pdf')"
              :href="paper.external_url"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-tinder-blue no-underline hover:bg-bg-hover transition-colors"
            >
              🔗 链接
            </a>
            <a
              v-if="paper.source_type === 'arxiv' && paper.source_ref"
              :href="`https://arxiv.org/abs/${paper.source_ref}`"
              target="_blank"
              rel="noopener"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-tinder-blue no-underline hover:bg-bg-hover transition-colors"
            >
              📄 arXiv
            </a>

            <!-- Upload PDF supplement (if no PDF yet) -->
            <button
              v-if="!paper.pdf_static_url && paper.source_type !== 'pdf'"
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-text-muted cursor-pointer hover:bg-bg-hover transition-colors"
              @click="openPdfSupplement(paper)"
            >
              ⬆ 补传 PDF
            </button>

            <div class="flex-1" />

            <!-- Edit -->
            <button
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-text-muted cursor-pointer hover:bg-bg-hover transition-colors"
              @click="openEdit(paper)"
            >
              ✏️ 编辑
            </button>

            <!-- Delete -->
            <button
              class="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-xs font-medium text-tinder-pink cursor-pointer hover:bg-bg-hover transition-colors"
              @click="confirmDelete(paper.paper_id)"
            >
              🗑 删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== Import dialog ===== -->
    <Teleport to="body">
      <div
        v-if="showImportDialog"
        class="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-2 sm:p-4"
        @click.self="showImportDialog = false"
      >
        <div class="w-full max-w-lg bg-bg-card border border-border rounded-2xl overflow-hidden shadow-2xl">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 class="text-base font-bold text-text-primary">导入论文</h2>
            <button
              class="w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary cursor-pointer border-none transition-colors"
              @click="showImportDialog = false"
            >✕</button>
          </div>

          <!-- Tabs -->
          <div class="flex border-b border-border px-5">
            <button
              v-for="tab in [
                { id: 'pdf', label: '📄 PDF 上传' },
                { id: 'arxiv', label: '🔬 arXiv 导入' },
                { id: 'manual', label: '✏️ 手动录入' },
              ]"
              :key="tab.id"
              class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0 mr-1"
              :class="importTab === tab.id
                ? 'border-tinder-pink text-tinder-pink'
                : 'border-transparent text-text-muted hover:text-text-secondary'"
              @click="importTab = tab.id as any"
            >{{ tab.label }}</button>
          </div>

          <!-- Tab content -->
          <div class="p-5 max-h-[70vh] overflow-y-auto space-y-3">

            <!-- PDF upload tab -->
            <template v-if="importTab === 'pdf'">
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">PDF 文件 <span class="text-tinder-pink">*</span></label>
                <div
                  class="relative flex items-center justify-center w-full h-24 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-tinder-pink/60 transition-colors bg-bg-elevated"
                  @click="openPdfInput"
                >
                  <div class="text-center pointer-events-none">
                    <div class="text-2xl mb-1">{{ pdfFile ? '📄' : '⬆️' }}</div>
                    <p class="text-xs text-text-muted">{{ pdfFile ? pdfFile.name : '点击选择 PDF（最大 50 MB）' }}</p>
                  </div>
                  <input ref="pdfInputRef" type="file" accept=".pdf,application/pdf" class="hidden" @change="onPdfFileChange" />
                </div>
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">标题</label>
                <input v-model="pdfMeta.title" type="text" placeholder="留空则使用文件名"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">作者（逗号分隔）</label>
                <input v-model="pdfMeta.authors" type="text" placeholder="例：张三, 李四"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <div class="flex gap-2">
                <div class="flex-1">
                  <label class="block text-xs font-semibold text-text-secondary mb-1">机构</label>
                  <input v-model="pdfMeta.institution" type="text" placeholder="发表机构"
                    class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
                </div>
                <div class="w-24">
                  <label class="block text-xs font-semibold text-text-secondary mb-1">年份</label>
                  <input v-model="pdfMeta.year" type="number" placeholder="2024"
                    class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
                </div>
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">摘要</label>
                <textarea v-model="pdfMeta.abstract" rows="3" placeholder="可选：粘贴摘要"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors resize-none" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">外部链接</label>
                <input v-model="pdfMeta.external_url" type="url" placeholder="https://..."
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
            </template>

            <!-- arXiv import tab -->
            <template v-else-if="importTab === 'arxiv'">
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">arXiv ID 或链接 <span class="text-tinder-pink">*</span></label>
                <input
                  v-model="arxivId"
                  type="text"
                  placeholder="例：2501.00001 或 https://arxiv.org/abs/2501.00001"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
                  @keyup.enter="submitArxivImport"
                />
              </div>
              <p class="text-xs text-text-muted leading-relaxed">
                将自动从 arXiv 拉取标题、作者、摘要等元数据。如需本地 PDF，导入后可在列表中点击「补传 PDF」。
              </p>
            </template>

            <!-- Manual entry tab -->
            <template v-else>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">标题 <span class="text-tinder-pink">*</span></label>
                <input v-model="manualForm.title" type="text" placeholder="论文标题"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">作者（逗号分隔）</label>
                <input v-model="manualForm.authors" type="text" placeholder="例：张三, 李四"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <div class="flex gap-2">
                <div class="flex-1">
                  <label class="block text-xs font-semibold text-text-secondary mb-1">机构</label>
                  <input v-model="manualForm.institution" type="text" placeholder="发表机构"
                    class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
                </div>
                <div class="w-24">
                  <label class="block text-xs font-semibold text-text-secondary mb-1">年份</label>
                  <input v-model="manualForm.year" type="number" placeholder="2024"
                    class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
                </div>
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">摘要</label>
                <textarea v-model="manualForm.abstract" rows="3" placeholder="论文摘要"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors resize-none" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-text-secondary mb-1">外部链接</label>
                <input v-model="manualForm.external_url" type="url" placeholder="原始论文链接（可选）"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
            </template>

            <!-- Feedback -->
            <p v-if="importError" class="text-sm text-tinder-pink">{{ importError }}</p>
            <p v-if="importSuccess" class="text-sm text-green-500 font-medium">✓ {{ importSuccess }}</p>
          </div>

          <!-- Footer actions -->
          <div class="flex justify-end gap-2 px-5 py-4 border-t border-border">
            <button
              class="px-4 py-2 rounded-full border border-border text-sm text-text-muted cursor-pointer bg-transparent hover:bg-bg-hover transition-colors"
              @click="showImportDialog = false"
            >取消</button>
            <button
              class="px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="importLoading"
              @click="importTab === 'pdf' ? submitPdfImport() : importTab === 'arxiv' ? submitArxivImport() : submitManualImport()"
            >
              <span v-if="importLoading">导入中…</span>
              <span v-else>{{ importTab === 'manual' ? '录入' : '导入' }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ===== Edit dialog ===== -->
    <Teleport to="body">
      <div
        v-if="showEditDialog"
        class="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-2 sm:p-4"
        @click.self="showEditDialog = false"
      >
        <div class="w-full max-w-lg bg-bg-card border border-border rounded-2xl overflow-hidden shadow-2xl">
          <div class="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 class="text-base font-bold text-text-primary">编辑论文信息</h2>
            <button class="w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary cursor-pointer border-none" @click="showEditDialog = false">✕</button>
          </div>
          <div class="p-5 space-y-3 max-h-[70vh] overflow-y-auto">
            <div>
              <label class="block text-xs font-semibold text-text-secondary mb-1">标题 <span class="text-tinder-pink">*</span></label>
              <input v-model="editForm.title" type="text"
                class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-text-secondary mb-1">作者（逗号分隔）</label>
              <input v-model="editForm.authors" type="text"
                class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
            </div>
            <div class="flex gap-2">
              <div class="flex-1">
                <label class="block text-xs font-semibold text-text-secondary mb-1">机构</label>
                <input v-model="editForm.institution" type="text"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <div class="w-24">
                <label class="block text-xs font-semibold text-text-secondary mb-1">年份</label>
                <input v-model="editForm.year" type="number"
                  class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
            </div>
            <div>
              <label class="block text-xs font-semibold text-text-secondary mb-1">摘要</label>
              <textarea v-model="editForm.abstract" rows="3"
                class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors resize-none" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-text-secondary mb-1">外部链接</label>
              <input v-model="editForm.external_url" type="url"
                class="w-full px-3 py-2 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
            </div>
            <p v-if="editError" class="text-sm text-tinder-pink">{{ editError }}</p>
          </div>
          <div class="flex justify-end gap-2 px-5 py-4 border-t border-border">
            <button class="px-4 py-2 rounded-full border border-border text-sm text-text-muted cursor-pointer bg-transparent hover:bg-bg-hover transition-colors" @click="showEditDialog = false">取消</button>
            <button
              class="px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="editLoading"
              @click="submitEdit"
            >{{ editLoading ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ===== PDF supplement dialog ===== -->
    <Teleport to="body">
      <div
        v-if="showPdfSupplementDialog"
        class="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-2 sm:p-4"
        @click.self="showPdfSupplementDialog = false"
      >
        <div class="w-full max-w-md bg-bg-card border border-border rounded-2xl overflow-hidden shadow-2xl">
          <div class="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 class="text-base font-bold text-text-primary">补传 PDF</h2>
            <button class="w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary cursor-pointer border-none" @click="showPdfSupplementDialog = false">✕</button>
          </div>
          <div class="p-5 space-y-3">
            <p class="text-sm text-text-secondary truncate">{{ pdfSupplementPaper?.title }}</p>
            <div
              class="relative flex items-center justify-center w-full h-24 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-tinder-pink/60 transition-colors bg-bg-elevated"
              @click="openPdfSupplementInput"
            >
              <div class="text-center pointer-events-none">
                <div class="text-2xl mb-1">{{ pdfSupplementFile ? '📄' : '⬆️' }}</div>
                <p class="text-xs text-text-muted">{{ pdfSupplementFile ? pdfSupplementFile.name : '点击选择 PDF（最大 50 MB）' }}</p>
              </div>
              <input ref="pdfSupplementInputRef" type="file" accept=".pdf,application/pdf" class="hidden" @change="onPdfSupplementFileChange" />
            </div>
            <p v-if="pdfSupplementError" class="text-sm text-tinder-pink">{{ pdfSupplementError }}</p>
          </div>
          <div class="flex justify-end gap-2 px-5 py-4 border-t border-border">
            <button class="px-4 py-2 rounded-full border border-border text-sm text-text-muted cursor-pointer bg-transparent hover:bg-bg-hover transition-colors" @click="showPdfSupplementDialog = false">取消</button>
            <button
              class="px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="pdfSupplementLoading"
              @click="submitPdfSupplement"
            >{{ pdfSupplementLoading ? '上传中…' : '上传' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ===== Delete confirmation dialog ===== -->
    <Teleport to="body">
      <div
        v-if="deletingPaperId"
        class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
        @click.self="deletingPaperId = null"
      >
        <div class="bg-bg-card border border-border rounded-2xl p-6 max-w-sm w-full shadow-2xl text-center">
          <div class="text-3xl mb-3">🗑</div>
          <h3 class="text-base font-bold text-text-primary mb-2">确认删除？</h3>
          <p class="text-sm text-text-muted mb-5 leading-relaxed">删除后论文及其关联 PDF 文件将无法恢复</p>
          <div class="flex gap-3 justify-center">
            <button class="px-5 py-2 rounded-full border border-border text-sm text-text-muted cursor-pointer bg-transparent hover:bg-bg-hover transition-colors" @click="deletingPaperId = null">取消</button>
            <button class="px-5 py-2 rounded-full bg-tinder-pink text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity" @click="doDelete">确认删除</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>
