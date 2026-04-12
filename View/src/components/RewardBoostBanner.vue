<script setup lang="ts">
import { ref } from 'vue'
import type { EngagementRewardGrant } from '../types/paper'
import { rewardIcon } from '../composables/useEngagement'

const props = withDefaults(defineProps<{
  reward: EngagementRewardGrant | null
  /** Whether the user has checked the "use reward" toggle */
  modelValue: boolean
  /** Loading state while applying reward */
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

// When enabling, show a lightweight inline confirmation before emitting true.
// Disabling is always instant (no friction on undo).
const confirming = ref(false)

function handleClick() {
  if (!props.reward) return
  if (props.modelValue) {
    // Toggling OFF — instant, no confirmation needed
    emit('update:modelValue', false)
  } else {
    // Toggling ON — request confirmation first
    confirming.value = true
  }
}

function confirmUse() {
  confirming.value = false
  emit('update:modelValue', true)
}

function cancelConfirm() {
  confirming.value = false
}

// rewardIcon imported from useEngagement.ts (P5)

function expiresText(expiresAt: string | null | undefined): string {
  if (!expiresAt) return ''
  const d = new Date(expiresAt)
  const now = new Date()
  const diffDays = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  const absDate = d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  if (diffDays <= 0) return '（已过期）'
  if (diffDays === 1) return `（今日到期 · ${absDate}）`
  return `（还剩 ${diffDays} 天 · ${absDate} 到期）`
}
</script>

<template>
  <div
    v-if="reward && reward.status === 'active'"
    class="rounded-xl border transition-colors select-none overflow-hidden"
    :class="modelValue
      ? 'border-tinder-green/50 bg-tinder-green/8'
      : confirming
        ? 'border-[#f59e0b]/50 bg-[#f59e0b]/6'
        : 'border-border bg-bg-elevated/60'"
  >
    <!-- Main row — C6: disable interaction while loading -->
    <div
      class="flex items-start gap-2.5 p-2.5 transition-colors"
      :class="loading ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:bg-bg-hover/30'"
      @click="loading ? undefined : handleClick()"
    >
      <span class="text-xl shrink-0 mt-0.5">{{ rewardIcon(reward.reward_code) }}</span>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-1.5 flex-wrap">
          <p class="text-xs font-semibold text-text-primary leading-tight">
            {{ reward.reward_name }}
          </p>
          <span
            v-if="reward.expires_at"
            class="text-[10px] text-text-muted"
          >{{ expiresText(reward.expires_at) }}</span>
        </div>
        <p class="text-[11px] text-text-secondary mt-0.5 leading-snug">
          {{ reward.description }}
        </p>
      </div>
      <!-- Toggle indicator -->
      <div class="shrink-0 flex items-center gap-1.5 mt-0.5">
        <span
          class="text-[10px] font-medium"
          :class="modelValue ? 'text-tinder-green' : confirming ? 'text-[#f59e0b]' : 'text-text-muted'"
        >{{ modelValue ? '已选择' : confirming ? '确认中…' : '点击使用' }}</span>
        <div
          class="w-8 h-4 rounded-full transition-colors relative"
          :class="modelValue ? 'bg-tinder-green' : 'bg-border'"
        >
          <div
            class="absolute top-0.5 w-3 h-3 rounded-full bg-white shadow-sm transition-all"
            :class="modelValue ? 'left-4' : 'left-0.5'"
          />
        </div>
      </div>
    </div>

    <!-- Inline confirmation bar (shown only when confirming) -->
    <div
      v-if="confirming"
      class="px-3 py-2 border-t border-[#f59e0b]/25 bg-[#f59e0b]/8 flex items-center justify-between gap-2"
    >
      <!-- C6: loading state while applying reward -->
      <template v-if="loading">
        <div class="flex items-center gap-2 flex-1">
          <svg class="w-3.5 h-3.5 animate-spin text-[#f59e0b] shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
          </svg>
          <p class="text-[10px] text-[#f59e0b]">正在使用奖励…</p>
        </div>
      </template>
      <template v-else>
        <p class="text-[10px] text-text-secondary leading-snug flex-1">
          确认后将在本次操作中消耗此券，消耗后<strong class="text-text-primary">无法撤销</strong>。
        </p>
        <div class="flex items-center gap-2 shrink-0">
          <button
            class="px-2.5 py-1 rounded-lg bg-[#f59e0b]/15 border border-[#f59e0b]/30 text-[10px] font-semibold text-[#f59e0b] hover:bg-[#f59e0b]/25 transition-colors cursor-pointer"
            @click.stop="confirmUse"
          >确认使用</button>
          <button
            class="text-[10px] text-text-muted hover:text-text-secondary transition-colors cursor-pointer px-1"
            @click.stop="cancelConfirm"
          >取消</button>
        </div>
      </template>
    </div>
  </div>
</template>
