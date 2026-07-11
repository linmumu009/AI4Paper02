<script setup lang="ts">
/**
 * EngagementPanel — The dropdown panel shown when the Navbar pill is clicked.
 * Redesigned: 3-zone layout (Hero + Milestone/Rewards + Footer).
 */
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { TaskItem } from '../../composables/useEngagement'
import {
  useEngagement,
  rewardIcon,
  rewardStatusLabel,
  rewardStatusClass,
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
  if (diff === 1) return `再坚持 1 天`
  return `再坚持 ${diff} 天`
})

const nextMilestonePreview = computed(() => {
  const streak = status.value?.streak
  if (!streak) return null
  const next = streak.next_milestones?.[0]
  if (!next) return null
  return MILESTONE_REWARD_PREVIEW[next] ?? null
})

const nextMilestoneDay = computed(() => status.value?.streak?.next_milestones?.[0])

// Research outcome highlights for key milestone days — shown above the reward brief
const _OUTCOME_HINTS: Record<number, string> = {
  7:  '生成你的 7 日研究地图',
  14: '解锁领域趋势摘要',
  30: '查看 30 天主题演化',
}
const nextMilestoneOutcomeHint = computed<string | null>(() => {
  const day = nextMilestoneDay.value
  return day ? (_OUTCOME_HINTS[day] ?? null) : null
})

const activeRewards = computed(() =>
  (status.value?.rewards ?? []).filter(r => r.status === 'active')
)
const allRewards = computed(() => status.value?.rewards ?? [])
const displayedRewards = computed(() => allRewards.value.slice(0, 3))
const hiddenRewardCount = computed(() => Math.max(0, allRewards.value.length - 3))

// Day-14 Pro Trial
const day14TrialHint = computed(() => {
  const s = status.value
  if (!s) return null
  if (s.streak.current >= 14) return null
  const isFree = !s.tier || s.tier === 'free'
  if (!isFree || s.trial_granted) return null
  return { daysLeft: 14 - s.streak.current }
})

// Circular progress ring values
const RING_R = 28
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R

const arcFraction = computed(() => {
  const streak = status.value?.streak
  if (!streak) return 0
  const next = streak.next_milestones?.[0]
  if (!next) return 1
  const MILESTONES = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]
  const nextIdx = MILESTONES.indexOf(next)
  const prevMilestone = nextIdx > 0 ? MILESTONES[nextIdx - 1]! : 0
  const range = next - prevMilestone
  const done = Math.max(0, streak.current - prevMilestone)
  return Math.min(1, done / range)
})

const arcDashOffset = computed(() => RING_CIRCUMFERENCE * (1 - arcFraction.value))

const arcColor = computed(() => {
  const c = status.value?.streak?.current ?? 0
  if (c >= 14) return '#a855f7'
  if (c >= 7)  return '#f5b731'
  if (c >= 3)  return '#f5b731'
  return '#ff8c5a'
})

const allDone = computed(() => status.value?.progress?.completed ?? false)
const streakCurrent = computed(() => status.value?.streak?.current ?? 0)
const doneCnt = computed(() => props.taskItems.filter(t => t.done).length)

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

const taskIcons: Record<string, string> = {
  view: '👁',
  collect: '❤️',
  analyze: '🧠',
}
</script>

<template>
  <div class="w-[340px] bg-bg-card border border-border rounded-2xl shadow-2xl overflow-hidden" @click.stop>

    <!-- ── Intro banner (one-time, lightweight) ── -->
    <div
      v-if="!introSeen"
      class="flex items-center gap-2.5 px-4 py-2.5 border-b border-border/60 bg-tinder-gold/5"
    >
      <span class="text-sm shrink-0">🎯</span>
      <p class="text-[11px] text-text-secondary leading-snug flex-1 min-w-0">
        完成三项任务，连续坚持解锁研究特权
        <button class="ml-1.5 text-tinder-gold hover:underline font-medium cursor-pointer" @click.stop="goToAchievements">了解 →</button>
      </p>
      <button class="shrink-0 text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer p-0.5 leading-none" @click.stop="dismissIntro">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <!-- ══════════════════════════════════════════ -->
    <!-- Zone 1: Hero — streak ring + task list     -->
    <!-- ══════════════════════════════════════════ -->
    <div class="px-5 py-4 flex items-center gap-4">

      <!-- Left: circular streak ring -->
      <div class="shrink-0 flex flex-col items-center gap-1">
        <div class="relative w-[72px] h-[72px]">
          <svg class="w-[72px] h-[72px] -rotate-90" viewBox="0 0 72 72">
            <!-- Track -->
            <circle cx="36" cy="36" :r="RING_R" fill="none" stroke="var(--color-bg-elevated)" stroke-width="6" />
            <!-- Progress arc -->
            <circle
              cx="36" cy="36" :r="RING_R"
              fill="none" :stroke="arcColor" stroke-width="6"
              stroke-linecap="round"
              :stroke-dasharray="RING_CIRCUMFERENCE"
              :stroke-dashoffset="arcDashOffset"
              class="transition-all duration-700"
            />
          </svg>
          <!-- Center: streak count -->
          <div class="absolute inset-0 flex flex-col items-center justify-center">
            <span
              class="text-xl font-bold leading-none"
              :class="allDone ? 'text-tinder-gold' : 'text-text-primary'"
            >{{ streakCurrent }}</span>
            <span class="text-[10px] text-text-muted mt-0.5">天</span>
          </div>
        </div>

        <!-- Streak break inline notice -->
        <template v-if="streakBroken">
          <span class="text-[10px] text-tinder-pink leading-none text-center">记录中断</span>
          <button
            v-if="freezeStatus?.freeze_allowed"
            class="mt-1 text-[10px] font-semibold text-tinder-gold border border-tinder-gold/30 bg-tinder-gold/8 rounded-full px-2 py-0.5 cursor-pointer hover:bg-tinder-gold/20 transition-colors disabled:opacity-50"
            :disabled="freezeApplying"
            @click.stop="handleApplyFreeze"
          >🛡 保护</button>
          <button v-else class="mt-0.5 text-[10px] text-text-muted cursor-pointer bg-transparent border-none hover:text-text-secondary" @click.stop="dismissStreakBroken">知道了</button>
        </template>
        <template v-else>
          <span class="text-[10px] text-text-muted leading-none">连续研究</span>
        </template>
      </div>

      <!-- Right: task checklist -->
      <div class="flex-1 min-w-0 space-y-2.5">
        <!-- Progress label -->
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-semibold text-text-primary">今日任务</span>
          <span
            class="text-[11px] font-bold tabular-nums"
            :class="allDone ? 'text-tinder-gold' : 'text-text-secondary'"
          >{{ doneCnt }}/{{ taskItems.length }}</span>
        </div>
        <!-- Tasks -->
        <div
          v-for="item in taskItems"
          :key="item.key"
          class="flex items-center gap-2.5"
        >
          <!-- Check indicator -->
          <span
            class="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-300"
            :class="[
              item.done
                ? 'bg-tinder-gold/20 text-tinder-gold'
                : 'bg-bg-elevated border border-border/80 text-text-muted',
              justCompletedKeys.has(item.key) ? 'scale-110' : ''
            ]"
          >
            <span v-if="item.done">✓</span>
            <span v-else class="text-base leading-none opacity-60">{{ taskIcons[item.key] }}</span>
          </span>
          <!-- Label -->
          <div class="min-w-0 flex-1">
            <span
              class="text-[13px] leading-none font-medium"
              :class="item.done ? 'text-text-primary' : 'text-text-secondary'"
            >{{ item.label }}</span>
            <p v-if="!item.done" class="text-[11px] text-text-muted leading-snug mt-0.5 truncate">{{ item.hint }}</p>
          </div>
        </div>

        <!-- Mini progress track -->
        <div class="flex items-center gap-1 pt-1">
          <div
            v-for="item in taskItems"
            :key="item.key"
            class="flex-1 h-1 rounded-full transition-colors duration-300"
            :class="item.done ? 'bg-tinder-gold' : 'bg-bg-elevated'"
          />
        </div>
      </div>
    </div>

    <!-- ══════════════════════════════════════════ -->
    <!-- Zone 2: Milestone preview + Rewards        -->
    <!-- ══════════════════════════════════════════ -->
    <div class="px-5 py-3.5 border-t border-border/40 space-y-3">

      <!-- Next milestone card -->
      <div v-if="nextMilestonePreview" class="flex items-center gap-3 rounded-xl bg-bg-elevated/60 border border-border/50 px-3 py-2.5">
        <span class="text-xl shrink-0">{{ rewardIcon(nextMilestonePreview.code) }}</span>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <p class="text-[13px] font-semibold text-text-primary leading-tight truncate">{{ nextMilestonePreview.name }}</p>
            <span class="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-tinder-gold/12 text-tinder-gold border border-tinder-gold/25 leading-none whitespace-nowrap">
              {{ nextMilestoneHint }} → 第 {{ nextMilestoneDay }} 天
            </span>
          </div>
          <!-- Research outcome hint — shown for days 7/14/30 -->
          <p v-if="nextMilestoneOutcomeHint" class="text-[12px] font-semibold text-tinder-purple mt-1 leading-snug">
            🗺 {{ nextMilestoneOutcomeHint }}
          </p>
          <p class="text-[11px] text-text-muted mt-0.5 leading-snug line-clamp-1"
            :class="nextMilestoneOutcomeHint ? 'opacity-70' : ''"
          >{{ nextMilestonePreview.brief }}</p>
          <!-- Pro trial hint merged here -->
          <p v-if="day14TrialHint" class="text-[11px] text-[#a5b4fc] mt-1 leading-snug">
            🎁 坚持到第 14 天 → 3 天 Pro 试用
          </p>
        </div>
      </div>

      <!-- All milestones unlocked -->
      <div v-else-if="!loading && status" class="flex items-center gap-2 rounded-xl bg-tinder-gold/6 border border-tinder-gold/20 px-3 py-2.5">
        <span class="text-lg shrink-0">🌟</span>
        <p class="text-[12px] font-semibold text-tinder-gold leading-snug">所有里程碑已解锁！</p>
      </div>

      <!-- Rewards list -->
      <div v-if="allRewards.length > 0">
        <p class="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-2">我的奖励</p>
        <div class="space-y-2">
          <div
            v-for="r in displayedRewards"
            :key="r.id ?? r.reward_code"
            class="relative"
          >
            <span
              v-if="isNewReward(r.reward_code)"
              class="absolute -top-1 -right-1 z-10 text-[8px] font-bold px-1 py-0.5 rounded bg-amber-400/20 text-amber-400 leading-none border border-amber-400/30"
            >NEW</span>
            <RewardCard :reward="r" compact :show-cta="false" />
          </div>
        </div>
      </div>

      <!-- Empty rewards -->
      <div v-else-if="!loading" class="flex flex-col items-center py-2 gap-1.5 text-center">
        <p class="text-[11px] text-text-muted leading-snug">每日完成任务，连续研究解锁特权</p>
      </div>

    </div>

    <!-- ══════════════════════════════════════════ -->
    <!-- Zone 3: Footer                             -->
    <!-- ══════════════════════════════════════════ -->
    <div class="px-5 py-3 border-t border-border/40 flex items-center justify-between">
      <span
        v-if="hiddenRewardCount > 0"
        class="text-[11px] text-text-muted"
      >另有 {{ hiddenRewardCount }} 条奖励</span>
      <span v-else class="text-[11px] text-transparent select-none">·</span>
      <button
        class="text-[11px] font-medium text-text-muted hover:text-tinder-gold transition-colors cursor-pointer bg-transparent border-none"
        @click.stop="goToAchievements"
      >查看规则 &amp; 全部奖励 →</button>
    </div>

  </div>
</template>
