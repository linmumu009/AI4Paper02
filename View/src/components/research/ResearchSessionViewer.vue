<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import type { ResearchSession } from '../../types/paper'
import { downloadResearchResult } from '../../api'
import { useEntitlements } from '../../composables/useEntitlements'

const props = defineProps<{
  session: ResearchSession
  loading: boolean
  paperTitles?: Record<string, string>
}>()

const emit = defineEmits<{
  back: []
  copy: []
  saveToLibrary: [sessionId: number]
}>()

const ent = useEntitlements()
const copyDone = ref(false)
const showDownloadMenu = ref(false)
const downloading = ref(false)
const savedLocal = ref(!!(props.session as ResearchSession & { saved?: boolean }).saved)

watch(() => props.session.id, () => {
  savedLocal.value = !!(props.session as ResearchSession & { saved?: boolean }).saved
})

function handleSaveToLibrary() {
  if (savedLocal.value) return
  savedLocal.value = true
  emit('saveToLibrary', props.session.id)
}
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

async function handleDownload(format: 'md' | 'docx' | 'pdf') {
  if (!props.session?.id || downloading.value) return
  showDownloadMenu.value = false
  downloading.value = true
  try {
    await downloadResearchResult(props.session.id, format)
  } catch (e) {
    console.error('[Research] download failed', e)
  } finally {
    downloading.value = false
  }
}

function onDownloadMenuBlur() {
  setTimeout(() => { showDownloadMenu.value = false }, 150)
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function statusLabel(s: string) {
  return ({ running: '进行中', done: '已完成', error: '失败', pending: '待执行' } as Record<string, string>)[s] ?? s
}

function statusClass(s: string) {
  return ({
    done: 'text-green-500',
    error: 'text-red-400',
    running: 'text-accent-primary',
    pending: 'text-text-muted',
  } as Record<string, string>)[s] ?? 'text-text-muted'
}

function getFinalText(): string {
  if (!props.session.rounds) return ''
  const r3 = props.session.rounds.find(r => r.round_type === 'full_text')
  if (r3 && (r3.output as Record<string, unknown>).full_text)
    return (r3.output as Record<string, unknown>).full_text as string
  const r2 = props.session.rounds.find(r => r.round_type === 'summary_analysis')
  if (r2 && (r2.output as Record<string, unknown>).full_text)
    return (r2.output as Record<string, unknown>).full_text as string
  return ''
}

function getSelectedIds(): string[] {
  if (!props.session.rounds) return []
  const r1 = props.session.rounds.find(r => r.round_type === 'relevance')
  return (r1?.output as Record<string, unknown>)?.selected_ids as string[] ?? []
}

function hasFull(): boolean {
  return !!props.session.rounds?.find(r => r.round_type === 'full_text')
}

const finalTextHtml = computed(() => md.render(getFinalText()))

async function handleCopy() {
  const text = getFinalText()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    try { document.execCommand('copy') } catch { /**/ }
    document.body.removeChild(el)
  }
  emit('copy')
  copyDone.value = true
  setTimeout(() => { copyDone.value = false }, 2000)
}
</script>

<template>
  <div class="space-y-3">
    <!-- Session header card -->
    <div class="flex items-start gap-3 p-4 rounded-2xl border border-border bg-bg-elevated/30">
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2 text-[10px] text-text-muted mb-1">
          <span class="flex items-center gap-1">
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>
            </svg>
            历史记录 #{{ session.id }}
          </span>
          <span :class="statusClass(session.status)">{{ statusLabel(session.status) }}</span>
          <span>{{ formatTime(session.created_at) }}</span>
          <span>{{ session.paper_ids?.length ?? 0 }} 篇论文</span>
        </div>
        <p class="text-sm font-semibold text-text-primary">{{ session.question }}</p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <!-- Save to library button -->
        <button
          class="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border font-medium transition-all active:scale-95 whitespace-nowrap"
          :class="savedLocal
            ? 'border-accent-primary/30 text-accent-primary bg-accent-primary/10 cursor-default'
            : 'border-accent-primary/30 text-accent-primary hover:bg-accent-primary/10 cursor-pointer'"
          :disabled="savedLocal"
          @click="handleSaveToLibrary"
        >
          <svg v-if="!savedLocal" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m20 6-11 11-5-5"/>
          </svg>
          {{ savedLocal ? '已收藏' : '加入收藏' }}
        </button>
        <!-- Back button -->
        <button
          class="shrink-0 text-xs px-3 py-1.5 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-accent-primary/30 transition-colors whitespace-nowrap"
          @click="emit('back')"
        >返回</button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex items-center justify-center gap-2 py-10 text-sm text-text-muted">
      <svg class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      加载历史记录…
    </div>

    <template v-else-if="session.rounds">
      <!-- R1 Summary -->
      <div
        v-if="session.rounds.find(r => r.round_type === 'relevance')"
        class="rounded-2xl border border-border border-l-[3px] border-l-accent-primary overflow-hidden"
      >
        <div class="flex items-center gap-2.5 px-5 py-3.5 bg-bg-elevated">
          <span class="text-xs font-bold px-1.5 py-0.5 rounded-md bg-accent-primary/15 border border-accent-primary/20 text-accent-primary">R1</span>
          <span class="text-sm font-medium">相关性排序结果</span>
          <span class="text-xs text-text-muted ml-auto tabular-nums">
            选入 {{ getSelectedIds().length }} / {{ session.paper_ids?.length ?? 0 }} 篇
          </span>
        </div>
        <div class="px-4 pb-3 flex flex-wrap gap-1.5">
          <span
            v-for="pid in getSelectedIds()"
            :key="pid"
            class="text-[11px] px-2 py-0.5 rounded-full bg-accent-primary/10 border border-accent-primary/20 text-accent-primary"
          >{{ paperTitles?.[pid] ?? pid }}</span>
        </div>
      </div>

      <!-- Final answer card -->
      <div class="rounded-2xl border border-border border-l-[3px]"
        :class="hasFull() ? 'border-l-purple-400' : 'border-l-blue-400'"
      >
        <div class="flex items-center gap-2.5 px-5 py-3.5 bg-bg-elevated rounded-t-2xl">
          <span
            class="text-xs font-bold px-1.5 py-0.5 rounded-md border"
            :class="hasFull()
              ? 'bg-purple-400/15 border-purple-400/20 text-purple-400'
              : 'bg-blue-400/15 border-blue-400/20 text-blue-400'"
          >{{ hasFull() ? 'R3' : 'R2' }}</span>
          <span class="text-sm font-medium">研究回答</span>
          <div v-if="getFinalText()" class="ml-auto flex items-center gap-1.5">
            <!-- Copy -->
            <button
              class="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-tinder-pink/30 transition-colors"
              @click="handleCopy"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
              </svg>
              {{ copyDone ? '已复制 ✓' : '复制' }}
            </button>

            <!-- Download dropdown -->
            <div class="relative">
              <button
                class="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-tinder-pink/30 transition-colors"
                :class="downloading ? 'opacity-60 cursor-not-allowed' : ''"
                :disabled="downloading"
                @click="showDownloadMenu = !showDownloadMenu"
                @blur="onDownloadMenuBlur"
              >
                <svg v-if="!downloading" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" x2="12" y1="15" y2="3"/>
                </svg>
                <svg v-else class="animate-spin" xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                下载
                <svg xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                  :class="showDownloadMenu ? 'rotate-180' : ''" class="transition-transform duration-150">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </button>

              <Transition name="popover">
                <div
                  v-if="showDownloadMenu"
                  class="absolute top-full right-0 mt-1.5 w-36 rounded-xl border border-border bg-bg-elevated shadow-xl z-20 overflow-hidden py-1"
                >
                  <button class="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors text-left"
                    @mousedown.prevent="handleDownload('md')">
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
        <div class="px-5 py-4">
          <div
            v-if="getFinalText()"
            class="research-prose prose dark:prose-invert max-w-none leading-relaxed text-text-primary"
            v-html="finalTextHtml"
          />
          <p v-else class="text-sm text-text-muted py-2">无回答内容（此会话可能未成功完成）</p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.research-prose { font-size: 0.9375rem; }
.research-prose :deep(p) { margin-top: 0.65em; margin-bottom: 0.65em; line-height: 1.75; }
.research-prose :deep(h1) { font-size: 1.2em; font-weight: 700; margin-top: 1.5em; margin-bottom: 0.6em; color: inherit; }
.research-prose :deep(h2) { font-size: 1.1em; font-weight: 700; margin-top: 1.4em; margin-bottom: 0.55em; color: inherit; }
.research-prose :deep(h3), .research-prose :deep(h4) { font-size: 1em; font-weight: 600; margin-top: 1.2em; margin-bottom: 0.4em; color: inherit; }
.research-prose :deep(code) {
  background: rgb(var(--color-bg-elevated));
  border: 1px solid rgb(var(--color-border) / 0.6);
  padding: 0.15em 0.4em; border-radius: 0.3em; font-size: 0.82em;
}
.research-prose :deep(pre) {
  background: rgb(var(--color-bg-elevated));
  border: 1px solid rgb(var(--color-border));
  border-radius: 0.5em; padding: 0.75em 1em; overflow-x: auto;
}
.research-prose :deep(pre code) { background: none; border: none; padding: 0; }
.research-prose :deep(ul), .research-prose :deep(ol) { padding-left: 1.6em; margin: 0.6em 0; }
.research-prose :deep(li) { margin-top: 0.3em; margin-bottom: 0.3em; line-height: 1.7; }
.research-prose :deep(strong) { color: inherit; font-weight: 600; }
.research-prose :deep(blockquote) {
  border-left: 3px solid rgb(var(--color-accent-primary) / 0.3);
  padding-left: 1em; margin: 0.75em 0;
  color: rgb(var(--color-text-muted)); font-style: italic;
}
.research-prose :deep(a) { color: rgb(var(--color-tinder-blue)); text-decoration: underline; text-underline-offset: 2px; }

.popover-enter-active, .popover-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.popover-enter-from, .popover-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
