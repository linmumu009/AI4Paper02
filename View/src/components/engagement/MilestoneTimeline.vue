<script setup lang="ts">
/**
 * MilestoneTimeline — Vertical timeline of streak milestones.
 * Replaces the old horizontal block grid with a narrative timeline.
 */
import { computed } from 'vue'
import { MILESTONE_REWARD_PREVIEW, rewardIcon } from '../../composables/useEngagement'

const props = defineProps<{
  currentStreak: number
  /** List of milestone days (e.g. [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]) */
  milestones: number[]
  /** Set of unlocked milestone days */
  unlockedDays: Set<number>
}>()

interface TimelineNode {
  day: number
  unlocked: boolean
  isCurrent: boolean  // the next milestone to unlock
  preview: { name: string; code: string; brief: string } | null
  icon: string
}

const nodes = computed<TimelineNode[]>(() =>
  props.milestones.map((day, idx) => {
    const unlocked = props.unlockedDays.has(day)
    const prevUnlocked = idx === 0 || props.unlockedDays.has(props.milestones[idx - 1])
    const isCurrent = !unlocked && prevUnlocked
    const preview = MILESTONE_REWARD_PREVIEW[day] ?? null
    const icon = rewardIcon(preview?.code ?? '', day)
    return { day, unlocked, isCurrent, preview, icon }
  })
)
</script>

<template>
  <div class="relative">
    <!-- Vertical connector line -->
    <div class="absolute left-5 top-4 bottom-4 w-px bg-border" />

    <div class="space-y-1">
      <div
        v-for="(node, idx) in nodes"
        :key="node.day"
        class="relative flex items-start gap-3 pl-0"
      >
        <!-- Node indicator -->
        <div class="relative z-10 shrink-0">
          <div
            class="w-10 h-10 rounded-full border-2 flex items-center justify-center text-base transition-all duration-300"
            :class="[
              node.unlocked
                ? 'bg-bg-card border-tinder-gold/60 shadow-sm'
                : node.isCurrent
                  ? 'bg-bg-card border-tinder-blue/60 animate-pulse'
                  : 'bg-bg-elevated border-border opacity-50',
            ]"
          >
            <template v-if="node.unlocked">
              {{ node.icon }}
            </template>
            <template v-else-if="node.isCurrent">
              <span class="text-tinder-blue text-sm font-bold">{{ node.day }}</span>
            </template>
            <template v-else>
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
            </template>
          </div>
        </div>

        <!-- Content -->
        <div
          class="flex-1 min-w-0 rounded-xl border p-3 mb-1 transition-all duration-200"
          :class="[
            node.unlocked
              ? 'border-tinder-gold/20 bg-tinder-gold/5'
              : node.isCurrent
                ? 'border-tinder-blue/25 bg-tinder-blue/5'
                : 'border-border bg-bg-elevated/30 opacity-60',
          ]"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5 flex-wrap mb-0.5">
                <span
                  class="text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none"
                  :class="node.unlocked
                    ? 'bg-tinder-gold/20 text-tinder-gold'
                    : node.isCurrent
                      ? 'bg-tinder-blue/20 text-tinder-blue'
                      : 'bg-bg-elevated text-text-muted'"
                >Day {{ node.day }}</span>
                <p class="text-xs font-semibold text-text-primary truncate">
                  {{ node.preview?.name ?? `第 ${node.day} 天里程碑` }}
                </p>
              </div>
              <p v-if="node.preview" class="text-[10px] text-text-muted leading-snug">{{ node.preview.brief }}</p>
              <p
                v-else-if="node.isCurrent"
                class="text-[10px] text-tinder-blue leading-snug"
              >再坚持 {{ node.day - currentStreak }} 天即可解锁</p>
            </div>
            <!-- Status icon -->
            <div class="shrink-0 mt-0.5">
              <svg
                v-if="node.unlocked"
                xmlns="http://www.w3.org/2000/svg"
                class="w-4 h-4 text-tinder-gold"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
