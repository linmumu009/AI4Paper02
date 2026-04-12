<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import {
  fetchAnalyticsOverview,
  fetchAnalyticsUsers,
  fetchAnalyticsTrends,
  fetchAnalyticsEngagementSignin,
  fetchAnalyticsActivation,
} from '@shared/api'
import type {
  AnalyticsOverviewResponse,
  AnalyticsUsersResponse,
  AnalyticsTrendsResponse,
} from '@shared/types/admin'

defineOptions({ name: 'AdminAnalyticsView' })

const router = useRouter()

const activeTab = ref<'overview' | 'users' | 'trends'>('overview')
const loading = ref(true)
const error = ref('')

const overview = ref<AnalyticsOverviewResponse | null>(null)
const usersRes = ref<AnalyticsUsersResponse | null>(null)
const trends = ref<AnalyticsTrendsResponse | null>(null)
const signinData = ref<any>(null)
const activationData = ref<any>(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ov, us, tr, si, ac] = await Promise.allSettled([
      fetchAnalyticsOverview(),
      fetchAnalyticsUsers(),
      fetchAnalyticsTrends(),
      fetchAnalyticsEngagementSignin().catch(() => null),
      fetchAnalyticsActivation().catch(() => null),
    ])
    if (ov.status === 'fulfilled') overview.value = ov.value
    if (us.status === 'fulfilled') usersRes.value = us.value
    if (tr.status === 'fulfilled') trends.value = tr.value
    if (si.status === 'fulfilled') signinData.value = si.value
    if (ac.status === 'fulfilled') activationData.value = ac.value
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmt(n?: number): string {
  if (n == null) return '-'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

// Simple sparkline bar helper
function barPercent(val: number, max: number): string {
  if (!max) return '0%'
  return `${Math.round((val / max) * 100)}%`
}

// Trend: pick last 14 days
const trendPoints = ref<{ date: string; new_users: number; paper_views: number }[]>([])

function processTrends() {
  if (!trends.value?.records) return
  trendPoints.value = trends.value.records.slice(-14)
}

function maxOf(arr: number[]): number {
  return Math.max(...arr, 1)
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="数据统计" @back="router.back()" />

    <!-- Tab bar -->
    <div class="shrink-0 flex border-b border-border bg-bg-card px-2">
      <button
        v-for="tab in [{ k: 'overview', l: '概览' }, { k: 'users', l: '用户' }, { k: 'trends', l: '趋势' }]"
        :key="tab.k"
        type="button"
        class="flex-1 py-2.5 text-[13px] font-medium transition-colors"
        :class="activeTab === tab.k ? 'text-tinder-pink border-b-2 border-tinder-pink -mb-px' : 'text-text-muted'"
        @click="activeTab = tab.k as any"
      >
        {{ tab.l }}
      </button>
    </div>

    <LoadingState v-if="loading" class="flex-1" message="加载统计数据…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <!-- Overview tab -->
    <div v-else-if="activeTab === 'overview'" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      <!-- Key metrics 2x2 grid -->
      <div v-if="overview" class="grid grid-cols-2 gap-3">
        <div class="card-section text-center py-4">
          <p class="text-[26px] font-bold text-tinder-blue">{{ fmt(overview.total_users) }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">总用户</p>
        </div>
        <div class="card-section text-center py-4">
          <p class="text-[26px] font-bold text-tinder-green">{{ fmt(overview.active_7d) }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">7日活跃</p>
        </div>
        <div class="card-section text-center py-4">
          <p class="text-[26px] font-bold text-tinder-pink">{{ fmt(overview.new_today) }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">今日新增</p>
        </div>
        <div class="card-section text-center py-4">
          <p class="text-[26px] font-bold text-tinder-purple">{{ fmt(overview.active_today) }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">今日活跃</p>
        </div>
      </div>

      <!-- Tier distribution -->
      <div v-if="overview?.tier_distribution" class="card-section">
        <p class="text-[13px] font-semibold text-text-primary mb-3">等级分布</p>
        <div class="space-y-2">
          <div
            v-for="(count, tier) in overview.tier_distribution"
            :key="tier"
            class="flex items-center gap-3"
          >
            <span class="text-[12px] w-14 shrink-0" :class="tier === 'pro_plus' ? 'text-tinder-purple' : tier === 'pro' ? 'text-tinder-gold' : 'text-text-muted'">{{ tier === 'pro_plus' ? 'Pro+' : tier === 'pro' ? 'Pro' : 'Free' }}</span>
            <div class="flex-1 h-2 bg-bg-elevated rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="tier === 'pro_plus' ? 'bg-tinder-purple' : tier === 'pro' ? 'bg-tinder-gold' : 'bg-bg-hover'"
                :style="{ width: barPercent(count, overview.total_users) }"
              />
            </div>
            <span class="text-[12px] text-text-muted w-8 text-right shrink-0">{{ fmt(count) }}</span>
          </div>
        </div>
      </div>

      <!-- Content stats -->
      <div v-if="overview?.content_stats" class="card-section">
        <p class="text-[13px] font-semibold text-text-primary mb-3">内容数据</p>
        <div class="grid grid-cols-3 gap-3">
          <div v-for="(v, k) in overview.content_stats" :key="k" class="text-center">
            <p class="text-[18px] font-bold text-text-primary">{{ fmt(v) }}</p>
            <p class="text-[10px] text-text-muted mt-0.5">{{ { papers_saved: '收藏', notes_written: '笔记', annotations: '批注', dismissed: '忽略', compare_results: '对比', ideas_generated: '灵感' }[k] ?? k }}</p>
          </div>
        </div>
      </div>

      <!-- Today's events -->
      <div v-if="overview?.today_events" class="card-section">
        <p class="text-[13px] font-semibold text-text-primary mb-3">今日事件</p>
        <div class="grid grid-cols-2 gap-3">
          <div class="text-center py-2">
            <p class="text-[20px] font-bold text-tinder-blue">{{ fmt(overview.today_events.page_views) }}</p>
            <p class="text-[11px] text-text-muted">页面访问</p>
          </div>
          <div class="text-center py-2">
            <p class="text-[20px] font-bold text-tinder-pink">{{ fmt(overview.today_events.paper_views) }}</p>
            <p class="text-[11px] text-text-muted">论文浏览</p>
          </div>
        </div>
      </div>

      <!-- Activation funnel (simplified) -->
      <div v-if="activationData?.steps" class="card-section">
        <p class="text-[13px] font-semibold text-text-primary mb-3">激活漏斗</p>
        <div class="space-y-2">
          <div
            v-for="step in activationData.steps"
            :key="step.name"
            class="flex items-center gap-3"
          >
            <span class="text-[11px] text-text-muted w-20 shrink-0 truncate">{{ step.label ?? step.name }}</span>
            <div class="flex-1 h-2.5 bg-bg-elevated rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-tinder-blue" :style="{ width: barPercent(step.count, activationData.steps[0]?.count ?? 1) }" />
            </div>
            <span class="text-[12px] font-mono text-text-secondary w-8 text-right shrink-0">{{ fmt(step.count) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Users tab -->
    <div v-else-if="activeTab === 'users'" class="flex-1 overflow-y-auto">
      <div v-if="!usersRes?.users?.length" class="px-4 py-8 text-center text-[13px] text-text-muted">暂无用户数据</div>
      <div v-else class="pb-4">
        <p class="px-4 py-2 text-[12px] text-text-muted">前 {{ usersRes.users.length }} 名活跃用户</p>
        <div
          v-for="(user, idx) in usersRes.users.slice(0, 30)"
          :key="user.user_id"
          class="flex items-center gap-3 px-4 py-3 border-b border-border/50"
        >
          <span class="text-[12px] text-text-muted w-5 shrink-0">{{ idx + 1 }}</span>
          <div class="flex-1 min-w-0">
            <p class="text-[13px] font-medium text-text-primary truncate">{{ user.username }}</p>
            <p class="text-[11px] text-text-muted mt-0.5">
              {{ user.papers_saved }} 收藏 · {{ user.notes_written }} 笔记 · {{ user.total_page_views }} 浏览
            </p>
          </div>
          <span
            class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0"
            :class="user.tier === 'pro_plus' ? 'bg-tinder-purple/10 text-tinder-purple' : user.tier === 'pro' ? 'bg-tinder-gold/10 text-tinder-gold' : 'bg-bg-elevated text-text-muted'"
          >{{ user.tier === 'pro_plus' ? 'Pro+' : user.tier === 'pro' ? 'Pro' : 'Free' }}</span>
        </div>
      </div>
    </div>

    <!-- Trends tab -->
    <div v-else-if="activeTab === 'trends'" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      <div v-if="!trends?.records?.length" class="text-center py-8 text-[13px] text-text-muted">暂无趋势数据</div>
      <template v-else>
        <!-- New users bar chart (last 14 days) -->
        <div class="card-section">
          <p class="text-[13px] font-semibold text-text-primary mb-3">新用户 (近14天)</p>
          <div class="flex items-end gap-1 h-32">
            <div
              v-for="rec in trends.records.slice(-14)"
              :key="rec.date"
              class="flex-1 flex flex-col items-center gap-1"
            >
              <div
                class="w-full rounded-t-sm bg-tinder-blue/70"
                :style="{ height: barPercent(rec.new_users ?? 0, maxOf(trends.records.slice(-14).map((r) => r.new_users ?? 0))) }"
              />
              <span class="text-[9px] text-text-muted" style="transform: rotate(-45deg);">{{ rec.date?.slice(5) }}</span>
            </div>
          </div>
        </div>

        <!-- Paper views bar chart -->
        <div class="card-section">
          <p class="text-[13px] font-semibold text-text-primary mb-3">论文浏览 (近14天)</p>
          <div class="flex items-end gap-1 h-32">
            <div
              v-for="rec in trends.records.slice(-14)"
              :key="rec.date"
              class="flex-1 flex flex-col items-center gap-1"
            >
              <div
                class="w-full rounded-t-sm bg-tinder-pink/60"
                :style="{ height: barPercent(rec.paper_views ?? 0, maxOf(trends.records.slice(-14).map((r) => r.paper_views ?? 0))) }"
              />
              <span class="text-[9px] text-text-muted" style="transform: rotate(-45deg);">{{ rec.date?.slice(5) }}</span>
            </div>
          </div>
        </div>

        <!-- Table of recent records -->
        <div class="card-section overflow-hidden">
          <p class="text-[13px] font-semibold text-text-primary mb-3">近7日明细</p>
          <div class="overflow-x-auto">
            <table class="w-full text-[11px]">
              <thead>
                <tr class="text-text-muted border-b border-border">
                  <th class="text-left py-1 pr-3">日期</th>
                  <th class="text-right py-1 pr-3">新用户</th>
                  <th class="text-right py-1 pr-3">论文浏览</th>
                  <th class="text-right py-1">活跃</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="rec in trends.records.slice(-7).reverse()"
                  :key="rec.date"
                  class="border-b border-border/50"
                >
                  <td class="py-1.5 pr-3 text-text-muted">{{ rec.date?.slice(5) }}</td>
                  <td class="text-right pr-3 text-tinder-blue">{{ rec.new_users ?? 0 }}</td>
                  <td class="text-right pr-3 text-tinder-pink">{{ rec.paper_views ?? 0 }}</td>
                  <td class="text-right text-tinder-green">{{ rec.active_users ?? 0 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Sign-in streak data -->
        <div v-if="signinData" class="card-section">
          <p class="text-[13px] font-semibold text-text-primary mb-3">签到统计</p>
          <div class="grid grid-cols-3 gap-3 text-center">
            <div>
              <p class="text-[18px] font-bold text-tinder-green">{{ fmt(signinData.today_signins ?? 0) }}</p>
              <p class="text-[10px] text-text-muted">今日签到</p>
            </div>
            <div>
              <p class="text-[18px] font-bold text-tinder-blue">{{ fmt(signinData.avg_streak ?? 0) }}</p>
              <p class="text-[10px] text-text-muted">平均连续</p>
            </div>
            <div>
              <p class="text-[18px] font-bold text-tinder-gold">{{ fmt(signinData.max_streak ?? 0) }}</p>
              <p class="text-[10px] text-text-muted">最长连续</p>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
