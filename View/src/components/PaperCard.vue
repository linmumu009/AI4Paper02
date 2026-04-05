<script setup lang="ts">
import { computed } from 'vue'
import type { PaperSummary } from '../types/paper'

const props = defineProps<{
  paper: PaperSummary
  animClass?: string
  source?: 'recommendation' | 'user_upload'
}>()

/* card background is set via CSS class, no dynamic gradient needed */

/** Remove leading emoji bullet (🔸) */
function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}

/**
 * 推荐卡片上始终有可展示的机构等级：API 未带 institution_tier 或旧数据时，
 * 用大机构标记回退为 T3，否则为 T4。
 */
const effectiveTier = computed(() => {
  const t = props.paper.institution_tier
  if (typeof t === 'number' && !Number.isNaN(t) && t >= 1 && t <= 4) {
    return t
  }
  return props.paper.is_large_institution ? 3 : 4
})

/** Return CSS class for institution badge based on tier */
function tierBadgeClass(tier: number): string {
  switch (tier) {
    case 1: return 'institution-badge institution-badge--t1'
    case 2: return 'institution-badge institution-badge--t2'
    case 3: return 'institution-badge institution-badge--t3'
    case 4: return 'institution-badge institution-badge--t4'
    default: return 'institution-badge institution-badge--t4'
  }
}

/** Return tier label text inside the pill */
function tierLabel(tier: number): string {
  switch (tier) {
    case 1: return 'T1'
    case 2: return 'T2'
    case 3: return 'T3'
    case 4: return 'T4'
    default: return 'T4'
  }
}
</script>

<template>
  <div
    class="card-bg relative w-full h-full rounded-2xl overflow-hidden select-none flex flex-col"
    :class="animClass"
  >
    <!-- Scrollable content area -->
    <div class="relative z-10 flex-1 overflow-y-auto px-5 pt-4 pb-5 space-y-4 scrollbar-thin card-body">

      <!-- === Header: institution + score === -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 flex-wrap">
          <span :class="tierBadgeClass(effectiveTier)">
            {{ paper.institution || '未知机构' }}
            <span class="tier-tag">{{ tierLabel(effectiveTier) }}</span>
          </span>
          <!-- Tier level label（T1–T4 均在推荐卡片上展示） -->
          <span
            v-if="effectiveTier === 1"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
          >T1 · 顶尖</span>
          <span
            v-else-if="effectiveTier === 2"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
          >T2 · 一流</span>
          <span
            v-else-if="effectiveTier === 3"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300"
          >T3 · 知名</span>
          <span
            v-else
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200"
          >T4 · 一般</span>
          <!-- Source badge -->
          <span
            v-if="source === 'user_upload'"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-600 border border-amber-500/30"
          >我的上传</span>
        </div>
        <div v-if="paper.relevance_score != null"
          class="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2"
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

      <!-- === 标题区 === -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">
          {{ paper.short_title }}
        </h2>
        <p class="text-sm card-text mt-1">
          📖 {{ paper['📖标题'] }}
        </p>
        <p class="text-xs text-text-muted mt-1 font-mono">
          🌐 {{ paper['🌐来源'] }}
        </p>
        <!-- 推荐理由（新格式） -->
        <p v-if="paper['推荐理由']" class="text-xs mt-2 text-tinder-blue leading-relaxed">
          <span class="font-semibold">推荐理由：</span>{{ paper['推荐理由'] }}
        </p>
      </div>

      <!-- === 🛎️文章简介 === -->
      <div class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🛎️ 文章简介</h3>
        <div class="text-sm card-text space-y-1">
          <p v-if="paper['🛎️文章简介']?.['🔸研究问题']">
            <span class="text-tinder-pink font-medium">研究问题：</span>{{ paper['🛎️文章简介']['🔸研究问题'] }}
          </p>
          <p v-if="paper['🛎️文章简介']?.['🔸主要贡献']">
            <span class="text-tinder-pink font-medium">主要贡献：</span>{{ paper['🛎️文章简介']['🔸主要贡献'] }}
          </p>
        </div>
      </div>

      <!-- === 📝重点思路 === -->
      <div v-if="paper['📝重点思路']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📝 重点思路</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in paper['📝重点思路']"
            :key="'m' + idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-5 h-5 rounded-full bg-tinder-blue/20 text-tinder-blue flex items-center justify-center text-[10px] font-bold mt-0.5">
              {{ idx + 1 }}
            </span>
            <p class="text-sm card-text">
              {{ cleanBullet(item) }}
            </p>
          </div>
        </div>
      </div>

      <!-- === 🔎分析总结 === -->
      <div v-if="paper['🔎分析总结']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🔎 分析总结</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in paper['🔎分析总结']"
            :key="'f' + idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-gold mt-1.5"></span>
            <p class="text-sm card-text">
              {{ cleanBullet(item) }}
            </p>
          </div>
        </div>
      </div>

      <!-- === 💡个人观点 === -->
      <div v-if="paper['💡个人观点']" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">💡 个人观点</h3>
        <p class="text-sm card-text italic">
          {{ paper['💡个人观点'] }}
        </p>
      </div>

      <!-- === 一句话记忆版（新格式） === -->
      <div v-if="paper['一句话记忆版']" class="text-xs text-text-muted italic leading-relaxed px-2 py-1.5 rounded bg-bg-elevated border border-border">
        <span class="not-italic font-semibold">💡 </span>{{ paper['一句话记忆版'] }}
      </div>

      <!-- === Footer: paper ID === -->
      <div class="flex items-center justify-between pt-2 border-t border-border">
        <span class="text-xs text-text-muted font-mono">
          {{ paper.paper_id }}
        </span>
        <span class="text-xs text-text-muted">
          arXiv · {{ paper.image_count || 0 }} 张图
        </span>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* Card background — uses theme variable */
.card-bg {
  background: var(--color-bg-card);
}

/* Prominent institution badge */
.institution-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 14px;
  border-radius: 9999px;
  font-size: 18px;
  font-weight: 300;
  letter-spacing: 0.06em;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", Georgia, serif;
  font-style: italic;
  color: #fff;
  background: linear-gradient(135deg, var(--color-gradient-start) 0%, var(--color-gradient-end) 100%);
}

/* T1: gold gradient — top-tier institutions */
.institution-badge--t1 {
  background: linear-gradient(135deg, #b8860b 0%, #f5c518 50%, #d4a017 100%);
  box-shadow: 0 2px 8px rgba(245, 197, 24, 0.35);
}

/* T2: silver-blue gradient — first-class institutions */
.institution-badge--t2 {
  background: linear-gradient(135deg, #4a6fa5 0%, #7bb3d3 50%, #5a82b8 100%);
  box-shadow: 0 2px 8px rgba(91, 143, 200, 0.3);
}

/* T3: bronze gradient — notable institutions */
.institution-badge--t3 {
  background: linear-gradient(135deg, #8b5e3c 0%, #c4956a 50%, #a0724f 100%);
  box-shadow: 0 2px 6px rgba(160, 114, 79, 0.25);
}

/* T4: slate gradient — 一般机构，与主题粉渐变区分 */
.institution-badge--t4 {
  background: linear-gradient(135deg, #52525b 0%, #71717a 45%, #64748b 100%);
  box-shadow: 0 1px 4px rgba(71, 85, 105, 0.25);
}

/* Tier tag pill inside the badge */
.tier-tag {
  display: inline-block;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.03em;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.28);
  line-height: 1.4;
  vertical-align: middle;
}

/* Body text: uses theme-aware secondary color */
.card-text {
  color: var(--color-text-secondary);
  line-height: 1.6;
}

/* Scrollable area inherits the same text defaults */
.card-body {
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.scrollbar-thin {
  scrollbar-width: thin;
  scrollbar-color: var(--color-border-light) transparent;
}
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: var(--color-border-light);
  border-radius: 2px;
}
</style>
