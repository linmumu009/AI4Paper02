<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useEngagement, REWARD_USAGE_HINTS, isHonoraryReward, rewardIcon, type EngagementToastItem } from '../composables/useEngagement'

const { toastQueue, dismissToast } = useEngagement()
const router = useRouter()

const AUTO_DISMISS_MS: Record<EngagementToastItem['type'], number> = {
  task_done:       2000,
  completion:      5000,
  milestone:       9000,
  streak_break:    4000,
  reward_expiring: 7000,
  reward_error:    5000,
  reward_used:     3000,
  freeze_success:  5000,
  freeze_error:    5000,
  pro_trial:       10000,
}

const _dismissTimers = new Map<number, ReturnType<typeof setTimeout>>()

watch(
  toastQueue,
  (queue) => {
    for (const toast of queue) {
      if (!_dismissTimers.has(toast.id)) {
        const delay = AUTO_DISMISS_MS[toast.type] ?? 4000
        const timer = setTimeout(() => {
          dismissToast(toast.id)
          _dismissTimers.delete(toast.id)
        }, delay)
        _dismissTimers.set(toast.id, timer)
      }
    }
  },
  { deep: true },
)

function navigateAndDismiss(id: number, route: string) {
  dismissToast(id)
  router.push(route)
}

// Toast border/bg classes per type
function toastWrapClass(type: EngagementToastItem['type']): string {
  switch (type) {
    case 'task_done':    return 'border-tinder-gold/25'
    case 'completion':
    case 'freeze_success': return 'border-tinder-gold/40'
    case 'milestone':   return 'border-tinder-gold/40'
    case 'streak_break': return 'border-border'
    case 'reward_expiring': return 'border-amber-500/40'
    case 'reward_error':
    case 'freeze_error': return 'border-tinder-pink/40'
    case 'reward_used':
    case 'pro_trial':   return 'border-[#6366f1]/40'
    default: return 'border-border'
  }
}
</script>

<template>
  <!-- Fixed toast stack, bottom-center above FAB area -->
  <div
    class="fixed bottom-24 left-1/2 -translate-x-1/2 z-[80] flex flex-col items-center gap-2 pointer-events-none"
    aria-live="polite"
  >
    <TransitionGroup
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-4 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 translate-y-2 scale-95"
    >
      <div
        v-for="toast in toastQueue"
        :key="toast.id"
        class="pointer-events-auto w-[min(90vw,300px)] rounded-2xl shadow-2xl overflow-hidden bg-bg-card border"
        :class="toastWrapClass(toast.type)"
      >

        <!-- ── task_done: brief chip ── -->
        <template v-if="toast.type === 'task_done'">
          <div class="px-3.5 py-2.5 flex items-center gap-2.5">
            <span class="text-lg shrink-0 leading-none">
              {{ toast.action === 'view' ? '👁️' : toast.action === 'collect' ? '❤️' : '🧠' }}
            </span>
            <p class="text-sm font-medium text-text-primary flex-1 leading-snug">
              {{ toast.action === 'view' ? '浏览任务完成' : toast.action === 'collect' ? '收藏任务完成' : '分析任务完成' }}
              <span class="text-tinder-gold ml-1 font-bold">✓</span>
            </p>
            <button class="shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── completion ── -->
        <template v-else-if="toast.type === 'completion'">
          <div class="px-4 py-3 flex items-start gap-3">
            <span class="text-2xl shrink-0 mt-0.5">🎉</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-text-primary leading-snug">今日研究任务全部完成！</p>
              <p class="text-xs text-tinder-gold mt-1">🔥 连续有效研究 {{ toast.streak ?? 0 }} 天</p>
              <p v-if="toast.nextMilestone" class="text-[11px] text-text-muted mt-1 leading-snug">
                下一里程碑：第 {{ toast.nextMilestone.day }} 天 — {{ toast.nextMilestone.name }}
              </p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── milestone: confetti shimmer ── -->
        <template v-else-if="toast.type === 'milestone'">
          <!-- Confetti shimmer header strip -->
          <div class="h-1 w-full bg-gradient-to-r from-tinder-gold via-tinder-pink to-tinder-gold bg-[length:200%] animate-[bgShift_2s_linear_infinite]" />
          <div class="px-4 py-3">
            <div class="flex items-start gap-3 mb-2.5">
              <span class="text-2xl shrink-0 mt-0.5">🏆</span>
              <div class="min-w-0 flex-1">
                <p class="text-sm font-semibold text-text-primary leading-snug">
                  第 {{ toast.reward?.streak_day }} 天里程碑达成！
                </p>
                <p class="text-xs text-tinder-gold mt-0.5">🔥 连续研究 {{ toast.streak ?? 0 }} 天</p>
              </div>
              <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <!-- Reward box -->
            <div class="bg-tinder-gold/10 border border-tinder-gold/20 rounded-xl px-3 py-2.5 mb-2.5">
              <div class="flex items-center gap-1.5 mb-0.5">
                <span class="text-sm">{{ rewardIcon(toast.reward?.reward_code ?? '', toast.reward?.streak_day) }}</span>
                <p class="text-xs font-semibold text-tinder-gold">{{ toast.reward?.reward_name }}</p>
              </div>
              <p class="text-[11px] text-text-secondary leading-snug">{{ toast.reward?.description }}</p>
            </div>
            <!-- Usage hint + CTA for functional tickets -->
            <template v-if="toast.reward && !isHonoraryReward(toast.reward.reward_code) && REWARD_USAGE_HINTS[toast.reward.reward_code]">
              <p class="text-[11px] text-text-muted leading-snug mb-2">💡 {{ REWARD_USAGE_HINTS[toast.reward.reward_code].text }}</p>
              <button
                v-if="REWARD_USAGE_HINTS[toast.reward.reward_code].route"
                class="w-full py-1.5 rounded-lg bg-tinder-gold/20 border border-tinder-gold/30 text-xs font-semibold text-tinder-gold hover:bg-tinder-gold/30 transition-colors cursor-pointer"
                @click="navigateAndDismiss(toast.id, REWARD_USAGE_HINTS[toast.reward.reward_code].route!)"
              >{{ REWARD_USAGE_HINTS[toast.reward.reward_code].routeLabel ?? '前往使用' }}</button>
            </template>
          </div>
        </template>

        <!-- ── streak_break ── -->
        <template v-else-if="toast.type === 'streak_break'">
          <div class="px-4 py-3 flex items-start gap-3">
            <span class="text-2xl shrink-0 mt-0.5">💪</span>
            <div class="min-w-0">
              <p class="text-sm font-semibold text-text-primary leading-snug">连续研究记录中断了</p>
              <p class="text-xs text-text-secondary mt-1">今天重新开始，一步一步来</p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── reward_expiring ── -->
        <template v-else-if="toast.type === 'reward_expiring'">
          <div class="px-4 py-3">
            <div class="flex items-start gap-3 mb-2">
              <span class="text-2xl shrink-0 mt-0.5">⏰</span>
              <div class="min-w-0 flex-1">
                <p class="text-sm font-semibold text-text-primary leading-snug">奖励即将过期</p>
                <p class="text-xs text-amber-400 mt-0.5 font-medium">{{ toast.message }}</p>
              </div>
              <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div v-if="toast.reward" class="bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 mb-2">
              <div class="flex items-center gap-1.5">
                <span class="text-sm">{{ rewardIcon(toast.reward.reward_code, toast.reward.streak_day) }}</span>
                <p class="text-xs font-semibold text-amber-400">{{ toast.reward.reward_name }}</p>
              </div>
            </div>
            <template v-if="toast.reward && REWARD_USAGE_HINTS[toast.reward.reward_code]">
              <p class="text-[11px] text-text-muted leading-snug mb-2">💡 {{ REWARD_USAGE_HINTS[toast.reward.reward_code].text }}</p>
              <button
                v-if="REWARD_USAGE_HINTS[toast.reward.reward_code].route"
                class="w-full py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/25 text-xs font-semibold text-amber-400 hover:bg-amber-500/25 transition-colors cursor-pointer"
                @click="navigateAndDismiss(toast.id, REWARD_USAGE_HINTS[toast.reward.reward_code].route!)"
              >{{ REWARD_USAGE_HINTS[toast.reward.reward_code].routeLabel ?? '前往使用' }}</button>
            </template>
          </div>
        </template>

        <!-- ── reward_error ── -->
        <template v-else-if="toast.type === 'reward_error'">
          <div class="px-4 py-3 flex items-start gap-3">
            <span class="text-2xl shrink-0 mt-0.5">⚠️</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-text-primary leading-snug">奖励未能生效</p>
              <p class="text-xs text-text-secondary mt-1 leading-snug">{{ toast.message || '奖励使用失败，请稍后重试' }}</p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── reward_used ── -->
        <template v-else-if="toast.type === 'reward_used'">
          <div class="px-3.5 py-2.5 flex items-center gap-2.5">
            <span class="text-lg shrink-0 leading-none">✨</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-text-primary leading-snug">已启用：{{ toast.message }}</p>
              <p class="text-[11px] text-[#6366f1] mt-0.5">本次操作已应用奖励加成</p>
            </div>
            <button class="shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── freeze_success ── -->
        <template v-else-if="toast.type === 'freeze_success'">
          <div class="px-4 py-3 flex items-start gap-3">
            <span class="text-2xl shrink-0 mt-0.5">🛡️</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-text-primary leading-snug">连续保护已生效</p>
              <p class="text-xs text-tinder-gold mt-1 leading-snug">{{ toast.message }}</p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── freeze_error ── -->
        <template v-else-if="toast.type === 'freeze_error'">
          <div class="px-4 py-3 flex items-start gap-3">
            <span class="text-2xl shrink-0 mt-0.5">⚠️</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-text-primary leading-snug">连续保护未能生效</p>
              <p class="text-xs text-text-secondary mt-1 leading-snug">{{ toast.message }}</p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

        <!-- ── pro_trial ── -->
        <template v-else-if="toast.type === 'pro_trial'">
          <div class="px-4 py-3.5 flex items-start gap-3 bg-[#6366f1]/5">
            <span class="text-2xl shrink-0 mt-0.5">🎁</span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-bold text-text-primary leading-snug">Pro 试用已解锁！</p>
              <p class="text-xs text-blue-300 mt-1 leading-relaxed">{{ toast.message }}</p>
            </div>
            <button class="ml-auto shrink-0 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0.5" @click="dismissToast(toast.id)">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </template>

      </div>
    </TransitionGroup>
  </div>
</template>
