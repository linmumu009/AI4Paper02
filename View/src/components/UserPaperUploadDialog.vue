<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  importUserPaperArxiv,
  importUserPaperPdf,
  batchProcessUserPapers,
} from '../api'
import { useEngagement } from '../composables/useEngagement'
import { useEntitlements } from '../composables/useEntitlements'
import RewardBoostBanner from './RewardBoostBanner.vue'
import UpgradePrompt from './UpgradePrompt.vue'
import QuotaWarningBanner from './QuotaWarningBanner.vue'

const emit = defineEmits<{
  close: []
  uploaded: [paperId: string]
}>()

type UploadTab = 'arxiv' | 'pdf'
const activeTab = ref<UploadTab>('arxiv')

const engagement = useEngagement()
const ent = useEntitlements()
const { refreshEntitlements } = ent
const useUploadReward = ref(false)

const uploadQuotaBlocked = computed(() => !ent.canUse('upload'))
const uploadQuotaSummary = computed(() => ent.quotaSummary('upload'))

onMounted(() => {
  if (engagement.loaded.value) {
    void engagement.loadActiveRewards('upload')
  }
})

// arXiv tab
const arxivInput = ref('')
const arxivLoading = ref(false)
const arxivError = ref('')

async function handleArxivImport() {
  const id = arxivInput.value.trim()
  if (!id) return
  arxivLoading.value = true
  arxivError.value = ''
  try {
    const paper = await importUserPaperArxiv(id)
    const rewardToUse = useUploadReward.value ? engagement.bestUploadReward.value : undefined
    const rewardId = rewardToUse?.id
    await batchProcessUserPapers([paper.paper_id], rewardId)
    if (rewardId !== undefined && rewardToUse) {
      engagement.notifyRewardUsed(rewardToUse.reward_name)
    }
    void refreshEntitlements(true)
    emit('uploaded', paper.paper_id)
    emit('close')
  } catch (e: any) {
    arxivError.value = e?.response?.data?.detail || e?.message || '导入失败'
  } finally {
    arxivLoading.value = false
  }
}

// PDF tab — multi-file
const MAX_FILES = 20
const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50 MB

const pdfFiles = ref<File[]>([])
const fileStatuses = ref<Array<'pending' | 'uploading' | 'done' | 'failed'>>([])
const pdfLoading = ref(false)
const pdfError = ref('')
const dropActive = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// Upload progress tracking
const uploadProgress = ref({ done: 0, total: 0 })
const uploadPhase = ref<'idle' | 'uploading' | 'processing' | 'done'>('idle')
const uploadResults = ref<Array<{ name: string; ok: boolean; error?: string }>>([])
const batchProcessFailed = ref(false)
const showSuccessList = ref(false)

const atFileLimit = computed(() => pdfFiles.value.length >= MAX_FILES)
const nearFileLimit = computed(() => pdfFiles.value.length >= 15 && pdfFiles.value.length < MAX_FILES)
const uploadPercent = computed(() =>
  uploadProgress.value.total ? Math.round((uploadProgress.value.done / uploadProgress.value.total) * 100) : 0,
)

function addFiles(files: FileList | null | undefined) {
  if (!files) return
  let pdfs = Array.from(files).filter(f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))

  // Size validation
  const oversized = pdfs.filter(f => f.size > MAX_FILE_SIZE)
  if (oversized.length > 0) {
    const names = oversized.length <= 2
      ? oversized.map(f => f.name).join('、')
      : `${oversized.slice(0, 2).map(f => f.name).join('、')} 等 ${oversized.length} 个`
    pdfError.value = `${names} 超过 50 MB 限制，已自动过滤`
    pdfs = pdfs.filter(f => f.size <= MAX_FILE_SIZE)
  } else {
    pdfError.value = ''
  }

  const combined = [...pdfFiles.value, ...pdfs]
  if (combined.length > MAX_FILES) {
    const allowed = MAX_FILES - pdfFiles.value.length
    if (!pdfError.value) pdfError.value = `单次最多选择 ${MAX_FILES} 个 PDF 文件，已截断`
    pdfFiles.value = [...pdfFiles.value, ...pdfs.slice(0, allowed)]
    fileStatuses.value = [...fileStatuses.value, ...Array(allowed).fill('pending')]
  } else {
    pdfFiles.value = combined
    fileStatuses.value = [...fileStatuses.value, ...Array(pdfs.length).fill('pending')]
  }
}

function onDrop(e: DragEvent) {
  dropActive.value = false
  if (uploadPhase.value !== 'idle') return
  addFiles(e.dataTransfer?.files)
}

function onFileChange(e: Event) {
  addFiles((e.target as HTMLInputElement).files)
  // Reset input so same file can be re-added after removal
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function removeFile(idx: number) {
  pdfFiles.value = pdfFiles.value.filter((_, i) => i !== idx)
  fileStatuses.value = fileStatuses.value.filter((_, i) => i !== idx)
  if (pdfFiles.value.length === 0) pdfError.value = ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Concurrency-limited map — max `concurrency` in-flight at once */
async function concurrentMap<T, R>(
  items: T[],
  fn: (item: T) => Promise<R>,
  concurrency: number,
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length)
  let index = 0
  async function worker() {
    while (index < items.length) {
      const i = index++
      try {
        results[i] = { status: 'fulfilled', value: await fn(items[i]) }
      } catch (reason: unknown) {
        results[i] = { status: 'rejected', reason }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker))
  return results
}

async function handlePdfUpload() {
  if (!pdfFiles.value.length) return
  pdfLoading.value = true
  pdfError.value = ''
  uploadResults.value = []
  batchProcessFailed.value = false
  showSuccessList.value = false
  uploadProgress.value = { done: 0, total: pdfFiles.value.length }
  uploadPhase.value = 'uploading'
  // Reset all to pending
  fileStatuses.value = pdfFiles.value.map(() => 'pending')

  const rewardToUse = useUploadReward.value ? engagement.bestUploadReward.value : undefined
  const rewardId = rewardToUse?.id

  // Upload files concurrently (max 3 at a time), tracking per-file status
  const files = pdfFiles.value.slice()
  const fileEntries = files.map((file, i) => ({ file, i }))

  const settled = await concurrentMap(
    fileEntries,
    async ({ file, i }) => {
      fileStatuses.value[i] = 'uploading'
      const paper = await importUserPaperPdf(file, {
        title: file.name.replace(/\.pdf$/i, ''),
      })
      uploadProgress.value.done++
      fileStatuses.value[i] = 'done'
      return paper
    },
    3,
  )

  // Mark failed statuses
  for (let i = 0; i < settled.length; i++) {
    if (settled[i].status === 'rejected') {
      fileStatuses.value[i] = 'failed'
    }
  }

  // Collect results
  const successPaperIds: string[] = []
  const resultsArr: Array<{ name: string; ok: boolean; error?: string }> = []
  for (let i = 0; i < settled.length; i++) {
    const r = settled[i]
    if (r.status === 'fulfilled') {
      successPaperIds.push(r.value.paper_id)
      resultsArr.push({ name: files[i].name, ok: true })
    } else {
      const err = (r.reason as any)?.response?.data?.detail || (r.reason as any)?.message || '上传失败'
      resultsArr.push({ name: files[i].name, ok: false, error: err })
    }
  }
  uploadResults.value = resultsArr

  if (successPaperIds.length > 0) {
    uploadPhase.value = 'processing'
    try {
      await batchProcessUserPapers(successPaperIds, rewardId)
      if (rewardId !== undefined && rewardToUse) {
        engagement.notifyRewardUsed(rewardToUse.reward_name)
      }
    } catch {
      batchProcessFailed.value = true
    }
    void refreshEntitlements(true)
  }

  uploadPhase.value = 'done'
  pdfLoading.value = false

  // If all succeeded, auto-close after a brief delay
  const allOk = resultsArr.every(r => r.ok)
  if (allOk) {
    emit('uploaded', successPaperIds[0])
    setTimeout(() => emit('close'), 1200)
  }
}

function resetPdfForm() {
  pdfFiles.value = []
  fileStatuses.value = []
  pdfError.value = ''
  uploadPhase.value = 'idle'
  uploadResults.value = []
  uploadProgress.value = { done: 0, total: 0 }
  batchProcessFailed.value = false
  showSuccessList.value = false
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="emit('close')">
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-black/60" @click="emit('close')" />

    <!-- Dialog -->
    <div class="relative z-10 w-full max-w-md bg-bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-border">
        <h2 class="text-base font-semibold text-text-primary">
          上传 / 导入论文
          <span v-if="activeTab === 'pdf' && pdfFiles.length > 0" class="ml-2 text-xs font-normal text-text-muted">
            已选 {{ pdfFiles.length }} 个文件
          </span>
        </h2>
        <button
          class="w-7 h-7 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover bg-transparent border-none cursor-pointer transition-colors"
          @click="emit('close')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-border px-5">
        <button
          class="pb-3 pt-3 mr-5 text-sm font-semibold border-b-2 bg-transparent cursor-pointer transition-colors"
          :class="activeTab === 'arxiv'
            ? 'border-[#f59e0b] text-[#f59e0b]'
            : 'border-transparent text-text-muted hover:text-text-secondary'"
          @click="activeTab = 'arxiv'; resetPdfForm()"
        >arXiv 导入</button>
        <button
          class="pb-3 pt-3 text-sm font-semibold border-b-2 bg-transparent cursor-pointer transition-colors"
          :class="activeTab === 'pdf'
            ? 'border-[#f59e0b] text-[#f59e0b]'
            : 'border-transparent text-text-muted hover:text-text-secondary'"
          @click="activeTab = 'pdf'"
        >PDF 上传</button>
      </div>

      <!-- arXiv tab -->
      <div v-if="activeTab === 'arxiv'" class="p-5">
        <p class="text-xs text-text-muted mb-3 leading-relaxed">
          输入 arXiv ID 或完整链接，系统将自动获取元数据并生成结构化摘要。
        </p>

        <UpgradePrompt
          v-if="uploadQuotaBlocked && ent.loaded.value"
          feature="upload"
          class="mb-3"
        />
        <QuotaWarningBanner
          v-else-if="ent.loaded.value"
          feature="upload"
          class="mb-3"
        />
        <div
          v-else-if="ent.loaded.value && ent.limit('upload') !== null"
          class="mb-3 text-[11px] text-text-muted text-right"
        >
          本月上传：{{ uploadQuotaSummary }}
        </div>

        <RewardBoostBanner
          v-if="engagement.bestUploadReward.value && !uploadQuotaBlocked"
          :reward="engagement.bestUploadReward.value"
          v-model="useUploadReward"
          class="mb-3"
        />
        <div v-if="!uploadQuotaBlocked" class="flex gap-2">
          <input
            v-model="arxivInput"
            class="flex-1 bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#f59e0b]/60 transition-colors"
            placeholder="例如：2501.00001 或 https://arxiv.org/abs/..."
            :disabled="arxivLoading"
            @keydown.enter="handleArxivImport"
          />
          <button
            class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-mypapers-gradient border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            :disabled="!arxivInput.trim() || arxivLoading"
            @click="handleArxivImport"
          >
            <span v-if="arxivLoading" class="inline-block animate-spin">⟳</span>
            <span v-else>导入</span>
          </button>
        </div>
        <p v-if="arxivError" class="text-xs text-red-500 mt-2">{{ arxivError }}</p>
        <p v-if="!uploadQuotaBlocked" class="text-xs text-text-muted mt-3 leading-relaxed">
          导入成功后将自动启动处理流程（约 1.5–3 分钟），可在「我的论文」Tab 中查看进度。
        </p>
      </div>

      <!-- PDF tab -->
      <div v-if="activeTab === 'pdf'" class="p-5">
        <p class="text-xs text-text-muted mb-3 leading-relaxed">
          支持批量上传，最多 {{ MAX_FILES }} 个 PDF（每个最大 50 MB）。上传后并行启动处理流水线。
        </p>

        <UpgradePrompt
          v-if="uploadQuotaBlocked && ent.loaded.value"
          feature="upload"
          class="mb-3"
        />
        <QuotaWarningBanner
          v-else-if="ent.loaded.value"
          feature="upload"
          class="mb-3"
        />
        <div
          v-else-if="ent.loaded.value && ent.limit('upload') !== null"
          class="mb-3 text-[11px] text-text-muted text-right"
        >
          本月上传：{{ uploadQuotaSummary }}
        </div>

        <template v-if="!uploadQuotaBlocked">
          <!-- Drop zone — hidden during upload/processing/done phases -->
          <div
            v-if="uploadPhase === 'idle'"
            class="border-2 border-dashed rounded-xl p-5 text-center transition-colors mb-3"
            :class="[
              atFileLimit
                ? 'border-border/40 bg-bg-elevated/50 cursor-not-allowed opacity-60'
                : dropActive
                  ? 'border-[#f59e0b] bg-[#f59e0b]/5 cursor-pointer'
                  : 'border-border hover:border-[#f59e0b]/50 cursor-pointer',
            ]"
            @dragover.prevent="!atFileLimit && (dropActive = true)"
            @dragleave="dropActive = false"
            @drop.prevent="onDrop"
            @click="!atFileLimit && fileInputRef?.click()"
          >
            <input
              ref="fileInputRef"
              type="file"
              accept=".pdf,application/pdf"
              multiple
              class="hidden"
              @change="onFileChange"
            />
            <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 mx-auto mb-1.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p class="text-sm text-text-muted">拖拽 PDF 到此处，或<span class="text-[#f59e0b]">点击选择文件</span></p>
            <p
              class="text-xs mt-0.5 transition-colors"
              :class="atFileLimit
                ? 'text-text-muted font-medium'
                : nearFileLimit
                  ? 'text-[#f59e0b]'
                  : 'text-text-muted/60'"
            >
              <span v-if="atFileLimit">已达上限 {{ MAX_FILES }} 个</span>
              <span v-else-if="nearFileLimit">已选 {{ pdfFiles.length }}/{{ MAX_FILES }}，即将达上限</span>
              <span v-else>可多选，最多 {{ MAX_FILES }} 个</span>
            </p>
          </div>

          <!-- File list — always visible when files are selected -->
          <div v-if="pdfFiles.length > 0" class="mb-3 space-y-1.5 max-h-48 overflow-y-auto">
            <div
              v-for="(file, idx) in pdfFiles"
              :key="idx"
              class="flex items-center gap-2 px-3 py-2 rounded-lg bg-bg-elevated border text-sm transition-colors"
              :class="fileStatuses[idx] === 'failed' ? 'border-red-500/40' : 'border-border'"
            >
              <span class="text-base shrink-0">📄</span>
              <span class="flex-1 truncate text-text-primary text-xs">{{ file.name }}</span>
              <span class="text-[10px] text-text-muted shrink-0">{{ formatSize(file.size) }}</span>
              <!-- Per-file status icon -->
              <span v-if="fileStatuses[idx] === 'uploading'" class="shrink-0 inline-block animate-spin text-[#f59e0b] text-xs leading-none" title="上传中">⟳</span>
              <span v-else-if="fileStatuses[idx] === 'done'" class="shrink-0 text-green-500 text-xs leading-none" title="上传成功">✓</span>
              <span v-else-if="fileStatuses[idx] === 'failed'" class="shrink-0 text-red-500 text-xs leading-none" title="上传失败">✗</span>
              <!-- Remove button — only in idle phase -->
              <button
                v-if="uploadPhase === 'idle'"
                class="shrink-0 text-text-muted hover:text-red-500 bg-transparent border-none cursor-pointer text-xs p-0.5 leading-none"
                @click.stop="removeFile(idx)"
              >✕</button>
            </div>
          </div>

          <!-- Upload progress -->
          <div v-if="uploadPhase === 'uploading'" class="mb-3 space-y-1.5">
            <div class="flex justify-between text-xs text-text-muted">
              <span>正在上传 {{ uploadProgress.done }}/{{ uploadProgress.total }}...</span>
              <span class="text-[#f59e0b] font-medium">{{ uploadPercent }}%</span>
            </div>
            <div class="w-full h-2 bg-bg-elevated rounded-full overflow-hidden">
              <div
                class="h-full bg-[#f59e0b] rounded-full transition-all duration-300"
                :style="{ width: `${uploadPercent}%` }"
              />
            </div>
          </div>

          <!-- Processing phase -->
          <div v-if="uploadPhase === 'processing'" class="mb-3 flex items-center gap-2 text-xs text-text-muted">
            <span class="inline-block animate-spin text-[#f59e0b]">⟳</span>
            正在启动处理流水线...
          </div>

          <!-- Results summary -->
          <div v-if="uploadPhase === 'done'" class="mb-3 space-y-2">
            <!-- Summary header -->
            <div class="flex items-center gap-2 text-xs font-medium">
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-green-500/10 text-green-500">
                ✓ 成功 {{ uploadResults.filter(r => r.ok).length }} 篇
              </span>
              <span v-if="uploadResults.some(r => !r.ok)" class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/10 text-red-500">
                ✗ 失败 {{ uploadResults.filter(r => !r.ok).length }} 篇
              </span>
              <span class="text-text-muted">/ 共 {{ uploadResults.length }} 篇</span>
            </div>

            <!-- Failed items — full error text, no truncate -->
            <div v-if="uploadResults.some(r => !r.ok)" class="space-y-1">
              <div
                v-for="r in uploadResults.filter(r => !r.ok)"
                :key="r.name"
                class="text-[11px] text-red-500 leading-relaxed bg-red-500/5 border border-red-500/20 rounded-lg px-2.5 py-1.5"
              >
                <span class="font-medium break-all">{{ r.name }}</span>
                <span class="text-red-400 block mt-0.5">{{ r.error }}</span>
              </div>
            </div>

            <!-- Success list — collapsible -->
            <div v-if="uploadResults.some(r => r.ok)">
              <button
                class="text-[11px] text-text-muted hover:text-text-secondary bg-transparent border-none cursor-pointer p-0 flex items-center gap-1 transition-colors"
                @click="showSuccessList = !showSuccessList"
              >
                <span class="transition-transform duration-200" :class="showSuccessList ? 'rotate-90' : ''">▶</span>
                {{ showSuccessList ? '收起' : '展开' }}成功列表（{{ uploadResults.filter(r => r.ok).length }} 篇）
              </button>
              <div v-if="showSuccessList" class="mt-1 space-y-0.5">
                <div
                  v-for="r in uploadResults.filter(r => r.ok)"
                  :key="r.name"
                  class="text-[11px] text-green-500/80 truncate px-2"
                >
                  ✓ {{ r.name }}
                </div>
              </div>
            </div>

            <!-- batchProcess failure warning -->
            <div v-if="batchProcessFailed" class="text-[11px] text-[#f59e0b] bg-[#f59e0b]/8 border border-[#f59e0b]/20 rounded-lg px-2.5 py-1.5 leading-relaxed">
              ⚠ 处理启动失败，文件已上传成功。可稍后在「我的论文」Tab 手动触发处理。
            </div>

            <!-- Success hint -->
            <p v-if="uploadResults.some(r => r.ok) && !batchProcessFailed" class="text-[11px] text-text-muted leading-relaxed">
              已并行启动处理（约 1.5–3 分钟），可在「我的论文」Tab 查看进度。
            </p>
          </div>

          <!-- Reward boost banner -->
          <RewardBoostBanner
            v-if="engagement.bestUploadReward.value && uploadPhase === 'idle'"
            :reward="engagement.bestUploadReward.value"
            v-model="useUploadReward"
            class="mb-3"
          />

          <p v-if="pdfError" class="text-xs text-red-500 mb-3">{{ pdfError }}</p>

          <!-- Action buttons -->
          <div v-if="uploadPhase !== 'done'" class="flex gap-2">
            <button
              class="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white bg-mypapers-gradient border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!pdfFiles.length || pdfLoading"
              @click="handlePdfUpload"
            >
              <span v-if="uploadPhase === 'uploading'" class="inline-flex items-center gap-1.5">
                <span class="inline-block animate-spin">⟳</span>
                上传中 {{ uploadProgress.done }}/{{ uploadProgress.total }}
              </span>
              <span v-else-if="uploadPhase === 'processing'" class="inline-flex items-center gap-1.5">
                <span class="inline-block animate-spin">⟳</span>
                处理启动中...
              </span>
              <span v-else>
                {{ useUploadReward && engagement.bestUploadReward.value ? '🚀 优先处理' : '上传并处理' }}
                <span v-if="pdfFiles.length > 1">（{{ pdfFiles.length }} 篇）</span>
              </span>
            </button>
          </div>
          <div v-else class="flex gap-2">
            <button
              class="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white bg-mypapers-gradient border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="resetPdfForm"
            >继续上传</button>
            <button
              class="flex-1 py-2.5 rounded-lg text-sm font-semibold border border-border text-text-muted bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="emit('close')"
            >关闭</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
