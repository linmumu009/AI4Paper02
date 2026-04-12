<script setup lang="ts">
import type { KbPaper } from '@shared/types/kb'

const props = withDefaults(
  defineProps<{
    paper: KbPaper
    showFolder?: boolean
    folderName?: string
    batchMode?: boolean
    selected?: boolean
  }>(),
  { showFolder: false, batchMode: false, selected: false },
)

const emit = defineEmits<{
  (e: 'click'): void
  (e: 'longpress'): void
  (e: 'toggleSelect'): void
}>()

let pressTimer: ReturnType<typeof setTimeout> | null = null

function onTouchStart() {
  pressTimer = setTimeout(() => emit('longpress'), 500)
}
function onTouchEnd() {
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}

function handleClick() {
  if (props.batchMode) {
    emit('toggleSelect')
  } else {
    emit('click')
  }
}
</script>

<template>
  <div
    class="flex items-start gap-3 px-4 py-3 active:bg-bg-hover transition-colors cursor-pointer"
    :class="{ 'bg-tinder-blue/5': batchMode && selected }"
    @click="handleClick"
    @touchstart.passive="onTouchStart"
    @touchend.passive="onTouchEnd"
    @touchcancel.passive="onTouchEnd"
  >
    <!-- Batch checkbox OR read status dot -->
    <div class="shrink-0 flex items-center justify-center w-5 h-5 mt-1">
      <template v-if="batchMode">
        <div
          class="w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all"
          :class="selected ? 'border-tinder-blue bg-tinder-blue' : 'border-border bg-transparent'"
        >
          <svg v-if="selected" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
      </template>
      <template v-else>
        <div
          class="w-2 h-2 rounded-full"
          :class="{
            'bg-tinder-blue': paper.read_status === 'unread' || !paper.read_status,
            'bg-tinder-gold': paper.read_status === 'reading',
            'bg-text-muted opacity-40': paper.read_status === 'read',
          }"
        />
      </template>
    </div>

    <!-- Content -->
    <div class="flex-1 min-w-0">
      <p class="text-[13px] font-medium text-text-primary line-clamp-2 leading-snug">
        {{ paper.paper_data?.short_title || paper.paper_data?.['📖标题'] || paper.paper_id }}
      </p>
      <div class="flex items-center gap-2 mt-1 flex-wrap">
        <span v-if="paper.paper_data?.institution" class="institution-badge-mini shrink-0">
          {{ paper.paper_data.institution }}
        </span>
        <span v-if="showFolder && folderName" class="text-[11px] text-text-muted">
          📁 {{ folderName }}
        </span>
        <span class="text-[11px] text-text-muted">
          {{ paper.created_at ? new Date(paper.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) : '' }}
        </span>
        <span
          v-if="paper.note_count && paper.note_count > 0"
          class="text-[11px] text-tinder-blue"
        >
          {{ paper.note_count }} 笔记
        </span>
        <!-- Process status badge -->
        <span
          v-if="paper.process_status && paper.process_status !== 'none' && paper.process_status !== 'completed'"
          class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          :class="{
            'bg-tinder-blue/12 text-tinder-blue': paper.process_status === 'processing',
            'bg-tinder-gold/15 text-tinder-gold': paper.process_status === 'pending',
            'bg-tinder-pink/15 text-tinder-pink': paper.process_status === 'failed',
          }"
        >
          {{ paper.process_status === 'processing' ? '处理中' : paper.process_status === 'pending' ? '等待中' : '失败' }}
        </span>
      </div>
    </div>

    <!-- Right arrow (hidden in batch mode) -->
    <svg v-if="!batchMode" class="shrink-0 text-text-muted mt-1" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  </div>
</template>
