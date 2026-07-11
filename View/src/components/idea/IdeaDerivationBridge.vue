<script setup lang="ts">
import { computed } from 'vue'
import type { IdeaAtom, IdeaCandidate } from '../../types/paper'
import { getStrategyMeta } from '../../utils/strategyMeta'

const props = defineProps<{
  candidate: IdeaCandidate
  atoms: IdeaAtom[]
}>()

/* ─── 策略映射（统一来自 strategyMeta） ──────────────────── */
const strategyInfo = computed(() => getStrategyMeta(props.candidate.strategy))

/* ─── 关键原子（观察用） ─────────────────────────────────── */
const limitationAtoms = computed(() =>
  props.atoms.filter((a) => a.atom_type === 'limitation').slice(0, 3),
)
const methodAtoms = computed(() =>
  props.atoms.filter((a) => a.atom_type === 'method').slice(0, 2),
)

// 展示在 Step 1 的原子列表：limitation 优先，不足时补 method，都没有时取前 3 个
const displayAtoms = computed<IdeaAtom[]>(() => {
  const lim = limitationAtoms.value
  const meth = methodAtoms.value
  if (!lim.length && !meth.length) return props.atoms.slice(0, 3)
  return [...lim, ...meth].slice(0, 4)
})

/* ─── 证据聚合 ────────────────────────────────────────────── */
interface EvidenceItem {
  text: string
  location: string
  paper_id: string
  atom_type: string
  confidence?: number
}

const allEvidence = computed<EvidenceItem[]>(() => {
  const items: EvidenceItem[] = []
  for (const atom of displayAtoms.value) {
    const evList = (atom.evidence ?? []) as Array<Record<string, unknown>>
    for (const ev of evList) {
      const text = (ev['text'] ?? ev['snippet'] ?? '') as string
      if (!text.trim()) continue
      items.push({
        text,
        location: (ev['location'] ?? ev['section'] ?? '') as string,
        paper_id: atom.paper_id ?? '',
        atom_type: atom.atom_type,
        confidence: atom.confidence,
      })
    }
    if (items.length >= 6) break
  }
  return items
})

const hasAnyEvidence = computed(() => allEvidence.value.length > 0)

/* ─── 推理连接文字 ────────────────────────────────────────── */
const reasoningConnector = computed(() => {
  const lim = limitationAtoms.value
  const meth = methodAtoms.value
  const { label, action } = strategyInfo.value
  const parts: string[] = []
  if (lim.length) parts.push(`${lim.length} 条局限原子`)
  if (meth.length) parts.push(`${meth.length} 条方法原子`)
  const base = parts.length ? `基于上述${parts.join('和')}，` : ''
  return `${base}采用「${label}」策略：${action}。生成的研究方向指向：`
})

/* ─── 待验证风险 ──────────────────────────────────────────── */
const riskParagraph = computed(() => (props.candidate.risks ?? '').trim())

const scoreWarnings = computed<string[]>(() => {
  const s = props.candidate.scores
  if (!s) return []
  const w: string[] = []
  if ((s['feasibility'] as number) != null && (s['feasibility'] as number) < 6) {
    w.push(`可行性评分偏低（${(s['feasibility'] as number).toFixed(1)}/10），实施方案需进一步验证`)
  }
  if ((s['novelty'] as number) != null && (s['novelty'] as number) < 6) {
    w.push(`新颖性评分偏低（${(s['novelty'] as number).toFixed(1)}/10），建议系统调研相关工作`)
  }
  if ((s['impact'] as number) != null && (s['impact'] as number) < 5) {
    w.push(`预期影响力有限（${(s['impact'] as number).toFixed(1)}/10），研究价值有待重新评估`)
  }
  return w
})

const hasRiskInfo = computed(() => riskParagraph.value || scoreWarnings.value.length > 0)

/* ─── 工具函数 ────────────────────────────────────────────── */
function truncate(text: string, maxLen = 120) {
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

const ATOM_TYPE_LABEL: Record<string, string> = {
  limitation: '局限',
  method: '方法',
  claim: '论断',
  setup: '设置',
  tag: '标签',
}
const ATOM_TYPE_COLOR: Record<string, string> = {
  limitation: 'atom-dot--limitation',
  method: 'atom-dot--method',
  claim: 'atom-dot--claim',
  setup: 'atom-dot--setup',
}

const CONFIDENCE_LABEL: Record<string, string> = {
  high: '高',
  mid: '中',
  low: '低',
}
function confidenceLabel(v?: number) {
  if (v == null) return null
  if (v >= 0.75) return { text: `可信度 ${(v * 100).toFixed(0)}%`, cls: 'conf--high' }
  if (v >= 0.5) return { text: `可信度 ${(v * 100).toFixed(0)}%`, cls: 'conf--mid' }
  return { text: `可信度 ${(v * 100).toFixed(0)}%`, cls: 'conf--low' }
}
</script>

<template>
  <div class="derivation-bridge">
    <!-- 标题 -->
    <div class="bridge-header">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="bridge-icon">
        <path fill-rule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clip-rule="evenodd" />
      </svg>
      <span class="bridge-header-label">推导依据</span>
      <span class="bridge-header-sub">（证据驱动）</span>
    </div>

    <ol class="bridge-steps">

      <!-- ① 观察 ─────────────────────────────────────────── -->
      <li class="bridge-step">
        <div class="step-indicator step-indicator--source">
          <span class="step-dot" />
        </div>
        <div class="step-content">
          <p class="step-title"><span class="step-num">01</span> 观察</p>
          <p class="step-desc">从来源论文中提取的关键原子</p>

          <div v-if="displayAtoms.length" class="atom-list">
            <div v-for="atom in displayAtoms" :key="atom.id" class="atom-block">
              <div class="atom-block-header">
                <span class="atom-dot" :class="ATOM_TYPE_COLOR[atom.atom_type]" />
                <span class="atom-type-label">{{ ATOM_TYPE_LABEL[atom.atom_type] ?? atom.atom_type }}</span>
                <span class="atom-paper-ref">{{ atom.paper_id ?? '—' }}</span>
                <span v-if="!(atom.evidence?.length)" class="no-evidence-tag">⚠️ 无原文引用</span>
              </div>
              <p class="atom-content">{{ truncate(atom.content, 110) }}</p>
            </div>
          </div>

          <div v-else class="step-empty">暂无关键原子，推导依据不完整</div>

          <!-- 所有原子都无证据时的全局警告 -->
          <div v-if="displayAtoms.length && !hasAnyEvidence" class="evidence-absence-warning">
            ⚠️ 该批原子暂无原文证据引用，以下推导基于 AI 提取论断，需人工核实原文
          </div>
        </div>
      </li>

      <!-- ② 证据 ─────────────────────────────────────────── -->
      <li class="bridge-step">
        <div class="step-indicator step-indicator--evidence">
          <span class="step-dot" />
        </div>
        <div class="step-content">
          <p class="step-title"><span class="step-num">02</span> 证据</p>
          <p class="step-desc">来源论文中的原文引用片段</p>

          <div v-if="hasAnyEvidence" class="evidence-list">
            <div v-for="(ev, idx) in allEvidence" :key="idx" class="evidence-snippet">
              <div class="evidence-meta-row">
                <span class="atom-dot atom-dot--sm" :class="ATOM_TYPE_COLOR[ev.atom_type]" />
                <span class="evidence-paper-ref">{{ ev.paper_id }}</span>
                <span v-if="ev.location" class="evidence-location">{{ ev.location }}</span>
                <span v-if="confidenceLabel(ev.confidence)" class="confidence-badge" :class="confidenceLabel(ev.confidence)!.cls">
                  {{ confidenceLabel(ev.confidence)!.text }}
                </span>
              </div>
              <p class="evidence-text">"{{ truncate(ev.text, 160) }}"</p>
            </div>
          </div>

          <div v-else class="evidence-absence-warning">
            ⚠️ 无原文证据引用。以下推导仅基于 AI 提取的原子论断，结论仍待原文验证。
          </div>
        </div>
      </li>

      <!-- ③ 推理 ─────────────────────────────────────────── -->
      <li class="bridge-step">
        <div class="step-indicator step-indicator--strategy">
          <span class="step-dot" />
        </div>
        <div class="step-content">
          <p class="step-title"><span class="step-num">03</span> 推理</p>
          <p class="step-desc">从观察到生成方向的逻辑转换</p>

          <div class="strategy-block">
            <span class="strategy-pill" :class="strategyInfo.colorClass">{{ strategyInfo.label }}</span>
            <p class="reasoning-connector-text">{{ reasoningConnector }}</p>
            <div class="goal-excerpt">
              <p class="goal-text">{{ candidate.goal.length > 200 ? candidate.goal.slice(0, 200) + '…' : candidate.goal }}</p>
            </div>
          </div>
        </div>
      </li>

      <!-- ④ 待验证 ──────────────────────────────────────── -->
      <li class="bridge-step bridge-step--last">
        <div class="step-indicator step-indicator--risk">
          <span class="step-dot" />
        </div>
        <div class="step-content">
          <p class="step-title"><span class="step-num">04</span> 待验证</p>
          <p class="step-desc">已知风险与尚待确认的假设</p>

          <div v-if="hasRiskInfo" class="risk-block">
            <p v-if="riskParagraph" class="risk-paragraph">{{ riskParagraph }}</p>
            <ul v-if="scoreWarnings.length" class="score-warnings">
              <li v-for="(w, i) in scoreWarnings" :key="i" class="score-warning-item">
                <span class="score-warning-dot" />{{ w }}
              </li>
            </ul>
          </div>

          <div v-else class="step-empty">
            未发现明确风险说明，建议进行同行评审后再推进
          </div>
        </div>
      </li>

    </ol>
  </div>
</template>

<style scoped>
/* ── 容器 ── */
.derivation-bridge {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 14px 16px;
}

/* ── 标题 ── */
.bridge-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
}
.bridge-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.bridge-header-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--color-text-muted);
}
.bridge-header-sub {
  font-size: 10px;
  color: var(--color-text-muted);
  opacity: 0.6;
}

/* ── 步骤列表 ── */
.bridge-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

/* ── 单步 ── */
.bridge-step {
  display: flex;
  align-items: stretch;
  gap: 12px;
}

/* 指示器列 */
.step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 16px;
  padding-top: 3px;
}
.step-indicator::after {
  content: '';
  flex: 1;
  width: 1.5px;
  background: var(--color-border);
  margin-top: 5px;
  margin-bottom: -2px;
}
.bridge-step--last .step-indicator::after {
  display: none;
}

/* 圆点颜色 */
.step-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.step-indicator--source .step-dot   { background: rgba(239,68,68,0.75);  border: 2px solid rgba(239,68,68,0.25); }
.step-indicator--evidence .step-dot { background: rgba(99,179,237,0.75); border: 2px solid rgba(99,179,237,0.25); }
.step-indicator--strategy .step-dot { background: rgba(245,158,11,0.8);  border: 2px solid rgba(245,158,11,0.25); }
.step-indicator--risk .step-dot     { background: rgba(167,139,250,0.75);border: 2px solid rgba(167,139,250,0.25); }

/* 内容区 */
.step-content {
  flex: 1;
  min-width: 0;
  padding-bottom: 16px;
}
.bridge-step--last .step-content { padding-bottom: 0; }

/* 步骤标题 */
.step-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin: 0 0 2px;
}
.step-num {
  font-size: 9px;
  font-weight: 700;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}
.step-desc {
  font-size: 10.5px;
  color: var(--color-text-muted);
  margin: 0 0 8px;
}
.step-empty {
  font-size: 11px;
  color: var(--color-text-muted);
  font-style: italic;
}

/* ── 原子块 ── */
.atom-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.atom-block {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 7px 10px;
}
.atom-block-header {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.atom-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.atom-dot--sm { width: 5px; height: 5px; }
.atom-dot--limitation { background: rgba(239,68,68,0.65); }
.atom-dot--method     { background: rgba(99,179,237,0.65); }
.atom-dot--claim      { background: rgba(104,211,145,0.65); }
.atom-dot--setup      { background: rgba(251,191,36,0.65); }

.atom-type-label {
  font-size: 9.5px;
  font-weight: 700;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.atom-paper-ref {
  font-size: 9.5px;
  color: var(--color-text-muted);
  opacity: 0.7;
  font-family: monospace;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.no-evidence-tag {
  font-size: 9px;
  color: rgba(251,191,36,0.8);
  background: rgba(251,191,36,0.08);
  border: 1px solid rgba(251,191,36,0.2);
  border-radius: 4px;
  padding: 0 5px;
  line-height: 1.6;
}
.atom-content {
  font-size: 11.5px;
  color: var(--color-text-muted);
  line-height: 1.6;
  margin: 0;
}

/* ── 证据片段 ── */
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.evidence-snippet {
  border-left: 2px solid rgba(99,179,237,0.35);
  padding: 5px 0 5px 10px;
  background: rgba(99,179,237,0.04);
  border-radius: 0 5px 5px 0;
}
.evidence-meta-row {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}
.evidence-paper-ref {
  font-size: 9.5px;
  color: var(--color-text-muted);
  font-family: monospace;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-location {
  font-size: 9.5px;
  color: var(--color-text-muted);
  opacity: 0.7;
}
.confidence-badge {
  font-size: 9px;
  border-radius: 4px;
  padding: 0 5px;
  line-height: 1.6;
  border: 1px solid;
}
.conf--high { color: #68d391; background: rgba(104,211,145,0.1); border-color: rgba(104,211,145,0.25); }
.conf--mid  { color: #f6e05e; background: rgba(246,224,94,0.1);  border-color: rgba(246,224,94,0.25); }
.conf--low  { color: #fc8181; background: rgba(252,129,129,0.1); border-color: rgba(252,129,129,0.25); }

.evidence-text {
  font-size: 11.5px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0;
  font-style: italic;
}

/* 无证据警告框 */
.evidence-absence-warning {
  font-size: 11px;
  color: rgba(251,191,36,0.85);
  background: rgba(251,191,36,0.07);
  border: 1px solid rgba(251,191,36,0.2);
  border-radius: 6px;
  padding: 6px 10px;
  margin-top: 6px;
  line-height: 1.5;
}

/* ── 策略块 ── */
.strategy-block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.strategy-pill {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 9999px;
  border: 1px solid transparent;
  width: fit-content;
}
.strategy-transfer { background: rgba(99,179,237,0.12); color: #63b3ed; border-color: rgba(99,179,237,0.3); }
.strategy-stitch   { background: rgba(167,139,250,0.12); color: #a78bfa; border-color: rgba(167,139,250,0.3); }
.strategy-patch    { background: rgba(52,211,153,0.12);  color: #34d399; border-color: rgba(52,211,153,0.3); }
.strategy-extend   { background: rgba(251,191,36,0.12);  color: #fbbf24; border-color: rgba(251,191,36,0.3); }
.strategy-counter  { background: rgba(251,146,60,0.12);  color: #fb923c; border-color: rgba(251,146,60,0.3); }
.strategy-explore  { background: rgba(244,114,182,0.12); color: #f472b6; border-color: rgba(244,114,182,0.3); }
.strategy-resource { background: rgba(248,113,113,0.12); color: #f87171; border-color: rgba(248,113,113,0.3); }
.strategy-default  { background: var(--color-bg-card);   color: var(--color-text-secondary); border-color: var(--color-border); }

.reasoning-connector-text {
  font-size: 11.5px;
  color: var(--color-text-muted);
  line-height: 1.6;
  margin: 0;
}

.goal-excerpt {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-left: 3px solid rgba(52,211,153,0.5);
  border-radius: 0 6px 6px 0;
  padding: 8px 12px;
}
.goal-text {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.65;
  margin: 0;
}

/* ── 风险块 ── */
.risk-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.risk-paragraph {
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.6;
  margin: 0;
}
.score-warnings {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.score-warning-item {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 11.5px;
  color: rgba(252,129,129,0.85);
  line-height: 1.5;
}
.score-warning-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(252,129,129,0.7);
  flex-shrink: 0;
  margin-top: 5px;
}
</style>
