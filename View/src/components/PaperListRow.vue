<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PaperSummary } from '../types/paper'
import { openExternal } from '../utils/openExternal'

const props = defineProps<{
  paper: PaperSummary
  index: number
  isActive: boolean
  isBookmarked: boolean
}>()

const emit = defineEmits<{
  click: []
}>()

const copiedId = ref(false)

function formatAuthors(authors: string[] | undefined): string {
  if (!authors || authors.length === 0) return ''
  const clean = authors.slice(0, 2).map(a => a.replace(/\s*\(.*?\)\s*/g, '').trim())
  if (authors.length <= 2) return clean.join(', ')
  return `${clean[0]}, ${clean[1]} et al.`
}

async function copyArxivId(e: MouseEvent) {
  e.stopPropagation()
  try {
    await navigator.clipboard.writeText(props.paper.paper_id)
    copiedId.value = true
    setTimeout(() => { copiedId.value = false }, 1500)
  } catch {
    // fallback: do nothing
  }
}

function openArxivPage(e: MouseEvent) {
  e.stopPropagation()
  openExternal(`https://arxiv.org/abs/${props.paper.paper_id}`)
}

const effectiveTier = computed(() => {
  const t = props.paper.institution_tier
  if (typeof t === 'number' && !Number.isNaN(t) && t >= 1 && t <= 4) return t
  return props.paper.is_large_institution ? 3 : 4
})

const tierLabel = computed(() => {
  switch (effectiveTier.value) {
    case 1: return 'T1 · 顶尖'
    case 2: return 'T2 · 一流'
    case 3: return 'T3 · 知名'
    default: return 'T4 · 一般'
  }
})

const authorsLine = computed(() => formatAuthors(props.paper.authors))

const hasEnglishTitle = computed(() =>
  props.paper['📖标题'] && props.paper['📖标题'] !== (props.paper.short_title || '')
)

const researchQuestion = computed(() => props.paper['🛎️文章简介']?.['🔸研究问题'] || '')
const mainContribution = computed(() => props.paper['🛎️文章简介']?.['🔸主要贡献'] || '')
const hasBrief = computed(() => !!(researchQuestion.value || mainContribution.value))

const insight = computed(() => props.paper['一句话记忆版'] || props.paper['💡个人观点'] || '')
const recommendReason = computed(() => props.paper['推荐理由'] || '')
const firstImage = computed(() => props.paper.images?.[0] ?? null)

const scoreClass = computed(() => {
  const s = props.paper.relevance_score
  if (s == null) return ''
  if (s >= 0.7) return 'score--high'
  if (s >= 0.4) return 'score--mid'
  return 'score--low'
})
</script>

<template>
  <div
    class="row-root relative cursor-pointer"
    :class="isActive ? 'row-root--active' : 'row-root--idle'"
    @click="emit('click')"
  >
    <!-- Active left accent bar -->
    <div v-if="isActive" class="accent-bar" />

    <!-- ── HEADER: index · tier pill · institution · categories · score ── -->
    <div class="row-header">
      <div class="row-header__left">
        <span class="row-index">{{ index + 1 }}</span>
        <span class="tier-pill" :class="`tier-pill--t${effectiveTier}`">T{{ effectiveTier }}</span>
        <span v-if="paper.institution" class="institution-name">{{ paper.institution }}</span>
        <span class="tier-label" :class="`tier-label--t${effectiveTier}`">{{ tierLabel }}</span>
      </div>
      <div class="row-header__right">
        <span v-if="paper.relevance_score != null" class="score" :class="scoreClass">
          {{ Math.round(paper.relevance_score * 100) }}
        </span>
      </div>
    </div>

    <!-- ── TITLE ZONE ── -->
    <div class="title-zone">
      <p class="title-zh">
        {{ paper.short_title || paper['📖标题'] || paper.paper_id }}
      </p>
      <p v-if="hasEnglishTitle" class="title-en">
        {{ paper['📖标题'] }}
      </p>
    </div>

    <!-- ── META LINE: source · authors · images ── -->
    <div class="meta-line">
      <span v-if="paper['🌐来源']" class="meta-item">{{ paper['🌐来源'] }}</span>
      <span v-if="authorsLine" class="meta-sep">·</span>
      <span v-if="authorsLine" class="meta-item">{{ authorsLine }}</span>
      <template v-if="paper.image_count && paper.image_count > 0">
        <span class="meta-sep">·</span>
        <span class="meta-item">{{ paper.image_count }} 张图</span>
      </template>
    </div>

    <div v-if="firstImage" class="image-preview">
      <img
        :src="firstImage.url"
        :alt="firstImage.caption || firstImage.filename"
        loading="lazy"
      />
      <span>图表预览</span>
    </div>

    <!-- ── RECOMMENDATION REASON ── -->
    <p v-if="recommendReason" class="reason-line">
      <span class="reason-label">推荐理由</span>{{ recommendReason }}
    </p>

    <!-- ── ARTICLE BRIEF: research question + main contribution ── -->
    <div v-if="hasBrief" class="brief-zone">
      <p v-if="researchQuestion" class="brief-item">
        <span class="brief-label">研究问题</span>{{ researchQuestion }}
      </p>
      <p v-if="mainContribution" class="brief-item">
        <span class="brief-label">主要贡献</span>{{ mainContribution }}
      </p>
    </div>

    <!-- ── INSIGHT: 一句话记忆版 / 个人观点 ── -->
    <div v-if="insight" class="insight-block">
      <span class="insight-icon">💡</span>
      <span class="insight-text">{{ insight }}</span>
    </div>

    <!-- ── FOOTER: paper id · copy · arxiv · bookmark ── -->
    <div class="row-footer">
      <span class="paper-id">{{ paper.paper_id }}</span>
      <div class="footer-actions">
        <button
          class="action-btn"
          :title="copiedId ? '已复制！' : '复制 arXiv ID'"
          @click="copyArxivId"
        >{{ copiedId ? '✓' : '⎘' }}</button>
        <button
          class="action-btn"
          title="在 arXiv 查看原文"
          @click="openArxivPage"
        >↗</button>
        <span v-if="isBookmarked" class="bookmark-star">★</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Root ─────────────────────────────────────────────────────────── */
.row-root {
  position: relative;
  padding: 16px 20px 14px 20px;
  transition: background 0.15s;
}
.row-root--active {
  background: rgba(45, 184, 226, 0.05);
}
.row-root--idle:hover {
  background: var(--color-bg-elevated);
}

/* Active left accent bar */
.accent-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  border-radius: 0 2px 2px 0;
  background: var(--color-tinder-blue);
}

/* ── Header ───────────────────────────────────────────────────────── */
.row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 7px;
}
.row-header__left {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  min-width: 0;
}
.row-header__right {
  flex-shrink: 0;
}

.row-index {
  font-size: 12px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  line-height: 1;
  min-width: 16px;
  text-align: right;
}

.institution-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.tier-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  border-radius: 3px;
  line-height: 1.5;
}
.tier-label--t1 {
  background: rgba(245, 197, 24, 0.12);
  color: #f5c518;
}
.tier-label--t2 {
  background: rgba(45, 184, 226, 0.1);
  color: var(--color-tinder-blue);
}
.tier-label--t3 {
  background: rgba(249, 115, 22, 0.1);
  color: #f97316;
}
.tier-label--t4 {
  background: rgba(113, 113, 122, 0.08);
  color: var(--color-text-muted);
}

/* Score */
.score {
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.score--high { color: var(--color-tag-score-high); }
.score--mid  { color: var(--color-tag-score-mid); }
.score--low  { color: var(--color-tag-score-low); }

/* ── Title Zone ───────────────────────────────────────────────────── */
.title-zone {
  margin-bottom: 5px;
}
.title-zh {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0 0 3px 0;
}
.title-en {
  font-size: 12.5px;
  color: var(--color-text-secondary);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
}

/* ── Meta Line ────────────────────────────────────────────────────── */
.meta-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
  margin-bottom: 6px;
}
.meta-item {
  font-size: 11.5px;
  color: var(--color-text-muted);
  line-height: 1.4;
}
.meta-sep {
  font-size: 11.5px;
  color: var(--color-text-muted);
  opacity: 0.5;
}

.image-preview {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 180px;
  padding: 3px 7px 3px 3px;
  margin: 0 0 7px 0;
  border: 1px solid var(--color-border-light);
  border-radius: 6px;
  background: var(--color-bg-elevated);
  color: var(--color-text-muted);
  font-size: 11px;
}
.image-preview img {
  width: 34px;
  height: 24px;
  object-fit: cover;
  border-radius: 4px;
  background: var(--color-bg-card);
}

/* ── Reason ───────────────────────────────────────────────────────── */
.reason-line {
  font-size: 12.5px;
  color: rgba(45, 184, 226, 0.8);
  line-height: 1.55;
  margin: 0 0 6px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.reason-label {
  font-weight: 600;
  margin-right: 4px;
  color: var(--color-tinder-blue);
  font-size: 11px;
  letter-spacing: 0.03em;
}

/* ── Brief Zone ───────────────────────────────────────────────────── */
.brief-zone {
  border-left: 2px solid var(--color-border-light);
  padding-left: 8px;
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.brief-item {
  font-size: 12.5px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.brief-label {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--color-tinder-pink);
  margin-right: 4px;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

/* ── Insight Block ────────────────────────────────────────────────── */
.insight-block {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-light);
  border-radius: 5px;
  padding: 5px 8px;
  margin-bottom: 7px;
}
.insight-icon {
  font-size: 12.5px;
  flex-shrink: 0;
  line-height: 1.55;
}
.insight-text {
  font-size: 12.5px;
  color: var(--color-text-muted);
  font-style: italic;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Footer ───────────────────────────────────────────────────────── */
.row-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 6px;
  border-top: 1px solid var(--color-border-light);
  margin-top: 2px;
}
.paper-id {
  font-size: 10.5px;
  color: var(--color-text-muted);
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
}
.footer-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 5px;
  font-size: 15px;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  line-height: 1;
}
.action-btn:hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}
.bookmark-star {
  font-size: 14px;
  color: var(--color-tinder-gold);
  line-height: 1;
}

/* ── Tier Pill (atom, reused from style.css pattern) ─────────────── */
.tier-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 16px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  line-height: 1;
  flex-shrink: 0;
}
.tier-pill--t1 {
  background: rgba(245, 197, 24, 0.18);
  color: #f5c518;
  border: 1px solid rgba(245, 197, 24, 0.35);
}
.tier-pill--t2 {
  background: rgba(45, 184, 226, 0.14);
  color: #2db8e2;
  border: 1px solid rgba(45, 184, 226, 0.3);
}
.tier-pill--t3 {
  background: rgba(249, 115, 22, 0.12);
  color: #f97316;
  border: 1px solid rgba(249, 115, 22, 0.28);
}
.tier-pill--t4 {
  background: rgba(113, 113, 122, 0.1);
  color: var(--color-text-muted);
  border: 1px solid rgba(113, 113, 122, 0.25);
}

</style>
