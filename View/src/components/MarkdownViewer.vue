<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { IS_TAURI, tauriFetchText } from '../api'
import MarkdownToc, { type TocHeading } from './MarkdownToc.vue'
import LoadingSpinner from './LoadingSpinner.vue'
import BilingualThemePicker from './BilingualThemePicker.vue'
import BilingualFontSizePicker from './BilingualFontSizePicker.vue'

const props = defineProps<{
  /** 完整 URL（含 API_ORIGIN） */
  url: string
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

const md = new MarkdownIt({ html: true, linkify: true, breaks: true }).use(texmath, {
  engine: katex,
  delimiters: 'dollars',
  katexOptions: { throwOnError: false },
})

const html = ref('')
const loading = ref(true)
const error = ref('')

// ── TOC state ────────────────────────────────────────────
const showToc = ref(false)
const headings = ref<TocHeading[]>([])
const activeHeadingId = ref('')
const bodyRef = ref<HTMLElement | null>(null)
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
    const raw = md.render(text)
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
    nextTick(() => setupTocObserver())
  }
}

onMounted(load)
watch(() => props.url, () => {
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
  tocObserver?.disconnect()
  _stopRefreshTimer()
})
</script>

<template>
  <!-- Outer positioning context: no card visuals, no overflow clipping -->
  <div
    class="relative flex flex-col min-h-0 h-full flex-1"
    :class="rootClass"
  >
    <!-- TOC: positioned absolutely to the left of the card -->
    <transition
      enter-active-class="transition-all duration-200 ease-out"
      leave-active-class="transition-all duration-200 ease-in"
      enter-from-class="opacity-0 -translate-x-2"
      leave-to-class="opacity-0 -translate-x-2"
    >
      <aside
        v-if="showToc && headings.length > 0"
        class="absolute right-full top-0 bottom-0 w-64 mr-2 border border-border rounded-xl bg-bg-sidebar overflow-hidden flex flex-col shadow-lg"
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
          v-if="headings.length > 0 || mode === 'bilingual'"
          class="shrink-0 flex items-center justify-between px-3 py-1.5 border-b border-border bg-bg-elevated/50"
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
          <!-- Bilingual controls: color picker + font size picker -->
          <div v-if="mode === 'bilingual'" class="bilingual-controls">
            <BilingualThemePicker />
            <BilingualFontSizePicker />
          </div>
        </div>

        <!-- Markdown body -->
        <div
          ref="bodyRef"
          class="flex-1 overflow-y-auto px-5 sm:px-6 py-4 text-text-primary markdown-viewer-body"
          :class="mode === 'bilingual' ? 'bilingual-mode' : ''"
          v-html="html"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
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

/* Container: set base font size from user preference (CSS var driven by useBilingualTheme) */
.markdown-viewer-body.bilingual-mode {
  font-size: var(--bilingual-font-size);
}

/* Override all p font-size from the generic 0.9rem so it inherits the container variable.
   Must be declared before the more specific p:not(...) rule. */
.markdown-viewer-body.bilingual-mode :deep(p) {
  font-size: 1em;
}

/* Override heading font-sizes from generic rem to em so they scale proportionally
   with the user-controlled --bilingual-font-size. Ratios preserved from the
   general rules: h1/p=1.61, h2/p=1.33, h3/p=1.17, h4-h6/p=1.06. */
.markdown-viewer-body.bilingual-mode :deep(h1) { font-size: 1.61em; }
.markdown-viewer-body.bilingual-mode :deep(h2) { font-size: 1.33em; }
.markdown-viewer-body.bilingual-mode :deep(h3) { font-size: 1.17em; }
.markdown-viewer-body.bilingual-mode :deep(h4),
.markdown-viewer-body.bilingual-mode :deep(h5),
.markdown-viewer-body.bilingual-mode :deep(h6) { font-size: 1.06em; }

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

/* [译] marker — styled as a small label */
.markdown-viewer-body.bilingual-mode :deep(p > strong:only-child) {
  display: inline-flex;
  align-items: center;
  font-size: 0.72em;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 42%);
  background: hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, calc(var(--bilingual-intensity) * 0.02));
  border: 1px solid hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, 0.25);
  border-radius: 4px;
  padding: 0.1em 0.5em;
  margin: 0.25em 0 0.1em;
  line-height: 1.5;
}

/* Chinese translation paragraph — inherits container font-size (= user's chosen value) */
.markdown-viewer-body.bilingual-mode :deep(p:not(:has(> strong:only-child))) {
  color: var(--color-text-primary);
  line-height: 1.8;
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
