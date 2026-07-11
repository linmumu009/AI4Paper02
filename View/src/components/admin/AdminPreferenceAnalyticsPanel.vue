<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { http } from '../../api'
import { getApiErrorMessage, reportClientError } from '../../utils/apiError'

interface PreferenceAnalyticsStats {
  days: number
  total_feedback_events: number
  active_users: number
  users_with_profile: number
  users_with_enough_data: number
  min_feedback_threshold: number
  action_distribution: Record<string, number>
  top_positive_categories: { category: string; count: number }[]
}

const days = ref(30)
const stats = ref<PreferenceAnalyticsStats | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await http.get<{ ok: boolean } & PreferenceAnalyticsStats>(
      '/admin/analytics/preference',
      { params: { days: days.value } },
    )
    stats.value = response.data
  } catch (cause: unknown) {
    reportClientError('admin.preferenceAnalytics.load', cause, '加载失败')
    error.value = getApiErrorMessage(cause, '加载失败')
  } finally {
    loading.value = false
  }
}

function actionBarWidth(count: number): string {
  const distribution = stats.value?.action_distribution
  if (!distribution) return '0%'
  const max = Math.max(...Object.values(distribution), 1)
  return `${Math.round((count / max) * 100)}%`
}

function categoryBarWidth(count: number): string {
  const categories = stats.value?.top_positive_categories
  if (!categories?.length) return '0%'
  const max = Math.max(...categories.map(category => category.count), 1)
  return `${Math.round((count / max) * 100)}%`
}

watch(days, load)
onMounted(load)
</script>

<template>
  <section class="flex-1 flex flex-col p-3 sm:p-6 overflow-auto gap-4">
    <header class="shrink-0 flex items-start justify-between gap-3">
      <div>
        <h1 class="text-lg font-bold text-text-primary">🧭 偏好推荐分析</h1>
        <p class="text-xs text-text-muted mt-0.5">用户偏好学习闭环的信号覆盖与行为分布</p>
      </div>
      <RouterLink
        to="/admin/preference-loop"
        class="shrink-0 px-3 py-1.5 rounded-lg border border-border bg-bg-elevated text-xs text-text-secondary hover:bg-bg-card hover:text-text-primary transition-colors"
      >
        🔁 偏好闭环仪表盘 →
      </RouterLink>
    </header>

    <div class="flex items-center gap-3 shrink-0">
      <label for="preference-analytics-days" class="sr-only">统计时间范围</label>
      <select
        id="preference-analytics-days"
        v-model="days"
        class="px-3 py-1.5 rounded-lg border border-border bg-bg-elevated text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-tinder-blue/40"
      >
        <option :value="7">最近 7 天</option>
        <option :value="14">最近 14 天</option>
        <option :value="30">最近 30 天</option>
        <option :value="90">最近 90 天</option>
      </select>
      <button
        type="button"
        class="px-3 py-1.5 rounded-lg border border-border bg-bg-elevated text-text-primary text-xs hover:bg-bg-card transition-colors"
        :disabled="loading"
        @click="load"
      >{{ loading ? '加载中…' : '刷新' }}</button>
    </div>

    <div v-if="error" role="alert" class="text-xs text-red-400 bg-red-900/20 rounded-lg p-3 shrink-0">{{ error }}</div>

    <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
      <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
        <span class="text-2xl font-bold text-tinder-blue">{{ stats.total_feedback_events?.toLocaleString() || 0 }}</span>
        <span class="text-xs text-text-muted">反馈事件总数（{{ stats.days }}天）</span>
      </div>
      <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
        <span class="text-2xl font-bold text-tinder-green">{{ stats.active_users || 0 }}</span>
        <span class="text-xs text-text-muted">产生反馈的用户</span>
      </div>
      <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
        <span class="text-2xl font-bold text-tinder-gold">{{ stats.users_with_profile || 0 }}</span>
        <span class="text-xs text-text-muted">已建画像用户</span>
      </div>
      <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
        <span class="text-2xl font-bold text-violet-400">{{ stats.users_with_enough_data || 0 }}</span>
        <span class="text-xs text-text-muted">偏好推荐已激活（≥{{ stats.min_feedback_threshold }}条反馈）</span>
      </div>
    </div>

    <div v-if="stats" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div class="rounded-xl bg-bg-elevated border border-border p-4">
        <h2 class="text-xs font-semibold text-text-primary mb-3">反馈行为分布</h2>
        <div class="space-y-2">
          <div v-for="(count, action) in stats.action_distribution" :key="action" class="flex items-center gap-2">
            <span class="w-32 shrink-0 text-[11px] text-text-muted font-mono truncate">{{ action }}</span>
            <div class="flex-1 h-2 rounded-full bg-bg-card overflow-hidden">
              <div class="h-full rounded-full bg-tinder-blue/70" :style="{ width: actionBarWidth(count) }" />
            </div>
            <span class="shrink-0 text-[11px] text-text-secondary w-10 text-right">{{ count }}</span>
          </div>
        </div>
        <p v-if="!stats.action_distribution || Object.keys(stats.action_distribution).length === 0" class="text-xs text-text-muted">暂无数据</p>
      </div>

      <div class="rounded-xl bg-bg-elevated border border-border p-4">
        <h2 class="text-xs font-semibold text-text-primary mb-3">用户正向兴趣 Top 类目</h2>
        <div class="space-y-2">
          <div
            v-for="(item, index) in (stats.top_positive_categories || []).slice(0, 15)"
            :key="item.category"
            class="flex items-center gap-2"
          >
            <span class="shrink-0 w-5 text-[11px] text-text-muted text-right">{{ index + 1 }}.</span>
            <span class="flex-1 text-[11px] text-text-primary font-mono">{{ item.category }}</span>
            <div class="w-16 h-2 rounded-full bg-bg-card overflow-hidden">
              <div class="h-full rounded-full bg-tinder-green/70" :style="{ width: categoryBarWidth(item.count) }" />
            </div>
            <span class="shrink-0 text-[11px] text-text-secondary w-8 text-right">{{ item.count }}</span>
          </div>
        </div>
        <p v-if="!stats.top_positive_categories?.length" class="text-xs text-text-muted">暂无数据</p>
      </div>
    </div>

    <div v-else-if="!loading" class="flex-1 flex items-center justify-center">
      <p class="text-sm text-text-muted">暂无偏好推荐分析数据</p>
    </div>
  </section>
</template>
