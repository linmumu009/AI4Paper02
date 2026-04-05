<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { openExternal } from '../../utils/openExternal'
import { IS_TAURI, tauriFetchPdfBlobUrl } from '../../api'

const props = defineProps<{
  src: string
  title?: string
  bareUrl?: string
  hideHeader?: boolean
  showClose?: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

// Tracks whether we're loading the PDF binary in Tauri mode
const loading = ref(false)
const errorMsg = ref('')

// The resolved iframe src (may be blob URL in Tauri, or original src in web)
const actualSrc = ref('')

// Keep a reference to the current blob URL so we can revoke it on change
let currentBlobUrl: string | null = null

function revokeCurrent() {
  if (currentBlobUrl) {
    URL.revokeObjectURL(currentBlobUrl)
    currentBlobUrl = null
  }
}

watch(
  () => props.src,
  async (newSrc) => {
    revokeCurrent()
    errorMsg.value = ''

    if (!newSrc) {
      actualSrc.value = ''
      return
    }

    if (!IS_TAURI) {
      // Web mode: use the URL as-is (Vite proxy handles /static/* → backend)
      actualSrc.value = newSrc
      return
    }

    // Tauri mode: parse out the raw PDF URL, fetch via Rust IPC, create blob URL,
    // then point the iframe at the local viewer with the blob URL.
    let pdfFileUrl: string
    try {
      const u = new URL(newSrc, window.location.origin)
      pdfFileUrl = u.searchParams.get('file') || ''
    } catch {
      pdfFileUrl = ''
    }

    if (!pdfFileUrl) {
      // No file param — nothing to load
      actualSrc.value = ''
      return
    }

    loading.value = true
    try {
      const blobUrl = await tauriFetchPdfBlobUrl(pdfFileUrl)
      currentBlobUrl = blobUrl

      // Extract paperId for highlight persistence
      let paperId = ''
      try {
        paperId = new URL(newSrc, window.location.origin).searchParams.get('paperId') || ''
      } catch { /* ignore */ }

      actualSrc.value = `/static/pdfjs/web/viewer.html?file=${encodeURIComponent(blobUrl)}${paperId ? `&paperId=${encodeURIComponent(paperId)}` : ''}`
    } catch (e: unknown) {
      errorMsg.value = e instanceof Error ? e.message : 'PDF 加载失败'
      actualSrc.value = ''
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  revokeCurrent()
})
</script>

<template>
  <div class="flex flex-col h-full min-h-0 overflow-hidden bg-bg-sidebar">
    <div
      v-if="!hideHeader"
      class="shrink-0 px-3 py-2 border-b border-border flex items-center justify-between gap-2"
    >
      <span class="text-xs text-text-muted truncate">{{ title || 'PDF' }}</span>
      <div class="flex items-center gap-2">
        <button
          v-if="showClose"
          type="button"
          class="px-2.5 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="emit('close')"
        >
          关闭
        </button>
        <!-- 使用 openExternal 保证桌面端通过系统默认 PDF 阅读器或浏览器打开 -->
        <button
          v-if="bareUrl"
          type="button"
          class="px-2.5 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="openExternal(bareUrl!)"
        >
          新窗口打开
        </button>
      </div>
    </div>
    <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted text-sm gap-2">
      <svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
      加载 PDF…
    </div>
    <div v-else-if="errorMsg" class="flex-1 flex items-center justify-center text-red-400 text-sm px-4 text-center">
      {{ errorMsg }}
    </div>
    <iframe
      v-else-if="actualSrc"
      :src="actualSrc"
      class="w-full flex-1 min-h-[200px] border-none bg-black"
      title="PDF"
    />
    <div
      v-else
      class="flex-1 flex items-center justify-center text-text-muted text-sm"
    >
      无 PDF
    </div>
  </div>
</template>
