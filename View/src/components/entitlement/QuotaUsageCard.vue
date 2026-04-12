<script setup lang="ts">
import { computed } from 'vue'
import { useEntitlements } from '../../composables/useEntitlements'
import type { UserEntitlements } from '../../types/paper'

const props = withDefaults(defineProps<{
  feature: keyof UserEntitlements['quotas']
  label: string
  icon: string
  /** If true, renders a compact single-row variant (for inline use in Sidebar etc.) */
  compact?: boolean
}>(), {
  compact: false,
})

const { quotaFraction, quotaSummary, remaining, limit, used, period } = useEntitlements()

const fraction = computed(() => quotaFraction(props.feature))
const summary = computed(() => quotaSummary(props.feature))
const isUnlimited = computed(() => limit(props.feature) === null)
const usedCount = computed(() => used(props.feature))
const limitCount = computed(() => limit(props.feature))
const periodLabel = computed(() => {
  const p = period(props.feature)
  return { daily: '今日', monthly: '本月', total: '总计' }[p ?? ''] ?? ''
})

// Status: normal (< 0.7), warning (0.7-0.9), danger (>= 0.9), exhausted (remaining == 0)
const status = computed(() => {
  if (isUnlimited.value) return 'unlimited'
  const rem = remaining(props.feature) ?? 0
  if (rem <= 0) return 'exhausted'
  const f = fraction.value
  if (f >= 0.9) return 'danger'
  if (f >= 0.7) return 'warning'
  return 'normal'
})

const borderClass = computed(() => {
  switch (status.value) {
    case 'exhausted': return 'border-red-500/50'
    case 'danger':    return 'border-red-500/30'
    case 'warning':   return 'border-amber-500/40'
    default:          return 'border-border'
  }
})

const pulseClass = computed(() =>
  status.value === 'exhausted' || status.value === 'danger' ? 'animate-pulse' : ''
)

const progressColor = computed(() => {
  switch (status.value) {
    case 'exhausted': return 'bg-red-500'
    case 'danger':    return 'bg-red-400'
    case 'warning':   return 'bg-amber-400'
    default:          return 'bg-tinder-blue'
  }
})

const iconBgClass = computed(() => {
  switch (status.value) {
    case 'exhausted': return 'bg-red-500/15 text-red-400'
    case 'danger':    return 'bg-red-500/10 text-red-400'
    case 'warning':   return 'bg-amber-500/15 text-amber-400'
    case 'unlimited': return 'bg-tinder-green/15 text-tinder-green'
    default:          return 'bg-tinder-blue/15 text-tinder-blue'
  }
})

const statusTextClass = computed(() => {
  switch (status.value) {
    case 'exhausted': return 'text-red-400'
    case 'danger':    return 'text-red-400'
    case 'warning':   return 'text-amber-400'
    case 'unlimited': return 'text-tinder-green'
    default:          return 'text-text-muted'
  }
})
</script>

<template>
  <!-- Compact variant: single row -->
  <div
    v-if="compact"
    class="flex items-center gap-2"
  >
    <span class="text-sm shrink-0">{{ icon }}</span>
    <span class="text-xs text-text-secondary w-24 shrink-0 truncate">{{ label }}</span>
    <template v-if="isUnlimited">
      <span class="text-xs text-tinder-green">不限次数</span>
    </template>
    <template v-else>
      <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-300"
          :class="progressColor"
          :style="`width: ${Math.min(100, fraction * 100)}%`"
        />
      </div>
      <span class="text-[11px] shrink-0 w-16 text-right" :class="statusTextClass">{{ summary }}</span>
    </template>
  </div>

  <!-- Card variant: full display -->
  <div
    v-else
    class="rounded-xl border p-3.5 bg-bg-card transition-all duration-200"
    :class="[borderClass, pulseClass && status === 'exhausted' ? 'border-opacity-80' : '']"
  >
    <!-- Header: icon + name + status badge -->
    <div class="flex items-start justify-between gap-2 mb-3">
      <div class="flex items-center gap-2">
        <div class="w-7 h-7 rounded-lg flex items-center justify-center text-sm shrink-0" :class="iconBgClass">
          {{ icon }}
        </div>
        <div>
          <p class="text-xs font-semibold text-text-primary leading-tight">{{ label }}</p>
          <p v-if="periodLabel" class="text-[10px] text-text-muted leading-none mt-0.5">{{ periodLabel }}</p>
        </div>
      </div>
      <!-- Status badge -->
      <span
        v-if="status === 'exhausted'"
        class="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 shrink-0 leading-none"
      >已耗尽</span>
      <span
        v-else-if="status === 'warning' || status === 'danger'"
        class="text-[9px] font-bold px-1.5 py-0.5 rounded-full shrink-0 leading-none"
        :class="status === 'danger' ? 'bg-red-500/15 text-red-400' : 'bg-amber-500/15 text-amber-400'"
      >即将耗尽</span>
      <span
        v-else-if="status === 'unlimited'"
        class="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-tinder-green/15 text-tinder-green shrink-0 leading-none"
      >不限</span>
    </div>

    <!-- Progress bar (hidden for unlimited) -->
    <template v-if="!isUnlimited">
      <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden mb-2">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="progressColor"
          :style="`width: ${Math.min(100, fraction * 100)}%`"
        />
      </div>
      <!-- Usage numbers -->
      <div class="flex items-center justify-between">
        <span class="text-[11px] text-text-muted">
          已用 {{ usedCount }} / {{ limitCount }}
        </span>
        <span class="text-[11px] font-medium" :class="statusTextClass">
          剩余 {{ remaining(feature) ?? 0 }}
        </span>
      </div>
    </template>

    <!-- Unlimited: just a checkmark line -->
    <template v-else>
      <div class="flex items-center gap-1.5">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-tinder-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <span class="text-[11px] text-tinder-green">不限次数</span>
      </div>
    </template>
  </div>
</template>
