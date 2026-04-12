<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PaperSummary } from '@shared/types/paper'

defineProps<{
  paper: PaperSummary
}>()

const emit = defineEmits<{
  (e: 'swipe-left'): void
  (e: 'swipe-right'): void
  (e: 'swipe-up'): void
  (e: 'ask-ai'): void
}>()

const scrollEl = ref<HTMLElement | null>(null)
const startX = ref(0)
const startY = ref(0)
const deltaX = ref(0)
const deltaY = ref(0)
const isDragging = ref(false)
const isVerticalScroll = ref(false)
const flyAway = ref<'' | 'left' | 'right' | 'up'>('')

const SWIPE_THRESHOLD = 80
const SWIPE_UP_THRESHOLD = 100

const cardStyle = computed(() => {
  if (flyAway.value) return {}
  if (!isDragging.value || isVerticalScroll.value) return { transform: 'translateX(0) rotate(0deg)', transition: 'transform 0.3s ease' }
  const rotate = deltaX.value * 0.06
  return {
    transform: `translateX(${deltaX.value}px) translateY(${Math.min(deltaY.value, 0)}px) rotate(${rotate}deg)`,
    transition: 'none',
  }
})

const likeOpacity = computed(() => {
  if (!isDragging.value || isVerticalScroll.value || deltaX.value <= 0) return 0
  return Math.min(deltaX.value / SWIPE_THRESHOLD, 1)
})

const nopeOpacity = computed(() => {
  if (!isDragging.value || isVerticalScroll.value || deltaX.value >= 0) return 0
  return Math.min(Math.abs(deltaX.value) / SWIPE_THRESHOLD, 1)
})

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  startX.value = touch.clientX
  startY.value = touch.clientY
  deltaX.value = 0
  deltaY.value = 0
  isDragging.value = true
  isVerticalScroll.value = false
}

function onTouchMove(e: TouchEvent) {
  if (!isDragging.value) return
  const touch = e.touches[0]
  const dx = touch.clientX - startX.value
  const dy = touch.clientY - startY.value

  // Lock direction on first meaningful movement
  if (!isVerticalScroll.value && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
    if (Math.abs(dy) > Math.abs(dx) * 1.2) {
      isVerticalScroll.value = true
    }
  }

  if (isVerticalScroll.value) {
    // Let the browser handle vertical scroll natively; do not update deltaX
    deltaY.value = dy
    return
  }

  deltaX.value = dx
  deltaY.value = dy

  // Prevent browser scroll only during horizontal swipe
  if (Math.abs(dx) > 10) {
    e.preventDefault()
  }
}

function onTouchEnd() {
  if (!isDragging.value) return
  isDragging.value = false

  if (isVerticalScroll.value) {
    isVerticalScroll.value = false
    deltaX.value = 0
    deltaY.value = 0
    return
  }

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

function tierBadgeClass(tier?: number): string {
  switch (tier) {
    case 1: return 'institution-badge institution-badge--t1'
    case 2: return 'institution-badge institution-badge--t2'
    case 3: return 'institution-badge institution-badge--t3'
    default: return 'institution-badge'
  }
}

function tierLabel(tier?: number): string {
  if (tier && tier <= 3) return `T${tier}`
  return ''
}

function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}
</script>

<template>
  <div
    class="absolute inset-0 bg-bg-card select-none flex flex-col overflow-hidden"
    :class="flyAway === 'left' ? 'card-swipe-left' : flyAway === 'right' ? 'card-swipe-right' : flyAway === 'up' ? 'card-swipe-up' : (isDragging && !isVerticalScroll ? '' : 'card-enter')"
    :style="cardStyle"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend.passive="onTouchEnd"
  >
    <!-- Top gradient accent -->
    <div class="h-1 shrink-0 bg-gradient-to-r from-[#fd267a] to-[#ff6036]" />

    <!-- LIKE overlay -->
    <div
      class="absolute top-10 left-5 z-30 px-4 py-1.5 rounded-xl border-[3px] border-tinder-green text-tinder-green text-2xl font-extrabold rotate-[-14deg] pointer-events-none"
      :style="{ opacity: likeOpacity }"
    >
      收藏
    </div>

    <!-- NOPE overlay -->
    <div
      class="absolute top-10 right-5 z-30 px-4 py-1.5 rounded-xl border-[3px] border-tinder-pink text-tinder-pink text-2xl font-extrabold rotate-[14deg] pointer-events-none"
      :style="{ opacity: nopeOpacity }"
    >
      跳过
    </div>

    <!-- Ask AI pill — tappable chip above the ActionBar gradient, non-swipe zone -->
    <button
      type="button"
      class="absolute bottom-24 right-4 z-20 flex items-center gap-1 px-3 py-1.5 rounded-full bg-tinder-purple/12 border border-tinder-purple/25 text-tinder-purple text-[12px] font-semibold active:bg-tinder-purple/25 transition-all select-none"
      @click.stop="emit('ask-ai')"
      @touchstart.stop
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      问 AI
    </button>

    <!-- Card content — scrollable rich layout -->
    <!-- pb-20 provides clearance for the overlaid ActionBar gradient at the bottom -->
    <div
      ref="scrollEl"
      class="flex-1 flex flex-col px-5 pt-4 pb-20 z-10 overflow-y-auto overscroll-contain"
    >

      <!-- Row 1: institution (compact) + score -->
      <div class="flex items-center justify-between gap-2 mb-3 shrink-0">
        <span :class="tierBadgeClass(paper.institution_tier)" class="max-w-[72%] text-sm">
          {{ paper.institution || '未知机构' }}
          <span v-if="tierLabel(paper.institution_tier)" class="tier-tag-mobile">{{ tierLabel(paper.institution_tier) }}</span>
        </span>
        <div
          v-if="paper.relevance_score != null"
          class="shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-[11px] font-bold border-2"
          :class="paper.relevance_score >= 0.7
            ? 'border-tag-score-high text-tag-score-high'
            : paper.relevance_score >= 0.4
              ? 'border-tag-score-mid text-tag-score-mid'
              : 'border-tag-score-low text-tag-score-low'"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ (paper.relevance_score * 100).toFixed(0) }}
        </div>
      </div>

      <!-- Row 2: main title — large, prominent -->
      <h2 class="text-xl font-bold text-text-primary leading-tight mb-3 shrink-0">
        {{ paper.short_title }}
      </h2>

      <!-- Row 3: recommendation reason -->
      <div
        v-if="paper['推荐理由']"
        class="px-3 py-2.5 rounded-xl bg-tinder-blue/8 border border-tinder-blue/20 mb-2.5 shrink-0"
      >
        <p class="text-[13px] text-text-primary leading-relaxed">
          <span class="font-semibold text-tinder-blue">推荐理由：</span>{{ paper['推荐理由'] }}
        </p>
      </div>

      <!-- Row 4: research question + contribution (both shown when available) -->
      <div
        v-if="paper['🛎️文章简介']?.['🔸研究问题'] || paper['🛎️文章简介']?.['🔸主要贡献']"
        class="flex flex-col gap-1.5 mb-2.5 shrink-0"
      >
        <p v-if="paper['🛎️文章简介']?.['🔸研究问题']" class="text-[13px] text-text-secondary leading-relaxed">
          <span class="text-tinder-pink font-medium">研究问题：</span>{{ paper['🛎️文章简介']['🔸研究问题'] }}
        </p>
        <p v-if="paper['🛎️文章简介']?.['🔸主要贡献']" class="text-[13px] text-text-secondary leading-relaxed">
          <span class="text-tinder-pink font-medium">主要贡献：</span>{{ paper['🛎️文章简介']['🔸主要贡献'] }}
        </p>
      </div>

      <!-- Fallback: abstract when no structured info at all -->
      <p
        v-else-if="!paper['推荐理由'] && paper.abstract"
        class="text-[13px] text-text-secondary leading-relaxed mb-2.5 shrink-0"
      >
        {{ paper.abstract }}
      </p>

      <!-- Row 5: 重点思路 -->
      <div v-if="paper['📝重点思路']?.length" class="mt-3 shrink-0">
        <h3 class="section-title mb-2">重点思路</h3>
        <div class="space-y-2">
          <div
            v-for="(item, idx) in paper['📝重点思路']"
            :key="'m' + idx"
            class="flex items-start gap-2.5"
          >
            <span class="shrink-0 w-5 h-5 rounded-full bg-tinder-blue/15 text-tinder-blue flex items-center justify-center text-[10px] font-bold mt-0.5">
              {{ idx + 1 }}
            </span>
            <p class="text-[13px] text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- Row 6: 分析总结 -->
      <div v-if="paper['🔎分析总结']?.length" class="mt-4 shrink-0">
        <h3 class="section-title mb-2">分析总结</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in paper['🔎分析总结']"
            :key="'f' + idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-gold mt-2" />
            <p class="text-[13px] text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- Row 7: 个人观点 + 一句话记忆版 -->
      <div v-if="paper['💡个人观点'] || paper['一句话记忆版']" class="mt-4 shrink-0">
        <p
          v-if="paper['💡个人观点']"
          class="text-[13px] text-text-secondary leading-relaxed italic mb-2"
        >
          <span class="not-italic font-semibold text-text-primary">个人观点：</span>{{ paper['💡个人观点'] }}
        </p>
        <p
          v-if="paper['一句话记忆版']"
          class="text-[12px] text-text-muted leading-relaxed italic"
        >
          <span class="not-italic font-semibold text-text-secondary">一句话记忆：</span>{{ paper['一句话记忆版'] }}
        </p>
      </div>

    </div>
  </div>
</template>
