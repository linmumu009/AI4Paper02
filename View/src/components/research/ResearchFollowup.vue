<script setup lang="ts">
import { ref } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{
  modelValue: string
  isRunning: boolean
  prevResearch?: { question: string; finalText: string } | null
}>()

const emit = defineEmits<{
  'update:modelValue': [v: string]
  submit: []
}>()

const prevCollapsed = ref(true)
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    if (props.modelValue.trim() && !props.isRunning) emit('submit')
  }
}

function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}
</script>

<template>
  <div class="space-y-2">
    <!-- Previous research context (collapsed by default) -->
    <div
      v-if="prevResearch"
      class="rounded-2xl border border-border/30 overflow-hidden"
    >
      <button
        class="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-bg-elevated/20 transition-colors text-left"
        @click="prevCollapsed = !prevCollapsed"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          class="text-text-muted shrink-0">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>
        </svg>
        <span class="text-xs font-semibold text-text-muted">上轮研究上下文</span>
        <span class="text-xs text-text-muted truncate flex-1">{{ prevResearch.question }}</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          class="text-text-muted shrink-0 transition-transform"
          :class="prevCollapsed ? '' : 'rotate-180'">
          <path d="m18 15-6-6-6 6"/>
        </svg>
      </button>
      <Transition name="prev-body">
        <div v-if="!prevCollapsed" class="px-4 pt-2 pb-3 border-t border-border/40">
          <div
            class="research-prose prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed text-text-muted"
            v-html="md.render(prevResearch.finalText + (prevResearch.finalText.length >= 1500 ? '\n\n…（内容已截断）' : ''))"
          />
        </div>
      </Transition>
    </div>

    <!-- Follow-up input area -->
    <div class="rounded-2xl border border-border/40 overflow-hidden">
      <div class="px-5 pt-4 pb-1.5">
        <span class="text-xs font-medium text-text-muted">继续追问</span>
        <p class="text-[11px] text-text-muted/50 mt-0.5 leading-relaxed">基于以上研究结果进一步提问，上轮结论将作为上下文</p>
      </div>
      <div class="px-4 pb-4 pt-2 flex items-end gap-2">
        <textarea
          :value="modelValue"
          :disabled="isRunning"
          placeholder="输入追问内容… (Ctrl+Enter 发送)"
          rows="1"
          class="flex-1 resize-none rounded-xl border border-border/40 bg-transparent px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent-primary/20 focus:border-accent-primary/30 disabled:opacity-40 transition-all overflow-hidden"
          style="min-height: 42px; max-height: 120px"
          @input="(e) => { emit('update:modelValue', (e.target as HTMLTextAreaElement).value); autoGrow(e) }"
          @keydown="handleKeydown"
        />
        <button
          :disabled="!modelValue.trim() || isRunning"
          class="shrink-0 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-accent-primary text-white hover:bg-accent-primary/90 active:scale-95"
          @click="emit('submit')"
        >追问</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prev-body-enter-active,
.prev-body-leave-active { transition: max-height 0.2s ease, opacity 0.15s ease; max-height: 500px; overflow: hidden; }
.prev-body-enter-from,
.prev-body-leave-to { max-height: 0; opacity: 0; }

.research-prose :deep(p) { margin-top: 0.3em; margin-bottom: 0.3em; }
.research-prose :deep(strong) { color: inherit; font-weight: 600; }
.research-prose :deep(code) {
  background: rgb(var(--color-bg-elevated) / 0.8);
  padding: 0.1em 0.3em; border-radius: 0.2em; font-size: 0.85em;
}
</style>
