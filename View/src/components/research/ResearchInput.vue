<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  paperIds: string[]
  paperTitles?: Record<string, string>
  topN: number
  isRunning: boolean
  canStart: boolean
  finalAnswerReached: boolean
  /** false = wide centred mode (empty state), true = compact top-bar mode (results active) */
  compact?: boolean
  scope?: string
}>(), { compact: true, scope: 'kb' })

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:topN': [value: number]
  start: []
  abort: []
  removePaper: [paperId: string]
  pickPapers: []
}>()

const showSettings = ref(false)
const settingsRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const chipsRef = ref<HTMLElement | null>(null)

function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, props.compact ? 120 : 160) + 'px'
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    if (props.canStart) emit('start')
  }
}

function titleFor(pid: string): string {
  return props.paperTitles?.[pid] ?? pid
}

function onSettingsOutside(e: MouseEvent) {
  if (settingsRef.value && !settingsRef.value.contains(e.target as Node)) {
    showSettings.value = false
  }
}

watch(showSettings, (v) => {
  if (v) {
    nextTick(() => document.addEventListener('click', onSettingsOutside, { capture: true }))
  } else {
    document.removeEventListener('click', onSettingsOutside, { capture: true })
  }
})
</script>

<template>
  <!-- ===== COMPACT mode (results active — top-bar strip) ===== -->
  <div v-if="compact" class="flex flex-col gap-0 border-b border-border/30">
    <!-- Paper chips row -->
    <div class="px-4 pt-3 pb-2 flex items-center gap-2">
      <span class="shrink-0 text-xs font-medium text-text-muted/60 tabular-nums">
        {{ paperIds.length }} 篇
      </span>
      <div ref="chipsRef" class="flex-1 overflow-x-auto flex gap-1.5 no-scrollbar" style="scrollbar-width: none">
        <span
          v-for="pid in paperIds"
          :key="pid"
          class="shrink-0 inline-flex items-center gap-1 text-[11px] pl-2 py-0.5 rounded-full border border-border/30 text-text-muted/60 group"
          :class="isRunning ? 'pr-2' : 'pr-1'"
          :title="titleFor(pid)"
        >
          <span class="truncate max-w-[130px]">{{ titleFor(pid) }}</span>
          <button
            v-if="!isRunning"
            type="button"
            class="shrink-0 w-3.5 h-3.5 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-red-400/20 hover:text-red-400 transition-all border-none bg-transparent cursor-pointer"
            :title="`移除「${titleFor(pid)}」`"
            @click.stop="emit('removePaper', pid)"
          >
            <svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </span>
      </div>
    </div>

    <!-- Question input row -->
    <div class="px-4 pb-3 flex items-end gap-2">
      <div class="flex-1 relative">
        <textarea
          ref="textareaRef"
          :value="modelValue"
          :disabled="isRunning"
          placeholder="输入研究问题，按 Ctrl+Enter 开始…"
          rows="1"
          class="w-full resize-none rounded-xl border border-border/40 bg-transparent px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent-primary/20 focus:border-accent-primary/30 disabled:opacity-40 transition-all leading-relaxed overflow-hidden"
          style="min-height: 42px; max-height: 120px"
          @input="(e) => { emit('update:modelValue', (e.target as HTMLTextAreaElement).value); autoGrow(e) }"
          @keydown="handleKeydown"
        />
      </div>

      <!-- Settings gear popover -->
      <div class="relative shrink-0" ref="settingsRef">
        <button
          class="p-2 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-accent-primary/30 hover:bg-bg-elevated transition-colors"
          :class="showSettings ? 'text-accent-primary border-accent-primary/40 bg-accent-primary/8' : ''"
          title="研究设置"
          @click.stop="showSettings = !showSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </button>

        <Transition name="popover">
          <div
            v-if="showSettings"
            class="absolute bottom-full right-0 mb-2 w-64 rounded-xl border border-border bg-bg-elevated shadow-xl p-4 z-20"
          >
            <div class="text-xs font-semibold text-text-muted mb-3">研究设置</div>
            <div class="space-y-1">
              <div class="flex items-center justify-between">
                <label class="text-xs text-text-secondary">最多分析论文数 (Top N)</label>
                <span class="text-xs font-mono font-bold text-accent-primary w-6 text-center">{{ topN }}</span>
              </div>
              <input
                :value="topN"
                type="range"
                min="1"
                :max="Math.min(Math.max(paperIds.length, 1), 15)"
                step="1"
                class="w-full accent-accent-primary"
                @input="emit('update:topN', Number(($event.target as HTMLInputElement).value))"
              />
              <div class="flex justify-between text-[10px] text-text-muted">
                <span>1</span>
                <span>{{ Math.min(Math.max(paperIds.length, 1), 15) }}</span>
              </div>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Start / Stop button -->
      <button
        v-if="!isRunning"
        :disabled="!canStart"
        class="shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-accent-primary text-white hover:bg-accent-primary/90 active:scale-95"
        @click="emit('start')"
      >
        {{ finalAnswerReached ? '重新' : '开始' }}
      </button>
      <button
        v-else
        class="shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all bg-bg-elevated border border-border text-text-secondary hover:text-red-400 hover:border-red-400/40 active:scale-95"
        @click="emit('abort')"
      >
        停止
      </button>
    </div>
  </div>

  <!-- ===== WIDE mode (empty state — centered card with integrated paper picker) ===== -->
  <div v-else class="flex flex-col gap-0">
    <div class="relative rounded-2xl border border-border bg-bg-elevated/40 focus-within:border-accent-primary/35 focus-within:ring-2 focus-within:ring-accent-primary/10 transition-all shadow-sm">

      <!-- Textarea -->
      <textarea
        ref="textareaRef"
        :value="modelValue"
        :disabled="isRunning"
        placeholder="输入你想研究的问题…"
        rows="3"
        class="w-full resize-none bg-transparent px-5 pt-5 pb-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-50 leading-relaxed overflow-hidden rounded-t-2xl"
        style="min-height: 96px; max-height: 160px"
        @input="(e) => { emit('update:modelValue', (e.target as HTMLTextAreaElement).value); autoGrow(e) }"
        @keydown="handleKeydown"
      />

      <!-- Paper picker section (integrated inside the card) -->
      <div class="px-4 pb-3 pt-2 border-t border-border/20 mx-1">
        <!-- No papers selected: dashed "select" button -->
        <button
          v-if="paperIds.length === 0"
          type="button"
          class="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl border border-dashed border-border/60 text-text-muted/60 hover:text-text-muted hover:border-border hover:bg-bg-elevated/40 transition-all text-xs cursor-pointer"
          @click="emit('pickPapers')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/>
          </svg>
          从知识库选择论文
        </button>

        <!-- Papers selected: chips + "更改" -->
        <div v-else class="flex items-center gap-2">
          <span class="shrink-0 text-[11px] font-semibold text-text-muted bg-bg-elevated border border-border px-2 py-0.5 rounded-full tabular-nums">
            {{ paperIds.length }} 篇
          </span>
          <div class="flex-1 overflow-x-auto flex gap-1.5 no-scrollbar min-w-0">
            <span
              v-for="pid in paperIds"
              :key="pid"
              class="shrink-0 inline-flex items-center gap-1 text-[11px] pl-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted group"
              :class="isRunning ? 'pr-2' : 'pr-1'"
              :title="titleFor(pid)"
            >
              <span class="truncate max-w-[120px]">{{ titleFor(pid) }}</span>
              <button
                v-if="!isRunning"
                type="button"
                class="shrink-0 w-3.5 h-3.5 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-red-400/20 hover:text-red-400 transition-all border-none bg-transparent cursor-pointer"
                :title="`移除「${titleFor(pid)}」`"
                @click.stop="emit('removePaper', pid)"
              >
                <svg viewBox="0 0 24 24" width="9" height="9" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <path d="M18 6 6 18M6 6l12 12"/>
                </svg>
              </button>
            </span>
          </div>
          <button
            v-if="!isRunning"
            type="button"
            class="shrink-0 text-[11px] text-text-muted/50 hover:text-text-muted transition-colors px-2 py-0.5 rounded-lg hover:bg-bg-elevated cursor-pointer border-none bg-transparent"
            @click.stop="emit('pickPapers')"
          >
            更改
          </button>
        </div>
      </div>

      <!-- Bottom toolbar -->
      <div class="flex items-center justify-between px-4 pb-4 gap-2">
        <!-- Settings (icon-only, minimal) -->
        <div class="relative" ref="settingsRef">
          <button
            class="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-lg text-text-muted/60 hover:text-text-muted hover:bg-bg-elevated/60 transition-colors"
            :class="showSettings ? 'text-text-muted bg-bg-elevated' : ''"
            title="研究设置"
            @click.stop="showSettings = !showSettings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            Top {{ topN }}
          </button>

          <Transition name="popover">
            <div
              v-if="showSettings"
              class="absolute bottom-full left-0 mb-2 w-64 rounded-xl border border-border bg-bg-elevated shadow-xl p-4 z-20"
            >
              <div class="text-xs font-semibold text-text-muted mb-3">研究设置</div>
              <div class="space-y-1">
                <div class="flex items-center justify-between">
                  <label class="text-xs text-text-secondary">最多分析论文数 (Top N)</label>
                  <span class="text-xs font-mono font-bold text-accent-primary w-6 text-center">{{ topN }}</span>
                </div>
                <input
                  :value="topN"
                  type="range"
                  min="1"
                  :max="Math.min(Math.max(paperIds.length, 1), 15)"
                  step="1"
                  class="w-full accent-accent-primary"
                  :disabled="paperIds.length === 0"
                  @input="emit('update:topN', Number(($event.target as HTMLInputElement).value))"
                />
                <div class="flex justify-between text-[10px] text-text-muted">
                  <span>1</span>
                  <span>{{ Math.min(Math.max(paperIds.length, 1), 15) }}</span>
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <span class="text-[10px] text-text-muted/35 hidden sm:block">Ctrl+Enter</span>

        <!-- Start / Stop -->
        <button
          v-if="!isRunning"
          :disabled="!canStart"
          class="shrink-0 px-6 py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-35 disabled:cursor-not-allowed bg-accent-primary text-white hover:bg-accent-primary/90 active:scale-95"
          @click="emit('start')"
        >
          开始研究
        </button>
        <button
          v-else
          class="shrink-0 px-5 py-2 rounded-xl text-sm font-semibold transition-all bg-bg-elevated border border-border text-text-secondary hover:text-red-400 hover:border-red-400/40 active:scale-95"
          @click="emit('abort')"
        >
          停止
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

.popover-enter-active, .popover-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.popover-enter-from, .popover-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
