<script setup lang="ts">
import type { ResearchSession } from '../../types/paper'

const props = defineProps<{
  session: ResearchSession
  batchMode: boolean
  checked: boolean
  expanded: boolean
  renamingId: number | null
  renamingText: string
  indent: boolean
}>()

const emit = defineEmits<{
  open: []
  toggleCheck: []
  toggleExpand: []
  openMenu: [e: MouseEvent]
  'update:renamingText': [value: string]
  confirmRename: []
  cancelRename: []
}>()

function statusLabel(s: string) {
  return ({ running: '进行中', done: '已完成', error: '失败', pending: '待执行' } as Record<string, string>)[s] ?? s
}

function statusBgClass(s: string) {
  return ({
    done: 'bg-green-500',
    error: 'bg-red-400',
    running: 'bg-accent-primary',
    pending: 'bg-text-muted/40',
  } as Record<string, string>)[s] ?? 'bg-text-muted/40'
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}
</script>

<template>
  <div class="border-b border-border/30 last:border-b-0">
    <!-- Session row -->
    <div
      class="flex items-center gap-2 py-2 rounded-lg hover:bg-bg-hover transition-colors group cursor-pointer"
      :class="indent ? 'pl-6 pr-2' : 'px-2'"
      @click="batchMode ? emit('toggleCheck') : emit('open')"
    >
      <!-- Batch checkbox -->
      <div v-if="batchMode" class="shrink-0" @click.stop="emit('toggleCheck')">
        <div
          class="w-4 h-4 rounded border flex items-center justify-center transition-colors cursor-pointer"
          :class="checked
            ? 'bg-tinder-pink border-tinder-pink'
            : 'border-border bg-transparent hover:border-tinder-pink/50'"
        >
          <svg v-if="checked" class="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
      </div>

      <!-- Expand arrow (non-batch) -->
      <template v-if="!batchMode">
        <button
          v-if="(session.paper_ids?.length ?? 0) > 0"
          class="w-4 h-4 flex items-center justify-center text-[8px] text-text-muted bg-transparent border-none cursor-pointer shrink-0 transition-transform duration-150"
          :class="expanded ? 'rotate-90' : ''"
          @click.stop="emit('toggleExpand')"
        >▶</button>
        <div v-else class="w-4 shrink-0"></div>
      </template>

      <!-- Status circle -->
      <div
        class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
        :class="statusBgClass(session.status)"
      >
        <svg v-if="session.status === 'done'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else-if="session.status === 'error'" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
        <svg v-else class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
      </div>

      <!-- Text: inline rename input or normal display -->
      <div class="min-w-0 flex-1" @click="renamingId === session.id && $event.stopPropagation()">
        <template v-if="renamingId === session.id">
          <input
            :value="renamingText"
            class="w-full bg-bg-elevated border border-accent-primary/50 rounded px-1.5 py-0.5 text-xs text-text-primary focus:outline-none focus:border-accent-primary"
            @input="emit('update:renamingText', ($event.target as HTMLInputElement).value)"
            @keydown.enter.prevent="emit('confirmRename')"
            @keydown.escape.prevent="emit('cancelRename')"
            @blur="emit('confirmRename')"
            @click.stop
          />
        </template>
        <template v-else>
          <div class="text-xs font-medium text-text-primary truncate flex items-center gap-1">
            <span class="truncate">{{ session.question }}</span>
            <svg v-if="session.saved" class="w-3 h-3 shrink-0 text-amber-400" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </div>
          <div class="text-[10px] text-text-muted truncate">
            <span :class="session.status === 'done' ? 'text-green-500' : session.status === 'error' ? 'text-red-400' : 'text-accent-primary'">{{ statusLabel(session.status) }}</span>
            &nbsp;·&nbsp;{{ formatTime(session.created_at) }}&nbsp;·&nbsp;{{ session.paper_ids?.length ?? 0 }} 篇
          </div>
        </template>
      </div>

      <!-- ⋯ menu button (hidden in batch mode) -->
      <div v-if="!batchMode" class="relative shrink-0">
        <button
          class="w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
          @click.stop="emit('openMenu', $event)"
        >⋯</button>
      </div>
    </div>

    <!-- Expanded: paper IDs list -->
    <div v-if="!batchMode && expanded && (session.paper_ids?.length ?? 0) > 0" class="pb-1">
      <div
        v-for="pid in session.paper_ids"
        :key="pid"
        class="flex items-center gap-2 py-1.5 pr-2 rounded hover:bg-bg-hover transition-colors cursor-default"
        :class="indent ? 'pl-16' : 'pl-14'"
      >
        <svg class="w-3 h-3 shrink-0 text-text-muted/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        </svg>
        <span class="text-[10px] text-text-muted truncate">{{ pid }}</span>
      </div>
    </div>
  </div>
</template>
