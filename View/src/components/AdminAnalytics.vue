<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick, shallowRef } from 'vue'
import {
  fetchAnalyticsOverview,
  fetchAnalyticsUsers,
  fetchAnalyticsPapers,
  fetchAnalyticsTrends,
  fetchAnalyticsFeatures,
  fetchAnalyticsRetention,
} from '../api'
import type {
  AnalyticsOverviewResponse,
  AnalyticsUserActivity,
  AnalyticsPaperPopularity,
  AnalyticsTrendsResponse,
  AnalyticsFeaturesResponse,
  AnalyticsRetentionResponse,
  RetentionCohort,
} from '../types/paper'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart, HeatmapChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, PieChart, HeatmapChart,
  TitleComponent, TooltipComponent, LegendComponent, GridComponent,
  VisualMapComponent, CanvasRenderer,
])

// ---------------------------------------------------------------------------
// Sub-tab navigation
// ---------------------------------------------------------------------------
const activeSubTab = ref<'overview' | 'users' | 'papers' | 'retention'>('overview')

// ---------------------------------------------------------------------------
// Overview data
// ---------------------------------------------------------------------------
const overviewLoading = ref(false)
const overviewError = ref('')
const overview = ref<AnalyticsOverviewResponse | null>(null)

async function loadOverview() {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    overview.value = await fetchAnalyticsOverview()
  } catch (e: any) {
    overviewError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    overviewLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Trends data
// ---------------------------------------------------------------------------
const trendsLoading = ref(false)
const trendsDays = ref(30)
const trendsData = ref<AnalyticsTrendsResponse | null>(null)

async function loadTrends() {
  trendsLoading.value = true
  try {
    trendsData.value = await fetchAnalyticsTrends({ days: trendsDays.value })
    await nextTick()
    renderTrendChart()
  } catch { /* silent */ } finally {
    trendsLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Features data
// ---------------------------------------------------------------------------
const featuresData = ref<AnalyticsFeaturesResponse | null>(null)

async function loadFeatures() {
  try {
    featuresData.value = await fetchAnalyticsFeatures()
    await nextTick()
    renderFeatureChart()
  } catch { /* silent */ }
}

// ---------------------------------------------------------------------------
// User activity data
// ---------------------------------------------------------------------------
const usersLoading = ref(false)
const userActivities = ref<AnalyticsUserActivity[]>([])
const usersTotal = ref(0)
const usersPage = ref(1)
const usersPageSize = 20
const usersSortField = ref<string>('last_login_at')
const usersSortDesc = ref(true)

async function loadUsers() {
  usersLoading.value = true
  try {
    const offset = (usersPage.value - 1) * usersPageSize
    const res = await fetchAnalyticsUsers({ limit: usersPageSize, offset })
    userActivities.value = res.users
    usersTotal.value = res.total
  } catch { /* silent */ } finally {
    usersLoading.value = false
  }
}

const sortedUserActivities = computed(() => {
  const arr = [...userActivities.value]
  const field = usersSortField.value as keyof AnalyticsUserActivity
  arr.sort((a, b) => {
    const va = a[field] ?? ''
    const vb = b[field] ?? ''
    if (typeof va === 'number' && typeof vb === 'number') {
      return usersSortDesc.value ? vb - va : va - vb
    }
    const sa = String(va)
    const sb = String(vb)
    return usersSortDesc.value ? sb.localeCompare(sa) : sa.localeCompare(sb)
  })
  return arr
})

function toggleSort(field: string) {
  if (usersSortField.value === field) {
    usersSortDesc.value = !usersSortDesc.value
  } else {
    usersSortField.value = field
    usersSortDesc.value = true
  }
}

function sortIcon(field: string) {
  if (usersSortField.value !== field) return '↕'
  return usersSortDesc.value ? '↓' : '↑'
}

// ---------------------------------------------------------------------------
// Paper popularity data
// ---------------------------------------------------------------------------
const papersLoading = ref(false)
const paperPopularity = ref<AnalyticsPaperPopularity[]>([])

async function loadPapers() {
  papersLoading.value = true
  try {
    const res = await fetchAnalyticsPapers({ limit: 30 })
    paperPopularity.value = res.papers
  } catch { /* silent */ } finally {
    papersLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Retention data
// ---------------------------------------------------------------------------
const retentionLoading = ref(false)
const retentionData = ref<AnalyticsRetentionResponse | null>(null)

async function loadRetention() {
  retentionLoading.value = true
  try {
    retentionData.value = await fetchAnalyticsRetention({ weeks: 8 })
    await nextTick()
    renderRetentionChart()
  } catch { /* silent */ } finally {
    retentionLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// ECharts instances
// ---------------------------------------------------------------------------
const trendChartRef = ref<HTMLDivElement | null>(null)
const featureChartRef = ref<HTMLDivElement | null>(null)
const tierChartRef = ref<HTMLDivElement | null>(null)
const retentionChartRef = ref<HTMLDivElement | null>(null)

let trendChartInstance: echarts.ECharts | null = null
let featureChartInstance: echarts.ECharts | null = null
let tierChartInstance: echarts.ECharts | null = null
let retentionChartInstance: echarts.ECharts | null = null

function renderTrendChart() {
  if (!trendChartRef.value || !trendsData.value) return
  if (trendChartInstance) trendChartInstance.dispose()
  trendChartInstance = echarts.init(trendChartRef.value)

  const d = trendsData.value
  trendChartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      data: ['活跃用户', '新增用户', '收藏论文', '写笔记', '页面浏览'],
      textStyle: { color: '#a0a0a0', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 40, right: 20, top: 10, bottom: 40 },
    xAxis: {
      type: 'category',
      data: d.dates.map((s: string) => s.slice(5)),
      axisLabel: { color: '#666', fontSize: 10, rotate: 45 },
      axisLine: { lineStyle: { color: '#333' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#666', fontSize: 10 },
      splitLine: { lineStyle: { color: '#222' } },
    },
    series: [
      { name: '活跃用户', type: 'line', data: d.active_users, smooth: true, lineStyle: { width: 2 }, itemStyle: { color: '#2db8e2' }, symbol: 'none' },
      { name: '新增用户', type: 'line', data: d.new_users, smooth: true, lineStyle: { width: 2 }, itemStyle: { color: '#2ee66d' }, symbol: 'none' },
      { name: '收藏论文', type: 'bar', data: d.papers_saved, itemStyle: { color: 'rgba(245,183,49,0.6)' }, barMaxWidth: 8 },
      { name: '写笔记', type: 'bar', data: d.notes_written, itemStyle: { color: 'rgba(166,77,255,0.6)' }, barMaxWidth: 8 },
      { name: '页面浏览', type: 'line', data: d.page_views, smooth: true, lineStyle: { width: 1, type: 'dashed' }, itemStyle: { color: '#ff4458' }, symbol: 'none' },
    ],
  })
}

function renderFeatureChart() {
  if (!featureChartRef.value || !featuresData.value) return
  if (featureChartInstance) featureChartInstance.dispose()
  featureChartInstance = echarts.init(featureChartRef.value)

  const f = featuresData.value.features
  const featureLabels: Record<string, string> = {
    knowledge_base: '知识库',
    notes: '笔记',
    annotations: '批注',
    compare: '论文对比',
    idea_generation: '灵感生成',
    dismiss: '不感兴趣',
  }
  const keys = Object.keys(f)
  const colors = ['#2db8e2', '#2ee66d', '#f5b731', '#a64dff', '#ff4458', '#ff6036']

  featureChartInstance.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (p: any) => `${p.name}: ${p.value} 位用户`,
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#1a1a1a', borderWidth: 2 },
      label: { show: true, color: '#a0a0a0', fontSize: 11, formatter: '{b}\n{c}人' },
      data: keys.map((k, i) => ({
        name: featureLabels[k] || k,
        value: f[k],
        itemStyle: { color: colors[i % colors.length] },
      })),
    }],
  })
}

function renderTierChart() {
  if (!tierChartRef.value || !overview.value) return
  if (tierChartInstance) tierChartInstance.dispose()
  tierChartInstance = echarts.init(tierChartRef.value)

  const dist = overview.value.tier_distribution
  const tierLabels: Record<string, string> = { free: '免费用户', pro: 'Pro 会员', 'pro+': 'Pro+ 会员' }
  const tierColors: Record<string, string> = { free: '#666', pro: '#f5b731', 'pro+': '#ff4458' }

  tierChartInstance.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      center: ['50%', '50%'],
      itemStyle: { borderRadius: 6, borderColor: '#1a1a1a', borderWidth: 2 },
      label: { show: true, color: '#a0a0a0', fontSize: 11, formatter: '{b}\n{c}人' },
      data: Object.entries(dist).map(([k, v]) => ({
        name: tierLabels[k] || k,
        value: v,
        itemStyle: { color: tierColors[k] || '#a64dff' },
      })),
    }],
  })
}

function renderRetentionChart() {
  if (!retentionChartRef.value || !retentionData.value) return
  if (retentionChartInstance) retentionChartInstance.dispose()
  retentionChartInstance = echarts.init(retentionChartRef.value)

  const cohorts = retentionData.value.cohorts
  const maxWeeks = retentionData.value.weeks

  // Build heatmap data: [weekIndex, cohortIndex, value]
  const heatData: number[][] = []
  const yLabels: string[] = []
  const xLabels: string[] = []
  for (let i = 0; i < maxWeeks; i++) xLabels.push(`第${i}周`)

  cohorts.forEach((c, ci) => {
    yLabels.push(`${c.week} (${c.cohort_size})`)
    c.retention.forEach((v, wi) => {
      heatData.push([wi, ci, v])
    })
  })

  retentionChartInstance.setOption({
    tooltip: {
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (p: any) => {
        const [week, cohort, val] = p.data
        return `${yLabels[cohort]}<br/>第${week}周留存: ${val}%`
      },
    },
    grid: { left: 100, right: 20, top: 10, bottom: 40 },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisLabel: { color: '#666', fontSize: 10 },
      axisLine: { lineStyle: { color: '#333' } },
    },
    yAxis: {
      type: 'category',
      data: yLabels,
      axisLabel: { color: '#a0a0a0', fontSize: 10 },
      axisLine: { lineStyle: { color: '#333' } },
    },
    visualMap: {
      min: 0,
      max: 100,
      show: false,
      inRange: { color: ['#1a1a1a', '#0d4429', '#2ee66d'] },
    },
    series: [{
      type: 'heatmap',
      data: heatData,
      label: { show: true, color: '#fff', fontSize: 10, formatter: (p: any) => `${p.data[2]}%` },
      itemStyle: { borderWidth: 2, borderColor: '#111' },
    }],
  })
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
const resizeHandler = () => {
  trendChartInstance?.resize()
  featureChartInstance?.resize()
  tierChartInstance?.resize()
  retentionChartInstance?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', resizeHandler)
  await loadOverview()
  await nextTick()
  renderTierChart()
  loadTrends()
  loadFeatures()
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  trendChartInstance?.dispose()
  featureChartInstance?.dispose()
  tierChartInstance?.dispose()
  retentionChartInstance?.dispose()
})

// Watch sub-tab changes to load data lazily
watch(activeSubTab, (tab) => {
  if (tab === 'users' && userActivities.value.length === 0) loadUsers()
  if (tab === 'papers' && paperPopularity.value.length === 0) loadPapers()
  if (tab === 'retention' && !retentionData.value) loadRetention()
})

// Watch trend days change
watch(trendsDays, () => loadTrends())

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return `${h}小时${m}分`
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Sub-tab nav -->
    <div class="flex gap-1 bg-bg-elevated rounded-lg p-1">
      <button
        v-for="tab in [
          { key: 'overview', label: '📊 平台总览' },
          { key: 'users', label: '👥 用户活跃' },
          { key: 'papers', label: '📄 论文热度' },
          { key: 'retention', label: '📈 留存分析' },
        ]"
        :key="tab.key"
        @click="activeSubTab = tab.key as any"
        class="px-4 py-2 rounded-md text-sm font-medium transition-all"
        :class="activeSubTab === tab.key
          ? 'bg-tinder-blue/20 text-tinder-blue'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- ================================================================= -->
    <!-- Overview Tab -->
    <!-- ================================================================= -->
    <div v-if="activeSubTab === 'overview'" class="space-y-6">
      <!-- Loading / Error -->
      <div v-if="overviewLoading" class="flex items-center justify-center py-16">
        <div class="w-6 h-6 border-2 border-tinder-blue border-t-transparent rounded-full animate-spin"></div>
        <span class="ml-3 text-text-muted text-sm">加载统计数据…</span>
      </div>
      <div v-else-if="overviewError" class="text-center py-16 text-red-400 text-sm">{{ overviewError }}</div>

      <template v-else-if="overview">
        <!-- KPI Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-text-muted text-xs mb-1">总用户数</div>
            <div class="text-2xl font-bold text-text-primary">{{ overview.total_users }}</div>
            <div class="text-xs text-tinder-green mt-1">今日 +{{ overview.new_today }}</div>
          </div>
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-text-muted text-xs mb-1">今日活跃</div>
            <div class="text-2xl font-bold text-tinder-blue">{{ overview.active_today }}</div>
            <div class="text-xs text-text-muted mt-1">7日 {{ overview.active_7d }} · 30日 {{ overview.active_30d }}</div>
          </div>
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-text-muted text-xs mb-1">收藏论文</div>
            <div class="text-2xl font-bold text-tinder-gold">{{ overview.content_stats.papers_saved }}</div>
            <div class="text-xs text-text-muted mt-1">笔记 {{ overview.content_stats.notes_written }} · 批注 {{ overview.content_stats.annotations }}</div>
          </div>
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-text-muted text-xs mb-1">灵感生成</div>
            <div class="text-2xl font-bold text-tinder-purple">{{ overview.content_stats.ideas_generated }}</div>
            <div class="text-xs text-text-muted mt-1">对比 {{ overview.content_stats.compare_results }} · 不感兴趣 {{ overview.content_stats.dismissed }}</div>
          </div>
        </div>

        <!-- Charts Row: Trend + Tier Distribution -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <!-- Trend Chart -->
          <div class="lg:col-span-2 bg-bg-card rounded-xl p-4 border border-border">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-semibold text-text-primary">趋势概览</h3>
              <select
                v-model="trendsDays"
                class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none"
              >
                <option :value="7">近7天</option>
                <option :value="14">近14天</option>
                <option :value="30">近30天</option>
                <option :value="90">近90天</option>
              </select>
            </div>
            <div ref="trendChartRef" class="w-full h-64"></div>
          </div>

          <!-- Tier Distribution -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <h3 class="text-sm font-semibold text-text-primary mb-3">用户等级分布</h3>
            <div ref="tierChartRef" class="w-full h-56"></div>
          </div>
        </div>

        <!-- Charts Row: Feature Usage -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <h3 class="text-sm font-semibold text-text-primary mb-3">功能使用人数</h3>
            <div ref="featureChartRef" class="w-full h-64"></div>
          </div>

          <!-- Quick Stats Table -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <h3 class="text-sm font-semibold text-text-primary mb-3">内容数据一览</h3>
            <div class="space-y-3">
              <div v-for="(item, idx) in [
                { label: '收藏论文', value: overview.content_stats.papers_saved, icon: '⭐', color: 'text-tinder-gold' },
                { label: '撰写笔记', value: overview.content_stats.notes_written, icon: '📝', color: 'text-tinder-green' },
                { label: 'PDF 批注', value: overview.content_stats.annotations, icon: '🖊️', color: 'text-tinder-blue' },
                { label: '论文对比', value: overview.content_stats.compare_results, icon: '🔄', color: 'text-tinder-purple' },
                { label: '灵感生成', value: overview.content_stats.ideas_generated, icon: '💡', color: 'text-tinder-pink' },
                { label: '不感兴趣', value: overview.content_stats.dismissed, icon: '👎', color: 'text-text-muted' },
              ]" :key="idx" class="flex items-center justify-between py-2 border-b border-border/50 last:border-b-0">
                <div class="flex items-center gap-2">
                  <span class="text-base">{{ item.icon }}</span>
                  <span class="text-sm text-text-secondary">{{ item.label }}</span>
                </div>
                <span class="text-sm font-semibold" :class="item.color">{{ item.value }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ================================================================= -->
    <!-- Users Tab -->
    <!-- ================================================================= -->
    <div v-if="activeSubTab === 'users'" class="space-y-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-text-primary">用户活跃度排行</h3>
        <span class="text-xs text-text-muted">共 {{ usersTotal }} 位用户</span>
      </div>

      <div v-if="usersLoading" class="flex items-center justify-center py-12">
        <div class="w-5 h-5 border-2 border-tinder-blue border-t-transparent rounded-full animate-spin"></div>
      </div>

      <div v-else class="overflow-x-auto rounded-lg border border-border">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-bg-elevated border-b border-border text-text-muted">
              <th class="text-left px-3 py-2.5 font-medium">用户</th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('papers_saved')">
                收藏 {{ sortIcon('papers_saved') }}
              </th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('notes_written')">
                笔记 {{ sortIcon('notes_written') }}
              </th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('annotations')">
                批注 {{ sortIcon('annotations') }}
              </th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('compare_results')">
                对比 {{ sortIcon('compare_results') }}
              </th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('total_page_views')">
                浏览 {{ sortIcon('total_page_views') }}
              </th>
              <th class="text-left px-3 py-2.5 font-medium">等级</th>
              <th class="text-left px-3 py-2.5 font-medium cursor-pointer hover:text-text-secondary" @click="toggleSort('last_login_at')">
                最后登录 {{ sortIcon('last_login_at') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="u in sortedUserActivities"
              :key="u.user_id"
              class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors"
            >
              <td class="px-3 py-2.5">
                <div class="flex items-center gap-2">
                  <div class="w-6 h-6 rounded-full bg-bg-elevated flex items-center justify-center text-[10px] font-bold text-text-muted">
                    {{ u.username.charAt(0).toUpperCase() }}
                  </div>
                  <div>
                    <div class="text-text-primary font-medium">{{ u.username }}</div>
                    <div class="text-text-muted text-[10px]">ID: {{ u.user_id }}</div>
                  </div>
                </div>
              </td>
              <td class="px-3 py-2.5 text-text-secondary font-mono">{{ u.papers_saved }}</td>
              <td class="px-3 py-2.5 text-text-secondary font-mono">{{ u.notes_written }}</td>
              <td class="px-3 py-2.5 text-text-secondary font-mono">{{ u.annotations }}</td>
              <td class="px-3 py-2.5 text-text-secondary font-mono">{{ u.compare_results }}</td>
              <td class="px-3 py-2.5 text-text-secondary font-mono">{{ u.total_page_views }}</td>
              <td class="px-3 py-2.5">
                <span
                  class="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium"
                  :class="{
                    'bg-amber-500/20 text-amber-400': u.tier === 'pro',
                    'bg-red-500/20 text-red-400': u.tier === 'pro+',
                    'bg-gray-500/20 text-gray-400': u.tier === 'free',
                  }"
                >
                  {{ u.tier === 'pro' ? 'Pro' : u.tier === 'pro+' ? 'Pro+' : 'Free' }}
                </span>
              </td>
              <td class="px-3 py-2.5 text-text-muted font-mono">{{ formatDate(u.last_login_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="usersTotal > usersPageSize" class="flex justify-center gap-2">
        <button
          @click="usersPage--; loadUsers()"
          :disabled="usersPage <= 1"
          class="px-3 py-1.5 text-xs rounded-md bg-bg-elevated text-text-muted hover:text-text-secondary disabled:opacity-30"
        >上一页</button>
        <span class="px-3 py-1.5 text-xs text-text-muted">{{ usersPage }} / {{ Math.ceil(usersTotal / usersPageSize) }}</span>
        <button
          @click="usersPage++; loadUsers()"
          :disabled="usersPage >= Math.ceil(usersTotal / usersPageSize)"
          class="px-3 py-1.5 text-xs rounded-md bg-bg-elevated text-text-muted hover:text-text-secondary disabled:opacity-30"
        >下一页</button>
      </div>
    </div>

    <!-- ================================================================= -->
    <!-- Papers Tab -->
    <!-- ================================================================= -->
    <div v-if="activeSubTab === 'papers'" class="space-y-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-text-primary">论文热度排行 🔥</h3>
        <span class="text-xs text-text-muted">按收藏人数排序</span>
      </div>

      <div v-if="papersLoading" class="flex items-center justify-center py-12">
        <div class="w-5 h-5 border-2 border-tinder-gold border-t-transparent rounded-full animate-spin"></div>
      </div>

      <div v-else-if="paperPopularity.length === 0" class="text-center py-12 text-text-muted text-sm">
        暂无论文收藏数据
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="(p, idx) in paperPopularity"
          :key="p.paper_id"
          class="bg-bg-card rounded-xl p-4 border border-border hover:border-border-light transition-colors"
        >
          <div class="flex items-start gap-3">
            <!-- Rank badge -->
            <div
              class="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold shrink-0"
              :class="{
                'bg-amber-500/20 text-amber-400': idx === 0,
                'bg-gray-400/20 text-gray-300': idx === 1,
                'bg-orange-600/20 text-orange-400': idx === 2,
                'bg-bg-elevated text-text-muted': idx > 2,
              }"
            >
              {{ idx + 1 }}
            </div>

            <div class="flex-1 min-w-0">
              <div class="text-sm text-text-primary font-medium truncate" :title="p.title">
                {{ p.title }}
              </div>
              <div class="text-[10px] text-text-muted font-mono mt-0.5">{{ p.paper_id }}</div>

              <!-- Stats chips -->
              <div class="flex flex-wrap gap-2 mt-2">
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tinder-gold/10 text-tinder-gold text-[10px]">
                  ⭐ {{ p.save_count }} 人收藏
                </span>
                <span v-if="p.note_count > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tinder-green/10 text-tinder-green text-[10px]">
                  📝 {{ p.note_count }} 篇笔记
                </span>
                <span v-if="p.annotation_count > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tinder-blue/10 text-tinder-blue text-[10px]">
                  🖊️ {{ p.annotation_count }} 条批注
                </span>
                <span v-if="p.view_count > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tinder-purple/10 text-tinder-purple text-[10px]">
                  👁️ {{ p.view_count }} 次浏览
                </span>
                <span v-if="p.avg_view_duration > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-tinder-pink/10 text-tinder-pink text-[10px]">
                  ⏱️ 平均 {{ formatDuration(p.avg_view_duration) }}
                </span>
                <span v-if="p.dismiss_count > 0" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-500/10 text-text-muted text-[10px]">
                  👎 {{ p.dismiss_count }} 人不感兴趣
                </span>
              </div>
            </div>

            <!-- Engagement bar -->
            <div class="w-20 shrink-0 text-right">
              <div class="text-lg font-bold text-tinder-gold">{{ p.save_count }}</div>
              <div class="text-[10px] text-text-muted">收藏</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ================================================================= -->
    <!-- Retention Tab -->
    <!-- ================================================================= -->
    <div v-if="activeSubTab === 'retention'" class="space-y-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-text-primary">周留存热力图</h3>
        <span class="text-xs text-text-muted">按注册周分组，绿色越深表示留存率越高</span>
      </div>

      <div v-if="retentionLoading" class="flex items-center justify-center py-12">
        <div class="w-5 h-5 border-2 border-tinder-green border-t-transparent rounded-full animate-spin"></div>
      </div>

      <div v-else class="bg-bg-card rounded-xl p-4 border border-border">
        <div ref="retentionChartRef" class="w-full h-80"></div>
      </div>

      <!-- Retention table fallback -->
      <div v-if="retentionData && retentionData.cohorts.length > 0" class="bg-bg-card rounded-xl p-4 border border-border">
        <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">留存明细表</h4>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="bg-bg-elevated border-b border-border text-text-muted">
                <th class="text-left px-2 py-2 font-medium">注册周</th>
                <th class="text-center px-2 py-2 font-medium">人数</th>
                <th
                  v-for="w in retentionData.weeks"
                  :key="w"
                  class="text-center px-2 py-2 font-medium"
                >第{{ w - 1 }}周</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in retentionData.cohorts"
                :key="c.week"
                class="border-b border-border/50"
              >
                <td class="px-2 py-1.5 text-text-secondary font-mono">{{ c.week }}</td>
                <td class="px-2 py-1.5 text-center text-text-muted">{{ c.cohort_size }}</td>
                <td
                  v-for="(r, ri) in c.retention"
                  :key="ri"
                  class="px-2 py-1.5 text-center font-mono"
                  :class="r > 50 ? 'text-tinder-green' : r > 20 ? 'text-tinder-gold' : 'text-text-muted'"
                >
                  {{ c.cohort_size > 0 ? r + '%' : '—' }}
                </td>
                <!-- Pad empty cells -->
                <td
                  v-for="_ in retentionData.weeks - c.retention.length"
                  :key="'pad-' + _"
                  class="px-2 py-1.5 text-center text-text-muted"
                >—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
