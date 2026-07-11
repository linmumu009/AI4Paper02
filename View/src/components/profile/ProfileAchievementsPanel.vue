<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchActivityCalendar, fetchEngagementRewards } from '../../api'
import type { ActivityCalendarDay } from '../../api'
import type { EngagementRewardGrant } from '../../types/paper'
import { useEngagement } from '../../composables/useEngagement'
import { getApiErrorMessage, reportClientError } from '../../utils/apiError'
import ActivityCalendar from '../engagement/ActivityCalendar.vue'
import MilestoneTimeline from '../engagement/MilestoneTimeline.vue'
import RewardCard from '../engagement/RewardCard.vue'
import StreakHeroCard from '../engagement/StreakHeroCard.vue'

const MILESTONES = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]

const engagement = useEngagement()
const achievementRewards = ref<EngagementRewardGrant[]>([])
const activityCalendar = ref<ActivityCalendarDay[]>([])
const activityCalendarToday = ref('')
const loading = ref(false)
const errorMessage = ref('')

const unlockedMilestoneDays = computed(() =>
  new Set(achievementRewards.value.map(reward => reward.streak_day))
)

const nextMilestoneDay = computed(() =>
  engagement.status.value?.streak?.next_milestones?.[0] ?? null
)

const activeRewards = computed(() =>
  achievementRewards.value.filter(reward => reward.status === 'active')
)

const usedRewards = computed(() =>
  achievementRewards.value.filter(reward => reward.status === 'used')
)

const expiredRewards = computed(() =>
  achievementRewards.value.filter(reward => reward.status === 'expired')
)

async function loadAchievements() {
  if (loading.value) return

  loading.value = true
  errorMessage.value = ''

  try {
    const [, rewardsResponse, calendarResponse] = await Promise.all([
      engagement.loadStatus(true),
      fetchEngagementRewards({ limit: 200 }),
      fetchActivityCalendar(60),
    ])

    achievementRewards.value = rewardsResponse.rewards
    activityCalendar.value = calendarResponse.calendar
    activityCalendarToday.value = calendarResponse.today
  } catch (error) {
    reportClientError('profile.achievements.load', error, '研究成就加载失败，请稍后重试')
    errorMessage.value = getApiErrorMessage(error, '研究成就加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

onMounted(loadAchievements)
</script>

<template>
  <section class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8" aria-labelledby="achievements-title">
    <header class="mb-6">
      <h2 id="achievements-title" class="text-lg font-bold text-text-primary flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="8 21 12 17 16 21"/><line x1="12" y1="17" x2="12" y2="11"/><path d="M7 4H2v3a5 5 0 0 0 5 5h0"/><path d="M17 4h5v3a5 5 0 0 1-5 5h0"/><rect x="7" y="2" width="10" height="9" rx="1"/>
        </svg>
        研究成就
      </h2>
      <p class="text-xs text-text-muted mt-1">每日完成浏览、收藏、分析三项任务，连续研究可解锁对比扩展、深度分析等实用特权</p>
    </header>

    <div v-if="loading" class="flex items-center justify-center py-16" role="status" aria-live="polite">
      <svg class="w-6 h-6 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
      </svg>
      <span class="sr-only">正在加载研究成就</span>
    </div>

    <div v-else-if="errorMessage" class="rounded-xl border border-red-500/30 bg-red-500/5 px-5 py-8 text-center" role="alert">
      <p class="text-sm text-red-500">{{ errorMessage }}</p>
      <button type="button" class="mt-4 rounded-lg bg-tinder-green px-4 py-2 text-sm font-medium text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tinder-green focus-visible:ring-offset-2" @click="loadAchievements">
        重新加载
      </button>
    </div>

    <template v-else>
      <div class="mb-5">
        <StreakHeroCard
          :current-streak="engagement.status.value?.streak?.current ?? 0"
          :longest-streak="engagement.status.value?.streak?.longest ?? 0"
          :next-milestone-day="nextMilestoneDay"
        />
      </div>

      <div v-if="activityCalendar.length > 0" class="rounded-xl border border-border bg-bg-card p-4 mb-5">
        <h3 class="text-sm font-semibold text-text-primary mb-3">近 60 天研究记录</h3>
        <ActivityCalendar :days="activityCalendar" :today="activityCalendarToday" />
      </div>

      <div class="rounded-xl border border-border bg-bg-card p-4 mb-5">
        <h3 class="text-sm font-semibold text-text-primary mb-4">里程碑路线</h3>
        <MilestoneTimeline
          :current-streak="engagement.status.value?.streak?.current ?? 0"
          :milestones="MILESTONES"
          :unlocked-days="unlockedMilestoneDays"
        />
      </div>

      <div class="rounded-xl border border-border bg-bg-card overflow-hidden mb-5">
        <div class="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 class="text-sm font-semibold text-text-primary">奖励记录</h3>
          <span v-if="activeRewards.length > 0" class="text-[11px] px-2 py-0.5 rounded-full bg-tinder-green/15 text-tinder-green">
            {{ activeRewards.length }} 个可用
          </span>
        </div>
        <div v-if="achievementRewards.length === 0" class="flex flex-col items-center justify-center py-12">
          <span class="text-3xl mb-3" aria-hidden="true">🎯</span>
          <p class="text-sm text-text-muted">还没有奖励记录</p>
          <p class="text-xs text-text-muted mt-1">每日完成浏览、收藏、分析三项任务，连续研究可解锁奖励</p>
        </div>
        <div v-else class="px-4 py-3 space-y-4">
          <template v-if="activeRewards.length > 0">
            <p class="text-[10px] font-semibold text-tinder-green uppercase tracking-wide">可使用</p>
            <div class="space-y-3">
              <RewardCard v-for="reward in activeRewards" :key="reward.id ?? reward.reward_code" :reward="reward" :show-cta="true" />
            </div>
          </template>

          <template v-if="usedRewards.length > 0">
            <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide pt-2">已使用</p>
            <div class="space-y-3">
              <RewardCard v-for="reward in usedRewards" :key="reward.id ?? reward.reward_code" :reward="reward" :show-cta="false" />
            </div>
          </template>

          <template v-if="expiredRewards.length > 0">
            <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide pt-2">已过期</p>
            <div class="space-y-3 opacity-60">
              <RewardCard v-for="reward in expiredRewards" :key="reward.id ?? reward.reward_code" :reward="reward" :show-cta="false" />
            </div>
          </template>
        </div>
      </div>

      <div class="rounded-xl border border-border bg-bg-elevated/50 p-4">
        <h3 class="text-sm font-semibold text-text-primary mb-3">激励规则说明</h3>
        <ul class="space-y-2">
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-tinder-green">✓</span><span>每日完成 <strong class="text-text-primary">浏览 + 收藏 + 分析</strong> 三项任务，即可积累有效研究日</span></li>
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-tinder-green">✓</span><span>连续达到里程碑天数（1 / 2 / 3 / 4 / 5 / 7 / 14 / 30 / 60 / 100 天）时自动解锁对应奖励</span></li>
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span><span><strong class="text-text-primary">扩展对比券</strong>：使用后本次可对比最多 8 篇论文（默认限制 5 篇）</span></li>
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span><span><strong class="text-text-primary">深度研究加速券</strong>：使用后获得 1.5 倍分析上下文长度和更多论文精选范围</span></li>
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span><span><strong class="text-text-primary">快速处理加速券</strong>：上传论文时使用，论文将被优先处理分析</span></li>
          <li class="flex items-start gap-2 text-xs text-text-secondary"><span class="shrink-0 mt-0.5 text-text-muted">ℹ</span><span>功能券均有有效期（14-30 天），请及时使用；徽章类奖励永久保留</span></li>
        </ul>
      </div>
    </template>
  </section>
</template>
