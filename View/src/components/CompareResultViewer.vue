<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { fetchCompareResult } from '../api'
import type { KbCompareResult } from '../types/paper'
import AddToProjectDialog from './project/AddToProjectDialog.vue'
import { renderChatMarkdown } from '../utils/chatMarkdown'
import 'katex/dist/katex.min.css'
import archiveIcon from '../assets/heroicons/archive-box.svg'
import closeIcon from '../assets/heroicons/x-mark.svg'
import documentIcon from '../assets/heroicons/document-text.svg'
import folderIcon from '../assets/heroicons/folder.svg'

const props = defineProps<{
  resultId: number
  paperTitles?: Record<string, string>
}>()

const emit = defineEmits<{
  close: []
}>()

const loading = ref(true)
const error = ref('')
const result = ref<KbCompareResult | null>(null)
const showProjectDialog = ref(false)

const renderedHtml = computed(() => {
  if (!result.value) return ''
  return renderChatMarkdown(result.value.markdown)
})

const copied = ref(false)

async function copyToClipboard() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value.markdown)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

async function loadResult() {
  loading.value = true
  error.value = ''
  try {
    result.value = await fetchCompareResult(props.resultId)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function getPaperTitle(paperId: string): string {
  return props.paperTitles?.[paperId] || paperId
}

onMounted(loadResult)
watch(() => props.resultId, loadResult)
</script>

<template>
  <div class="compare-result-viewer h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 px-5 py-3 border-b border-border bg-bg-card">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <img :src="archiveIcon" alt="" class="w-5 h-5">
          <h2 class="text-base font-bold text-text-primary truncate">{{ result?.title || '对比结果' }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <button
            v-if="result"
            class="px-3 py-1 rounded-full text-xs font-medium border border-border bg-transparent text-tinder-green cursor-pointer hover:bg-bg-hover transition-colors flex items-center gap-1"
            @click="showProjectDialog = true"
          ><img :src="folderIcon" alt="" class="w-3 h-3">加入课题</button>
          <button
            v-if="result"
            class="px-3 py-1 rounded-full text-xs font-medium border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors flex items-center gap-1"
            :class="copied ? 'text-tinder-green border-tinder-green/30' : 'text-text-muted'"
            @click="copyToClipboard"
          >
            <img v-if="!copied" :src="documentIcon" alt="" class="w-3 h-3">
            {{ copied ? '已复制' : '复制' }}
          </button>
          <button
            class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors flex items-center gap-1"
            @click="emit('close')"
          ><img :src="closeIcon" alt="" class="w-3 h-3">关闭</button>
        </div>
      </div>
      <!-- Paper tags -->
      <div v-if="result" class="flex flex-wrap gap-1.5">
        <span
          v-for="pid in result.paper_ids"
          :key="pid"
          class="text-[11px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-secondary"
        >
          <img :src="documentIcon" alt="" class="inline-block w-3 h-3 mr-1">{{ getPaperTitle(pid) }}
        </span>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center justify-center h-full gap-4">
        <img :src="archiveIcon" alt="" class="animate-spin h-8 w-8">
        <span class="text-sm text-text-muted">加载对比结果...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center justify-center h-full gap-4">
        <img :src="closeIcon" alt="" class="h-8 w-8">
        <h3 class="text-sm font-semibold text-tinder-pink">加载失败</h3>
        <p class="text-xs text-text-muted">{{ error }}</p>
        <button
          class="px-4 py-2 rounded-full bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white text-xs font-medium border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="loadResult"
        >重试</button>
      </div>

      <!-- Markdown -->
      <div
        v-else-if="result"
        class="compare-markdown prose prose-sm max-w-none"
        v-html="renderedHtml"
      ></div>
      </div>
      <AddToProjectDialog
        v-if="showProjectDialog && result"
        asset-type="compare_result"
        :asset-id="String(result.id)"
        :asset-title="result.title"
        @close="showProjectDialog = false"
      />
    </div>
</template>

<style scoped>
.compare-markdown :deep(h1) {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border);
}
.compare-markdown :deep(h2) {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
}
.compare-markdown :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
}
.compare-markdown :deep(p) {
  color: var(--color-text-secondary);
  line-height: 1.7;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}
.compare-markdown :deep(ul),
.compare-markdown :deep(ol) {
  color: var(--color-text-secondary);
  padding-left: 1.5rem;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}
.compare-markdown :deep(li) {
  margin-bottom: 0.25rem;
  line-height: 1.6;
}
.compare-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1rem;
  font-size: 0.8125rem;
}
.compare-markdown :deep(th) {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  border: 1px solid var(--color-border);
}
.compare-markdown :deep(td) {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}
.compare-markdown :deep(tr:nth-child(even)) {
  background: var(--color-bg-elevated);
}
.compare-markdown :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 600;
}
.compare-markdown :deep(code) {
  background: var(--color-bg-elevated);
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-tinder-purple);
}
.compare-markdown :deep(blockquote) {
  border-left: 3px solid var(--color-tinder-purple);
  padding-left: 1rem;
  color: var(--color-text-muted);
  font-style: italic;
  margin: 0.75rem 0;
}
.compare-markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 1.25rem 0;
}
.compare-markdown :deep(.katex-display) {
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.4rem 0;
}
:global(.dark) .compare-result-viewer img {
  filter: invert(1);
}
</style>
