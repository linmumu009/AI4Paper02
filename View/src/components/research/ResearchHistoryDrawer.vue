<script setup lang="ts">
import type { ResearchSession } from '../../types/paper'
import archiveIcon from '../../assets/heroicons/archive-box.svg'
import closeIcon from '../../assets/heroicons/x-mark.svg'

const props = defineProps<{
  open: boolean
  sessions: ResearchSession[]
  loading: boolean
  viewedSessionId?: number | null
  isRunning: boolean
}>()

const emit = defineEmits<{
  close: []
  refresh: []
  view: [id: number]
  delete: [id: number]
}>()

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

async function handleDelete(e: MouseEvent, id: number) {
  e.stopPropagation()
  if (confirm('确认删除这条研究记录？删除后无法恢复。')) {
    emit('delete', id)
  }
}
</script>

<template>
  <!-- Backdrop -->
  <Transition name="backdrop-fade">
    <button
      v-if="open"
      type="button"
      aria-label="关闭研究历史遮罩"
      class="absolute inset-0 border-0 bg-bg/60 backdrop-blur-sm z-30"
      @click="emit('close')"
    />
  </Transition>

  <!-- Drawer -->
  <Transition name="drawer-slide">
    <div
      v-if="open"
      class="absolute right-0 top-0 bottom-0 w-[320px] max-w-[90vw] bg-bg-sidebar border-l border-border flex flex-col z-40 shadow-2xl"
    >
      <!-- Drawer header -->
      <div class="flex items-center justify-between px-4 py-3.5 border-b border-border shrink-0">
        <div class="flex items-center gap-2">
          <img :src="archiveIcon" alt="" class="history-icon w-[15px] h-[15px]">
          <span class="text-sm font-semibold text-text-primary">研究历史</span>
        </div>
        <div class="flex items-center gap-1">
          <button
            class="text-xs text-text-muted hover:text-accent-primary transition-colors px-2 py-1 rounded-lg hover:bg-bg-elevated"
            @click="emit('refresh')"
          >刷新</button>
          <button
            type="button"
            aria-label="关闭研究历史"
            class="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            @click="emit('close')"
          >
            <img :src="closeIcon" alt="" class="history-icon w-[15px] h-[15px]">
          </button>
        </div>
      </div>

      <!-- Session list -->
      <div class="flex-1 overflow-y-auto">
        <div v-if="loading" class="flex items-center justify-center gap-2 py-12 text-sm text-text-muted">
          <img :src="archiveIcon" alt="" class="history-icon animate-spin w-4 h-4">
          加载中…
        </div>

        <div v-else-if="sessions.length === 0" class="flex flex-col items-center justify-center py-12 text-text-muted">
          <img :src="archiveIcon" alt="" class="history-icon w-7 h-7 mb-3 opacity-30">
          <p class="text-sm">暂无历史记录</p>
        </div>

        <div v-else class="divide-y divide-border/40 py-1">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="flex items-start gap-3 px-4 py-3 hover:bg-bg-elevated/50 transition-colors group cursor-pointer"
            :class="viewedSessionId === s.id ? 'bg-accent-primary/6 border-l-2 border-l-accent-primary' : 'border-l-2 border-l-transparent'"
            :title="isRunning ? '研究进行中，无法查看历史' : '点击查看此研究结果'"
            @click="!isRunning && emit('view', s.id)"
          >
            <!-- Status dot -->
            <div class="mt-1.5 shrink-0">
              <div
                class="w-2 h-2 rounded-full"
                :class="[
                  s.status === 'done' ? 'bg-green-500' :
                  s.status === 'error' ? 'bg-red-400' :
                  s.status === 'running' ? 'bg-accent-primary animate-pulse' :
                  'bg-border'
                ]"
              />
            </div>

            <div class="flex-1 min-w-0">
              <p class="text-xs font-medium text-text-primary truncate" :title="s.question">{{ s.question }}</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-[10px]" :class="statusClass(s.status)">{{ statusLabel(s.status) }}</span>
                <span class="text-[10px] text-text-muted">{{ formatTime(s.created_at) }}</span>
                <span class="text-[10px] text-text-muted">{{ s.paper_ids?.length ?? 0 }} 篇</span>
              </div>
              <div v-if="viewedSessionId === s.id" class="mt-1">
                <span class="text-[10px] text-accent-primary font-medium">当前查看</span>
              </div>
            </div>

            <!-- Delete button -->
            <button
              class="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-text-muted hover:text-red-400 p-1 rounded-lg hover:bg-red-400/10"
              title="删除此记录"
              @click="handleDelete($event, s.id)"
            >
              <img :src="closeIcon" alt="" class="history-icon w-[13px] h-[13px]">
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.backdrop-fade-enter-active,
.backdrop-fade-leave-active { transition: opacity 0.2s ease; }
.backdrop-fade-enter-from,
.backdrop-fade-leave-to { opacity: 0; }

.drawer-slide-enter-active,
.drawer-slide-leave-active { transition: transform 0.25s ease; }
.drawer-slide-enter-from,
.drawer-slide-leave-to { transform: translateX(100%); }
:global(.dark) .history-icon { filter: invert(1); }
</style>
