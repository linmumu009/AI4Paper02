<script setup lang="ts">
/**
 * EngagementPanel — The dropdown panel shown when the Navbar pill is clicked.
 * Extracted from EngagementProgressBar to separate concerns.
 */
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { TaskItem } from '../../composables/useEngagement'
import {
  useEngagement,
  rewardIcon,
  rewardStatusLabel,
  rewardStatusColor,
  MILESTONE_REWARD_PREVIEW,
} from '../../composables/useEngagement'
import RewardCard from './RewardCard.vue'

const props = defineProps<{
  taskItems: TaskItem[]
}>()

const router = useRouter()
const freezeApplying = ref(false)

const {
  status, loading, loadStatus,
  streakBroken, dismissStreakBroken,
  progressText, streakText,
  hasNewRewards, isNewReward, markRewardsRead,
  freezeStatus, applyStreakFreeze,
} = useEngagement()

async function handleApplyFreeze() {
  if (freezeApplying.value) return
  freezeApplying.value = true
  try {
    await applyStreakFreeze()
    dismissStreakBroken()
  } finally {
    freezeApplying.value = false
  }
}

const INTRO_SEEN_KEY = 'engagement-intro-seen:v1'
function _loadIntroSeen(): boolean {
  try { return localStorage.getItem(INTRO_SEEN_KEY) === '1' } catch { return false }
}
const introSeen = ref(_loadIntroSeen())
function dismissIntro() {
  introSeen.value = true
  try { localStorage.setItem(INTRO_SEEN_KEY, '1') } catch { /* ignore */ }
}

function goToAchievements() {
  dismissIntro()
  router.push('/profile?tab=achievements')
}

// Next milestone hint
const nextMilestoneHint = computed(() => {
  const streak = status.value?.streak
  if (!streak) return ''
  const next = streak.next_milestones?.[0]
  if (!next) return '已解锁所有里程碑！'
  const diff = next - streak.current
  if (diff === 1) return `再坚持 1 天即可解锁第 ${next} 天奖励`
  return `再坚持 ${diff} 天即可解锁第 ${next} 天奖励`
})

const nextMilestonePreview = computed(() => {
  const streak = status.value?.streak
  if (!streak) return null
  const next = streak.next_milestones?.[0]
  if (!next) return null
  return MILESTONE_REWARD_PREVIEW[next] ?? null
})

const nextMilestoneDay = computed(() => status.value?.streak?.next_milestones?.[0])

const activeRewards = computed(() =>
  (status.value?.rewards ?? []).filter(r => r.status === 'active')
)
const allRewards = computed(() => status.value?.rewards ?? [])

// Day-14 Pro Trial
const day14TrialHint = computed(() => {
  const s = status.value
  if (!s) return null
  if (s.streak.current >= 14) return null
  const isFree = !s.tier || s.tier === 'free'
  if (!isFree || s.trial_granted) return null
  return { daysLeft: 14 - s.streak.current }
})

// P6: task just-completed pulse
const justCompletedKeys = ref(new Set<string>())
watch(
  () => props.taskItems,
  (newItems, oldItems) => {
    if (!oldItems?.length) return
    newItems.forEach((item, idx) => {
      const prev = oldItems[idx]
      if (prev && !prev.done && item.done) {
        justCompletedKeys.value = new Set([...justCompletedKeys.value, item.key])
        setTimeout(() => {
          justCompletedKeys.value.delete(item.key)
          justCompletedKeys.value = new Set(justCompletedKeys.value)
        }, 700)
      }
    })
  },
  { deep: true },
)

const allDone = computed(() => status.value?.progress?.completed ?? false)
</script>

<template>
  <div class="w-full max-w-[288px] bg-bg-card border border-border rounded-2xl shadow-2xl overflow-hidden" @click.stop>

    <!-- Intro banner (one-time) -->
    <div
      v-if="!introSeen"
      class="px-4 pt-3 pb-2.5 border-b border-tinder-gold/20 bg-tinder-gold/6 flex items-start gap-2"
    >
      <span class="text-base shrink-0 leading-none mt-0.5">🎯</span>
      <div class="min-w-0 flex-1">
        <p class="text-[11px] font-semibold text-text-primary leading-snug">每日研究激励</p>
        <p class="text-[10px] text-text-secondary mt-0.5 leading-snug">
          每天完成<strong class="text-text-primary">浏览 · 收藏 · 分析</strong>三项任务，连续坚持可解锁对比扩展、深度研究增强等实用特权。
          <span class="text-text-muted">（向 AI 提问即算"分析"，每日 10 次免费）</span>
        </p>
        <div class="flex items-center gap-3 mt-1.5">
          <button class="text-[10px] font-semibold text-tinder-gold hover:underline cursor-pointer" @click.stop="goToAchievements">查看奖励规则 →</button>
          <button class="text-[10px] text-text-muted hover:text-text-secondary cursor-pointer" @click.stop="dismissIntro">知道了</button>
        </div>
      </div>
    </div>

    <!-- Streak break banner -->
    <div
      v-if="streakBroken"
      class="px-4 pt-3 pb-2.5 border-b border-amber-500/20 bg-amber-500/6"
    >
      <div class="flex items-start gap-2">
        <span class="text-base shrink-0 leading-none mt-0.5">💪</span>
        <div class="min-w-0 flex-1">
          <p class="text-[11px] font-semibold text-text-primary leading-snug">连续研究记录中断了</p>
          <p class="text-[10px] text-text-secondary mt-0.5 leading-snug">今天重新开始，完成三项任务即可重新积累连续天数</p>
        </div>
        <button class="shrink-0 text-text-muted hover:text-text-secondary bg-transparent border-none cursor-pointer p-0.5 mt-0.5" @click.stop="dismissStreakBroken">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <!-- Streak freeze button -->
      <div v-if="freezeStatus?.freeze_allowed" class="mt-2 flex items-center gap-2">
        <button
          class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border bg-tinder-gold/10 border-tinder-gold/30 text-tinder-gold hover:bg-tinder-gold/20 transition-colors cursor-pointer disabled:opacity-50"
          :disabled="freezeApplying"
          @click.stop="handleApplyFreeze"
        >
          <span>🛡️</span>
          <span>{{ freezeApplying ? '保护中...' : '使用连续保护' }}</span>
        </button>
        <span class="text-[10px] text-text-muted">剩余 {{ freezeStatus.freeze_remaining }} 次/月</span>
      </div>
    </div>

    <!-- Progress summary header -->
    <div class="px-4 pt-3 pb-2.5 border-b border-border bg-bg-elevated/50">
      <!-- Streak arc indicator -->
      <div class="flex items-center gap-3 mb-2">
        <div class="flex flex-col">
          <span class="text-[11px] font-semibold text-text-primary">{{ progressText }}</span>
          <span class="text-[10px] text-text-secondary mt-0.5">{{ streakText }}</span>
        </div>
        <div class="ml-auto flex items-center gap-1.5">
          <span v-if="allDone" class="text-sm">🔥</span>
          <span class="text-lg font-bold" :class="allDone ? 'text-tinder-gold' : 'text-text-primary'">
            {{ status?.streak?.current ?? 0 }}
          </span>
          <span class="text-[10px] text-text-muted">天</span>
        </div>
      </div>

      <!-- Mini progress track -->
      <div class="flex items-center gap-1.5">
        <div
          v-for="item in taskItems"
          :key="item.key"
          class="flex-1 h-1 rounded-full transition-colors duration-300"
          :class="item.done ? 'bg-tinder-gold' : 'bg-bg-elevated'"
        />
      </div>
    </div>

    <!-- Task list -->
    <div class="px-4 py-3 border-b border-border space-y-2">
      <div v-for="item in taskItems" :key="item.key" class="flex items-start gap-2.5">
        <span
          :class="[
            'mt-0.5 shrink-0 inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-bold transition-colors',
            item.done ? 'bg-tinder-gold/20 text-tinder-gold' : 'bg-bg-elevated border border-border text-text-muted',
            justCompletedKeys.has(item.key) ? 'animate-ping-once ring-2 ring-tinder-gold/40' : '',
          ]"
        >{{ item.done ? '✓' : '○' }}</span>
        <div class="min-w-0">
          <p class="text-xs font-medium leading-tight" :class="item.done ? 'text-text-primary' : 'text-text-secondary'">{{ item.label }}</p>
          <p v-if="!item.done" class="text-[10px] text-text-muted leading-snug mt-0.5">{{ item.hint }}</p>
          <p v-else class="text-[10px] text-tinder-gold mt-0.5">已完成</p>
        </div>
      </div>
    </div>

    <!-- Day-14 Pro Trial hint -->
    <div
      v-if="day14TrialHint"
      class="mx-3 mt-2 rounded-xl border border-[#6366f1]/30 bg-[#6366f1]/8 px-3 py-2.5"
    >
      <div class="flex items-center gap-2 mb-1">
        <span class="text-sm shrink-0">🎁</span>
        <p class="text-[11px] font-semibold text-[#a5b4fc] leading-tight">
          再坚持 {{ day14TrialHint.daysLeft }} 天 → 解锁 3 天 Pro 试用
        </p>
      </div>
      <p class="text-[10px] text-text-muted leading-snug">
        连续研究 14 天后，免费用户可获得 3 天 Pro 试用——包含无限 AI 问答、全文翻译、DOCX/PDF 导出等全部 Pro 权益。
      </p>
    </div>

    <!-- Next milestone preview -->
    <div v-if="nextMilestoneHint" class="px-4 py-2.5 border-b border-border bg-bg-elevated/30">
      <p class="text-[10px] text-text-muted italic mb-1.5">{{ nextMilestoneHint }}</p>
      <div v-if="nextMilestonePreview" class="flex items-center gap-2 bg-bg-card rounded-lg px-2.5 py-1.5">
        <span class="text-sm shrink-0">{{ rewardIcon(nextMilestonePreview.code) }}</span>
        <div class="min-w-0">
          <p class="text-[11px] font-semibold text-text-primary leading-tight">{{ nextMilestonePreview.name }}</p>
          <p class="text-[10px] text-text-muted leading-tight mt-0.5">{{ nextMilestonePreview.brief }}</p>
        </div>
      </div>
    </div>

    <!-- Rewards section -->
    <div class="px-4 py-3">
      <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-2.5">我的奖励</p>

      <!-- Empty state -->
      <div v-if="allRewards.length === 0" class="flex flex-col items-center py-3 gap-1.5">
        <span class="text-2xl">🎯</span>
        <p class="text-[10px] text-text-muted text-center leading-snug">
          每日完成三项任务，连续研究可解锁对比扩展、深度研究增强等实用特权
        </p>
      </div>

      <!-- Reward list (up to 5) -->
      <div v-else class="space-y-2.5">
        <div
          v-for="r in allRewards.slice(0, 5)"
          :key="r.id ?? r.reward_code"
          class="relative"
        >
          <!-- NEW badge -->
          <span
            v-if="isNewReward(r.reward_code)"
            class="absolute -top-1 -right-1 z-10 text-[8px] font-bold px-1 py-0.5 rounded bg-amber-400/20 text-amber-400 leading-none border border-amber-400/30"
          >NEW</span>
          <RewardCard :reward="r" compact :show-cta="false" />
        </div>
      </div>

      <!-- Footer link -->
      <div class="mt-3 pt-2.5 border-t border-border flex items-center justify-between">
        <span v-if="allRewards.length > 5" class="text-[10px] text-text-muted">共 {{ allRewards.length }} 条奖励</span>
        <span v-else class="text-[10px] text-transparent select-none">·</span>
        <button
          class="text-[10px] font-medium text-text-muted hover:text-tinder-gold transition-colors cursor-pointer"
          @click.stop="goToAchievements"
        >查看规则 &amp; 全部奖励 →</button>
      </div>
    </div>
  </div>
</template>
