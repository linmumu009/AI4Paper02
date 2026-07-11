<script setup lang="ts">
import { computed } from 'vue'
import type { IdeaAtom, IdeaCandidate, IdeaQuestion, IdeaSourcePaper } from '../../types/paper'
import { getStrategyLabel } from '../../utils/strategyMeta'

const props = defineProps<{
  candidate: IdeaCandidate
  atoms: IdeaAtom[]
  question: IdeaQuestion | null
  questionLoading: boolean
  sourcePapers: string[]
  sourcePapersInfo: Record<string, IdeaSourcePaper>
  sourcePapersLoading: boolean
}>()

/* ─── atom type display ─────────────────────────────────── */
const ATOM_TYPE_ICON: Record<string, string> = {
  limitation: '⚠️',
  method: '⚙️',
  claim: '💡',
  setup: '📊',
  tag: '🏷️',
}
const ATOM_TYPE_LABEL: Record<string, string> = {
  limitation: '局限',
  method: '方法',
  claim: '论断',
  setup: '设置',
  tag: '标签',
}

const atomTypeSummary = computed(() => {
  const counts: Record<string, number> = {}
  for (const atom of props.atoms) {
    counts[atom.atom_type] = (counts[atom.atom_type] ?? 0) + 1
  }
  const ORDER = ['limitation', 'method', 'claim', 'setup', 'tag']
  return ORDER.filter((t) => (counts[t] ?? 0) > 0)
    .map((t) => `${ATOM_TYPE_ICON[t] ?? '·'} ${counts[t]} ${ATOM_TYPE_LABEL[t] ?? t}`)
    .join('  ')
})

/* ─── source papers display ──────────────────────────────── */
const sourcePapersCount = computed(() => props.sourcePapers.length)

/** 论文篇数文字，带加载态 */
const sourcePapersCountLabel = computed(() => {
  if (props.sourcePapersLoading) return '加载中…'
  return sourcePapersCount.value ? `${sourcePapersCount.value} 篇` : '暂无'
})

/** 首篇论文标题（仅用于来源文献行副标注） */
const firstPaperTitle = computed(() => {
  const pid = props.sourcePapers[0]
  if (!pid) return ''
  const info = props.sourcePapersInfo[pid]
  if (!info?.title || info.title === pid) return pid.length > 40 ? pid.slice(0, 40) + '…' : pid
  const t = info.title
  return t.length > 45 ? t.slice(0, 45) + '…' : t
})

/* ─── strategy ───────────────────────────────────────────── */
const strategyLabel = computed(() => getStrategyLabel(props.candidate.strategy))

/* ─── AI scores ──────────────────────────────────────────── */
const scoreItems = computed(() => {
  const s = props.candidate.scores
  if (!s || Object.keys(s).length === 0) return []
  const order: Array<{ key: string; label: string }> = [
    { key: 'overall', label: '综合' },
    { key: 'novelty', label: '新颖' },
    { key: 'feasibility', label: '可行' },
    { key: 'impact', label: '影响' },
  ]
  return order
    .filter((o) => s[o.key] != null)
    .map((o) => ({ label: o.label, value: s[o.key] as number }))
})

function scoreClass(v: number) {
  if (v >= 7.5) return 'score--high'
  if (v >= 5.5) return 'score--mid'
  return 'score--low'
}
</script>

<template>
  <div class="provenance-flow">
    <!-- 标题 + 导语 -->
    <div class="pf-header">
      <p class="pf-title">生成溯源</p>
      <p class="pf-subtitle">当前灵感的来源文献、知识原子、研究问题与生成策略一览。细化推导见下方「推导依据」。</p>
    </div>

    <!-- 1. 来源文献（论文 → 原子的起点） -->
    <div class="pf-row">
      <span class="pf-row-icon">📄</span>
      <div class="pf-row-body">
        <span class="pf-row-label">来源文献</span>
        <span class="pf-row-value" :class="{ 'pf-muted': !sourcePapers.length }">
          <template v-if="sourcePapersLoading">加载中…</template>
          <template v-else-if="sourcePapers.length">
            {{ sourcePapersCountLabel }}
            <template v-if="firstPaperTitle">
              <span class="pf-sep">·</span>
              <span class="pf-first-title">{{ firstPaperTitle }}{{ sourcePapers.length > 1 ? ' 等' : '' }}</span>
            </template>
          </template>
          <template v-else>暂无</template>
        </span>
      </div>
    </div>

    <!-- 2. 知识原子（与空态流水线「知识原子」步骤对应） -->
    <div class="pf-row">
      <span class="pf-row-icon">🔬</span>
      <div class="pf-row-body">
        <span class="pf-row-label">知识原子</span>
        <span v-if="atoms.length" class="pf-row-value">{{ atomTypeSummary }}</span>
        <span v-else class="pf-row-value pf-muted">无原子数据</span>
      </div>
    </div>

    <!-- 3. 研究问题 -->
    <div class="pf-row">
      <span class="pf-row-icon">❓</span>
      <div class="pf-row-body">
        <span class="pf-row-label">研究问题</span>
        <span v-if="questionLoading" class="pf-skeleton" />
        <span v-else-if="question?.question_text" class="pf-row-value pf-question-text">
          "{{ question.question_text }}"
        </span>
        <span v-else-if="candidate.question_id" class="pf-row-value pf-muted">
          研究问题标题加载失败
        </span>
        <span v-else class="pf-row-value pf-muted">生成时未关联研究问题，直接从原子推导</span>
      </div>
    </div>

    <!-- 4. 生成策略 -->
    <div class="pf-row">
      <span class="pf-row-icon">🎯</span>
      <div class="pf-row-body">
        <span class="pf-row-label">生成策略</span>
        <span class="pf-strategy-badge">{{ strategyLabel }}</span>
      </div>
    </div>

    <!-- 5. AI 评分（模型估计，非同行评议） -->
    <div v-if="scoreItems.length" class="pf-row pf-row--scores">
      <span class="pf-row-icon">📊</span>
      <div class="pf-row-body pf-row-body--col">
        <div class="pf-scores-wrap">
          <span class="pf-row-label">模型评分</span>
          <span class="pf-scores">
            <span
              v-for="item in scoreItems"
              :key="item.label"
              class="pf-score-chip"
              :class="scoreClass(item.value)"
            >
              {{ item.label }} {{ item.value.toFixed(1) }}
            </span>
          </span>
        </div>
        <p class="pf-score-note">各维度为语言模型在 0–10 量表上的估计，仅供参考筛选，不代表同行评议结论。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.provenance-flow {
  background: var(--color-bg-card, #1a1a2e);
  border: 1px solid var(--color-border, rgba(255, 255, 255, 0.08));
  border-radius: 10px;
  padding: 14px 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}

/* ── 标题区 ──────────────────────────────────────────────── */
.pf-header {
  margin: 0 0 2px;
}

.pf-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted, rgba(255, 255, 255, 0.35));
  margin: 0 0 3px;
}

.pf-subtitle {
  font-size: 11px;
  color: var(--color-text-muted, rgba(255, 255, 255, 0.3));
  line-height: 1.5;
  margin: 0;
}

/* ── 字段行 ──────────────────────────────────────────────── */
.pf-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.pf-row-icon {
  font-size: 13px;
  line-height: 1.6;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}

.pf-row-body {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 5px 8px;
  flex: 1;
  min-width: 0;
}

.pf-row-body--col {
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}

.pf-row-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted, rgba(255, 255, 255, 0.4));
  flex-shrink: 0;
  line-height: 1.6;
  min-width: 60px;
}

.pf-row-value {
  font-size: 12px;
  color: var(--color-text-secondary, rgba(255, 255, 255, 0.7));
  line-height: 1.6;
  word-break: break-word;
}

.pf-first-title {
  font-size: 11px;
  color: var(--color-text-muted, rgba(255, 255, 255, 0.4));
}

.pf-question-text {
  font-style: italic;
  color: var(--color-text-primary, rgba(255, 255, 255, 0.88));
}

.pf-muted {
  color: var(--color-text-muted, rgba(255, 255, 255, 0.35));
  font-style: italic;
}

.pf-sep {
  color: var(--color-text-muted, rgba(255, 255, 255, 0.3));
  margin: 0 2px;
}

/* ── 骨架屏 ──────────────────────────────────────────────── */
.pf-skeleton {
  display: inline-block;
  width: 160px;
  height: 13px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.05) 25%,
    rgba(255, 255, 255, 0.1) 50%,
    rgba(255, 255, 255, 0.05) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── 生成策略徽章 ─────────────────────────────────────────── */
.pf-strategy-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  color: #63b3ed;
  background: rgba(99, 179, 237, 0.12);
  border: 1px solid rgba(99, 179, 237, 0.25);
  border-radius: 6px;
  padding: 1px 8px;
  line-height: 1.6;
}

/* ── AI 评分区 ────────────────────────────────────────────── */
.pf-scores-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 8px;
}

.pf-scores {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pf-score-chip {
  font-size: 11px;
  font-weight: 500;
  border-radius: 5px;
  padding: 1px 7px;
  border: 1px solid;
}
.pf-score-chip.score--high {
  color: #68d391;
  background: rgba(104, 211, 145, 0.1);
  border-color: rgba(104, 211, 145, 0.25);
}
.pf-score-chip.score--mid {
  color: #f6e05e;
  background: rgba(246, 224, 94, 0.1);
  border-color: rgba(246, 224, 94, 0.25);
}
.pf-score-chip.score--low {
  color: #fc8181;
  background: rgba(252, 129, 129, 0.1);
  border-color: rgba(252, 129, 129, 0.25);
}

.pf-score-note {
  font-size: 10px;
  color: var(--color-text-muted, rgba(255, 255, 255, 0.28));
  line-height: 1.5;
  margin: 0;
  font-style: italic;
}
</style>
