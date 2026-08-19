<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PaperSummary, SummaryDensity } from '../types/paper'
import { openExternal } from '../utils/openExternal'
import { useEntitlements } from '../composables/useEntitlements'
import { useSummaryDensity } from '../composables/useSummaryDensity'
import PaperCardShareMenu from './PaperCardShareMenu.vue'
import SummaryDensityToggle from './SummaryDensityToggle.vue'
import { fetchPaperDetail, nudgePaper } from '../api/index'

const props = defineProps<{
  paper: PaperSummary
  animClass?: string
  source?: 'recommendation' | 'user_upload'
  recDate?: string
}>()

const emit = defineEmits<{
  (e: 'nudge', direction: 'more' | 'less'): void
}>()

async function onNudge(direction: 'more' | 'less') {
  try {
    await nudgePaper({
      paper_id: props.paper.paper_id,
      direction,
      categories: props.paper.categories || [],
      institution_tier: props.paper.institution_tier || 4,
    })
    emit('nudge', direction)
  } catch {
    // fail silently — preference nudge is non-critical
  }
}

const cardRootEl = ref<HTMLElement | null>(null)
const { tier } = useEntitlements()
const { density: summaryDensity, setDensity } = useSummaryDensity('concise')
const detailedPaper = ref<PaperSummary | null>(null)
const detailedLoading = ref(false)
const detailedUnavailable = ref(props.paper.has_detailed_summary === false)
const summaryVersionMessage = ref('')
let detailRequestToken = 0

const detailedAvailable = computed(() =>
  props.paper.has_detailed_summary !== false && !detailedUnavailable.value,
)
const activeSummaryDensity = computed<SummaryDensity>(() =>
  summaryDensity.value === 'detailed' && detailedPaper.value ? 'detailed' : 'concise',
)
const displayPaper = computed(() =>
  activeSummaryDensity.value === 'detailed' && detailedPaper.value
    ? detailedPaper.value
    : props.paper,
)

async function loadDetailedSummary(activateAfterLoad: boolean) {
  if (detailedPaper.value) {
    if (activateAfterLoad) setDensity('detailed')
    return
  }
  if (!detailedAvailable.value || detailedLoading.value) return

  const paperId = props.paper.paper_id
  const requestToken = ++detailRequestToken
  detailedLoading.value = true
  summaryVersionMessage.value = ''
  try {
    const detail = await fetchPaperDetail(paperId)
    if (requestToken !== detailRequestToken || props.paper.paper_id !== paperId) return
    const detailed = detail.summary_variants?.detailed
    if (!detailed) {
      detailedUnavailable.value = true
      summaryVersionMessage.value = '这篇论文暂时只有精简版'
      return
    }
    detailedPaper.value = { ...props.paper, ...detailed }
    if (activateAfterLoad) setDensity('detailed')
  } catch {
    if (requestToken === detailRequestToken) {
      summaryVersionMessage.value = '详细版加载失败，可点击重试'
    }
  } finally {
    if (requestToken === detailRequestToken) detailedLoading.value = false
  }
}

function selectSummaryDensity(value: SummaryDensity) {
  if (value === 'concise') {
    summaryVersionMessage.value = ''
    setDensity('concise')
    return
  }
  void loadDetailedSummary(true)
}

watch(
  summaryDensity,
  value => {
    if (value === 'detailed') void loadDetailedSummary(false)
  },
  { immediate: true },
)

watch(
  () => props.paper.paper_id,
  () => {
    detailRequestToken += 1
    detailedPaper.value = null
    detailedLoading.value = false
    detailedUnavailable.value = props.paper.has_detailed_summary === false
    summaryVersionMessage.value = ''
    if (summaryDensity.value === 'detailed') void loadDetailedSummary(false)
  },
)

function buildCardPlainText(): string {
  const p = props.paper
  const lines: string[] = []

  if (p.institution) lines.push(p.institution)
  if (p.short_title) lines.push(p.short_title)
  if (p['📖标题']) lines.push(p['📖标题'])
  if (p['🌐来源']) lines.push(p['🌐来源'])
  if (p.authors?.length) lines.push(formatAuthors(p.authors))
  if (p['推荐理由']) lines.push(`推荐理由：${p['推荐理由']}`)

  if (p['🛎️文章简介']) {
    lines.push('')
    lines.push('文章简介')
    if (p['🛎️文章简介']['🔸研究问题'])
      lines.push(`研究问题：${p['🛎️文章简介']['🔸研究问题']}`)
    if (p['🛎️文章简介']['🔸主要贡献'])
      lines.push(`主要贡献：${p['🛎️文章简介']['🔸主要贡献']}`)
  }

  if (p['📝重点思路']?.length) {
    lines.push('')
    lines.push('重点思路')
    p['📝重点思路'].forEach((item, i) => {
      lines.push(`${i + 1}. ${cleanBullet(item)}`)
    })
  }

  if (p['🔎分析总结']?.length) {
    lines.push('')
    lines.push('分析总结')
    p['🔎分析总结'].forEach(item => {
      lines.push(`- ${cleanBullet(item)}`)
    })
  }

  if (p['💡个人观点']) {
    lines.push('')
    lines.push(`个人观点：${p['💡个人观点']}`)
  }

  if (p['一句话记忆版']) {
    lines.push('')
    lines.push(p['一句话记忆版'])
  }

  return lines.join('\n')
}

function formatAuthors(authors: string[] | undefined): string {
  if (!authors || authors.length === 0) return ''
  const clean = authors.slice(0, 3).map(a => {
    // Strip email/affiliation in brackets if present
    return a.replace(/\s*\(.*?\)\s*/g, '').trim()
  })
  if (authors.length <= 2) return clean.join(', ')
  return `${clean[0]}, ${clean[1]}${authors.length > 2 ? ' et al.' : ''}`
}

function mainCategory(categories: string[] | undefined): string {
  if (!categories || categories.length === 0) return ''
  return categories[0]
}

function openArxivPage() {
  openExternal(`https://arxiv.org/abs/${props.paper.paper_id}`)
}

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

const firstImage = computed(() => displayPaper.value.images?.[0] ?? null)

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
    ref="cardRootEl"
    class="card-bg relative w-full h-full rounded-2xl overflow-hidden flex flex-col"
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

      <div class="flex items-center justify-between gap-3">
        <SummaryDensityToggle
          compact
          :model-value="activeSummaryDensity"
          :detailed-available="detailedAvailable"
          :loading="detailedLoading"
          @update:model-value="selectSummaryDensity"
        />
        <span
          v-if="summaryVersionMessage"
          class="text-[10px] leading-snug text-text-muted text-right"
          role="status"
        >{{ summaryVersionMessage }}</span>
        <span
          v-else-if="activeSummaryDensity === 'detailed'"
          class="text-[10px] leading-snug text-text-muted text-right"
        >分享仍使用精简版</span>
      </div>

      <!-- === 标题区 === -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">
          {{ displayPaper.short_title }}
        </h2>
        <p class="text-sm card-text mt-1">
          📖 {{ displayPaper['📖标题'] }}
        </p>
        <p class="text-xs text-text-muted mt-1 font-mono">
          🌐 {{ displayPaper['🌐来源'] }}
        </p>
        <!-- 作者信息 -->
        <p v-if="displayPaper.authors && displayPaper.authors.length" class="text-xs text-text-muted mt-1 truncate">
          👤 {{ formatAuthors(displayPaper.authors) }}
        </p>
        <!-- 推荐理由（新格式） -->
        <p v-if="displayPaper['推荐理由']" class="text-xs mt-2 text-tinder-blue leading-relaxed">
          <span class="font-semibold">推荐理由：</span>{{ displayPaper['推荐理由'] }}
        </p>
        <!-- 个性化推荐解释 + 轻量纠偏按钮 -->
        <div v-if="paper.why_recommended || paper.is_exploration" class="flex items-center gap-2 mt-2 flex-wrap">
          <span
            v-if="paper.is_exploration"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 border border-violet-300/40 shrink-0"
          >探索</span>
          <p v-if="paper.why_recommended" class="text-[11px] text-text-muted leading-relaxed flex-1 min-w-0">
            {{ paper.why_recommended }}
          </p>
          <div v-if="source === 'recommendation'" class="flex items-center gap-1 shrink-0">
            <button
              class="preference-nudge-btn preference-nudge-btn--less"
              title="减少此类推荐"
              aria-label="减少此类推荐"
              @click.stop="onNudge('less')"
            >👎</button>
            <button
              class="preference-nudge-btn preference-nudge-btn--more"
              title="多看此类论文"
              aria-label="多看此类论文"
              @click.stop="onNudge('more')"
            >👍</button>
          </div>
        </div>
      </div>

      <div
        v-if="firstImage"
        class="rounded-xl overflow-hidden border border-border bg-bg-elevated"
      >
        <img
          :src="firstImage.url"
          :alt="firstImage.caption || firstImage.filename"
          loading="lazy"
          class="w-full h-32 object-contain bg-bg-card"
        />
        <div class="px-3 py-1.5 border-t border-border flex items-center justify-between gap-2">
          <span class="text-[11px] text-text-muted">图表预览</span>
          <span class="text-[11px] text-text-muted">{{ displayPaper.image_count || 1 }} 张图</span>
        </div>
      </div>

      <!-- === 🛎️文章简介 === -->
      <div class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🛎️ 文章简介</h3>
        <div class="text-sm card-text space-y-1">
          <p v-if="displayPaper['🛎️文章简介']?.['🔸研究问题']">
            <span class="text-tinder-pink font-medium">研究问题：</span>{{ displayPaper['🛎️文章简介']['🔸研究问题'] }}
          </p>
          <p v-if="displayPaper['🛎️文章简介']?.['🔸主要贡献']">
            <span class="text-tinder-pink font-medium">主要贡献：</span>{{ displayPaper['🛎️文章简介']['🔸主要贡献'] }}
          </p>
        </div>
      </div>

      <!-- === 📝重点思路 === -->
      <div v-if="displayPaper['📝重点思路']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📝 重点思路</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in displayPaper['📝重点思路']"
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
      <div v-if="displayPaper['🔎分析总结']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🔎 分析总结</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in displayPaper['🔎分析总结']"
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
      <div v-if="displayPaper['💡个人观点']" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">💡 个人观点</h3>
        <p class="text-sm card-text italic">
          {{ displayPaper['💡个人观点'] }}
        </p>
      </div>

      <!-- === 一句话记忆版（新格式） === -->
      <div v-if="displayPaper['一句话记忆版']" class="text-xs text-text-muted italic leading-relaxed px-2 py-1.5 rounded bg-bg-elevated border border-border">
        <span class="not-italic font-semibold">💡 </span>{{ displayPaper['一句话记忆版'] }}
      </div>

      <!-- === Footer: rec date + quick actions === -->
      <div class="flex items-center justify-between pt-2 border-t border-border select-none">
        <span class="text-xs text-text-muted font-mono">
          {{ recDate || '' }}
        </span>
        <div class="flex items-center gap-2">
          <span class="text-xs text-text-muted">
            arXiv · {{ paper.image_count || 0 }} 张图
          </span>
          <!-- Quick action: share menu -->
          <PaperCardShareMenu
            :paper="paper"
            :card-ref="cardRootEl"
            :tier="tier"
            :plain-text="buildCardPlainText()"
          />
          <!-- Quick action: open arXiv page -->
          <button
            class="quick-action-btn"
            title="在 arXiv 查看原文"
            aria-label="在 arXiv 查看原文（新窗口）"
            @click.stop="openArxivPage"
          >
            ↗
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* Card background — uses theme variable */
.card-bg {
  background: var(--color-bg-card);
  will-change: transform;
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
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  touch-action: pan-y;
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

/* Quick-action icon buttons in card footer */
.quick-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.quick-action-btn:hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

/* Preference nudge micro-buttons */
.preference-nudge-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--color-border-light);
  cursor: pointer;
  opacity: 0.55;
  transition: opacity 0.15s, background 0.15s;
}
.preference-nudge-btn:hover {
  opacity: 1;
  background: var(--color-bg-elevated);
}
</style>
