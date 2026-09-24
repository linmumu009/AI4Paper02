<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import 'katex/dist/katex.min.css'
import { IS_TAURI, tauriFetchText } from '../api'
import { renderPaperMarkdown } from '../utils/paperMarkdown'
import MarkdownToc, { type TocHeading } from './MarkdownToc.vue'
import LoadingSpinner from './LoadingSpinner.vue'
import { prepareTrialBilingual } from '../utils/readingTrial'
import { captureReadingAnchor, locateReadingAnchor, parseReadingAnchor, type ReadingAnchor } from '../utils/readingAnchor'
import { readingPalette, readingPapers } from '../utils/readingPalette'
import type { KbScope } from '../api'
import ReadingExcerptMenu from './ReadingExcerptMenu.vue'
import ReadingNotesPanel from './ReadingNotesPanel.vue'
import type { KbNote } from '../types/paper'

const notesOpen = ref(false)
const lastNote = ref<KbNote | null>(null)
const preferredNoteId = ref<number>()
const savedNotice = ref('')
const notesPanel = ref<{ flush: () => Promise<boolean>; append: (id: number, update: () => Promise<KbNote>) => Promise<KbNote> } | null>(null)
let noticeTimer: ReturnType<typeof setTimeout> | null = null

const settingsOpen = ref(false)
const fontSize = ref(20)
const leading = ref(1.8)
const measure = ref(36)
const tracking = ref(0)
const paper = ref('warm')
const colorDepth = ref(12)
const customColor = ref('#bba673')
const paletteStyle = computed(() => readingPalette(paper.value, colorDepth.value, customColor.value))
const showAllSources = ref(false)
try {
  const saved = JSON.parse(localStorage.getItem('ai4papers-reading-trial-v1') || '{}')
  if (typeof saved.fontSize === 'number') fontSize.value = Math.max(16, Math.min(28, saved.fontSize))
  if (typeof saved.leading === 'number') leading.value = Math.max(1.5, Math.min(2.2, saved.leading))
  if (typeof saved.measure === 'number') measure.value = Math.max(28, Math.min(42, saved.measure))
  if (typeof saved.tracking === 'number') tracking.value = Math.max(0, Math.min(0.06, saved.tracking))
  if (readingPapers.some(item => item.value === saved.paper)) paper.value = saved.paper
  if (typeof saved.colorDepth === 'number') colorDepth.value = Math.max(0, Math.min(100, saved.colorDepth))
  else if (paper.value === 'dark') colorDepth.value = 92
  if (/^#[a-f\d]{6}$/i.test(saved.customColor || '')) customColor.value = saved.customColor
} catch { /* Storage may be unavailable. */ }
watch([fontSize, leading, measure, tracking, paper, colorDepth, customColor, notesOpen], () => {
  const body = bodyRef.value
  const top = body?.getBoundingClientRect().top ?? 0
  const anchor = body && Array.from(body.children).find(el => el.getBoundingClientRect().bottom > top)
  const offset = anchor ? anchor.getBoundingClientRect().top - top : 0
  nextTick(() => {
    if (body && anchor?.isConnected) body.scrollTop += anchor.getBoundingClientRect().top - body.getBoundingClientRect().top - offset
  })
  try { localStorage.setItem('ai4papers-reading-trial-v1', JSON.stringify({ fontSize: fontSize.value, leading: leading.value, measure: measure.value, tracking: tracking.value, paper: paper.value, colorDepth: colorDepth.value, customColor: customColor.value })) } catch { /* Reading still works without persistence. */ }
})
watch(showAllSources, async () => {
  await nextTick()
  bodyRef.value?.querySelectorAll<HTMLDetailsElement>('details.trial-source').forEach(el => { el.open = showAllSources.value })
})

const props = defineProps<{
  /** 完整 URL（含 API_ORIGIN） */
  url: string
  paperId?: string
  scope?: KbScope
  sourceAnchor?: ReadingAnchor | null
  /** 附加到根节点 class */
  rootClass?: string
  /** 内容模式：影响特定排版样式 */
  mode?: 'mineru' | 'zh' | 'bilingual'
  /**
   * 自动刷新间隔（毫秒）。大于 0 时每隔该时间重新 fetch 文件，用于翻译进行中
   * 的实时预览。仅当远端文件内容变化时才重新渲染，不会无效闪烁。
   * 设为 0 或不传则关闭自动刷新。
   */
  autoRefreshMs?: number
}>()
const emit = defineEmits<{ navigateSource: [payload: { mode: 'mineru' | 'zh' | 'bilingual'; anchor: ReadingAnchor }] }>()

function excerptSaved(note: KbNote) {
  lastNote.value = note
  preferredNoteId.value = note.id
  selectionMenu.value = null
  savedNotice.value = `已存入「${note.title}」`
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => { savedNotice.value = '' }, 6000)
}
async function appendToNote(id: number, update: () => Promise<KbNote>) {
  return notesPanel.value ? notesPanel.value.append(id, update) : update()
}
async function flushNotes() { return await notesPanel.value?.flush() ?? true }
async function toggleNotes() {
  if (notesOpen.value && !await flushNotes()) return
  notesOpen.value = !notesOpen.value
}
function sourceLink(href: string) {
  const source = new URL(href, window.location.origin)
  const anchor = parseReadingAnchor(source.hash)
  const mode = source.searchParams.get('mode')
  if (decodeURIComponent(source.pathname) !== `/reading-source/${props.paperId}` || !anchor || !['mineru', 'zh', 'bilingual'].includes(mode ?? '')) {
    anchorMessage.value = '该摘录不属于当前论文，或定位信息已失效。'
    return
  }
  if (mode === props.mode) { anchorRestored = false; restoreSourceAnchor(anchor) }
  else emit('navigateSource', { mode: mode as 'mineru' | 'zh' | 'bilingual', anchor })
  if (window.matchMedia('(max-width: 1100px)').matches) void toggleNotes()
}
defineExpose({ flushNotes })

const html = ref('')
const loading = ref(true)
const error = ref('')

// ── TOC state ────────────────────────────────────────────
const showToc = ref(false)
const headings = ref<TocHeading[]>([])
const activeHeadingId = ref('')
const bodyRef = ref<HTMLElement | null>(null)
const selectionMenu = ref<{ anchor: ReadingAnchor; quote: string; x: number; y: number } | null>(null)
const anchorMessage = ref('')
let anchorRestored = false
let sourceHighlight: Highlight | null = null

function positionKey() { return `ai4papers.reading-position:${props.scope || 'kb'}:${props.paperId || props.url}:${props.mode || 'mineru'}` }
function rememberPosition() {
  selectionMenu.value = null
  if (bodyRef.value) {
    try { sessionStorage.setItem(positionKey(), String(bodyRef.value.scrollTop)) } catch { /* Optional session storage. */ }
  }
}
function restorePosition() {
  if (props.sourceAnchor || !bodyRef.value) return
  try {
    const offset = Number(sessionStorage.getItem(positionKey()))
    if (Number.isFinite(offset) && offset > 0) bodyRef.value.scrollTop = offset
  } catch { /* Optional session storage. */ }
}

function captureSelection(event: MouseEvent | KeyboardEvent) {
  if (!props.paperId || (event instanceof KeyboardEvent && !event.shiftKey)) return
  const selection = window.getSelection()
  if (!selection?.rangeCount || selection.isCollapsed || !bodyRef.value) { selectionMenu.value = null; return }
  const range = selection.getRangeAt(0)
  const anchor = captureReadingAnchor(bodyRef.value, range)
  if (!anchor) { anchorMessage.value = '请选择正文文字；单次摘录请控制在 10000 字符以内。'; return }
  const rect = range.getBoundingClientRect()
  selectionMenu.value = { anchor, quote: selection.toString(), x: Math.max(12, Math.min(rect.left, window.innerWidth - 312)), y: Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 330)) }
}

function restoreSourceAnchor(anchor: ReadingAnchor | null | undefined = props.sourceAnchor) {
  if (!anchor || !bodyRef.value || anchorRestored) return
  anchorRestored = true
  const range = locateReadingAnchor(bodyRef.value, anchor)
  if (!range) { anchorMessage.value = '原文内容可能已更新，未能准确定位。请使用目录查找。'; return }
  bodyRef.value.querySelectorAll('details').forEach(details => { if (range.intersectsNode(details)) details.open = true })
  let element = range.startContainer.parentElement
  while (element && element !== bodyRef.value) {
    if (element instanceof HTMLDetailsElement) element.open = true
    element = element.parentElement
  }
  anchorMessage.value = '已定位并选中笔记中的原文。'
  nextTick(() => {
    const body = bodyRef.value
    if (!body || !body.contains(range.startContainer)) return
    body.focus({ preventScroll: true })
    const bounds = range.getBoundingClientRect()
    body.scrollTop += bounds.top - body.getBoundingClientRect().top - (body.clientHeight - bounds.height) / 2
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    if (typeof Highlight !== 'undefined' && CSS.highlights) {
      sourceHighlight = new Highlight(range)
      CSS.highlights.set('reading-source', sourceHighlight)
    }
  })
}
watch(() => props.sourceAnchor, () => { anchorRestored = false; nextTick(() => restoreSourceAnchor()) })
let tocObserver: IntersectionObserver | null = null
let _refreshTimer: ReturnType<typeof setInterval> | null = null
let _lastText = ''  // used to skip re-render when content unchanged

/** 将相对资源路径解析为相对当前 Markdown 文件目录的绝对路径（同源）。 */
function rewriteRelativeAssetUrls(rendered: string, mdFileUrl: string): string {
  let baseHref: string
  try {
    const u = new URL(mdFileUrl, window.location.origin)
    const path = u.pathname
    const slash = path.lastIndexOf('/')
    u.pathname = path.slice(0, slash + 1)
    baseHref = u.toString()
  } catch {
    return rendered
  }

  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div id="md-asset-root">${rendered}</div>`, 'text/html')
  const root = doc.getElementById('md-asset-root')
  if (!root) return rendered

  root.querySelectorAll('img[src]').forEach((el) => {
    const img = el as HTMLImageElement
    const src = img.getAttribute('src')?.trim() ?? ''
    if (!src || /^data:/i.test(src)) return
    if (/^https?:\/\//i.test(src) || src.startsWith('//')) return
    try {
      img.setAttribute('src', new URL(src, baseHref).href)
    } catch {
      /* keep original */
    }
  })

  return root.innerHTML
}

/** 为渲染后的 HTML 中的 heading 注入 id，并提取 TOC 条目。 */
function injectHeadingIds(rendered: string): { html: string; headings: TocHeading[] } {
  const parser = new DOMParser()
  const doc = parser.parseFromString(`<div id="md-toc-root">${rendered}</div>`, 'text/html')
  const root = doc.getElementById('md-toc-root')
  if (!root) return { html: rendered, headings: [] }

  const list: TocHeading[] = []
  const els = root.querySelectorAll('h1,h2,h3,h4,h5,h6')
  els.forEach((el, idx) => {
    const level = parseInt(el.tagName[1], 10)
    const text = el.textContent?.trim() ?? ''
    const slug = text
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^\w\u4e00-\u9fa5-]/g, '')
      .slice(0, 60)
    const id = `toc-${idx}-${slug}`
    el.setAttribute('id', id)
    list.push({ id, text, level })
  })

  return { html: root.innerHTML, headings: list }
}

function setupTocObserver() {
  if (tocObserver) {
    tocObserver.disconnect()
    tocObserver = null
  }
  if (!bodyRef.value || headings.value.length === 0) return

  tocObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          activeHeadingId.value = entry.target.id
          break
        }
      }
    },
    {
      root: bodyRef.value,
      rootMargin: '0px 0px -70% 0px',
      threshold: 0,
    },
  )

  headings.value.forEach(({ id }) => {
    const el = bodyRef.value?.querySelector(`#${CSS.escape(id)}`)
    if (el) tocObserver!.observe(el)
  })
}

function scrollToHeading(id: string) {
  const el = bodyRef.value?.querySelector(`#${CSS.escape(id)}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    activeHeadingId.value = id
  }
}

async function load() {
  if (!props.url) {
    html.value = ''
    headings.value = []
    loading.value = false
    error.value = ''
    _lastText = ''
    return
  }

  // Background refresh: already has content and auto-refresh is active.
  // Skip loading=true so bodyRef stays mounted (avoids DOM destroy → scrollTop reset).
  const isBackgroundRefresh = (props.autoRefreshMs ?? 0) > 0 && _lastText !== ''
  if (!isBackgroundRefresh) {
    loading.value = true
    error.value = ''
  }

  try {
    let text: string
    if (IS_TAURI) {
      text = await tauriFetchText(props.url)
    } else {
      const res = await fetch(props.url, { credentials: 'include' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      text = await res.text()
    }
    // Skip re-render if content has not changed (prevents flicker during auto-refresh)
    if (text === _lastText) return

    // Save scroll position BEFORE updating html while bodyRef is still the same DOM element.
    let savedRatio = -1
    if (isBackgroundRefresh && bodyRef.value) {
      const el = bodyRef.value
      const maxScroll = el.scrollHeight - el.clientHeight
      savedRatio = maxScroll > 0 ? el.scrollTop / maxScroll : 0
    }

    _lastText = text
    const rendered = renderPaperMarkdown(text)
    const raw = props.mode === 'bilingual' ? prepareTrialBilingual(rendered) : rendered
    const withIds = injectHeadingIds(raw)
    headings.value = withIds.headings
    html.value = rewriteRelativeAssetUrls(withIds.html, props.url)
    activeHeadingId.value = headings.value[0]?.id ?? ''

    // Restore scroll position after Vue patches the DOM.
    // bodyRef is the SAME element (not destroyed), so we just need to wait for
    // the new v-html content to be laid out before writing scrollTop back.
    if (savedRatio >= 0) {
      await nextTick()
      requestAnimationFrame(() => {
        if (!bodyRef.value) return
        const el = bodyRef.value
        const maxScroll = el.scrollHeight - el.clientHeight
        if (maxScroll > 0) {
          el.scrollTop = Math.round(Math.min(savedRatio * maxScroll, maxScroll))
        }
      })
    }
  } catch (e: unknown) {
    // During background refresh, keep existing content visible; don't wipe the page.
    if (!isBackgroundRefresh) {
      error.value = e instanceof Error ? e.message : '加载失败'
      html.value = ''
      headings.value = []
      _lastText = ''
    }
  } finally {
    if (!isBackgroundRefresh) {
      loading.value = false
    }
    nextTick(() => {
      setupTocObserver()
      requestAnimationFrame(() => { if (!isBackgroundRefresh) restorePosition(); restoreSourceAnchor() })
      if (showAllSources.value) bodyRef.value?.querySelectorAll<HTMLDetailsElement>('details.trial-source').forEach(el => { el.open = true })
    })
  }
}

onMounted(load)
watch(() => props.url, () => {
  anchorRestored = false
  selectionMenu.value = null
  _lastText = ''  // force re-render when URL changes even if content looks identical
  load()
})

// ── Auto-refresh timer ────────────────────────────────────
function _startRefreshTimer(ms: number) {
  _stopRefreshTimer()
  if (ms > 0) {
    _refreshTimer = setInterval(load, ms)
  }
}
function _stopRefreshTimer() {
  if (_refreshTimer) {
    clearInterval(_refreshTimer)
    _refreshTimer = null
  }
}

watch(
  () => props.autoRefreshMs,
  (ms) => {
    if (ms && ms > 0) {
      _startRefreshTimer(ms)
    } else {
      _stopRefreshTimer()
    }
  },
  { immediate: true },
)

// Re-init observer when TOC is opened (body ref may become available)
watch(showToc, (v) => {
  if (v) nextTick(() => setupTocObserver())
})

onBeforeUnmount(() => {
  if (sourceHighlight && CSS.highlights?.get('reading-source') === sourceHighlight) CSS.highlights.delete('reading-source')
  if (noticeTimer) clearTimeout(noticeTimer)
  tocObserver?.disconnect()
  _stopRefreshTimer()
})
</script>

<template>
  <div class="reading-workspace" :class="{ 'notes-open': notesOpen }">
  <!-- Outer positioning context: no card visuals, no overflow clipping -->
  <div
    class="relative flex flex-col min-h-0 h-full flex-1"
    :class="[rootClass, 'trial-reader', `paper-${paper}`]"
    :style="{ ...paletteStyle, '--trial-size': `${fontSize}px`, '--trial-leading': leading, '--trial-width': `${measure}em`, '--trial-tracking': `${tracking}em` }"
  >
    <ReadingExcerptMenu v-if="selectionMenu && paperId" :key="selectionMenu.anchor.start + ':' + selectionMenu.anchor.text" :paper-id="paperId" :scope="scope || 'kb'" :mode="mode || 'mineru'" :preferred-note-id="preferredNoteId" :append-to-note="appendToNote" v-bind="selectionMenu" @close="selectionMenu = null" @saved="excerptSaved" />
    <div v-if="savedNotice" class="saved-notice" role="status"><span>{{ savedNotice }}</span><button v-if="!notesOpen" @click="notesOpen = true">查看笔记</button><button aria-label="关闭保存提示" @click="savedNotice = ''">×</button></div>
    <!-- TOC: positioned absolutely to the left of the card -->
    <transition
      enter-active-class="transition-all duration-200 ease-out"
      leave-active-class="transition-all duration-200 ease-in"
      enter-from-class="opacity-0 -translate-x-2"
      leave-to-class="opacity-0 -translate-x-2"
    >
      <aside
        v-if="showToc && headings.length > 0"
        class="reader-controls absolute z-20 left-0 top-12 bottom-0 w-64 mr-2 border border-border rounded-xl bg-bg-sidebar overflow-hidden flex flex-col shadow-lg"
      >
        <!-- TOC header -->
        <div class="shrink-0 px-3 py-2.5 border-b border-border flex items-center justify-between gap-2">
          <div class="flex items-center gap-2.5 min-w-0">
            <!-- Brand gradient marker bar -->
            <span class="shrink-0 w-[3px] h-[22px] rounded-full bg-gradient-to-b from-gradient-start to-gradient-end" />
            <div class="flex flex-col min-w-0">
              <span class="text-[13px] font-semibold text-text-primary leading-tight">大纲</span>
              <span class="text-[10.5px] text-text-muted leading-tight">共 {{ headings.length }} 个标题</span>
            </div>
          </div>
          <button
            class="shrink-0 flex items-center justify-center w-6 h-6 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors bg-transparent border-none cursor-pointer"
            :title="'收起目录'"
            @click="showToc = false"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <MarkdownToc
          :headings="headings"
          :active-id="activeHeadingId"
          :is-bilingual="mode === 'bilingual' || mode === 'zh'"
          @select="scrollToHeading"
        />
      </aside>
    </transition>

    <!-- Inner card: holds all visual styling and content -->
    <div class="flex flex-col flex-1 min-h-0 bg-bg-card rounded-xl border border-border overflow-hidden">
      <!-- Loading -->
      <div v-if="loading" class="flex-1 flex flex-col items-center justify-center gap-2 p-4">
        <LoadingSpinner size="md" text="加载中…" />
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex-1 flex items-center justify-center text-sm text-tinder-pink p-4 text-center">
        {{ error }}
      </div>

      <!-- Content -->
      <template v-else>
        <!-- TOC toggle button (only when there are headings) -->
        <div
          v-if="headings.length > 0 || mode"
          class="reader-toolbar shrink-0 flex items-center justify-between px-3 py-1.5 border-b border-border"
        >
          <button
            v-if="headings.length > 0"
            class="flex items-center gap-1.5 text-[12px] px-2 py-1 rounded-md transition-colors bg-transparent border-none cursor-pointer"
            :class="showToc
              ? 'text-tinder-pink bg-tinder-pink/10'
              : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'"
            :title="showToc ? '收起目录' : '展开目录'"
            @click="showToc = !showToc"
          >
            <!-- List icon -->
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="8" y1="6" x2="21" y2="6"/>
              <line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/>
              <line x1="3" y1="6" x2="3.01" y2="6"/>
              <line x1="3" y1="12" x2="3.01" y2="12"/>
              <line x1="3" y1="18" x2="3.01" y2="18"/>
            </svg>
            <span>目录</span>
            <span class="text-text-muted">({{ headings.length }})</span>
          </button>
          <span v-else />
          <!-- Reading controls: shared by MinerU, Chinese and bilingual modes -->
          <div v-if="mode" class="bilingual-controls">
            <button v-if="paperId" type="button" :aria-expanded="notesOpen" @click="toggleNotes">{{ notesOpen ? '收起笔记' : '论文笔记' }}</button>
            <button v-if="mode === 'bilingual'" type="button" @click="showAllSources = !showAllSources">{{ showAllSources ? '中文主读' : '展开全部原文' }}</button>
            <button type="button" :aria-expanded="settingsOpen" @click="settingsOpen = !settingsOpen">阅读设置</button>
          </div>
        </div>

        <p v-if="anchorMessage" class="px-4 py-2 text-sm" role="status">{{ anchorMessage }}</p>
        <div v-if="settingsOpen" class="trial-settings reader-controls">
          <label>字号 {{ fontSize }}px <input v-model.number="fontSize" aria-label="字号" type="range" min="16" max="28" step="1" /></label>
          <label>行距 {{ leading }} <input v-model.number="leading" aria-label="行距" type="range" min="1.5" max="2.2" step="0.05" /></label>
          <label>行宽 {{ measure }}字 <input v-model.number="measure" aria-label="行宽" type="range" min="28" max="42" step="1" /></label>
          <label>字距 <input v-model.number="tracking" aria-label="字距" type="range" min="0" max="0.06" step="0.01" /></label>
          <label>纸面 <select v-model="paper" aria-label="纸面" @change="paper === 'dark' ? colorDepth = 92 : undefined"><option v-for="item in readingPapers" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        </div>
        <div v-if="settingsOpen" class="trial-settings reader-controls">
          <label>颜色深度 {{ colorDepth }}% <input v-model.number="colorDepth" aria-label="颜色深度" type="range" min="0" max="100" step="1" /></label>
          <label v-if="paper === 'custom'">自选颜色 <input v-model="customColor" type="color" aria-label="自选颜色" /></label>
          <span>正文首行缩进两字符</span>
        </div>
        <!-- Markdown body -->
        <div
          ref="bodyRef"
          tabindex="-1"
          @mouseup="captureSelection"
          @keyup="captureSelection"
          @scroll="rememberPosition"
          class="flex-1 overflow-y-auto px-5 sm:px-6 py-4 text-text-primary markdown-viewer-body"
          :class="[
            mode ? 'reading-mode' : '',
            mode === 'bilingual' ? 'bilingual-mode' : '',
          ]"
          v-html="html"
        />
      </template>
    </div>
  </div>
  <ReadingNotesPanel v-if="notesOpen && paperId" ref="notesPanel" :paper-id="paperId" :scope="scope || 'kb'" :preferred-id="preferredNoteId" :latest-note="lastNote" @selected="preferredNoteId = $event" @close="notesOpen = false" @source-link="sourceLink" />
  </div>
</template>

<style scoped>
.reading-workspace { --reader-ui-bg: var(--color-bg-card); --reader-ui-ink: var(--color-text-primary); --reader-ui-muted: var(--color-text-muted); --reader-ui-border: var(--color-border); --reader-ui-hover: var(--color-bg-hover); position: relative; display: flex; gap: 12px; min-height: 0; height: 100%; width: 100%; max-width: 1100px; margin: 0 auto; }
.reading-workspace.notes-open { max-width: 1540px; }
.trial-reader { min-width: 0; }
.saved-notice { position: absolute; z-index: 30; top: 48px; right: 16px; display: flex; gap: 10px; align-items: center; max-width: calc(100% - 32px); padding: 9px 12px; border: 1px solid var(--trial-line); border-radius: 8px; background: var(--trial-bg); color: var(--trial-ink); box-shadow: 0 3px 14px #0001; font-size: 12px; }
.saved-notice span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.saved-notice button { cursor: pointer; border: 0; background: transparent; color: inherit; white-space: nowrap; text-decoration: underline; }
/* ── Headings ─────────────────────────────────────── */
.markdown-viewer-body :deep(h1) {
  font-size: 1.45rem;
  font-weight: 700;
  margin: 1.5rem 0 0.6rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-primary);
  line-height: 1.3;
}
.markdown-viewer-body :deep(h2) {
  font-size: 1.2rem;
  font-weight: 600;
  margin: 1.25rem 0 0.45rem;
  color: var(--color-text-primary);
  line-height: 1.35;
}
.markdown-viewer-body :deep(h3) {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 1rem 0 0.4rem;
  color: var(--color-text-primary);
}
.markdown-viewer-body :deep(h4),
.markdown-viewer-body :deep(h5),
.markdown-viewer-body :deep(h6) {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0.85rem 0 0.35rem;
  color: var(--color-text-secondary);
}

/* ── Body text ────────────────────────────────────── */
.markdown-viewer-body :deep(p) {
  margin: 0.6rem 0;
  line-height: 1.75;
  font-size: 0.9rem;
}
.markdown-viewer-body :deep(ul),
.markdown-viewer-body :deep(ol) {
  margin: 0.6rem 0;
  padding-left: 1.4rem;
  font-size: 0.9rem;
}
.markdown-viewer-body :deep(li) {
  margin: 0.3rem 0;
  line-height: 1.65;
}

/* ── Blockquote (general) ─────────────────────────── */
.markdown-viewer-body :deep(blockquote) {
  border-left: 3px solid var(--color-tinder-pink, #ff4458);
  margin: 0.75rem 0;
  padding: 0.5rem 0.85rem;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  background: rgba(255, 68, 88, 0.04);
  border-radius: 0 6px 6px 0;
}

/* ── Horizontal rule ──────────────────────────────── */
.markdown-viewer-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border-light);
  margin: 1rem 0;
}

/* ── Tables ───────────────────────────────────────── */
.markdown-viewer-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  margin: 0.85rem 0;
  display: block;
  overflow-x: auto;
  max-width: 100%;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-border);
}
.markdown-viewer-body :deep(th) {
  padding: 0.45rem 0.65rem;
  background: var(--color-bg-elevated);
  font-weight: 600;
  text-align: left;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border);
}
.markdown-viewer-body :deep(th + th) {
  border-left: 1px solid var(--color-border);
}
.markdown-viewer-body :deep(td) {
  padding: 0.4rem 0.65rem;
  color: var(--color-text-secondary);
  border-top: 1px solid var(--color-border);
}
.markdown-viewer-body :deep(td + td) {
  border-left: 1px solid var(--color-border);
}
.markdown-viewer-body :deep(tr:nth-child(even) td) {
  background: var(--color-bg-elevated);
}

/* ── Code ─────────────────────────────────────────── */
.markdown-viewer-body :deep(pre) {
  overflow-x: auto;
  padding: 0.85rem 1rem;
  border-radius: 8px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  font-size: 0.78rem;
  margin: 0.85rem 0;
  line-height: 1.6;
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
}
.markdown-viewer-body :deep(code) {
  font-size: 0.82em;
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
}
.markdown-viewer-body :deep(:not(pre) > code) {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 0.1em 0.35em;
  color: var(--color-tinder-pink, #ff4458);
  font-size: 0.82em;
}

/* ── Images ───────────────────────────────────────── */
.markdown-viewer-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.5rem 0;
}

/* ── Links ────────────────────────────────────────── */
.markdown-viewer-body :deep(a) {
  color: var(--color-tinder-blue, #2db8e2);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.markdown-viewer-body :deep(a:hover) {
  opacity: 0.8;
}

/* ── Math ─────────────────────────────────────────── */
.markdown-viewer-body :deep(.katex-display) {
  overflow-x: auto;
  overflow-y: hidden;
  max-width: 100%;
  padding: 0.35rem 0;
}
.markdown-viewer-body :deep(.katex) {
  font-size: 1em;
}

/* ═══════════════════════════════════════════════════
   Bilingual mode — English blockquote vs Chinese prose
   ═══════════════════════════════════════════════════ */

.bilingual-controls {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Reading modes share the persisted font-size and accent preferences. */
.markdown-viewer-body.reading-mode {
  font-size: var(--bilingual-font-size);
}

/* Override rem sizes so the reader's preference scales the whole paper. */
.markdown-viewer-body.reading-mode :deep(p),
.markdown-viewer-body.reading-mode :deep(ul),
.markdown-viewer-body.reading-mode :deep(ol) {
  font-size: 1em;
}

.markdown-viewer-body.reading-mode :deep(h1) {
  font-size: 1.61em;
  border-bottom-color: hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, 0.32);
}
.markdown-viewer-body.reading-mode :deep(h2) {
  font-size: 1.33em;
  color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 38%);
}
.markdown-viewer-body.reading-mode :deep(h3) {
  font-size: 1.17em;
  color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 42%);
}
.markdown-viewer-body.reading-mode :deep(h4),
.markdown-viewer-body.reading-mode :deep(h5),
.markdown-viewer-body.reading-mode :deep(h6) { font-size: 1.06em; }
.markdown-viewer-body.reading-mode :deep(a) {
  color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 42%);
}
.markdown-viewer-body.reading-mode :deep(blockquote) {
  border-left-color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 45%);
  background: hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, calc(var(--bilingual-intensity) * 0.01));
}

/* English source paragraph (rendered as blockquote) */
.markdown-viewer-body.bilingual-mode :deep(blockquote) {
  border-left: 3px solid hsl(var(--bilingual-hue), var(--bilingual-saturation), 45%);
  background: hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, calc(var(--bilingual-intensity) * 0.01));
  color: var(--color-text-secondary);
  font-size: 0.92em;
  padding: 0.5em 0.85em;
  margin: 0.5em 0 0;
  border-radius: 0 6px 6px 0;
}

/* Emphasis belongs to the paper, not to the reader's UI labels. */
.markdown-viewer-body.reading-mode :deep(strong) {
  font-size: inherit;
  color: inherit;
  font-weight: 700;
}

/* Chinese translation paragraph — inherits container font-size (= user's chosen value) */
.markdown-viewer-body.bilingual-mode :deep(p) {
  color: var(--color-text-primary);
  line-height: var(--trial-leading);
  margin: 0.2em 0 0.6em;
}

/* Section separator */
.markdown-viewer-body.bilingual-mode :deep(hr) {
  border-top: 1px dashed var(--color-border-light);
  margin: 0.85em 0;
  opacity: 0.6;
}

/* Scroll-margin so IntersectionObserver doesn't fire too early */
.markdown-viewer-body :deep(h1),
.markdown-viewer-body :deep(h2),
.markdown-viewer-body :deep(h3),
.markdown-viewer-body :deep(h4),
.markdown-viewer-body :deep(h5),
.markdown-viewer-body :deep(h6) {
  scroll-margin-top: 8px;
}
</style>

<style scoped>
.trial-reader { --trial-bg: #f7f5ef; --trial-ink: #2b2b2b; --trial-muted: #595951; --trial-line: #d7d4ca; --color-text-primary: var(--trial-ink); --color-text-secondary: var(--trial-muted); --color-border: var(--trial-line); --color-bg-card: var(--trial-bg); --color-bg-sidebar: var(--trial-bg); }
.paper-white { --trial-bg: #fff; --trial-ink: #292929; --trial-muted: #595959; --trial-line: #ddd; }
.paper-dark { --trial-bg: #232522; --trial-ink: #e5e5dc; --trial-muted: #bcbfb5; --trial-line: #53574e; }
.trial-reader > div { background: var(--trial-bg); }
.markdown-viewer-body { background: var(--trial-bg); }
.trial-settings { display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 12px 20px; color: var(--trial-ink); border-bottom: 1px solid var(--trial-line); font-size: 13px; }
.trial-settings label { display: flex; align-items: center; gap: 8px; }
.trial-settings input { width: 100px; }
.trial-settings select, .bilingual-controls button { background: var(--trial-bg); color: var(--trial-ink); border: 1px solid var(--trial-line); padding: 4px 8px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.markdown-viewer-body.reading-mode { font-size: var(--trial-size); color: var(--trial-ink); letter-spacing: var(--trial-tracking); padding: 24px max(20px, calc((100% - var(--trial-width)) / 2)) 80px; overflow-wrap: anywhere; scrollbar-gutter: stable; }
.markdown-viewer-body.reading-mode :deep(p), .markdown-viewer-body.reading-mode :deep(ul), .markdown-viewer-body.reading-mode :deep(ol) { font-size: 1em; line-height: var(--trial-leading); margin: 0.85em 0; color: var(--trial-ink); }
.markdown-viewer-body.reading-mode :deep(h1), .markdown-viewer-body.reading-mode :deep(h2), .markdown-viewer-body.reading-mode :deep(h3) { color: var(--trial-ink); border: 0; margin-top: 1.5em; }
.markdown-viewer-body :deep(h1:first-child) { margin-top: 0.4em; }
.markdown-viewer-body.reading-mode :deep(blockquote) { background: transparent; color: var(--trial-ink); border-left: 2px solid var(--trial-line); margin: 0.5em 0; padding: 0 0 0 1em; font-size: 1em; }
.markdown-viewer-body :deep(.trial-pair) { margin: 0 0 1.2em; }
.markdown-viewer-body :deep(.trial-pair > p:last-of-type) { margin-bottom: 0.25em; }
.markdown-viewer-body :deep(.trial-source) { font-size: 0.95em; margin: 0 0 0.3em; }
.markdown-viewer-body :deep(.trial-source summary) { color: var(--trial-muted); font-size: 0.75em; cursor: pointer; padding: 6px 0; }
.markdown-viewer-body :deep(hr) { border: 0; height: 0; margin: 1.5em 0; }
.markdown-viewer-body :deep(table) { display: block; max-width: 100%; overflow-x: auto; font-size: 0.85em; }
.markdown-viewer-body :deep(pre) { font-size: 0.85em; max-width: 100%; overflow-x: auto; }
.markdown-viewer-body :deep(a) { color: var(--trial-ink); text-decoration: underline; }
.markdown-viewer-body.reading-mode :deep(p) { text-indent: 2em; }
.markdown-viewer-body.reading-mode :deep(li p), .markdown-viewer-body.reading-mode :deep(td p), .markdown-viewer-body.reading-mode :deep(th p), .markdown-viewer-body.reading-mode :deep(p:has(img)) { text-indent: 0; }
.markdown-viewer-body ::selection { background: #e5bf62; color: #191919; }
:global(::highlight(reading-source)) { background: #e5bf62; color: #191919; }
@media (max-width: 600px) { .markdown-viewer-body.reading-mode { padding: 16px 16px 64px; } }
</style>

<style scoped>
/* Site chrome uses site tokens; typography and paper colors remain local to the body. */
.reader-toolbar, .reader-controls { --color-text-primary: var(--reader-ui-ink); --color-text-secondary: var(--reader-ui-muted); --color-text-muted: var(--reader-ui-muted); --color-border: var(--reader-ui-border); --color-bg-sidebar: var(--reader-ui-bg); background: var(--reader-ui-bg); color: var(--reader-ui-ink); border-color: var(--reader-ui-border); }
.reader-toolbar { min-height: 44px; flex-wrap: wrap; gap: 6px; }
.trial-reader .trial-settings { background: var(--reader-ui-bg); color: var(--reader-ui-ink); border-color: var(--reader-ui-border); }
.trial-settings select, .reader-toolbar .bilingual-controls button { background: var(--reader-ui-bg); color: var(--reader-ui-ink); border: 1px solid var(--reader-ui-border); border-radius: 8px; min-height: 30px; }
.reader-toolbar button:hover { background: var(--reader-ui-hover); }
.reader-toolbar button[aria-expanded="true"] { border-color: var(--color-accent-primary); box-shadow: inset 0 -2px var(--color-accent-primary); }
.reader-toolbar button:focus-visible, .trial-settings :is(input, select):focus-visible { outline: 2px solid var(--color-accent-primary); outline-offset: 2px; }
.trial-settings input { accent-color: var(--color-accent-primary); }
</style>
