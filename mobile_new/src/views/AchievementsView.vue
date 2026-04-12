<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import { useEngagement, MILESTONE_REWARD_PREVIEW, rewardIcon, rewardStatusClass, REWARD_USAGE_HINTS } from '@shared/composables/useEngagement'
import { fetchActivityCalendar } from '@shared/api/engagement'
import type { ActivityCalendarResponse } from '@shared/api/engagement'
import { toMobilePath } from '@/utils/seo'

const router = useRouter()
const { status, taskItems, loadStatus, record } = useEngagement()

const calendarData = ref<ActivityCalendarResponse | null>(null)
const loadingCalendar = ref(false)
const pageLoading = ref(true)

// --- Streak computed ---
const currentStreak = computed(() => status.value?.streak?.current ?? 0)
const longestStreak = computed(() => status.value?.streak?.longest ?? 0)
const nextMilestoneDay = computed(() => status.value?.streak?.next_milestones?.[0] ?? null)
const tasksDoneCount = computed(() => taskItems.value.filter((t) => t.done).length)
const milestoneProgress = computed(() => {
  if (!nextMilestoneDay.value) return 1
  const prev = prevMilestoneDay.value
  const span = nextMilestoneDay.value - prev
  const done = Math.max(0, currentStreak.value - prev)
  return span > 0 ? Math.min(1, done / span) : 1
})
const prevMilestoneDay = computed(() => {
  const days = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]
  const next = nextMilestoneDay.value ?? 0
  for (let i = days.length - 1; i >= 0; i--) {
    if (days[i] < next && days[i] <= currentStreak.value) return days[i]
  }
  return 0
})

// --- SVG ring ---
const RING_R = 42
const RING_CIRC = 2 * Math.PI * RING_R
const ringDash = computed(() => milestoneProgress.value * RING_CIRC)

// --- Milestones list ---
const allMilestoneDays = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]

// --- Rewards ---
const activeRewards = computed(() =>
  (status.value?.rewards ?? []).filter((r) => r.status === 'active'),
)

// --- Calendar ---
const grantedDays = computed(() => {
  const rewards = status.value?.rewards ?? []
  return new Set(rewards.map((r) => r.streak_day))
})

// --- Calendar: last 4 weeks (28 days), Mon→Sun rows ---
const calendarWeeks = computed(() => {
  if (!calendarData.value) return []
  const entries = calendarData.value.calendar
  const dayMap = new Map(entries.map((d) => [d.day_key, d]))
  const today = new Date()
  const todayStr = formatDate(today)

  // Build 28-day window ending today
  const cells: Array<{ date: string; completed: boolean; partial: boolean; isToday: boolean }> = []
  for (let i = 27; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const ds = formatDate(d)
    const info = dayMap.get(ds)
    cells.push({
      date: ds,
      completed: info?.completed ?? false,
      partial: info?.partial ?? false,
      isToday: ds === todayStr,
    })
  }

  // Group into 4 weeks (7 per week)
  const weeks: typeof cells[] = []
  for (let w = 0; w < 4; w++) {
    weeks.push(cells.slice(w * 7, w * 7 + 7))
  }
  return weeks
})

function formatDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function cellColor(cell: { completed: boolean; partial: boolean }): string {
  if (cell.completed) return 'bg-tinder-green'
  if (cell.partial) return 'bg-tinder-gold/60'
  return 'bg-bg-elevated border border-border/40'
}

function navigateReward(code: string) {
  const hint = REWARD_USAGE_HINTS[code]
  if (hint?.route) {
    const mobilePath = toMobilePath(hint.route)
    router.push(mobilePath)
  }
}

async function doSignIn() {
  await record('view', 'achievements', 'sign-in')
}

const signedInToday = computed(() => status.value?.progress?.tasks?.view ?? false)

onMounted(async () => {
  await loadStatus()
  loadingCalendar.value = true
  try {
    calendarData.value = await fetchActivityCalendar(28)
  } catch { /* best-effort */ }
  loadingCalendar.value = false
  pageLoading.value = false
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="成就与签到" @back="router.back()" />

    <LoadingState v-if="pageLoading" class="flex-1" message="加载中…" />

    <div v-else class="flex-1 overflow-y-auto min-h-0 pb-6">

      <!-- ── Streak Hero ── -->
      <div class="mx-4 mt-4 card-section">
        <div class="flex items-center gap-5">
          <!-- Ring -->
          <div class="relative shrink-0 w-24 h-24">
            <svg width="96" height="96" viewBox="0 0 96 96" class="-rotate-90">
              <circle cx="48" cy="48" r="42" fill="none" stroke="var(--color-border)" stroke-width="6" />
              <circle
                cx="48" cy="48" r="42"
                fill="none"
                stroke="var(--color-tinder-green)"
                stroke-width="6"
                stroke-linecap="round"
                :stroke-dasharray="`${ringDash} ${RING_CIRC}`"
                class="transition-all duration-700"
              />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="text-[26px] font-extrabold text-text-primary leading-none">{{ currentStreak }}</span>
              <span class="text-[10px] text-text-muted mt-0.5">天</span>
            </div>
          </div>

          <!-- Stats -->
          <div class="flex-1">
            <p class="text-[15px] font-bold text-text-primary mb-0.5">连续签到</p>
            <p class="text-[12px] text-text-muted mb-3">最长记录：{{ longestStreak }} 天</p>
            <div v-if="nextMilestoneDay" class="text-[12px] text-tinder-gold font-medium">
              🏆 第 {{ nextMilestoneDay }} 天里程碑
              <span class="text-text-muted font-normal">还差 {{ nextMilestoneDay - currentStreak }} 天</span>
            </div>
            <div v-else class="text-[12px] text-tinder-green font-medium">🌟 已达成所有里程碑</div>
          </div>
        </div>

        <!-- Sign in button -->
        <div class="mt-4">
          <button
            v-if="!signedInToday"
            type="button"
            class="w-full py-2.5 rounded-xl font-semibold text-[14px] text-white"
            style="background: linear-gradient(135deg, var(--color-tinder-green), #0b9b58);"
            @click="doSignIn"
          >
            签到打卡
          </button>
          <div v-else class="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-tinder-green/10 text-tinder-green text-[13px] font-medium">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            今日已签到
          </div>
        </div>
      </div>

      <!-- ── Today's Tasks ── -->
      <div class="mx-4 mt-3 card-section">
        <div class="flex items-center justify-between mb-3">
          <h3 class="section-title mb-0">今日任务</h3>
          <span class="text-[12px] text-text-muted">
            {{ tasksDoneCount }}/3 完成
          </span>
        </div>
        <div class="space-y-2">
          <div
            v-for="task in taskItems"
            :key="task.key"
            class="flex items-center gap-3 py-2"
          >
            <div
              class="shrink-0 w-6 h-6 rounded-full flex items-center justify-center"
              :class="task.done ? 'bg-tinder-green' : 'bg-bg border border-border'"
            >
              <svg v-if="task.done" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[13px] font-medium text-text-primary">{{ task.label }}</p>
              <p class="text-[11px] text-text-muted">{{ task.hint }}</p>
            </div>
            <span
              class="text-[11px] font-medium px-2 py-0.5 rounded-full shrink-0"
              :class="task.done ? 'bg-tinder-green/15 text-tinder-green' : 'bg-bg-elevated text-text-muted'"
            >{{ task.done ? '已完成' : '待完成' }}</span>
          </div>
        </div>
      </div>

      <!-- ── Milestone Horizontal Scroll ── -->
      <div class="mt-3">
        <div class="px-4 mb-2">
          <h3 class="section-title mb-0">里程碑</h3>
        </div>
        <div class="overflow-x-auto px-4 pb-1">
          <div class="flex gap-2" style="width: max-content">
            <div
              v-for="day in allMilestoneDays"
              :key="day"
              class="flex flex-col items-center gap-1 px-3 py-2.5 rounded-2xl border shrink-0"
              :class="grantedDays.has(day)
                ? 'bg-tinder-green/10 border-tinder-green/30'
                : day === nextMilestoneDay
                  ? 'bg-tinder-gold/10 border-tinder-gold/40'
                  : 'bg-bg-elevated border-border/50'"
              style="min-width: 68px"
            >
              <span class="text-[18px]">{{ rewardIcon(MILESTONE_REWARD_PREVIEW[day]?.code ?? '', day) }}</span>
              <span class="text-[11px] font-bold" :class="grantedDays.has(day) ? 'text-tinder-green' : day === nextMilestoneDay ? 'text-tinder-gold' : 'text-text-muted'">
                第 {{ day }} 天
              </span>
              <span class="text-[10px] text-text-muted text-center leading-tight" style="max-width: 60px">
                {{ MILESTONE_REWARD_PREVIEW[day]?.name ?? '' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Active Rewards ── -->
      <div v-if="activeRewards.length" class="mx-4 mt-3 card-section">
        <h3 class="section-title mb-3">活跃奖励</h3>
        <div class="space-y-2.5">
          <div
            v-for="reward in activeRewards"
            :key="reward.id ?? reward.reward_code"
            class="flex items-start gap-3 py-1"
          >
            <span class="text-[22px] shrink-0 mt-0.5">{{ rewardIcon(reward.reward_code, reward.streak_day) }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <p class="text-[13px] font-semibold text-text-primary">{{ reward.reward_name }}</p>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium" :class="rewardStatusClass(reward.status)">
                  {{ reward.status === 'active' ? '可使用' : reward.status === 'used' ? '已使用' : '已过期' }}
                </span>
              </div>
              <p class="text-[11px] text-text-muted mt-0.5 leading-relaxed">{{ reward.description }}</p>
              <div v-if="reward.expires_at" class="text-[10px] text-text-muted mt-0.5">
                到期：{{ new Date(reward.expires_at).toLocaleDateString('zh-CN') }}
              </div>
            </div>
            <button
              v-if="REWARD_USAGE_HINTS[reward.reward_code]"
              type="button"
              class="shrink-0 text-[12px] text-tinder-blue font-medium px-2.5 py-1.5 rounded-xl bg-tinder-blue/10 active:bg-tinder-blue/20 mt-0.5"
              @click="navigateReward(reward.reward_code)"
            >
              前往
            </button>
          </div>
        </div>
      </div>

      <!-- ── Activity Calendar ── -->
      <div class="mx-4 mt-3 card-section">
        <div class="flex items-center justify-between mb-3">
          <h3 class="section-title mb-0">最近 4 周活动</h3>
          <div class="flex items-center gap-2 text-[10px] text-text-muted">
            <span class="inline-block w-3 h-3 rounded-sm bg-tinder-green" /> 完成
            <span class="inline-block w-3 h-3 rounded-sm bg-tinder-gold/60" /> 部分
          </div>
        </div>

        <div v-if="loadingCalendar" class="flex justify-center py-4">
          <div class="w-5 h-5 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
        </div>

        <div v-else class="space-y-1.5">
          <!-- Week labels: Mon~Sun -->
          <div class="flex gap-1.5 px-8">
            <div v-for="d in ['一','二','三','四','五','六','日']" :key="d" class="flex-1 text-center text-[10px] text-text-muted">
              {{ d }}
            </div>
          </div>
          <!-- Weeks -->
          <div v-for="(week, wi) in calendarWeeks" :key="wi" class="flex items-center gap-1.5">
            <span class="text-[9px] text-text-muted w-7 shrink-0 text-right">W{{ wi + 1 }}</span>
            <div
              v-for="(cell, ci) in week"
              :key="ci"
              class="flex-1 aspect-square rounded-[4px]"
              :class="[cellColor(cell), cell.isToday ? 'ring-2 ring-tinder-blue ring-offset-1' : '']"
              :title="cell.date"
            />
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
