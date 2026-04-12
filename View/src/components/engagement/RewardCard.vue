<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { EngagementRewardGrant } from '../../types/paper'
import { rewardIcon, rewardStatusLabel, rewardStatusClass, isHonoraryReward, REWARD_USAGE_HINTS } from '../../composables/useEngagement'

const props = withDefaults(defineProps<{
  reward: EngagementRewardGrant
  /** Show CTA / usage hint */
  showCta?: boolean
  /** Compact single-row list variant (for EngagementPanel dropdown) */
  compact?: boolean
}>(), {
  showCta: true,
  compact: false,
})

const router = useRouter()

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function expiresText(expiresAt?: string | null): string {
  if (!expiresAt) return ''
  const d = new Date(expiresAt)
  const now = new Date()
  const diffDays = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  const absDate = formatDate(expiresAt)
  if (diffDays <= 0) return '已过期'
  if (diffDays === 1) return `今日到期 · ${absDate}`
  return `还剩 ${diffDays} 天 · ${absDate} 到期`
}

const isHonorary = computed(() => isHonoraryReward(props.reward.reward_code))
const hint = computed(() => REWARD_USAGE_HINTS[props.reward.reward_code] ?? null)
const statusClass = computed(() => rewardStatusClass(props.reward.status))

const expiryClass = computed(() => {
  if (!props.reward.expires_at) return ''
  const diffDays = Math.ceil((new Date(props.reward.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  if (diffDays <= 1) return 'text-red-400'
  if (diffDays <= 3) return 'text-amber-400'
  return 'text-text-muted'
})
</script>

<template>
  <!-- Compact variant: single row for panels/dropdowns -->
  <div v-if="compact" class="flex items-start gap-2.5">
    <span class="text-base shrink-0 mt-0.5 leading-none">{{ rewardIcon(reward.reward_code, reward.streak_day) }}</span>
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-1.5 flex-wrap">
        <p class="text-xs font-medium text-text-primary truncate">{{ reward.reward_name }}</p>
        <span class="text-[9px] font-bold px-1 py-0.5 rounded leading-none" :class="statusClass">
          {{ rewardStatusLabel(reward.status) }}
        </span>
      </div>
      <p class="text-[10px] text-text-muted mt-0.5">
        第 {{ reward.streak_day }} 天里程碑
        <span v-if="reward.expires_at && reward.status === 'active'" class="ml-1" :class="expiryClass">
          · {{ expiresText(reward.expires_at) }}
        </span>
      </p>
    </div>
  </div>

  <!-- Full card variant for achievements page -->
  <div v-else class="flex items-start gap-3 py-0.5">
    <!-- Icon -->
    <span class="text-xl shrink-0 mt-0.5 leading-none">{{ rewardIcon(reward.reward_code, reward.streak_day) }}</span>

    <div class="min-w-0 flex-1">
      <!-- Title row -->
      <div class="flex items-center gap-2 flex-wrap mb-0.5">
        <span class="text-sm font-semibold text-text-primary">{{ reward.reward_name }}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none" :class="statusClass">
          {{ rewardStatusLabel(reward.status) }}
        </span>
        <span v-if="isHonorary" class="text-[10px] text-text-muted">永久荣誉</span>
      </div>

      <!-- Description -->
      <p class="text-xs text-text-secondary leading-snug mb-1">{{ reward.description }}</p>

      <!-- Meta: dates -->
      <p class="text-[10px] text-text-muted leading-snug">
        <span>获得于 {{ formatDate(reward.created_at) }}</span>
        <template v-if="reward.used_at">
          <span class="mx-1">·</span>
          <span>使用于 {{ formatDate(reward.used_at) }}</span>
        </template>
        <template v-else-if="reward.expires_at && reward.status === 'active'">
          <span class="mx-1">·</span>
          <span :class="expiryClass">有效期至 {{ formatDate(reward.expires_at) }}</span>
        </template>
        <template v-else-if="reward.expires_at && reward.status === 'expired'">
          <span class="mx-1">·</span>
          <span class="text-text-muted">已于 {{ formatDate(reward.expires_at) }} 过期</span>
        </template>
        <template v-if="reward.used_context">
          <span class="mx-1">·</span>
          <span>{{ reward.used_context }}</span>
        </template>
      </p>

      <!-- CTA for active, non-honorary functional tickets -->
      <template v-if="showCta && reward.status === 'active' && !isHonorary && hint">
        <div class="mt-2 rounded-lg bg-tinder-gold/6 border border-tinder-gold/15 px-2.5 py-2">
          <p class="text-[10px] text-text-secondary leading-snug mb-1.5">
            💡 {{ hint.text }}
          </p>
          <button
            v-if="hint.route"
            class="px-2.5 py-1 rounded-lg bg-tinder-gold/10 border border-tinder-gold/25 text-[10px] font-semibold text-tinder-gold hover:bg-tinder-gold/20 transition-colors cursor-pointer"
            @click="router.push(hint.route)"
          >
            {{ hint.routeLabel ?? '前往使用' }} →
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
