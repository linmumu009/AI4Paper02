<script setup lang="ts">
/**
 * EngagementPill — Compact Navbar pill showing progress (X/3) + streak days.
 * Clean, low-information-density redesign of the old EngagementProgressBar pill.
 *
 * Emits 'toggle' when clicked, so the parent (EngagementProgressBar or Navbar) can
 * control whether the panel is shown.
 */
import { computed, ref, watch } from 'vue'
import type { TaskItem } from '../../composables/useEngagement'

const props = defineProps<{
  taskItems: TaskItem[]
  streakCurrent: number
  allDone: boolean
  hasNewRewards: boolean
  activeRewardCount: number
  loading?: boolean
  loadError?: boolean
  isOpen: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()

// Brief pulse animation when pill enters "all done" state
const celebrating = ref(false)
watch(() => props.allDone, (isDone) => {
  if (isDone) {
    celebrating.value = true
    setTimeout(() => { celebrating.value = false }, 1200)
  }
})

// Count how many tasks are done
const doneCnt = computed(() => props.taskItems.filter(t => t.done).length)
const totalCnt = computed(() => props.taskItems.length)

// Pill appearance
const pillClass = computed(() => {
  if (props.loadError) return 'border-tinder-pink/40 text-tinder-pink'
  if (props.allDone) return 'border-tinder-gold/50 bg-tinder-gold/8 text-tinder-gold'
  if (doneCnt.value > 0) return 'border-tinder-blue/30 text-text-secondary'
  return 'border-border text-text-secondary'
})
</script>

<template>
  <!-- Error retry pill -->
  <button
    v-if="loadError && !loading"
    class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-bg-card/90 border border-tinder-pink/40 text-[11px] text-tinder-pink backdrop-blur-sm whitespace-nowrap select-none cursor-pointer hover:bg-bg-elevated/90 transition-colors"
    @click.stop="emit('toggle')"
  >
    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span>加载失败</span>
  </button>

  <!-- Normal pill -->
  <button
    v-else
    class="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-bg-card/90 border backdrop-blur-sm whitespace-nowrap select-none cursor-pointer transition-all duration-300"
    :class="[
      pillClass,
      loading ? 'opacity-50 pointer-events-none' : 'hover:bg-bg-elevated/90',
      celebrating ? 'ring-2 ring-tinder-gold/30 scale-105' : '',
    ]"
    @click.stop="emit('toggle')"
  >
    <!-- Progress: X/3 -->
    <span class="text-[11px] font-semibold tabular-nums">
      <template v-if="allDone">✓ 今日完成</template>
      <template v-else>{{ doneCnt }}/{{ totalCnt }}</template>
    </span>

    <!-- Mini task dots (3 dots for quick visual scan) -->
    <span v-if="!allDone" class="flex items-center gap-0.5 ml-0.5">
      <span
        v-for="item in taskItems"
        :key="item.key"
        class="inline-block w-1.5 h-1.5 rounded-full transition-colors"
        :class="item.done ? 'bg-tinder-gold' : 'bg-border'"
      />
    </span>

    <!-- Divider -->
    <span class="text-text-muted/40 text-[10px] mx-0.5">|</span>

    <!-- Streak: 🔥 X天 -->
    <span class="text-[11px] font-medium tabular-nums" :class="allDone ? 'text-tinder-gold' : 'text-text-muted'">
      {{ allDone ? '🔥' : '' }}{{ streakCurrent }}天
    </span>

    <!-- New reward amber dot -->
    <span
      v-if="hasNewRewards"
      class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 animate-pulse"
    />

    <!-- Active reward count badge -->
    <span
      v-else-if="activeRewardCount > 0"
      class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-tinder-gold text-white text-[9px] font-bold shrink-0"
    >{{ activeRewardCount }}</span>

    <!-- Chevron -->
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="w-2.5 h-2.5 text-text-muted transition-transform duration-200"
      :class="isOpen ? 'rotate-180' : ''"
      viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
      stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="18 15 12 9 6 15" />
    </svg>
  </button>
</template>
