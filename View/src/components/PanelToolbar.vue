<script setup lang="ts">
import { ref } from 'vue'
import type { PanelLayoutMode, PanelConfigItem } from '../composables/usePanelLayout'
import { downloadPaperFile } from '../api'

const props = defineProps<{
  mode: PanelLayoutMode
  leftPanel: string
  rightPanel: string
  panels: PanelConfigItem[]
  showClose?: boolean
  downloadParams?: {
    paperId: string
    fileType: 'mineru' | 'zh' | 'bilingual'
    scope: 'kb' | 'mypapers'
  }
  downloadUrl?: string
}>()

const emit = defineEmits<{
  'update:leftPanel': [id: string]
  'update:rightPanel': [id: string]
  toggleSplit: []
  swap: []
  close: []
}>()

const available = () => props.panels.filter((p) => p.available)

function onLeftChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  emit('update:leftPanel', v)
}

function onRightChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  emit('update:rightPanel', v)
}

const showFormatMenu = ref(false)
const downloading = ref(false)

const FORMAT_OPTIONS: { fmt: 'md' | 'docx' | 'pdf'; label: string }[] = [
  { fmt: 'md', label: 'MD' },
  { fmt: 'docx', label: 'DOCX' },
  { fmt: 'pdf', label: 'PDF' },
]

async function triggerDownload(fmt: 'md' | 'docx' | 'pdf') {
  showFormatMenu.value = false
  if (!props.downloadParams) return
  const { paperId, fileType, scope } = props.downloadParams
  downloading.value = true
  try {
    await downloadPaperFile(paperId, fileType, scope, fmt)
  } catch (e: any) {
    alert(`下载失败：${e?.message ?? '未知错误'}`)
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <div
    class="shrink-0 flex flex-wrap items-center gap-2 px-2 sm:px-4 py-2 border-b border-border bg-bg-card/80 backdrop-blur-sm"
  >
    <span class="text-xs text-text-muted hidden sm:inline">左栏</span>
    <select
      class="text-xs sm:text-sm bg-bg-elevated border border-border rounded-lg px-2 py-1.5 text-text-primary max-w-[42vw] sm:max-w-none"
      :value="leftPanel"
      @change="onLeftChange"
    >
      <option
        v-for="p in available()"
        :key="'L-' + p.id"
        :value="p.id"
      >
        {{ p.icon }} {{ p.label }}
      </option>
    </select>

    <button
      type="button"
      class="text-xs px-2.5 py-1.5 rounded-lg border border-border bg-bg-elevated text-text-secondary hover:bg-bg-hover cursor-pointer transition-colors"
      title="交换左右栏"
      :disabled="mode !== 'split'"
      :class="mode !== 'split' ? 'opacity-40 cursor-not-allowed' : ''"
      @click="emit('swap')"
    >
      ⇄
    </button>

    <template v-if="mode === 'split'">
      <span class="text-xs text-text-muted hidden sm:inline">右栏</span>
      <select
        class="text-xs sm:text-sm bg-bg-elevated border border-border rounded-lg px-2 py-1.5 text-text-primary max-w-[42vw] sm:max-w-none"
        :value="rightPanel"
        @change="onRightChange"
      >
        <option
          v-for="p in available()"
          :key="'R-' + p.id"
          :value="p.id"
        >
          {{ p.icon }} {{ p.label }}
        </option>
      </select>
    </template>

    <button
      type="button"
      class="ml-auto text-xs px-3 py-1.5 rounded-full font-medium border cursor-pointer transition-colors"
      :class="mode === 'split'
        ? 'border-tinder-pink/50 text-tinder-pink bg-tinder-pink/10'
        : 'border-border text-text-secondary bg-bg-elevated hover:bg-bg-hover'"
      @click="emit('toggleSplit')"
    >
      {{ mode === 'split' ? '单栏' : '分栏' }}
    </button>

    <!-- Download button -->
    <div v-if="downloadParams || downloadUrl" class="relative">
      <button
        v-if="downloadParams"
        type="button"
        :disabled="downloading"
        class="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full font-medium border border-border bg-bg-elevated hover:bg-bg-hover cursor-pointer transition-colors"
        :class="downloading ? 'opacity-50 cursor-not-allowed text-text-muted' : 'text-text-secondary'"
        :title="downloading ? '正在生成，请稍候…' : '下载此文件'"
        @click.stop="!downloading && (showFormatMenu = !showFormatMenu)"
      >
        <svg v-if="downloading" class="w-3 h-3 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        {{ downloading ? '生成中…' : '下载' }}
        <svg v-if="!downloading" xmlns="http://www.w3.org/2000/svg" class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      <a
        v-else-if="downloadUrl"
        :href="downloadUrl"
        download
        target="_blank"
        class="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full font-medium border border-border bg-bg-elevated hover:bg-bg-hover text-text-secondary cursor-pointer transition-colors no-underline"
        title="下载此文件"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        下载
      </a>
      <!-- Format dropdown -->
      <div
        v-if="showFormatMenu && !downloading"
        class="absolute right-0 top-full mt-1 bg-bg-elevated border border-border rounded-lg shadow-lg overflow-hidden min-w-[80px] z-20"
      >
        <button
          v-for="opt in FORMAT_OPTIONS"
          :key="opt.fmt"
          type="button"
          class="w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-bg-hover transition-colors cursor-pointer"
          @click="triggerDownload(opt.fmt)"
        >
          {{ opt.label }}
        </button>
      </div>
      <div v-if="showFormatMenu" class="fixed inset-0 z-10" @click="showFormatMenu = false" />
    </div>

    <button
      v-if="showClose"
      type="button"
      class="text-xs px-3 py-1.5 rounded-full font-medium border border-border text-text-muted bg-bg-elevated hover:bg-bg-hover cursor-pointer transition-colors"
      @click="emit('close')"
    >
      关闭
    </button>
  </div>
</template>
