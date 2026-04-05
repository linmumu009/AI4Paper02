<script setup lang="ts">
import { ref } from 'vue'
import {
  importUserPaperArxiv,
  importUserPaperPdf,
  processUserPaper,
} from '../api'

const emit = defineEmits<{
  close: []
  uploaded: [paperId: string]
}>()

type UploadTab = 'arxiv' | 'pdf'
const activeTab = ref<UploadTab>('arxiv')

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
    await processUserPaper(paper.paper_id)
    emit('uploaded', paper.paper_id)
    emit('close')
  } catch (e: any) {
    arxivError.value = e?.response?.data?.detail || e?.message || '导入失败'
  } finally {
    arxivLoading.value = false
  }
}

// PDF tab
const pdfFile = ref<File | null>(null)
const pdfTitle = ref('')
const pdfLoading = ref(false)
const pdfError = ref('')
const dropActive = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

function onDrop(e: DragEvent) {
  dropActive.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type === 'application/pdf') {
    pdfFile.value = file
    if (!pdfTitle.value) pdfTitle.value = file.name.replace(/\.pdf$/i, '')
  }
}

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) {
    pdfFile.value = file
    if (!pdfTitle.value) pdfTitle.value = file.name.replace(/\.pdf$/i, '')
  }
}

async function handlePdfUpload() {
  if (!pdfFile.value) return
  pdfLoading.value = true
  pdfError.value = ''
  try {
    const paper = await importUserPaperPdf(pdfFile.value, {
      title: pdfTitle.value || pdfFile.value.name.replace(/\.pdf$/i, ''),
    })
    await processUserPaper(paper.paper_id)
    emit('uploaded', paper.paper_id)
    emit('close')
  } catch (e: any) {
    pdfError.value = e?.response?.data?.detail || e?.message || '上传失败'
  } finally {
    pdfLoading.value = false
  }
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
        <h2 class="text-base font-semibold text-text-primary">上传 / 导入论文</h2>
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
          @click="activeTab = 'arxiv'"
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
        <div class="flex gap-2">
          <input
            v-model="arxivInput"
            class="flex-1 bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#f59e0b]/60 transition-colors"
            placeholder="例如：2501.00001 或 https://arxiv.org/abs/..."
            :disabled="arxivLoading"
            @keydown.enter="handleArxivImport"
          />
          <button
            class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-[#f59e0b] to-[#ef4444] border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            :disabled="!arxivInput.trim() || arxivLoading"
            @click="handleArxivImport"
          >
            <span v-if="arxivLoading" class="inline-block animate-spin">⟳</span>
            <span v-else>导入</span>
          </button>
        </div>
        <p v-if="arxivError" class="text-xs text-red-500 mt-2">{{ arxivError }}</p>
        <p class="text-xs text-text-muted mt-3 leading-relaxed">
          导入成功后将自动启动处理流程（约 1.5–3 分钟），可在「我的论文」Tab 中查看进度。
        </p>
      </div>

      <!-- PDF tab -->
      <div v-if="activeTab === 'pdf'" class="p-5">
        <p class="text-xs text-text-muted mb-3 leading-relaxed">
          上传 PDF 文件，系统将提取文本并生成结构化摘要（最大 50 MB）。
        </p>

        <!-- Drop zone -->
        <div
          class="border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer mb-3"
          :class="dropActive
            ? 'border-[#f59e0b] bg-[#f59e0b]/5'
            : 'border-border hover:border-[#f59e0b]/50'"
          @dragover.prevent="dropActive = true"
          @dragleave="dropActive = false"
          @drop.prevent="onDrop"
          @click="fileInputRef?.click()"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept=".pdf,application/pdf"
            class="hidden"
            @change="onFileChange"
          />
          <div v-if="pdfFile" class="flex items-center justify-center gap-2">
            <span class="text-xl">📄</span>
            <span class="text-sm text-text-primary font-medium truncate max-w-[200px]">{{ pdfFile.name }}</span>
            <button
              class="text-xs text-text-muted hover:text-red-500 bg-transparent border-none cursor-pointer ml-1"
              @click.stop="pdfFile = null; pdfTitle = ''"
            >✕</button>
          </div>
          <div v-else>
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 mx-auto mb-2 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p class="text-sm text-text-muted">拖拽 PDF 到此处，或<span class="text-[#f59e0b]">点击选择文件</span></p>
          </div>
        </div>

        <!-- Title input -->
        <input
          v-model="pdfTitle"
          class="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#f59e0b]/60 transition-colors mb-3"
          placeholder="论文标题（可选，留空将使用文件名）"
          :disabled="pdfLoading"
        />

        <p v-if="pdfError" class="text-xs text-red-500 mb-3">{{ pdfError }}</p>

        <button
          class="w-full py-2.5 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-[#f59e0b] to-[#ef4444] border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!pdfFile || pdfLoading"
          @click="handlePdfUpload"
        >
          <span v-if="pdfLoading" class="inline-block animate-spin mr-1">⟳</span>
          上传并处理
        </button>
      </div>
    </div>
  </div>
</template>
