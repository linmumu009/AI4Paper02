<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { FEATURE_LABELS, FEATURE_UPGRADE_TO, useEntitlements } from '../composables/useEntitlements'
import type { UserEntitlements } from '../types/paper'

const props = withDefaults(defineProps<{
  /**
   * The feature key that triggered this prompt.
   * For quota features:  'chat' | 'compare' | 'research' | 'idea_gen' | 'upload'
   * For gate features:   'general_chat' | 'note_file_upload' | 'llm_preset' | 'prompt_preset'
   *                      'export_docx_pdf' | 'batch_export' | 'translate'
   * For storage:         'kb_papers' | 'kb_folders' | 'kb_notes' | 'kb_compare_results'
   * For browse limit:    'browse'
   */
  feature: string
  /** Compact inline variant (no background card, just icon + text + button) */
  inline?: boolean
  /** Additional CSS classes for the root element */
  class?: string
}>(), {
  inline: false,
})

const router = useRouter()
const { entitlements, quotaFraction, used, limit } = useEntitlements()

const featureLabel = computed(() => FEATURE_LABELS[props.feature] ?? props.feature)
const targetTier = computed(() => FEATURE_UPGRADE_TO[props.feature] ?? 'pro')
const targetTierLabel = computed(() => targetTier.value === 'pro_plus' ? 'Pro+' : 'Pro')

const isQuotaFeature = computed(() =>
  ['chat', 'compare', 'research', 'idea_gen', 'upload', 'translate'].includes(props.feature)
)

const isStorageFeature = computed(() =>
  ['kb_papers', 'kb_folders', 'kb_notes', 'kb_compare_results'].includes(props.feature)
)

const quotaInfo = computed(() => {
  if (!isQuotaFeature.value || !entitlements.value) return null
  return entitlements.value.quotas[props.feature as keyof UserEntitlements['quotas']]
})

const storageInfo = computed(() => {
  if (!isStorageFeature.value || !entitlements.value) return null
  return entitlements.value.storage[props.feature as keyof UserEntitlements['storage']]
})

const isExhausted = computed(() => {
  if (quotaInfo.value) {
    const q = quotaInfo.value
    return q.limit !== null && (q.remaining ?? 0) <= 0
  }
  if (storageInfo.value) {
    const s = storageInfo.value
    return s.limit !== null && (s.remaining ?? 0) <= 0
  }
  return false
})

const periodLabel = computed(() => {
  const p = quotaInfo.value?.period
  return { daily: '今日', monthly: '本月', total: '总计' }[p ?? ''] ?? ''
})

// Usage percentage for urgency display
const usagePercent = computed(() => {
  const q = quotaInfo.value
  if (!q || q.limit === null) return 0
  return Math.round((q.used / q.limit) * 100)
})

// Before/after comparison: current limit vs next tier limit
const NEXT_TIER_LIMITS: Record<string, Record<string, string>> = {
  chat:     { free: '10 次/天',  pro: '不限次数',  pro_plus: '不限次数' },
  compare:  { free: '3 次/月',   pro: '30 次/月',  pro_plus: '100 次/月' },
  research: { free: '2 次/月',   pro: '15 次/月',  pro_plus: '50 次/月' },
  idea_gen: { free: '3 次/月',   pro: '30 次/月',  pro_plus: '100 次/月' },
  upload:   { free: '2 篇/月',   pro: '30 篇/月',  pro_plus: '100 篇/月' },
  translate:{ free: '2 次/月',   pro: '15 次/月',  pro_plus: '28 次/月' },
  export:   { free: '2 次/月',   pro: '15 次/月',  pro_plus: '28 次/月' },
  browse:   { free: '3 篇/天',   pro: '9 篇/天',   pro_plus: '不限' },
}

const currentTierKey = computed(() => entitlements.value?.tier ?? 'free')
const currentLimitText = computed(() => NEXT_TIER_LIMITS[props.feature]?.[currentTierKey.value] ?? null)
const nextLimitText = computed(() => NEXT_TIER_LIMITS[props.feature]?.[targetTier.value] ?? null)

const descriptionText = computed(() => {
  const q = quotaInfo.value
  if (q && q.limit !== null) {
    return `${featureLabel.value}${periodLabel.value}用量已达上限（${q.used}/${q.limit}）。升级到 ${targetTierLabel.value} 解锁更多用量。`
  }
  const s = storageInfo.value
  if (s && s.limit !== null) {
    return `${featureLabel.value}已达存储上限（${s.used}/${s.limit}）。升级到 ${targetTierLabel.value} 解锁更多空间。`
  }
  if (props.feature === 'browse') {
    const browseLimit = entitlements.value?.browse?.limit
    if (browseLimit !== null && browseLimit !== undefined) {
      return `每日可浏览论文已达上限（${browseLimit} 篇）。升级到 ${targetTierLabel.value} 查看更多论文。`
    }
  }
  return `${featureLabel.value}需要 ${targetTierLabel.value} 套餐，当前套餐不可用。升级后立即解锁此功能。`
})

// Engagement hint: for quota-exhausted features that have engagement boost rewards
const engagementHint = computed<{ day: number; desc: string; daysNeeded: string } | null>(() => {
  if (!isExhausted.value) return null
  if (props.feature === 'chat') return { day: 2, daysNeeded: '2', desc: '连续 2 天研究可解锁对话增强券（AI 可读 1.5 倍论文上下文，回答更深入）' }
  if (props.feature === 'idea_gen') return { day: 4, daysNeeded: '4', desc: '连续 4 天研究可解锁灵感增强券（1.5 倍知识原子池，灵感更多元）' }
  if (props.feature === 'compare') return { day: 5, daysNeeded: '5', desc: '连续 5 天研究可解锁对比扩展券（+2 名额/次）' }
  if (props.feature === 'research') return { day: 7, daysNeeded: '7', desc: '连续 7 天研究可解锁深度研究加速券（1.5 倍上下文）' }
  if (props.feature === 'upload') return { day: 3, daysNeeded: '3', desc: '连续 3 天研究可解锁快速处理加速券（上传优先处理）' }
  return null
})

// Tier benefit hints — derived from live entitlements data
const tierBenefits = computed<string[]>(() => {
  const ent = entitlements.value
  const tier = targetTier.value

  if (ent) {
    const q = ent.quotas
    const s = ent.storage
    const browse = ent.browse?.limit
    const caps = ent.session_caps
    const retention = ent.retention?.research_history_days
    const gates = ent.gates

    const chatLabel = q.chat?.limit === null ? 'AI 论文问答不限次数' : `AI 论文问答 ${q.chat?.limit} 次/天`
    const browseLine = browse ? `每日浏览论文 ${browse} 篇` : '每日浏览论文不限'
    const compareLine = q.compare?.limit != null
      ? `对比分析 ${q.compare.limit} 次/月（每次 ${caps?.compare_max_items ?? '?'} 篇）`
      : '对比分析不限次数'
    const researchLine = q.research?.limit != null ? `深度研究 ${q.research.limit} 次/月` : '深度研究不限次数'
    const ideaLine = q.idea_gen?.limit != null ? `灵感生成 ${q.idea_gen.limit} 次/月` : '灵感生成不限次数'
    const translateLine = q.translate?.limit != null && q.translate.limit > 0
      ? `全文翻译 ${q.translate.limit} 次/月`
      : (q.translate?.limit === null ? '全文翻译不限次数' : null)
    const exportLine = q.export?.limit != null && q.export.limit > 0
      ? `DOCX/PDF 导出 ${q.export.limit} 次/月`
      : (q.export?.limit === null ? 'DOCX/PDF 导出不限次数' : null)
    const kbLine = s?.kb_papers?.limit != null
      ? `知识库最多 ${s.kb_papers.limit} 篇 + ${s.kb_notes?.limit ?? '?'} 笔记`
      : null
    const retentionLine = retention ? `${retention} 天研究历史保留` : null

    const lines: string[] = [browseLine, chatLabel]
    if (gates?.general_chat) lines.push('通用 AI 助手')
    if (translateLine) lines.push(translateLine)
    if (exportLine) lines.push(exportLine)
    lines.push(compareLine, researchLine, ideaLine)
    if (kbLine) lines.push(kbLine)
    if (gates?.batch_export) lines.push('批量导出 + 全格式支持')
    if (retentionLine) lines.push(retentionLine)
    return lines
  }

  if (tier === 'pro_plus') {
    return [
      '每日浏览论文不限篇数', 'AI 论文问答不限次数',
      '对比分析 100 次/月（每次 8 篇）', '深度研究 50 次/月',
      '灵感生成 100 次/月', '全文翻译 28 次/月',
      'DOCX/PDF 导出 28 次/月', '知识库最多 500 篇 + 200 笔记',
      '批量导出 + 全格式支持', '30 天研究历史保留',
    ]
  }
  return [
    '每日浏览论文 9 篇', 'AI 论文问答不限次数',
    '通用 AI 助手', '论文全文翻译（15 次/月）',
    'DOCX/PDF 导出（15 次/月）', '对比分析 30 次/月（每次 5 篇）',
    '深度研究 15 次/月', '灵感生成 30 次/月',
    '知识库最多 100 篇 + 50 笔记', '14 天研究历史保留',
  ]
})

const ctaGradient = computed(() =>
  targetTier.value === 'pro_plus'
    ? 'linear-gradient(135deg, #fd267a, #a855f7)'
    : 'linear-gradient(135deg, #f59e0b, #f97316)'
)

function goToProfile() {
  router.push('/profile?tab=subscription')
}
</script>

<template>
  <!-- Inline compact variant -->
  <div
    v-if="inline"
    class="flex items-center gap-2 text-xs text-text-muted"
    :class="props.class"
  >
    <span class="shrink-0 text-amber-400">🔒</span>
    <span class="flex-1 min-w-0 truncate">{{ descriptionText }}</span>
    <button
      class="shrink-0 px-2 py-0.5 rounded-md text-[11px] font-semibold text-white cursor-pointer hover:opacity-90 transition-opacity"
      :style="`background: ${ctaGradient};`"
      @click="goToProfile"
    >
      兑换会员
    </button>
  </div>

  <!-- Card variant -->
  <div
    v-else
    class="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-3"
    :class="props.class"
  >
    <!-- Header -->
    <div class="flex items-start gap-3">
      <div class="shrink-0 w-9 h-9 rounded-xl bg-amber-500/15 flex items-center justify-center text-lg">
        🔒
      </div>
      <div class="flex-1 min-w-0">
        <p class="text-sm font-semibold text-text-primary leading-snug">
          {{ isExhausted
            ? (isStorageFeature ? `${featureLabel}存储已满` : `${featureLabel}${periodLabel}次数已用完`)
            : `${featureLabel}需要 ${targetTierLabel} 套餐` }}
        </p>
        <p class="text-xs text-text-muted mt-0.5 leading-relaxed">
          {{ descriptionText }}
        </p>
      </div>
    </div>

    <!-- Before/After comparison (quota features only) -->
    <div
      v-if="isQuotaFeature && currentLimitText && nextLimitText && isExhausted"
      class="rounded-lg border border-border bg-bg-elevated/60 px-3 py-2 flex items-center gap-2"
    >
      <div class="flex-1 text-center">
        <p class="text-[9px] text-text-muted uppercase tracking-wide mb-0.5">当前套餐</p>
        <p class="text-xs font-semibold text-text-secondary">{{ currentLimitText }}</p>
      </div>
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
      </svg>
      <div class="flex-1 text-center">
        <p class="text-[9px] text-text-muted uppercase tracking-wide mb-0.5">{{ targetTierLabel }}</p>
        <p class="text-xs font-bold" :style="`background: ${ctaGradient}; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;`">{{ nextLimitText }}</p>
      </div>
    </div>

    <!-- Usage urgency bar (quota features, not yet exhausted) -->
    <div
      v-if="isQuotaFeature && usagePercent >= 70 && !isExhausted && quotaInfo?.limit"
      class="rounded-lg border border-amber-500/15 bg-amber-500/5 px-3 py-2"
    >
      <div class="flex items-center justify-between mb-1.5">
        <p class="text-[10px] text-amber-400 font-medium">{{ periodLabel }}已使用 {{ usagePercent }}%</p>
        <p class="text-[10px] text-text-muted">{{ quotaInfo.used }}/{{ quotaInfo.limit }}</p>
      </div>
      <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <div
          class="h-full rounded-full bg-amber-400 transition-all duration-300"
          :style="`width: ${usagePercent}%`"
        />
      </div>
    </div>

    <!-- Benefit list -->
    <ul class="space-y-1">
      <li
        v-for="benefit in tierBenefits.slice(0, 6)"
        :key="benefit"
        class="flex items-center gap-1.5 text-xs text-text-secondary"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-tinder-green shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        {{ benefit }}
      </li>
    </ul>

    <!-- Engagement alternative hint (free path for quota-exhausted features) -->
    <div
      v-if="engagementHint"
      class="rounded-xl border border-tinder-green/25 bg-tinder-green/6 px-3 py-3"
    >
      <div class="flex items-center gap-1.5 mb-1.5">
        <span class="text-sm shrink-0">🔥</span>
        <p class="text-[11px] font-semibold text-tinder-green">免费替代方案</p>
        <span class="ml-auto text-[10px] text-tinder-green/70 bg-tinder-green/10 px-1.5 py-0.5 rounded-full">第 {{ engagementHint.day }} 天解锁</span>
      </div>
      <p class="text-[10px] text-text-secondary leading-snug">
        {{ engagementHint.desc }}
      </p>
      <p class="text-[10px] text-text-muted mt-1 leading-snug">
        每日完成浏览 · 收藏 · 分析三项任务积累连续天数（向 AI 提问即算"分析"，每日 10 次免费）
      </p>
    </div>

    <!-- CTA -->
    <button
      class="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-opacity hover:opacity-90 active:opacity-75 cursor-pointer"
      :style="`background: ${ctaGradient}; box-shadow: 0 4px 12px rgba(253,38,122,0.25);`"
      @click="goToProfile"
    >
      前往兑换会员 → {{ targetTierLabel }}
    </button>
  </div>
</template>
