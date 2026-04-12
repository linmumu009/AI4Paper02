<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { FEATURE_LABELS, useEntitlements } from '../composables/useEntitlements'
import type { UserEntitlements } from '../types/paper'

const props = withDefaults(defineProps<{
  /**
   * The quota feature key to check.
   * One of: 'chat' | 'compare' | 'research' | 'idea_gen' | 'upload' | 'translate'
   */
  feature: keyof UserEntitlements['quotas']
  /** Threshold fraction [0,1] above which the warning is shown. Default 0.8 */
  threshold?: number
  /** Compact single-line variant */
  compact?: boolean
}>(), {
  threshold: 0.8,
  compact: false,
})

const router = useRouter()
const { entitlements, quotaFraction, quotaSummary, remaining, tier } = useEntitlements()

const shouldShow = computed(() => {
  if (!entitlements.value) return false
  const q = entitlements.value.quotas[props.feature]
  // Only show if there's a real limit (not unlimited)
  if (q.limit === null) return false
  return quotaFraction(props.feature) >= props.threshold
})

const isExhausted = computed(() => {
  if (!entitlements.value) return false
  const q = entitlements.value.quotas[props.feature]
  return q.limit !== null && (q.remaining ?? 0) <= 0
})

const featureLabel = computed(() => FEATURE_LABELS[props.feature] ?? props.feature)

const periodLabel = computed(() => {
  const p = entitlements.value?.quotas[props.feature]?.period
  return { daily: '今日', monthly: '本月', total: '总计' }[p ?? ''] ?? ''
})

const remainingCount = computed(() => remaining(props.feature) ?? 0)

const summaryText = computed(() => quotaSummary(props.feature))

const message = computed(() => {
  if (isExhausted.value) {
    return `${featureLabel.value}${periodLabel.value}用量已全部用完（${summaryText.value}）`
  }
  return `${featureLabel.value}${periodLabel.value}用量即将耗尽，仅剩 ${remainingCount.value} 次（${summaryText.value}）`
})

function goToSubscription() {
  router.push('/profile?tab=subscription')
}
</script>

<template>
  <div v-if="shouldShow">
    <!-- Compact single-line variant -->
    <div
      v-if="compact"
      class="flex items-center gap-2 rounded-lg px-3 py-2 text-xs"
      :class="isExhausted
        ? 'bg-red-500/8 border border-red-500/20 text-red-400'
        : 'bg-amber-500/8 border border-amber-500/20 text-amber-400'"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="w-3.5 h-3.5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span class="flex-1 min-w-0">{{ message }}</span>
      <button
        class="shrink-0 underline underline-offset-2 hover:no-underline transition-all font-medium cursor-pointer"
        @click="goToSubscription"
      >兑换会员</button>
    </div>

    <!-- Full banner variant -->
    <div
      v-else
      class="rounded-xl px-4 py-3 flex items-start gap-3"
      :class="isExhausted
        ? 'bg-red-500/8 border border-red-500/20'
        : 'bg-amber-500/8 border border-amber-500/20'"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="w-4 h-4 shrink-0 mt-0.5"
        :class="isExhausted ? 'text-red-400' : 'text-amber-400'"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <div class="flex-1 min-w-0">
        <p
          class="text-xs font-semibold leading-snug"
          :class="isExhausted ? 'text-red-400' : 'text-amber-400'"
        >
          {{ isExhausted ? `${featureLabel}用量已耗尽` : `${featureLabel}用量即将耗尽` }}
        </p>
        <p class="text-[11px] text-text-secondary mt-0.5 leading-snug">
          {{ message }}。升级套餐可获得更多用量。
        </p>
      </div>
      <button
        v-if="tier !== 'pro_plus'"
        class="shrink-0 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-white transition-opacity hover:opacity-90 cursor-pointer"
        :style="isExhausted
          ? 'background: linear-gradient(135deg, #ef4444, #f97316);'
          : 'background: linear-gradient(135deg, #f59e0b, #f97316);'"
        @click="goToSubscription"
      >兑换会员</button>
    </div>
  </div>
</template>
