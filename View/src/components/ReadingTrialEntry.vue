<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { readingSessionKey, type ReadingSession } from '../utils/readingSession'
import { API_ORIGIN } from '../api'
import MarkdownViewer from './MarkdownViewer.vue'
import ReadingTrialViewer from './ReadingTrialViewer.vue'
import type { KbScope } from '../api'
import type { ReadingAnchor } from '../utils/readingAnchor'

const props = defineProps<{
  paperId?: string
  paperTitle?: string
  scope?: KbScope
  mineruUrl?: string | null
  zhUrl?: string | null
  bilingualUrl?: string | null
  translating?: boolean
  resume?: ReadingSession
}>()
const opened = ref(false)
const version = ref(props.resume?.version || 'trial')
const mode = ref<'mineru' | 'zh' | 'bilingual'>(props.resume?.mode || 'bilingual')
const dialog = ref<HTMLDialogElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const reader = ref<{ flushNotes?: () => Promise<boolean> } | null>(null)
const sourceAnchor = ref<ReadingAnchor | null>(null)
const choices = computed(() => [
  { value: 'mineru' as const, label: 'MinerU 解析', url: props.mineruUrl },
  { value: 'zh' as const, label: '中文翻译版', url: props.zhUrl },
  { value: 'bilingual' as const, label: '中英文对照版', url: props.bilingualUrl },
].filter(item => item.url))
const url = computed(() => {
  const value = choices.value.find(item => item.value === mode.value)?.url ?? ''
  return value.startsWith('/') ? `${API_ORIGIN}${value}` : value
})
watch(choices, () => {
  if (!choices.value.some(item => item.value === mode.value)) mode.value = choices.value[0]?.value ?? 'mineru'
}, { immediate: true })
async function open() {
  opened.value = true
  rememberSession()
  await nextTick()
  dialog.value?.showModal()
}
async function close() {
  if (reader.value?.flushNotes && !await reader.value.flushNotes()) return
  dialog.value?.close()
  opened.value = false
  try { sessionStorage.removeItem(readingSessionKey) } catch { /* Storage may be unavailable. */ }
  trigger.value?.focus()
}
function rememberSession() {
  if (!opened.value || !props.paperId) return
  const { resume, ...paper } = props
  try { sessionStorage.setItem(readingSessionKey, JSON.stringify({ ...paper, path: location.pathname + location.search, version: version.value, mode: mode.value })) } catch { /* Reading still works without storage. */ }
}
watch([version, mode], rememberSession)
onMounted(() => { if (props.resume) void open() })
function navigateSource(payload: { mode: 'mineru' | 'zh' | 'bilingual'; anchor: ReadingAnchor }) {
  mode.value = payload.mode
  sourceAnchor.value = payload.anchor
}
</script>

<template>
  <div v-if="choices.length" class="trial-entry" @click.stop>
    <div v-if="!resume" class="text-[10px] text-text-muted">阅读页面：原版入口保留在下方</div>
    <button v-if="!resume" ref="trigger" type="button" class="trial-launch" @click="open">新版阅读（试用） ↗</button>
    <Teleport to="body">
      <dialog v-if="opened" ref="dialog" class="trial-dialog" aria-label="论文阅读对比" @cancel.prevent="close" @click.stop>
        <header class="trial-header">
          <div class="reader-identity"><span class="reader-space">{{ scope === 'mypapers' ? '我的论文' : scope === 'inspiration' ? '灵感' : '知识库' }}</span><strong :title="paperTitle">{{ paperTitle || '论文阅读' }}</strong></div>
          <label>页面 <select v-model="version" aria-label="阅读版本"><option value="original">原版</option><option value="trial">新版（试用）</option></select></label>
          <label>内容 <select v-model="mode" aria-label="阅读内容" @change="sourceAnchor = null"><option v-for="item in choices" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          <button type="button" class="trial-close" @click="close">返回论文</button>
        </header>
        <div class="trial-stage" :style="version === 'original' ? { maxWidth: '792px' } : undefined">
          <component :is="version === 'trial' ? ReadingTrialViewer : MarkdownViewer" :key="version" ref="reader" :url="url" :mode="mode" :paper-id="paperId" :scope="scope" :source-anchor="sourceAnchor" :auto-refresh-ms="translating && mode !== 'mineru' ? 4000 : 0" @navigate-source="navigateSource" />
        </div>
      </dialog>
    </Teleport>
  </div>
</template>

<style scoped>
.trial-entry { padding: 6px 12px 6px 50px; }
.trial-launch { background: transparent; border: 0; padding: 5px 0; color: var(--color-text-primary); font-size: 12px; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
.trial-dialog { position: fixed; inset: 0; margin: 0; padding: 0; width: 100vw; height: 100dvh; max-width: none; max-height: none; border: 0; background: var(--color-bg); color: var(--color-text-primary); }
.trial-dialog[open] { display: flex; flex-direction: column; }
.trial-header { background: var(--color-bg-card); display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px 20px; border-bottom: 1px solid var(--color-border); font-size: 13px; }
.trial-header select, .trial-close { border: 1px solid var(--color-border); background: var(--color-bg-card); color: inherit; border-radius: 6px; padding: 5px 8px; }
.trial-close { margin-left: auto; cursor: pointer; }
.trial-stage { flex: 1; min-height: 0; display: flex; width: min(100%, 1564px); margin: 0 auto; padding: 12px; }
.reader-identity { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 160px; }
.reader-identity strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 560px; font-size: 14px; }
.reader-space { flex-shrink: 0; font-size: 11px; color: var(--color-text-secondary); background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 6px; padding: 3px 7px; }
.trial-header label { display: flex; align-items: center; gap: 6px; color: var(--color-text-secondary); font-size: 12px; }
.trial-header select, .trial-close { min-height: 32px; border-radius: 8px; font: inherit; cursor: pointer; }
.trial-close:hover { background: var(--color-bg-hover); }
.trial-header :is(button, select):focus-visible { outline: 2px solid var(--color-accent-primary); outline-offset: 2px; }
@media (max-width: 760px) { .trial-header { gap: 8px; padding: 10px 12px; } .reader-identity { flex-basis: 100%; } .reader-identity strong { max-width: calc(100vw - 110px); } }
</style>
