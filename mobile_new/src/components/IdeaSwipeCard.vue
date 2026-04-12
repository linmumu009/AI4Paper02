<script setup lang="ts">
import { ref, computed } from 'vue'
import type { IdeaCandidate } from '@shared/types/idea'

const props = defineProps<{
  candidate: IdeaCandidate
}>()

const emit = defineEmits<{
  (e: 'swipe-left'): void
  (e: 'swipe-right'): void
  (e: 'swipe-up'): void
}>()

const startX = ref(0)
const startY = ref(0)
const deltaX = ref(0)
const deltaY = ref(0)
const isDragging = ref(false)
const flyAway = ref<'' | 'left' | 'right' | 'up'>('')

const SWIPE_THRESHOLD = 80
const SWIPE_UP_THRESHOLD = 100

const cardStyle = computed(() => {
  if (flyAway.value) return {}
  if (!isDragging.value) return { transform: 'translateX(0) rotate(0deg)', transition: 'transform 0.3s ease' }
  const rotate = deltaX.value * 0.06
  return {
    transform: `translateX(${deltaX.value}px) translateY(${Math.min(deltaY.value, 0)}px) rotate(${rotate}deg)`,
    transition: 'none',
  }
})

const likeOpacity = computed(() => {
  if (!isDragging.value || deltaX.value <= 0) return 0
  return Math.min(deltaX.value / SWIPE_THRESHOLD, 1)
})

const nopeOpacity = computed(() => {
  if (!isDragging.value || deltaX.value >= 0) return 0
  return Math.min(Math.abs(deltaX.value) / SWIPE_THRESHOLD, 1)
})

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  startX.value = touch.clientX
  startY.value = touch.clientY
  deltaX.value = 0
  deltaY.value = 0
  isDragging.value = true
}

function onTouchMove(e: TouchEvent) {
  if (!isDragging.value) return
  const touch = e.touches[0]
  deltaX.value = touch.clientX - startX.value
  deltaY.value = touch.clientY - startY.value
  if (Math.abs(deltaX.value) > 10 || deltaY.value < -10) {
    e.preventDefault()
  }
}

function onTouchEnd() {
  if (!isDragging.value) return
  isDragging.value = false
  if (deltaX.value > SWIPE_THRESHOLD) {
    flyAway.value = 'right'
    setTimeout(() => emit('swipe-right'), 350)
  } else if (deltaX.value < -SWIPE_THRESHOLD) {
    flyAway.value = 'left'
    setTimeout(() => emit('swipe-left'), 350)
  } else if (deltaY.value < -SWIPE_UP_THRESHOLD) {
    flyAway.value = 'up'
    setTimeout(() => emit('swipe-up'), 350)
  } else {
    deltaX.value = 0
    deltaY.value = 0
  }
}

const overallScore = computed(() => props.candidate.scores?.overall ?? null)

const scoreClass = computed(() => {
  const v = overallScore.value
  if (v === null) return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
  if (v >= 8) return { border: 'border-tag-score-high', text: 'text-tag-score-high' }
  if (v >= 6) return { border: 'border-tag-score-mid', text: 'text-tag-score-mid' }
  return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
})

const strategyLabel: Record<string, string> = {
  transfer: '迁移', migration: '迁移', stitch: '缝合', stitching: '缝合',
  counterfactual: '反事实', patch: '修补', patching: '修补',
  resource_constrained: '资源约束', resource_constraint: '资源约束',
}
</script>

<template>
  <div
    class="absolute inset-0 bg-bg-card select-none flex flex-col overflow-hidden"
    :class="flyAway === 'left' ? 'card-swipe-left' : flyAway === 'right' ? 'card-swipe-right' : flyAway === 'up' ? 'card-swipe-up' : (isDragging ? '' : 'card-enter')"
    :style="cardStyle"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend.passive="onTouchEnd"
  >
    <!-- Top gradient accent -->
    <div class="h-1 shrink-0 bg-gradient-to-r from-[#fd267a] to-[#ff6036]" />

    <!-- LIKE overlay -->
    <div
      class="absolute top-10 left-5 z-30 px-4 py-1.5 rounded-xl border-[3px] border-tinder-green text-tinder-green text-xl font-extrabold rotate-[-14deg] pointer-events-none"
      :style="{ opacity: likeOpacity }"
    >
      感兴趣
    </div>

    <!-- NOPE overlay -->
    <div
      class="absolute top-10 right-5 z-30 px-4 py-1.5 rounded-xl border-[3px] border-tinder-pink text-tinder-pink text-xl font-extrabold rotate-[14deg] pointer-events-none"
      :style="{ opacity: nopeOpacity }"
    >
      跳过
    </div>

    <!-- Card content -->
    <!-- pb-16 accounts for the overlaid ActionBar gradient at the bottom -->
    <div class="flex-1 flex flex-col px-5 pt-5 pb-16 z-10 overflow-hidden">

      <!-- Row 1: strategy badge + score -->
      <div class="flex items-center justify-between gap-2 mb-3">
        <span v-if="candidate.strategy" class="strategy-badge shrink-0">
          {{ strategyLabel[candidate.strategy] || candidate.strategy }}
        </span>
        <span v-else class="inline-block px-3 py-1 rounded-full bg-tinder-purple/15 text-tinder-purple text-xs font-medium">灵感</span>
        <div
          v-if="overallScore !== null"
          class="shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-[11px] font-bold border-2"
          :class="scoreClass.border + ' ' + scoreClass.text"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ overallScore.toFixed(1) }}
        </div>
      </div>

      <!-- Row 2: title — large and prominent -->
      <h2 class="text-2xl font-bold text-text-primary leading-tight mb-4 line-clamp-3">
        {{ candidate.title }}
      </h2>

      <!-- Row 3: goal -->
      <div v-if="candidate.goal" class="flex-1 min-h-0">
        <p class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">研究目标</p>
        <p class="text-sm text-text-secondary leading-relaxed line-clamp-4">{{ candidate.goal }}</p>
      </div>

      <!-- Row 4: tags -->
      <div v-if="candidate.tags?.length" class="flex flex-wrap gap-1.5 mt-3">
        <span
          v-for="tag in candidate.tags.slice(0, 4)"
          :key="tag"
          class="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted"
        >{{ tag }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strategy-badge {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 300;
  letter-spacing: 0.06em;
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  font-style: italic;
  color: #fff;
  background: linear-gradient(135deg, var(--color-gradient-start) 0%, var(--color-gradient-end) 100%);
}
</style>
