<script setup lang="ts">
/**
 * StreakHeroCard — Hero section for the achievements page.
 * Shows current streak, longest streak, SVG arc progress ring to next milestone,
 * and a motivational goal text.
 */
import { computed } from 'vue'
import { MILESTONE_REWARD_PREVIEW } from '../../composables/useEngagement'

const props = defineProps<{
  currentStreak: number
  longestStreak: number
  nextMilestoneDay: number | null | undefined
}>()

// Circular progress ring: progress toward next milestone
const RING_R = 40
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R

const arcFraction = computed(() => {
  if (!props.nextMilestoneDay) return 1
  // Previous milestone (or 0 if first)
  const MILESTONES = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]
  const nextIdx = MILESTONES.indexOf(props.nextMilestoneDay)
  const prevMilestone = nextIdx > 0 ? MILESTONES[nextIdx - 1] : 0
  const range = props.nextMilestoneDay - prevMilestone
  const done = Math.max(0, props.currentStreak - prevMilestone)
  return Math.min(1, done / range)
})

const dashOffset = computed(() =>
  RING_CIRCUMFERENCE * (1 - arcFraction.value)
)

const nextRewardPreview = computed(() => {
  if (!props.nextMilestoneDay) return null
  return MILESTONE_REWARD_PREVIEW[props.nextMilestoneDay] ?? null
})

const daysUntilNext = computed(() => {
  if (!props.nextMilestoneDay) return 0
  return Math.max(0, props.nextMilestoneDay - props.currentStreak)
})

const arcColor = computed(() => {
  if (props.currentStreak >= 14) return '#a855f7' // purple for high streaks
  if (props.currentStreak >= 7)  return '#f59e0b' // gold
  if (props.currentStreak >= 3)  return '#f5b731' // gold (warm)
  return '#ff8c5a' // coral — matches brand gradient
})
</script>

<template>
  <div class="rounded-2xl border border-border bg-bg-card p-5 flex flex-col sm:flex-row items-center gap-5">

    <!-- Ring progress -->
    <div class="shrink-0 flex flex-col items-center gap-1">
      <div class="relative w-24 h-24">
        <svg class="w-24 h-24 -rotate-90" viewBox="0 0 96 96">
          <!-- Track -->
          <circle
            cx="48" cy="48" :r="RING_R"
            fill="none" stroke="var(--color-bg-elevated)" stroke-width="7"
          />
          <!-- Progress arc -->
          <circle
            cx="48" cy="48" :r="RING_R"
            fill="none" :stroke="arcColor" stroke-width="7"
            stroke-linecap="round"
            :stroke-dasharray="RING_CIRCUMFERENCE"
            :stroke-dashoffset="dashOffset"
            class="transition-all duration-700"
          />
        </svg>
        <!-- Center text -->
        <div class="absolute inset-0 flex flex-col items-center justify-center">
          <span class="text-2xl font-bold text-text-primary leading-none">{{ currentStreak }}</span>
          <span class="text-[10px] text-text-muted mt-0.5">天</span>
        </div>
      </div>
      <p class="text-[11px] text-text-muted">当前连续研究</p>
    </div>

    <!-- Stats + goal text -->
    <div class="flex-1 min-w-0">
      <!-- Longest streak -->
      <div class="flex items-center gap-2 mb-3">
        <div class="rounded-lg border border-border bg-bg-elevated px-3 py-2 flex items-center gap-2">
          <span class="text-base">🏆</span>
          <div>
            <p class="text-[10px] text-text-muted leading-none">最长记录</p>
            <p class="text-lg font-bold text-tinder-gold leading-tight">{{ longestStreak }}<span class="text-xs font-normal text-text-muted ml-0.5">天</span></p>
          </div>
        </div>
      </div>

      <!-- Goal: next milestone -->
      <template v-if="nextMilestoneDay && nextRewardPreview">
        <div class="rounded-xl border border-border bg-bg-elevated/60 px-3 py-2.5">
          <p class="text-[10px] text-text-muted mb-1">
            <span v-if="daysUntilNext > 0">再坚持 <strong class="text-text-primary">{{ daysUntilNext }}</strong> 天 → 第 {{ nextMilestoneDay }} 天里程碑</span>
            <span v-else>🎉 今日完成可解锁第 {{ nextMilestoneDay }} 天里程碑！</span>
          </p>
          <div class="flex items-center gap-2">
            <span class="text-sm">{{ MILESTONE_REWARD_PREVIEW[nextMilestoneDay]?.code?.includes('badge') ? '🏆' : '🎁' }}</span>
            <div class="min-w-0">
              <p class="text-[11px] font-semibold text-text-primary truncate">{{ nextRewardPreview.name }}</p>
              <p class="text-[10px] text-text-muted leading-snug truncate">{{ nextRewardPreview.brief }}</p>
            </div>
          </div>
        </div>
      </template>
      <template v-else-if="currentStreak === 0">
        <div class="rounded-xl border border-border bg-bg-elevated/60 px-3 py-2.5">
          <p class="text-[11px] text-text-secondary leading-snug">
            今天完成<strong class="text-text-primary">浏览 · 收藏 · 分析</strong>三项任务，开始你的连续研究之旅！
          </p>
        </div>
      </template>
      <template v-else>
        <div class="rounded-xl border border-tinder-gold/20 bg-tinder-gold/6 px-3 py-2.5">
          <p class="text-[11px] font-semibold text-tinder-gold">🌟 所有里程碑已解锁！</p>
          <p class="text-[10px] text-text-muted mt-0.5">你是传奇研究者，继续保持！</p>
        </div>
      </template>
    </div>

  </div>
</template>
