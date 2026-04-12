<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { useBilingualTheme, BILINGUAL_PRESETS, type BilingualPreset } from '@shared/composables/useBilingualTheme'
import { fetchKbPaperFiles } from '@shared/api/kb-processing'
import { fetchUserPaperFiles } from '@shared/api/user-papers'
import type { KbPaperFilesResponse } from '@shared/types/kb'

defineOptions({ name: 'PaperReaderView' })

const route = useRoute()
const router = useRouter()

// Auto-hide bottom bar on scroll down, show on scroll up
const bottomBarVisible = ref(true)
let lastScrollTop = 0
function onContentScroll(e: Event) {
  const el = e.target as HTMLElement
  const st = el.scrollTop
  if (st > lastScrollTop && st > 60) {
    bottomBarVisible.value = false
  } else {
    bottomBarVisible.value = true
  }
  lastScrollTop = st
}

const { theme, setPreset, setIntensity, setFontSize, isActivePreset } = useBilingualTheme()

type ReaderMode = 'mineru' | 'zh' | 'bilingual'

const paperId = computed(() => route.params.id as string)
const mode = computed<ReaderMode>(() => (route.query.mode as ReaderMode) || 'bilingual')
const title = computed(() => (route.query.title as string) || '论文阅读')
const isUserPaper = computed(() => route.query.source === 'user-paper')

const filesData = ref<KbPaperFilesResponse | null>(null)
const loading = ref(true)
const error = ref('')
const content = ref('')
const contentLoading = ref(false)
const contentError = ref('')
const settingsVisible = ref(false)

const modeLabels: Record<ReaderMode, string> = {
  mineru: '结构化正文',
  zh: '中文翻译',
  bilingual: '双语对照',
}

const activeUrl = computed(() => {
  if (!filesData.value) return null
  if (mode.value === 'mineru') return filesData.value.mineru_static_url
  if (mode.value === 'zh') return filesData.value.zh_static_url
  return filesData.value.bilingual_static_url
})

const isBilingual = computed(() => mode.value === 'bilingual')

async function loadFiles() {
  loading.value = true
  error.value = ''
  try {
    if (isUserPaper.value) {
      const res = await fetchUserPaperFiles(paperId.value)
      filesData.value = { ...res, process_status: '', process_step: '', translate_progress: 0 } as KbPaperFilesResponse
    } else {
      filesData.value = await fetchKbPaperFiles(paperId.value, 'kb')
    }
  } catch {
    error.value = '加载失败，请重试'
  } finally {
    loading.value = false
  }
}

async function loadContent(url: string) {
  contentLoading.value = true
  contentError.value = ''
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    content.value = await res.text()
  } catch {
    contentError.value = '内容加载失败'
    content.value = ''
  } finally {
    contentLoading.value = false
  }
}

watch(activeUrl, (url) => {
  if (url) loadContent(url)
  else content.value = ''
})

onMounted(() => {
  loadFiles()
})

watch(paperId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    filesData.value = null
    content.value = ''
    contentError.value = ''
    loadFiles()
  }
})

function switchMode(m: ReaderMode) {
  router.replace({ query: { ...route.query, mode: m } })
}

function presetSwatchStyle(preset: BilingualPreset) {
  return { background: `hsl(${preset.hue}, ${preset.saturation}%, 55%)` }
}

function onFontSizeInput(e: Event) {
  setFontSize(Number((e.target as HTMLInputElement).value))
}

function onIntensityInput(e: Event) {
  setIntensity(Number((e.target as HTMLInputElement).value))
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader :glass="true" @back="router.back()">
      <template #title>
        <span class="text-[14px] font-semibold text-text-primary truncate">{{ title }}</span>
      </template>
      <template #right>
        <button
          type="button"
          class="w-8 h-8 flex items-center justify-center rounded-lg active:bg-bg-hover"
          aria-label="阅读设置"
          @click="settingsVisible = true"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </template>
    </PageHeader>

    <!-- Mode tabs -->
    <div class="flex gap-2 px-4 py-2.5 shrink-0 border-b border-border overflow-x-auto">
      <button
        v-for="m in (['mineru', 'zh', 'bilingual'] as ReaderMode[])"
        :key="m"
        type="button"
        class="mode-pill shrink-0"
        :class="mode === m ? 'active' : 'inactive'"
        @click="switchMode(m)"
      >
        {{ modeLabels[m] }}
      </button>
    </div>

    <!-- Content -->
    <LoadingState v-if="loading" class="flex-1" message="加载文件…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadFiles" />
    <template v-else>
      <!-- No file available for this mode -->
      <div v-if="!activeUrl" class="flex-1 flex flex-col items-center justify-center px-8 gap-3">
        <div class="w-14 h-14 rounded-2xl bg-bg-elevated flex items-center justify-center">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <p class="text-[14px] font-semibold text-text-primary text-center">{{ modeLabels[mode] }}尚未生成</p>
        <p class="text-[12px] text-text-muted text-center">
          {{ mode === 'bilingual' || mode === 'zh' ? '请先完成中文翻译，再查看双语/译文内容' : '请先触发论文处理，待完成后即可阅读' }}
        </p>
        <button type="button" class="btn-ghost text-[13px] px-4 py-2" @click="router.back()">返回论文详情</button>
      </div>

      <div v-else class="flex-1 overflow-y-auto pb-safe" @scroll="onContentScroll">
        <LoadingState v-if="contentLoading" class="py-12" />
        <ErrorState v-else-if="contentError" :message="contentError" @retry="() => activeUrl && loadContent(activeUrl)" />
        <div
          v-else
          class="px-4 py-5 pb-20 reader-content"
          :class="{ 'bilingual-mode': isBilingual }"
          :style="{
            '--reader-font-size': `${theme.fontSize}px`,
            '--bilingual-hue': String(theme.hue),
            '--bilingual-saturation': `${theme.saturation}%`,
            '--bilingual-intensity': String(theme.intensity),
          }"
        >
          <MarkdownRenderer :content="content" :reader-mode="mode" />
        </div>
      </div>
    </template>

    <!-- Fixed bottom bar: AI chat + paper detail (auto-hides while scrolling) -->
    <div
      v-if="paperId && !loading && !error"
      class="shrink-0 fixed bottom-0 left-0 right-0 bg-bg/90 backdrop-blur-md border-t border-border safe-area-bottom px-4 py-2.5 flex gap-2 z-20 transition-transform duration-300"
      :class="bottomBarVisible ? 'translate-y-0' : 'translate-y-full'"
    >
      <button
        type="button"
        class="flex-[3] py-2.5 rounded-2xl bg-tinder-purple/12 border border-tinder-purple/25 text-[13px] font-semibold text-tinder-purple active:bg-tinder-purple/25 transition-all flex items-center justify-center gap-1.5"
        @click="router.push({ name: 'chat', query: { paperId, title } })"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        问 AI
      </button>
      <button
        type="button"
        class="flex-[2] py-2.5 rounded-2xl bg-bg-elevated border border-border text-[13px] font-semibold text-text-secondary active:bg-bg-hover transition-all"
        @click="router.back()"
      >
        论文详情
      </button>
    </div>

    <!-- Settings BottomSheet -->
    <BottomSheet :visible="settingsVisible" title="阅读设置" @close="settingsVisible = false">
      <div class="px-5 pb-8 pt-1 space-y-6">
        <!-- Font size -->
        <div>
          <div class="flex items-center justify-between mb-3">
            <span class="text-[12px] font-semibold uppercase tracking-wider text-text-muted">字号</span>
            <span class="text-[13px] font-semibold text-tinder-blue">{{ theme.fontSize }}px</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-[11px] text-text-muted w-4">小</span>
            <input
              type="range"
              class="reader-slider flex-1"
              min="12"
              max="20"
              step="1"
              :value="theme.fontSize"
              @input="onFontSizeInput"
            />
            <span class="text-[11px] text-text-muted w-4 text-right">大</span>
          </div>
          <div class="flex justify-between mt-1.5 px-7">
            <span
              v-for="sz in [12, 14, 16, 18, 20]"
              :key="sz"
              class="text-[10px] cursor-pointer transition-colors"
              :class="theme.fontSize === sz ? 'text-tinder-blue font-semibold' : 'text-text-muted'"
              @click="setFontSize(sz)"
            >{{ sz }}</span>
          </div>
        </div>

        <!-- Color preset (only for bilingual) -->
        <div v-if="isBilingual">
          <div class="mb-3">
            <span class="text-[12px] font-semibold uppercase tracking-wider text-text-muted">配色</span>
          </div>
          <div class="flex gap-3 flex-wrap">
            <button
              v-for="preset in BILINGUAL_PRESETS"
              :key="preset.name"
              type="button"
              class="flex flex-col items-center gap-1.5"
              @click="setPreset(preset)"
            >
              <div
                class="w-10 h-10 rounded-full transition-all"
                :class="isActivePreset(preset) ? 'ring-2 ring-offset-2 ring-tinder-blue scale-110' : ''"
                :style="presetSwatchStyle(preset)"
              />
              <span class="text-[10px] text-text-muted">{{ preset.name }}</span>
            </button>
          </div>
        </div>

        <!-- Intensity (only for bilingual) -->
        <div v-if="isBilingual">
          <div class="flex items-center justify-between mb-3">
            <span class="text-[12px] font-semibold uppercase tracking-wider text-text-muted">高亮浓度</span>
            <span class="text-[13px] font-semibold text-tinder-blue">{{ theme.intensity }}</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-[11px] text-text-muted">淡</span>
            <input
              type="range"
              class="reader-slider flex-1"
              min="2"
              max="15"
              step="1"
              :value="theme.intensity"
              @input="onIntensityInput"
            />
            <span class="text-[11px] text-text-muted">浓</span>
          </div>
        </div>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.reader-content {
  font-size: var(--reader-font-size, 15px);
}

.reader-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--color-border-light);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.reader-slider::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-tinder-blue);
  border: 3px solid var(--color-bg);
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
  cursor: pointer;
}
.reader-slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--color-tinder-blue);
  border: 3px solid var(--color-bg);
  cursor: pointer;
}
</style>
