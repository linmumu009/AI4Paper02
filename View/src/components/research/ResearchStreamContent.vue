<script setup lang="ts">
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  streamText: string
  isRunning: boolean
  progressMsg?: string
  /** For R2: suggest full-text read for these papers */
  papersToRead?: string[]
  /** For R2: reason text shown after done */
  decisionReason?: string
  /** For R2: show full-text suggestion card */
  showReadFullSuggestion?: boolean
  /** For R2: title resolver */
  titleFor?: (id: string) => string
  /** For R3: truncation warning */
  truncationWarning?: string
  /** For R2: can force full read */
  canForceFullRead?: boolean
}>()

const emit = defineEmits<{
  forceFullRead: []
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const renderedHtml = () => md.render(props.streamText)
</script>

<template>
  <div class="space-y-3">
    <!-- Truncation warning (R3) -->
    <div
      v-if="truncationWarning"
      class="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/20 text-xs text-amber-400"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>
      </svg>
      {{ truncationWarning }}
    </div>

    <!-- Streaming markdown content -->
    <div
      v-if="streamText"
      class="prose dark:prose-invert max-w-none research-prose text-text-primary"
      v-html="renderedHtml()"
    />

    <!-- Running state with spinner -->
    <div v-else-if="isRunning" class="flex items-center gap-2.5 text-sm text-text-muted py-4">
      <svg class="animate-spin shrink-0" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      <span>{{ progressMsg || '正在分析…' }}</span>
    </div>

    <!-- R2: Suggest papers to read full-text -->
    <div
      v-if="showReadFullSuggestion && papersToRead && papersToRead.length > 0"
      class="mt-3 p-3 rounded-xl bg-bg-elevated/30 border border-border/40"
    >
      <div class="text-xs font-medium text-text-muted mb-2 flex items-center gap-1.5">
        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
        建议阅读全文
      </div>
      <div class="flex flex-wrap gap-1 mb-2">
        <span
          v-for="pid in papersToRead"
          :key="pid"
          class="text-[11px] px-2 py-0.5 rounded-full border border-border/50 text-text-muted bg-bg-elevated/50"
        >{{ titleFor ? titleFor(pid) : pid }}</span>
      </div>
    </div>

    <!-- R2: Decision reason -->
    <div v-if="decisionReason" class="text-[11px] text-text-muted/60 italic leading-relaxed border-l border-border/40 pl-3 mt-2">
      {{ decisionReason }}
    </div>

    <!-- R2: Force full read option -->
    <div v-if="canForceFullRead" class="pt-4 border-t border-border/25">
      <p class="text-xs text-text-muted/70 mb-2.5">AI 摘要已能回答问题。需要更深入的全文分析？</p>
      <button
        class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border/50 text-text-secondary hover:text-text-primary hover:border-border transition-colors"
        @click="emit('forceFullRead')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
        深度阅读全文
      </button>
    </div>
  </div>
</template>

<style scoped>
.research-prose { font-size: 0.9375rem; }
.research-prose :deep(p) { margin-top: 0.75em; margin-bottom: 0.75em; line-height: 1.82; }
.research-prose :deep(h1) { font-size: 1.2em; font-weight: 600; margin-top: 1.8em; margin-bottom: 0.65em; color: inherit; }
.research-prose :deep(h2) { font-size: 1.1em; font-weight: 600; margin-top: 1.6em; margin-bottom: 0.55em; color: inherit; }
.research-prose :deep(h3), .research-prose :deep(h4) { font-size: 1em; font-weight: 600; margin-top: 1.4em; margin-bottom: 0.45em; color: inherit; }
.research-prose :deep(code) {
  background: var(--color-bg-elevated);
  border: 1px solid color-mix(in srgb, var(--color-border) 50%, transparent);
  padding: 0.15em 0.4em; border-radius: 0.3em; font-size: 0.82em;
}
.research-prose :deep(pre) {
  background: var(--color-bg-elevated);
  border: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent);
  border-radius: 0.75em; padding: 1em 1.25em; overflow-x: auto;
}
.research-prose :deep(pre code) { background: none; border: none; padding: 0; }
.research-prose :deep(ul), .research-prose :deep(ol) { padding-left: 1.6em; margin: 0.7em 0; }
.research-prose :deep(li) { margin-top: 0.35em; margin-bottom: 0.35em; line-height: 1.8; }
.research-prose :deep(strong) { color: inherit; font-weight: 600; }
.research-prose :deep(blockquote) {
  border-left: 2px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  padding-left: 1em; margin: 1em 0;
  color: var(--color-text-muted);
  font-style: italic;
}
.research-prose :deep(hr) { border-color: color-mix(in srgb, var(--color-border) 50%, transparent); margin: 1.5em 0; }
.research-prose :deep(a) { color: var(--color-tinder-blue); text-decoration: underline; text-underline-offset: 2px; }
</style>
