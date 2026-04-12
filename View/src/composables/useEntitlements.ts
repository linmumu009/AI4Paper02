/**
 * useEntitlements — centralised reactive store for the current user's
 * entitlement snapshot (tier, quotas, gates, storage, session caps).
 *
 * Usage:
 *   const { entitlements, canUse, remaining, limit, isGated, refreshEntitlements } = useEntitlements()
 *
 * Call `refreshEntitlements()` after login or after consuming a quota.
 */

import { computed, ref } from 'vue'
import { fetchEntitlements } from '../api'
import type { UserEntitlements } from '../types/paper'

// ---------------------------------------------------------------------------
// Module-level singleton state
// ---------------------------------------------------------------------------

const entitlements = ref<UserEntitlements | null>(null)
const loading = ref(false)
const loaded = ref(false)
const loadError = ref(false)

// ---------------------------------------------------------------------------
// Feature display labels (for UpgradePrompt and usage indicators)
// ---------------------------------------------------------------------------

export const FEATURE_LABELS: Record<string, string> = {
  chat: 'AI 论文问答',
  compare: '对比分析',
  research: '深度研究',
  idea_gen: '灵感生成',
  upload: '论文上传',
  translate: '论文全文翻译',
  export: 'DOCX/PDF 导出',
  general_chat: '通用 AI 助手',
  note_file_upload: '笔记附件上传',
  llm_preset: '自定义模型预设',
  prompt_preset: '自定义提示词预设',
  export_docx_pdf: 'DOCX/PDF 导出',
  batch_export: '批量导出',
  browse: '每日浏览论文',
  kb_papers: '知识库论文',
  kb_folders: '知识库文件夹',
  kb_notes: '知识库笔记',
  kb_compare_results: '保存的对比结果',
}

// What upgrade tier unlocks a feature
export const FEATURE_UPGRADE_TO: Record<string, 'pro' | 'pro_plus'> = {
  chat: 'pro',
  compare: 'pro',
  research: 'pro',
  idea_gen: 'pro',
  upload: 'pro',
  translate: 'pro',
  export: 'pro',
  general_chat: 'pro',
  note_file_upload: 'pro',
  llm_preset: 'pro',
  prompt_preset: 'pro',
  export_docx_pdf: 'pro',
  batch_export: 'pro_plus',
  browse: 'pro',
  kb_papers: 'pro',
  kb_folders: 'pro',
  kb_notes: 'pro',
  kb_compare_results: 'pro',
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useEntitlements() {
  const tier = computed(() => entitlements.value?.tier ?? 'free')
  const tierLabel = computed(() => entitlements.value?.tier_label ?? 'Free')
  const isPro = computed(() => tier.value === 'pro' || tier.value === 'pro_plus')
  const isProPlus = computed(() => tier.value === 'pro_plus')

  async function refreshEntitlements(force = false) {
    if (loading.value) return
    if (loaded.value && !force) return
    loading.value = true
    try {
      entitlements.value = await fetchEntitlements()
      loaded.value = true
      loadError.value = false
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
    }
  }

  /**
   * Check whether the user has remaining quota for a feature.
   * Returns false until entitlements are loaded (conservative — avoids triggering
   * requests that the server will reject with 429 before we know the user's quota).
   * Returns true if unlimited or quota > 0, false if exhausted.
   */
  function canUse(feature: keyof UserEntitlements['quotas']): boolean {
    if (!loaded.value) return false // conservative before first load
    if (!entitlements.value) return false
    const q = entitlements.value.quotas[feature]
    if (q.limit === null) return true
    return (q.remaining ?? 0) > 0
  }

  /** Returns remaining quota (null = unlimited). */
  function remaining(feature: keyof UserEntitlements['quotas']): number | null {
    return entitlements.value?.quotas[feature]?.remaining ?? null
  }

  /** Returns the hard limit (null = unlimited). */
  function limit(feature: keyof UserEntitlements['quotas']): number | null {
    return entitlements.value?.quotas[feature]?.limit ?? null
  }

  /** Returns the current usage count. */
  function used(feature: keyof UserEntitlements['quotas']): number {
    return entitlements.value?.quotas[feature]?.used ?? 0
  }

  /** Returns the period type for a feature ('daily' | 'monthly' | 'total' | null). */
  function period(feature: keyof UserEntitlements['quotas']): string | null {
    return entitlements.value?.quotas[feature]?.period ?? null
  }

  /**
   * Check a boolean gate feature.
   * Returns true (blocked) until entitlements are loaded — conservative, prevents a
   * brief flash of gated UI appearing for free users before we know their tier.
   */
  function isGated(gate: keyof UserEntitlements['gates']): boolean {
    if (!loaded.value) return true // conservative: treat as gated until we know
    if (!entitlements.value) return true
    return !entitlements.value.gates[gate]
  }

  /**
   * Returns true if the gate feature is available for current tier.
   * Returns false until entitlements are loaded (conservative).
   */
  function gateAllowed(gate: keyof UserEntitlements['gates']): boolean {
    if (!loaded.value) return false // conservative before first load
    if (!entitlements.value) return false
    return entitlements.value.gates[gate]
  }

  /** Returns the max papers per compare session for the current tier. */
  const compareMaxItems = computed(() => entitlements.value?.session_caps?.compare_max_items ?? 2)

  /** Storage status for KB papers */
  const kbPaperStorage = computed(() => entitlements.value?.storage?.kb_papers ?? { limit: 20, used: 0, remaining: 20 })

  /** Storage status for KB folders */
  const kbFolderStorage = computed(() => entitlements.value?.storage?.kb_folders ?? { limit: 3, used: 0, remaining: 3 })

  /** Storage status for KB notes */
  const kbNoteStorage = computed(() => entitlements.value?.storage?.kb_notes ?? { limit: 10, used: 0, remaining: 10 })

  /** Storage status for saved compare results */
  const kbCompareResultStorage = computed(() => entitlements.value?.storage?.kb_compare_results ?? { limit: 3, used: 0, remaining: 3 })

  /** Daily visible paper count limit (null = unlimited) */
  const browseLimit = computed(() => entitlements.value?.browse?.limit ?? 3)

  /** Research session history retention (days, null = unlimited) */
  const researchHistoryDays = computed(() => entitlements.value?.retention?.research_history_days ?? 3)

  /**
   * Returns a human-readable quota summary string for a feature.
   * e.g. "3/15 本月" or "10/10 今日" or "不限"
   */
  function quotaSummary(feature: keyof UserEntitlements['quotas']): string {
    const q = entitlements.value?.quotas[feature]
    if (!q || q.limit === null) return '不限'
    const periodLabel = ({ daily: '今日', monthly: '本月', total: '总计' } as Record<string, string>)[q.period ?? ''] ?? ''
    return `${q.used}/${q.limit}${periodLabel ? ' ' + periodLabel : ''}`
  }

  /**
   * Returns a quota usage fraction [0, 1] for progress-bar display.
   */
  function quotaFraction(feature: keyof UserEntitlements['quotas']): number {
    const q = entitlements.value?.quotas[feature]
    if (!q || q.limit === null) return 0
    return Math.min(1, q.used / q.limit)
  }

  return {
    entitlements,
    loading,
    loaded,
    loadError,
    tier,
    tierLabel,
    isPro,
    isProPlus,
    refreshEntitlements,
    canUse,
    remaining,
    limit,
    used,
    period,
    isGated,
    gateAllowed,
    compareMaxItems,
    kbPaperStorage,
    kbFolderStorage,
    kbNoteStorage,
    kbCompareResultStorage,
    browseLimit,
    researchHistoryDays,
    quotaSummary,
    quotaFraction,
  }
}
