<script setup lang="ts">
import { ref } from 'vue'
import { downloadResearchResult } from '../../api'
import { useEntitlements } from '../../composables/useEntitlements'

const props = defineProps<{
  hasText: boolean
  sessionId?: number | null
}>()

const emit = defineEmits<{
  copy: []
  saveToLibrary: [sessionId: number]
}>()

const ent = useEntitlements()
const copyDone = ref(false)
const showDownloadMenu = ref(false)
const downloading = ref(false)
const saved = ref(false)

function handleSaveToLibrary() {
  if (saved.value || !props.sessionId) return
  saved.value = true
  emit('saveToLibrary', props.sessionId)
}

async function handleCopy() {
  emit('copy')
  copyDone.value = true
  setTimeout(() => { copyDone.value = false }, 2000)
}

async function handleDownload(format: 'md' | 'docx' | 'pdf') {
  if (!props.sessionId || downloading.value) return
  showDownloadMenu.value = false
  downloading.value = true
  try {
    await downloadResearchResult(props.sessionId, format)
  } catch (e) {
    console.error('[Research] download failed', e)
  } finally {
    downloading.value = false
  }
}

function toggleDownloadMenu() {
  showDownloadMenu.value = !showDownloadMenu.value
}

function onDownloadMenuBlur() {
  setTimeout(() => { showDownloadMenu.value = false }, 150)
}
</script>

<template>
  <div class="relative rounded-2xl border border-border/40 bg-bg-elevated/10">
    <!-- Subtle top accent line -->
    <div class="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border/60 to-transparent rounded-t-2xl"></div>

    <div class="flex items-center gap-3 px-5 py-4">
      <!-- Success icon -->
      <div class="shrink-0 flex items-center justify-center w-7 h-7 rounded-full border border-border/50">
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
          class="text-text-muted">
          <path d="m20 6-11 11-5-5"/>
        </svg>
      </div>

      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-text-secondary">研究完成</p>
        <p class="text-xs text-text-muted/60 mt-0.5">上方为基于论文全文的最终回答</p>
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-1.5 shrink-0">
        <!-- Save to library button -->
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all active:scale-95"
          :class="saved
            ? 'border-border/40 text-text-muted cursor-default'
            : 'border-border/50 text-text-secondary hover:text-text-primary hover:border-border cursor-pointer'"
          :disabled="saved"
          @click="handleSaveToLibrary"
        >
          <svg v-if="!saved" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m20 6-11 11-5-5"/>
          </svg>
          {{ saved ? '已保存' : '保存到研究库' }}
        </button>

        <!-- Copy button -->
        <button
          v-if="hasText"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/50 text-text-secondary text-xs font-medium hover:text-text-primary hover:border-border transition-all active:scale-95"
          @click="handleCopy"
        >
          <svg v-if="!copyDone" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m20 6-11 11-5-5"/>
          </svg>
          {{ copyDone ? '已复制' : '复制' }}
        </button>

        <!-- Download dropdown -->
        <div v-if="hasText && sessionId" class="relative">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-text-secondary text-xs font-medium hover:text-text-primary hover:border-tinder-pink/40 hover:bg-tinder-pink/5 transition-all active:scale-95"
            :class="downloading ? 'opacity-60 cursor-not-allowed' : ''"
            :disabled="downloading"
            @click="toggleDownloadMenu"
            @blur="onDownloadMenuBlur"
          >
            <svg v-if="!downloading" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" x2="12" y1="15" y2="3"/>
            </svg>
            <svg v-else class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
            </svg>
            下载
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              class="transition-transform duration-150" :class="showDownloadMenu ? 'rotate-180' : ''">
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </button>

          <!-- Download menu -->
          <Transition name="popover">
            <div
              v-if="showDownloadMenu"
              class="absolute top-full right-0 mt-1.5 w-36 rounded-xl border border-border bg-bg-elevated shadow-xl z-20 overflow-hidden py-1"
            >
              <button
                class="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors text-left"
                @mousedown.prevent="handleDownload('md')"
              >
                <span class="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-bg text-text-muted border border-border">MD</span>
                Markdown
              </button>
              <button
                class="w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors text-left"
                :class="ent.canUse('export') ? 'text-text-secondary hover:text-text-primary hover:bg-bg-hover' : 'text-text-muted cursor-not-allowed opacity-60'"
                :title="ent.canUse('export') ? undefined : '本月导出次数已用完'"
                @mousedown.prevent="ent.canUse('export') ? handleDownload('docx') : undefined"
              >
                <span class="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-bg text-text-muted border border-border">DOC</span>
                Word 文档
                <span v-if="!ent.canUse('export')" class="ml-auto text-amber-400">🔒</span>
              </button>
              <button
                class="w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors text-left"
                :class="ent.canUse('export') ? 'text-text-secondary hover:text-text-primary hover:bg-bg-hover' : 'text-text-muted cursor-not-allowed opacity-60'"
                :title="ent.canUse('export') ? undefined : '本月导出次数已用完'"
                @mousedown.prevent="ent.canUse('export') ? handleDownload('pdf') : undefined"
              >
                <span class="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-bg text-text-muted border border-border">PDF</span>
                PDF 文件
                <span v-if="!ent.canUse('export')" class="ml-auto text-amber-400">🔒</span>
              </button>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.popover-enter-active, .popover-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.popover-enter-from, .popover-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
