<script setup lang="ts">
/**
 * AdminAnalytics — 问题驱动的管理后台分析面板
 *
 * 顶部：健康总览行（今日快速巡检）
 * 4 个核心判断模块：
 *   A. 新用户激活 — 是否在 7 天内完成首次有价值行为（收藏/笔记/批注/对比，不含 dismiss）？
 *   B. 激活用户留存 — 已激活用户是否持续回来？支持「会话留存」与「价值行为留存」切换 + 参与深度信号
 *   C. 内容与功能价值 — 严格步骤漏斗：卡片曝光→详情→收藏→深度行为，含高浏览低转化异常
 *   D. AI 功能采用 — 深度研究/论文聊天/灵感生成的使用渗透率与趋势
 *
 * 每个模块：1 个主信号 + 分群维度 + 1 个下钻列表
 */
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import {
  fetchAnalyticsOverview,
  fetchAnalyticsActivation,
  fetchAnalyticsActivatedRetention,
  fetchAnalyticsContentFunnel,
  fetchAnalyticsValueRetention,
  fetchAnalyticsContentStepFunnel,
  fetchAnalyticsAiFeatures,
  fetchAnalyticsEngagementDepth,
} from '../api'
import type {
  AnalyticsOverviewResponse,
  AnalyticsActivationResponse,
  AnalyticsActivatedRetentionResponse,
  AnalyticsContentFunnelResponse,
  AnalyticsValueRetentionResponse,
  AnalyticsContentStepFunnelResponse,
  AnalyticsAiFeatureResponse,
  AnalyticsEngagementDepthResponse,
  RetentionCohort,
} from '../types/paper'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, HeatmapChart } from 'echarts/charts'
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart, BarChart, HeatmapChart,
  TooltipComponent, LegendComponent, GridComponent, VisualMapComponent, MarkLineComponent,
  CanvasRenderer,
])

// ---------------------------------------------------------------------------
// Health Overview Row
// ---------------------------------------------------------------------------
const overviewLoading = ref(false)
const overviewData = ref<AnalyticsOverviewResponse | null>(null)

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
const activeModule = ref<'activation' | 'retention' | 'content' | 'ai'>('activation')

// Module A — Activation
const activationLoading = ref(false)
const activationError = ref('')
const activationData = ref<AnalyticsActivationResponse | null>(null)
const activationDays = ref(30)
const activationWindow = ref(7)
const activationTierFilter = ref<'all' | 'free' | 'pro' | 'pro_plus'>('all')
const showUnactivatedList = ref(false)
const showTierBreakdown = ref(false)

// Module B — Activated retention (session-based + value-action-based toggle)
const retentionLoading = ref(false)
const retentionError = ref('')
const retentionData = ref<AnalyticsActivatedRetentionResponse | null>(null)
const retentionWeeks = ref(8)
const retentionType = ref<'session' | 'value'>('session')
const valueRetentionLoading = ref(false)
const valueRetentionError = ref('')
const valueRetentionData = ref<AnalyticsValueRetentionResponse | null>(null)

// Module C — Content funnel
const contentLoading = ref(false)
const contentError = ref('')
const contentData = ref<AnalyticsContentFunnelResponse | null>(null)
const contentDays = ref(30)
const stepFunnelLoading = ref(false)
const stepFunnelError = ref('')
const stepFunnelData = ref<AnalyticsContentStepFunnelResponse | null>(null)

// Module D — AI Feature Adoption
const aiLoading = ref(false)
const aiError = ref('')
const aiData = ref<AnalyticsAiFeatureResponse | null>(null)
const aiDays = ref(30)

// Engagement Depth (embedded in Module B)
const depthLoading = ref(false)
const depthError = ref('')
const depthData = ref<AnalyticsEngagementDepthResponse | null>(null)

// ---------------------------------------------------------------------------
// Chart refs
// ---------------------------------------------------------------------------
const activationChartRef = ref<HTMLDivElement | null>(null)
const retentionChartRef = ref<HTMLDivElement | null>(null)
const valueRetentionChartRef = ref<HTMLDivElement | null>(null)
const contentChartRef = ref<HTMLDivElement | null>(null)
const aiChartRef = ref<HTMLDivElement | null>(null)
const depthChartRef = ref<HTMLDivElement | null>(null)

let activationChartInst: echarts.ECharts | null = null
let retentionChartInst: echarts.ECharts | null = null
let valueRetentionChartInst: echarts.ECharts | null = null
let contentChartInst: echarts.ECharts | null = null
let aiChartInst: echarts.ECharts | null = null
let depthChartInst: echarts.ECharts | null = null

// ---------------------------------------------------------------------------
// Tier-breakdown helpers
// ---------------------------------------------------------------------------
const tierBreakdownRows = computed(() => {
  if (!activationData.value?.tier_breakdown) return []
  const order = ['pro_plus', 'pro', 'free']
  const tb = activationData.value.tier_breakdown
  return order
    .filter(t => tb[t])
    .map(t => ({
      tier: t,
      label: t === 'pro_plus' ? 'Pro+' : t === 'pro' ? 'Pro' : '免费',
      registered: tb[t].registered,
      activated: tb[t].activated,
      rate: tb[t].rate,
    }))
})

// ---------------------------------------------------------------------------
// Load functions
// ---------------------------------------------------------------------------
async function loadOverview() {
  overviewLoading.value = true
  try {
    overviewData.value = await fetchAnalyticsOverview()
  } catch {
    // non-fatal: overview row just stays hidden
  } finally {
    overviewLoading.value = false
  }
}

async function loadActivation() {
  activationLoading.value = true
  activationError.value = ''
  try {
    activationData.value = await fetchAnalyticsActivation({
      days: activationDays.value,
      activation_window_days: activationWindow.value,
      tier: activationTierFilter.value !== 'all' ? activationTierFilter.value : undefined,
    })
    await nextTick()
    renderActivationChart()
  } catch (e: any) {
    activationError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    activationLoading.value = false
  }
}

async function loadRetention() {
  retentionLoading.value = true
  retentionError.value = ''
  try {
    retentionData.value = await fetchAnalyticsActivatedRetention({ weeks: retentionWeeks.value })
    await nextTick()
    renderRetentionChart()
  } catch (e: any) {
    retentionError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    retentionLoading.value = false
  }
}

async function loadValueRetention() {
  valueRetentionLoading.value = true
  valueRetentionError.value = ''
  try {
    valueRetentionData.value = await fetchAnalyticsValueRetention({ weeks: retentionWeeks.value })
    await nextTick()
    renderValueRetentionChart()
  } catch (e: any) {
    valueRetentionError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    valueRetentionLoading.value = false
  }
}

async function loadContent() {
  contentLoading.value = true
  contentError.value = ''
  stepFunnelLoading.value = true
  stepFunnelError.value = ''
  try {
    const [contentRes, stepRes] = await Promise.all([
      fetchAnalyticsContentFunnel({ days: contentDays.value }),
      fetchAnalyticsContentStepFunnel({ days: contentDays.value }),
    ])
    contentData.value = contentRes
    stepFunnelData.value = stepRes
    await nextTick()
    renderContentChart()
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '加载失败'
    contentError.value = msg
    stepFunnelError.value = msg
  } finally {
    contentLoading.value = false
    stepFunnelLoading.value = false
  }
}

async function loadAiFeatures() {
  aiLoading.value = true
  aiError.value = ''
  try {
    aiData.value = await fetchAnalyticsAiFeatures({ days: aiDays.value })
    await nextTick()
    renderAiChart()
  } catch (e: any) {
    aiError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    aiLoading.value = false
  }
}

async function loadEngagementDepth() {
  depthLoading.value = true
  depthError.value = ''
  try {
    depthData.value = await fetchAnalyticsEngagementDepth({ days: retentionWeeks.value * 7 })
    await nextTick()
    renderDepthChart()
  } catch (e: any) {
    depthError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    depthLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Chart renderers
// ---------------------------------------------------------------------------
function renderActivationChart() {
  if (!activationChartRef.value || !activationData.value) return
  if (activationChartInst) activationChartInst.dispose()
  activationChartInst = echarts.init(activationChartRef.value)
  const d = activationData.value
  activationChartInst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      data: ['新注册', '已激活'],
      textStyle: { color: '#a0a0a0', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 40, right: 20, top: 12, bottom: 40 },
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
      {
        name: '新注册',
        type: 'bar',
        data: d.daily_registrations,
        itemStyle: { color: 'rgba(45,184,226,0.5)' },
        barMaxWidth: 10,
      },
      {
        name: '已激活',
        type: 'bar',
        data: d.daily_activations,
        itemStyle: { color: 'rgba(46,230,109,0.8)' },
        barMaxWidth: 10,
        barGap: '-100%',
      },
    ],
  })
}

function renderRetentionChart() {
  if (!retentionChartRef.value || !retentionData.value) return
  if (retentionChartInst) retentionChartInst.dispose()
  retentionChartInst = echarts.init(retentionChartRef.value)

  const cohorts = retentionData.value.cohorts
  const maxWeeks = retentionData.value.weeks
  const heatData: number[][] = []
  const yLabels: string[] = []
  const xLabels: string[] = []
  for (let i = 0; i < maxWeeks; i++) xLabels.push(`W${i}`)

  cohorts.forEach((c: RetentionCohort, ci: number) => {
    yLabels.push(`${c.week}(${c.cohort_size})`)
    c.retention.forEach((v: number, wi: number) => {
      heatData.push([wi, ci, v])
    })
  })

  retentionChartInst.setOption({
    tooltip: {
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (p: any) => {
        const [week, cohort, val] = p.data
        return `${yLabels[cohort]}<br/>第${week}周留存: ${val}%`
      },
    },
    grid: { left: 90, right: 20, top: 12, bottom: 40 },
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

function renderValueRetentionChart() {
  if (!valueRetentionChartRef.value || !valueRetentionData.value) return
  if (valueRetentionChartInst) valueRetentionChartInst.dispose()
  valueRetentionChartInst = echarts.init(valueRetentionChartRef.value)

  const cohorts = valueRetentionData.value.cohorts
  const maxWeeks = valueRetentionData.value.weeks
  const heatData: number[][] = []
  const yLabels: string[] = []
  const xLabels: string[] = []
  for (let i = 0; i < maxWeeks; i++) xLabels.push(`W${i}`)

  cohorts.forEach((c: RetentionCohort, ci: number) => {
    yLabels.push(`${c.week}(${c.cohort_size})`)
    c.retention.forEach((v: number, wi: number) => {
      heatData.push([wi, ci, v])
    })
  })

  valueRetentionChartInst.setOption({
    tooltip: {
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (p: any) => {
        const [week, cohort, val] = p.data
        return `${yLabels[cohort]}<br/>第${week}周价值行为回访: ${val}%`
      },
    },
    grid: { left: 90, right: 20, top: 12, bottom: 40 },
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
      inRange: { color: ['#1a1a1a', '#2d0e58', '#a64dff'] },
    },
    series: [{
      type: 'heatmap',
      data: heatData,
      label: { show: true, color: '#fff', fontSize: 10, formatter: (p: any) => `${p.data[2]}%` },
      itemStyle: { borderWidth: 2, borderColor: '#111' },
    }],
  })
}

function renderContentChart() {
  if (!contentChartRef.value || !contentData.value) return
  if (contentChartInst) contentChartInst.dispose()
  contentChartInst = echarts.init(contentChartRef.value)
  const d = contentData.value
  contentChartInst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      data: ['论文浏览', '收藏', '写笔记'],
      textStyle: { color: '#a0a0a0', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 40, right: 20, top: 12, bottom: 40 },
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
      {
        name: '论文浏览',
        type: 'line',
        data: d.daily_paper_views,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2db8e2' },
        symbol: 'none',
      },
      {
        name: '收藏',
        type: 'bar',
        data: d.daily_saves,
        itemStyle: { color: 'rgba(245,183,49,0.7)' },
        barMaxWidth: 8,
      },
      {
        name: '写笔记',
        type: 'bar',
        data: d.daily_notes,
        itemStyle: { color: 'rgba(166,77,255,0.7)' },
        barMaxWidth: 8,
      },
    ],
  })
}

function renderAiChart() {
  if (!aiChartRef.value || !aiData.value) return
  if (aiChartInst) aiChartInst.dispose()
  aiChartInst = echarts.init(aiChartRef.value)
  const d = aiData.value
  aiChartInst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
    },
    legend: {
      data: ['深度研究', '论文聊天', '灵感生成'],
      textStyle: { color: '#a0a0a0', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 36, right: 20, top: 12, bottom: 40 },
    xAxis: {
      type: 'category',
      data: d.dates.map((s: string) => s.slice(5)),
      axisLabel: { color: '#666', fontSize: 10, rotate: 45 },
      axisLine: { lineStyle: { color: '#333' } },
    },
    yAxis: {
      type: 'value',
      name: '日活用户数',
      nameTextStyle: { color: '#555', fontSize: 10 },
      axisLabel: { color: '#666', fontSize: 10 },
      splitLine: { lineStyle: { color: '#222' } },
    },
    series: [
      {
        name: '深度研究',
        type: 'line',
        data: d.features.research.daily,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2db8e2' },
        symbol: 'none',
      },
      {
        name: '论文聊天',
        type: 'line',
        data: d.features.chat.daily,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2ee66d' },
        symbol: 'none',
      },
      {
        name: '灵感生成',
        type: 'line',
        data: d.features.idea.daily,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#a64dff' },
        symbol: 'none',
      },
    ],
  })
}

function renderDepthChart() {
  if (!depthChartRef.value || !depthData.value) return
  if (depthChartInst) depthChartInst.dispose()
  depthChartInst = echarts.init(depthChartRef.value)
  const d = depthData.value
  depthChartInst.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: any[]) => {
        const lines = params.map((p: any) => {
          const val = p.value != null ? Math.round(p.value) + '秒' : '暂无'
          return `${p.marker}${p.seriesName}: ${val}`
        })
        return `${params[0]?.axisValue}<br/>${lines.join('<br/>')}`
      },
    },
    legend: {
      data: ['平均 Session 时长', '平均论文阅读时长'],
      textStyle: { color: '#a0a0a0', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 44, right: 20, top: 12, bottom: 40 },
    xAxis: {
      type: 'category',
      data: d.dates.map((s: string) => s.slice(5)),
      axisLabel: { color: '#666', fontSize: 10, rotate: 45 },
      axisLine: { lineStyle: { color: '#333' } },
    },
    yAxis: {
      type: 'value',
      name: '秒',
      nameTextStyle: { color: '#555', fontSize: 10 },
      axisLabel: { color: '#666', fontSize: 10 },
      splitLine: { lineStyle: { color: '#222' } },
    },
    series: [
      {
        name: '平均 Session 时长',
        type: 'line',
        data: d.avg_session_duration_by_day,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#2ee66d' },
        connectNulls: true,
        symbol: 'none',
      },
      {
        name: '平均论文阅读时长',
        type: 'line',
        data: d.avg_paper_read_duration_by_day,
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        itemStyle: { color: '#f5b731' },
        connectNulls: true,
        symbol: 'none',
      },
    ],
  })
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
const resizeHandler = () => {
  activationChartInst?.resize()
  retentionChartInst?.resize()
  valueRetentionChartInst?.resize()
  contentChartInst?.resize()
  aiChartInst?.resize()
  depthChartInst?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', resizeHandler)
  // Load overview row and activation simultaneously
  loadOverview()
  await loadActivation()
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeHandler)
  activationChartInst?.dispose()
  retentionChartInst?.dispose()
  valueRetentionChartInst?.dispose()
  contentChartInst?.dispose()
  aiChartInst?.dispose()
  depthChartInst?.dispose()
})

watch(activeModule, (mod) => {
  if (mod === 'retention' && !retentionData.value) {
    loadRetention()
    loadEngagementDepth()
  }
  if (mod === 'content' && !contentData.value) loadContent()
  if (mod === 'ai' && !aiData.value) loadAiFeatures()
})

watch(activationDays, () => loadActivation())
watch(activationWindow, () => loadActivation())
watch(activationTierFilter, () => loadActivation())
watch(retentionWeeks, () => {
  loadRetention()
  if (retentionType.value === 'value') loadValueRetention()
  if (depthData.value) loadEngagementDepth()
})
watch(retentionType, (type) => {
  if (type === 'value' && !valueRetentionData.value) loadValueRetention()
  if (type === 'session') {
    nextTick(() => renderRetentionChart())
  } else {
    nextTick(() => renderValueRetentionChart())
  }
})
watch(contentDays, () => loadContent())
watch(aiDays, () => loadAiFeatures())

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function activationRateColor(rate: number): string {
  if (rate >= 50) return 'text-tinder-green'
  if (rate >= 25) return 'text-tinder-gold'
  return 'text-red-400'
}

function conversionRateColor(rate: number): string {
  if (rate >= 30) return 'text-tinder-green'
  if (rate >= 10) return 'text-tinder-gold'
  return 'text-red-400'
}

function penetrationRateColor(rate: number): string {
  if (rate >= 30) return 'text-tinder-green'
  if (rate >= 10) return 'text-tinder-gold'
  return 'text-red-400'
}

function fmtSeconds(s: number | null | undefined): string {
  if (s == null) return '—'
  if (s < 60) return `${Math.round(s)}秒`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  return rem > 0 ? `${m}分${rem}秒` : `${m}分钟`
}
</script>

<template>
  <div class="space-y-5">
    <!-- ====================================================================
         Health Overview Row (今日快速巡检)
    ===================================================================== -->
    <div v-if="overviewData" class="grid grid-cols-2 sm:grid-cols-5 gap-2">
      <div v-for="kpi in [
        { label: '今日活跃', value: overviewData.active_today, sub: `7日: ${overviewData.active_7d}`, color: 'text-tinder-blue' },
        { label: '今日新注册', value: overviewData.new_today, sub: `7日: ${overviewData.new_7d}`, color: 'text-tinder-green' },
        { label: '今日页面浏览', value: overviewData.today_events.page_views, sub: '(page_view 事件)', color: 'text-tinder-gold' },
        { label: '今日论文浏览', value: overviewData.today_events.paper_views, sub: '(paper_view 事件)', color: 'text-purple-400' },
        { label: '累计收藏', value: overviewData.content_stats.papers_saved, sub: `笔记: ${overviewData.content_stats.notes_written}`, color: 'text-tinder-blue' },
      ]" :key="kpi.label"
        class="bg-bg-card rounded-lg px-3 py-2.5 border border-border flex flex-col gap-0.5">
        <div class="text-[10px] text-text-muted">{{ kpi.label }}</div>
        <div class="text-xl font-bold" :class="kpi.color">{{ kpi.value.toLocaleString() }}</div>
        <div class="text-[10px] text-text-muted/70">{{ kpi.sub }}</div>
      </div>
    </div>
    <div v-else-if="overviewLoading" class="flex items-center gap-2 text-text-muted text-xs py-1">
      <div class="w-3 h-3 border border-tinder-blue border-t-transparent rounded-full animate-spin"></div>
      <span>加载总览数据…</span>
    </div>

    <!-- Module selector -->
    <div class="flex gap-1 bg-bg-elevated rounded-lg p-1">
      <button
        v-for="mod in [
          { key: 'activation', label: '新用户激活', hint: '他们有没有完成首次有价值行为？' },
          { key: 'retention', label: '激活用户留存', hint: '已激活用户是否持续回来？' },
          { key: 'content', label: '内容与功能价值', hint: '什么内容/功能在真正驱动行为？' },
          { key: 'ai', label: 'AI 功能采用', hint: '深度研究/聊天/灵感的渗透率与趋势' },
        ]"
        :key="mod.key"
        @click="activeModule = mod.key as any"
        class="flex-1 px-3 py-2.5 rounded-md text-xs font-medium transition-all text-left"
        :class="activeModule === mod.key
          ? 'bg-tinder-blue/20 text-tinder-blue'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        <div class="font-semibold">{{ mod.label }}</div>
        <div class="text-[10px] mt-0.5 opacity-70 hidden sm:block">{{ mod.hint }}</div>
      </button>
    </div>

    <!-- ====================================================================
         Module A: 新用户激活
    ===================================================================== -->
    <div v-if="activeModule === 'activation'" class="space-y-4">
      <!-- Controls (统计范围 + 激活窗口 + 用户层级分群) -->
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>统计范围</span>
          <select v-model="activationDays" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option :value="14">近14天</option>
            <option :value="30">近30天</option>
            <option :value="60">近60天</option>
            <option :value="90">近90天</option>
          </select>
        </div>
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>激活窗口</span>
          <select v-model="activationWindow" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option :value="3">注册后3天</option>
            <option :value="7">注册后7天</option>
            <option :value="14">注册后14天</option>
          </select>
        </div>
        <!-- 分群：按用户层级过滤 -->
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>用户层级</span>
          <select v-model="activationTierFilter" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option value="all">全部</option>
            <option value="free">免费</option>
            <option value="pro">Pro</option>
            <option value="pro_plus">Pro+</option>
          </select>
        </div>
        <!-- 激活定义说明 -->
        <div class="ml-auto text-[10px] text-text-muted/70 bg-bg-elevated rounded px-2 py-1 border border-border/50">
          激活 = 收藏/笔记/批注/对比，不含 dismiss
        </div>
      </div>

      <div v-if="activationLoading" class="flex items-center justify-center py-16">
        <div class="w-6 h-6 border-2 border-tinder-blue border-t-transparent rounded-full animate-spin"></div>
        <span class="ml-3 text-text-muted text-sm">计算激活数据…</span>
      </div>
      <div v-else-if="activationError" class="text-center py-10 text-red-400 text-sm">{{ activationError }}</div>

      <template v-else-if="activationData">
        <!-- Primary signal: activation rate -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <!-- Headline signal -->
          <div class="md:col-span-2 bg-bg-card rounded-xl p-5 border border-border flex flex-col justify-between">
            <div class="text-xs text-text-muted mb-1">
              {{ activationWindow }}日激活率
              <span class="ml-1 text-text-muted/60">（注册后{{ activationWindow }}天内完成首次有价值行为）</span>
            </div>
            <div class="text-4xl font-bold" :class="activationRateColor(activationData.activation_rate_overall)">
              {{ activationData.activation_rate_overall }}%
            </div>
            <div class="text-[11px] text-text-muted mt-2">
              本期注册 {{ activationData.activation_funnel.registered }} 人 ·
              已激活 {{ activationData.activation_funnel.activated }} 人 ·
              等待中 {{ activationData.activation_funnel.pending }} 人
            </div>
          </div>

          <!-- Funnel breakdown -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs text-text-muted mb-3">激活漏斗明细</div>
            <div class="space-y-2">
              <div v-for="item in [
                { label: '注册', value: activationData.activation_funnel.registered, color: 'bg-tinder-blue/20 text-tinder-blue' },
                { label: '已激活', value: activationData.activation_funnel.activated, color: 'bg-tinder-green/20 text-tinder-green' },
                { label: '窗口内待激活', value: activationData.activation_funnel.pending, color: 'bg-tinder-gold/20 text-tinder-gold' },
                { label: '超期未激活', value: activationData.activation_funnel.not_activated, color: 'bg-gray-500/20 text-gray-400' },
              ]" :key="item.label" class="flex items-center justify-between">
                <span class="text-xs text-text-secondary">{{ item.label }}</span>
                <span class="text-xs font-semibold px-2 py-0.5 rounded-full" :class="item.color">{{ item.value }}</span>
              </div>
            </div>
          </div>

          <!-- Non-activated alert -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs text-text-muted mb-1">超期未激活</div>
            <div class="text-2xl font-bold text-red-400">{{ activationData.activation_funnel.not_activated }}</div>
            <div class="text-[11px] text-text-muted mt-1">注册已超过{{ activationWindow }}天，无任何关键行为</div>
            <button
              v-if="activationData.recent_unactivated.length > 0"
              @click="showUnactivatedList = !showUnactivatedList"
              class="mt-2 text-[10px] text-tinder-blue hover:underline"
            >
              {{ showUnactivatedList ? '收起' : '查看列表' }}
            </button>
          </div>
        </div>

        <!-- Activation trend chart -->
        <div class="bg-bg-card rounded-xl p-4 border border-border">
          <div class="text-xs font-semibold text-text-primary mb-3">
            每日注册 vs 激活趋势
            <span class="ml-2 text-text-muted font-normal text-[11px]">绿色为激活，蓝色（叠加）为注册总量</span>
          </div>
          <div ref="activationChartRef" class="w-full h-52"></div>
        </div>

        <!-- Tier breakdown segment table (分群：按层级看激活率差异) -->
        <div v-if="tierBreakdownRows.length > 0" class="bg-bg-card rounded-xl border border-border overflow-hidden">
          <div class="px-4 py-2 bg-bg-elevated border-b border-border flex items-center justify-between">
            <span class="text-xs font-semibold text-text-primary">按用户层级分群</span>
            <button @click="showTierBreakdown = !showTierBreakdown" class="text-[10px] text-tinder-blue hover:underline">
              {{ showTierBreakdown ? '收起' : '展开' }}
            </button>
          </div>
          <div v-if="showTierBreakdown" class="p-3">
            <div class="grid gap-2">
              <div v-for="row in tierBreakdownRows" :key="row.tier"
                class="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-bg-elevated">
                <span class="text-xs font-semibold w-10"
                  :class="row.tier === 'pro_plus' ? 'text-red-400' : row.tier === 'pro' ? 'text-amber-400' : 'text-gray-400'">
                  {{ row.label }}
                </span>
                <div class="flex-1 h-2 bg-bg-hover rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all"
                    :style="{ width: row.rate + '%' }"
                    :class="row.rate >= 50 ? 'bg-tinder-green' : row.rate >= 25 ? 'bg-tinder-gold' : 'bg-red-400/70'">
                  </div>
                </div>
                <span class="text-xs font-bold w-12 text-right"
                  :class="row.rate >= 50 ? 'text-tinder-green' : row.rate >= 25 ? 'text-tinder-gold' : 'text-red-400'">
                  {{ row.rate }}%
                </span>
                <span class="text-[11px] text-text-muted w-20 text-right">
                  {{ row.activated }}/{{ row.registered }} 人
                </span>
              </div>
            </div>
            <p class="mt-2 text-[10px] text-text-muted/60">
              对比不同层级激活率，判断是产品问题还是特定用户群体的问题。
            </p>
          </div>
          <div v-else class="px-4 py-2 flex gap-4">
            <span v-for="row in tierBreakdownRows" :key="row.tier"
              class="text-[11px] flex items-center gap-1.5">
              <span class="font-medium"
                :class="row.tier === 'pro_plus' ? 'text-red-400' : row.tier === 'pro' ? 'text-amber-400' : 'text-gray-400'">
                {{ row.label }}
              </span>
              <span :class="row.rate >= 50 ? 'text-tinder-green' : row.rate >= 25 ? 'text-tinder-gold' : 'text-red-400'" class="font-bold">
                {{ row.rate }}%
              </span>
            </span>
          </div>
        </div>

        <!-- Drill-down: unactivated user list -->
        <div v-if="showUnactivatedList && activationData.recent_unactivated.length > 0" class="bg-bg-card rounded-xl border border-border overflow-hidden">
          <div class="px-4 py-2 bg-bg-elevated border-b border-border flex items-center justify-between">
            <span class="text-xs font-semibold text-text-primary">超期未激活用户（最多20条）</span>
            <span class="text-[10px] text-text-muted">橙色=窗口期内仍可激活</span>
          </div>
          <table class="w-full text-xs">
            <thead>
              <tr class="bg-bg-elevated border-b border-border text-text-muted">
                <th class="text-left px-3 py-2 font-medium">用户</th>
                <th class="text-left px-3 py-2 font-medium">等级</th>
                <th class="text-left px-3 py-2 font-medium">注册时间</th>
                <th class="text-left px-3 py-2 font-medium">最后登录</th>
                <th class="text-left px-3 py-2 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in activationData.recent_unactivated"
                :key="u.user_id"
                class="border-b border-border/50 hover:bg-bg-hover/30"
              >
                <td class="px-3 py-2">
                  <div class="text-text-primary font-medium">{{ u.username }}</div>
                  <div class="text-text-muted text-[10px]">ID: {{ u.user_id }}</div>
                </td>
                <td class="px-3 py-2">
                  <span class="px-1.5 py-0.5 rounded-full text-[10px]"
                    :class="u.tier === 'pro' ? 'bg-amber-500/20 text-amber-400' : u.tier === 'pro+' ? 'bg-red-500/20 text-red-400' : 'bg-gray-500/20 text-gray-400'">
                    {{ u.tier }}
                  </span>
                </td>
                <td class="px-3 py-2 text-text-muted font-mono">{{ formatDate(u.created_at) }}</td>
                <td class="px-3 py-2 text-text-muted font-mono">{{ formatDate(u.last_login_at) }}</td>
                <td class="px-3 py-2">
                  <span class="text-[10px]" :class="u.is_pending ? 'text-tinder-gold' : 'text-red-400'">
                    {{ u.is_pending ? '窗口期内' : '已超期' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ====================================================================
         Module B: 激活用户留存
    ===================================================================== -->
    <div v-if="activeModule === 'retention'" class="space-y-4">
      <!-- Controls -->
      <!-- Controls: 周数 + 留存类型切换 -->
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>回看周数</span>
          <select v-model="retentionWeeks" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option :value="6">6周</option>
            <option :value="8">8周</option>
            <option :value="12">12周</option>
          </select>
        </div>
        <!-- 留存类型切换 -->
        <div class="flex items-center gap-1 bg-bg-elevated rounded-lg p-0.5 border border-border">
          <button @click="retentionType = 'session'"
            class="px-3 py-1 text-xs rounded-md transition-all"
            :class="retentionType === 'session' ? 'bg-tinder-green/20 text-tinder-green font-medium' : 'text-text-muted hover:text-text-secondary'">
            会话留存
          </button>
          <button @click="retentionType = 'value'"
            class="px-3 py-1 text-xs rounded-md transition-all"
            :class="retentionType === 'value' ? 'bg-purple-500/20 text-purple-400 font-medium' : 'text-text-muted hover:text-text-secondary'">
            价值行为留存
          </button>
        </div>
        <div class="text-[10px] text-text-muted/60 bg-bg-elevated rounded px-2 py-1 border border-border/50">
          <span v-if="retentionType === 'session'">会话 = 有过登录/访问（含只看未操作）</span>
          <span v-else class="text-purple-400/80">价值行为 = 当周做了收藏/笔记/批注/对比</span>
        </div>
      </div>

      <!-- Session retention -->
      <template v-if="retentionType === 'session'">
        <div v-if="retentionLoading" class="flex items-center justify-center py-16">
          <div class="w-6 h-6 border-2 border-tinder-green border-t-transparent rounded-full animate-spin"></div>
          <span class="ml-3 text-text-muted text-sm">计算留存数据…</span>
        </div>
        <div v-else-if="retentionError" class="text-center py-10 text-red-400 text-sm">{{ retentionError }}</div>
        <template v-else-if="retentionData">
          <!-- Headline -->
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div class="bg-bg-card rounded-xl p-4 border border-border">
              <div class="text-xs text-text-muted mb-1">激活用户总数</div>
              <div class="text-3xl font-bold text-tinder-green">{{ retentionData.total_activated }}</div>
              <div class="text-[11px] text-text-muted mt-1">曾完成过至少一次关键行为的用户</div>
            </div>
            <div class="md:col-span-2 bg-bg-card rounded-xl p-4 border border-border">
              <div class="text-xs text-text-muted mb-1">口径说明（会话留存）</div>
              <div class="text-xs text-text-secondary leading-relaxed">
                统计<span class="text-tinder-green font-medium">已激活用户</span>在各周是否有过会话（登录或访问）。
                W0 = 注册当周，W1 = 次周。<span class="text-tinder-gold">注意：会话留存不等于有效使用，建议对照「价值行为留存」。</span>
              </div>
            </div>
          </div>
          <!-- Heatmap -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs font-semibold text-text-primary mb-3">
              激活用户周留存热力图（会话）
              <span class="ml-2 text-text-muted font-normal text-[11px]">每行 = 一个注册周 cohort，括号内为人数</span>
            </div>
            <div ref="retentionChartRef" class="w-full h-72"></div>
          </div>
          <!-- Detail table -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">留存明细表（会话）</div>
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="bg-bg-elevated border-b border-border text-text-muted">
                    <th class="text-left px-2 py-2 font-medium">注册周</th>
                    <th class="text-center px-2 py-2 font-medium">人数</th>
                    <th v-for="w in retentionData.weeks" :key="w" class="text-center px-2 py-2 font-medium">W{{ w - 1 }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in retentionData.cohorts" :key="c.week" class="border-b border-border/50">
                    <td class="px-2 py-1.5 text-text-secondary font-mono">{{ c.week }}</td>
                    <td class="px-2 py-1.5 text-center text-text-muted">{{ c.cohort_size }}</td>
                    <td v-for="(r, ri) in c.retention" :key="ri" class="px-2 py-1.5 text-center font-mono"
                      :class="r > 50 ? 'text-tinder-green' : r > 20 ? 'text-tinder-gold' : 'text-text-muted'">
                      {{ c.cohort_size > 0 ? r + '%' : '—' }}
                    </td>
                    <td v-for="_ in retentionData.weeks - c.retention.length" :key="'pad-' + _"
                      class="px-2 py-1.5 text-center text-text-muted">—</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </template>

      <!-- Value action retention -->
      <template v-else>
        <div v-if="valueRetentionLoading" class="flex items-center justify-center py-16">
          <div class="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
          <span class="ml-3 text-text-muted text-sm">计算价值行为留存…</span>
        </div>
        <div v-else-if="valueRetentionError" class="text-center py-10 text-red-400 text-sm">{{ valueRetentionError }}</div>
        <template v-else-if="valueRetentionData">
          <!-- Headline -->
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div class="bg-bg-card rounded-xl p-4 border border-border">
              <div class="text-xs text-text-muted mb-1">激活用户总数</div>
              <div class="text-3xl font-bold text-purple-400">{{ valueRetentionData.total_activated }}</div>
              <div class="text-[11px] text-text-muted mt-1">曾完成收藏/笔记/批注/对比的用户</div>
            </div>
            <div class="md:col-span-2 bg-bg-card rounded-xl p-4 border border-border">
              <div class="text-xs text-text-muted mb-1">口径说明（价值行为留存）</div>
              <div class="text-xs text-text-secondary leading-relaxed">
                统计<span class="text-purple-400 font-medium">已激活用户</span>在各周是否有收藏/写笔记/批注/对比操作。
                比会话留存更能反映<span class="text-purple-400">真实的产品使用价值</span>。
                数据明显低于会话留存时，说明用户在"回来但不用核心功能"。
              </div>
            </div>
          </div>
          <!-- Heatmap -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs font-semibold text-text-primary mb-3">
              激活用户周留存热力图（价值行为）
              <span class="ml-2 text-text-muted font-normal text-[11px]">紫色深度代表该 cohort 做了实际价值操作的比例</span>
            </div>
            <div ref="valueRetentionChartRef" class="w-full h-72"></div>
          </div>
          <!-- Detail table -->
          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">留存明细表（价值行为）</div>
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="bg-bg-elevated border-b border-border text-text-muted">
                    <th class="text-left px-2 py-2 font-medium">注册周</th>
                    <th class="text-center px-2 py-2 font-medium">人数</th>
                    <th v-for="w in valueRetentionData.weeks" :key="w" class="text-center px-2 py-2 font-medium">W{{ w - 1 }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in valueRetentionData.cohorts" :key="c.week" class="border-b border-border/50">
                    <td class="px-2 py-1.5 text-text-secondary font-mono">{{ c.week }}</td>
                    <td class="px-2 py-1.5 text-center text-text-muted">{{ c.cohort_size }}</td>
                    <td v-for="(r, ri) in c.retention" :key="ri" class="px-2 py-1.5 text-center font-mono"
                      :class="r > 50 ? 'text-purple-400' : r > 20 ? 'text-tinder-gold' : 'text-text-muted'">
                      {{ c.cohort_size > 0 ? r + '%' : '—' }}
                    </td>
                    <td v-for="_ in valueRetentionData.weeks - c.retention.length" :key="'vpad-' + _"
                      class="px-2 py-1.5 text-center text-text-muted">—</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </template>

      <!-- ---- Engagement Depth (嵌入 Module B 底部) ---- -->
      <div class="bg-bg-card rounded-xl border border-border overflow-hidden">
        <div class="px-4 py-2 bg-bg-elevated border-b border-border flex items-center justify-between">
          <span class="text-xs font-semibold text-text-primary">参与深度（Session 时长 + 阅读时长）</span>
          <span class="text-[10px] text-text-muted/70">来自前端 session_duration / paper_view_duration 事件</span>
        </div>

        <div v-if="depthLoading" class="flex items-center gap-2 px-4 py-4 text-text-muted text-xs">
          <div class="w-4 h-4 border-2 border-tinder-green border-t-transparent rounded-full animate-spin"></div>
          <span>加载参与深度数据…</span>
        </div>
        <div v-else-if="depthError" class="px-4 py-3 text-red-400 text-xs">{{ depthError }}</div>
        <template v-else-if="depthData">
          <div v-if="!depthData.data_available" class="px-4 py-4 text-text-muted text-xs">
            暂无事件数据（需前端埋点积累后才有 session_duration / paper_view_duration 记录）
          </div>
          <template v-else>
            <!-- KPI 行 -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 p-4">
              <div class="bg-bg-elevated rounded-lg p-3 border border-border/50">
                <div class="text-[10px] text-text-muted mb-1">均 Session 时长</div>
                <div class="text-xl font-bold text-tinder-green">{{ fmtSeconds(depthData.window_avg_session_seconds) }}</div>
                <div class="text-[10px] text-text-muted/60 mt-1">近 {{ depthData.days }} 天均值</div>
              </div>
              <div class="bg-bg-elevated rounded-lg p-3 border border-border/50">
                <div class="text-[10px] text-text-muted mb-1">均论文阅读时长</div>
                <div class="text-xl font-bold text-tinder-gold">{{ fmtSeconds(depthData.window_avg_paper_read_seconds) }}</div>
                <div class="text-[10px] text-text-muted/60 mt-1">近 {{ depthData.days }} 天均值</div>
              </div>
              <!-- Session 时长分布 -->
              <div class="md:col-span-2 bg-bg-elevated rounded-lg p-3 border border-border/50">
                <div class="text-[10px] text-text-muted mb-2">Session 时长分布</div>
                <div class="grid grid-cols-4 gap-1 text-center">
                  <div v-for="bucket in [
                    { label: '<30秒', value: depthData.session_duration_distribution.lt30s, color: 'text-red-400' },
                    { label: '30秒-2分', value: depthData.session_duration_distribution.s30_120, color: 'text-tinder-gold' },
                    { label: '2-10分', value: depthData.session_duration_distribution.m2_10, color: 'text-tinder-green' },
                    { label: '>10分', value: depthData.session_duration_distribution.gt10m, color: 'text-tinder-blue' },
                  ]" :key="bucket.label">
                    <div class="text-[9px] text-text-muted mb-0.5">{{ bucket.label }}</div>
                    <div class="text-sm font-bold" :class="bucket.color">{{ bucket.value }}</div>
                  </div>
                </div>
                <div class="text-[9px] text-text-muted/50 mt-1">次数。&lt;30秒占比高 = 大量浅浏览，需关注</div>
              </div>
            </div>
            <!-- 趋势图 -->
            <div class="px-4 pb-4">
              <div class="text-[10px] text-text-muted mb-2">日均时长趋势（秒）</div>
              <div ref="depthChartRef" class="w-full h-44"></div>
            </div>
          </template>
        </template>
        <div v-else class="px-4 py-3 text-text-muted text-xs">切换到此 Tab 时自动加载参与深度数据</div>
      </div>
    </div>

    <!-- ====================================================================
         Module C: 内容与功能价值
    ===================================================================== -->
    <div v-if="activeModule === 'content'" class="space-y-4">
      <!-- Controls -->
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>统计范围</span>
          <select v-model="contentDays" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option :value="14">近14天</option>
            <option :value="30">近30天</option>
            <option :value="60">近60天</option>
          </select>
        </div>
      </div>

      <div v-if="contentLoading" class="flex items-center justify-center py-16">
        <div class="w-6 h-6 border-2 border-tinder-gold border-t-transparent rounded-full animate-spin"></div>
        <span class="ml-3 text-text-muted text-sm">计算转化数据…</span>
      </div>
      <div v-else-if="contentError" class="text-center py-10 text-red-400 text-sm">{{ contentError }}</div>

      <template v-else-if="contentData">
        <!-- ---- Step Funnel (严格步骤漏斗) ---- -->
        <div class="bg-bg-card rounded-xl p-4 border border-border">
          <div class="text-xs font-semibold text-text-primary mb-4">
            发现 → 参与 步骤漏斗
            <span class="ml-2 text-text-muted font-normal text-[11px]">去重用户数；各步骤独立统计，drop-off 即为流失</span>
          </div>
          <div v-if="stepFunnelData" class="space-y-3">
            <div
              v-for="(step, idx) in stepFunnelData.funnel"
              :key="step.step"
              class="flex items-center gap-3"
            >
              <!-- Step number -->
              <div class="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                :class="idx === 0 ? 'bg-tinder-blue/20 text-tinder-blue'
                  : idx === 1 ? 'bg-tinder-green/20 text-tinder-green'
                  : idx === 2 ? 'bg-tinder-gold/20 text-tinder-gold'
                  : 'bg-purple-500/20 text-purple-400'">
                {{ idx + 1 }}
              </div>
              <!-- Bar + label -->
              <div class="flex-1">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-xs text-text-secondary">{{ step.label }}</span>
                  <span class="text-xs font-bold font-mono"
                    :class="idx === 0 ? 'text-tinder-blue' : idx === 1 ? 'text-tinder-green' : idx === 2 ? 'text-tinder-gold' : 'text-purple-400'">
                    {{ step.users }} 人
                  </span>
                </div>
                <div class="h-2 bg-bg-hover rounded-full overflow-hidden">
                  <div class="h-full rounded-full transition-all"
                    :class="idx === 0 ? 'bg-tinder-blue/60' : idx === 1 ? 'bg-tinder-green/60' : idx === 2 ? 'bg-tinder-gold/60' : 'bg-purple-500/60'"
                    :style="{
                      width: stepFunnelData.funnel[0].users > 0
                        ? Math.round(step.users / stepFunnelData.funnel[0].users * 100) + '%'
                        : (step.users > 0 ? '100%' : '0%')
                    }">
                  </div>
                </div>
                <!-- Drop-off arrow between steps -->
                <div v-if="idx < stepFunnelData.funnel.length - 1 && stepFunnelData.funnel[idx].users > 0"
                  class="mt-1 text-[10px] text-text-muted/60 flex items-center gap-1">
                  <span>↓</span>
                  <span class="text-red-400/70">
                    流失 {{ stepFunnelData.funnel[idx].users - stepFunnelData.funnel[idx+1].users }} 人
                    ({{ Math.round((stepFunnelData.funnel[idx].users - stepFunnelData.funnel[idx+1].users) / stepFunnelData.funnel[idx].users * 100) }}%)
                  </span>
                </div>
              </div>
              <!-- Note if any -->
              <div v-if="step.note" class="flex-shrink-0 text-[10px] text-tinder-gold/70 max-w-[120px] text-right">
                {{ step.note }}
              </div>
            </div>
          </div>
          <div v-else class="py-8 text-center text-text-muted text-xs">漏斗数据加载中…</div>
        </div>

        <!-- ---- Conversion headline + action breakdown ---- -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="md:col-span-2 bg-bg-card rounded-xl p-5 border border-border flex flex-col justify-between">
            <div class="text-xs text-text-muted mb-1">
              浏览→关键行为转化率
              <span class="ml-1 text-text-muted/60">（来自现有事件数据，作为参考指标）</span>
            </div>
            <div class="text-4xl font-bold" :class="conversionRateColor(contentData.conversion_rate)">
              {{ contentData.conversion_rate }}%
            </div>
            <div class="text-[11px] text-text-muted mt-2">
              浏览 {{ contentData.totals.paper_views }} 次 · 关键行为 {{ contentData.totals.key_actions }} 次
            </div>
            <div v-if="contentData.totals.paper_views === 0" class="mt-1 text-[11px] text-tinder-gold">
              浏览事件积累后才有转化率；收藏/笔记数据已可用
            </div>
          </div>

          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs text-text-muted mb-3">关键行为拆解</div>
            <div class="space-y-2">
              <div v-for="item in [
                { label: '收藏论文', value: contentData.totals.saves, color: 'text-tinder-gold' },
                { label: '写笔记', value: contentData.totals.notes, color: 'text-tinder-green' },
                { label: 'PDF批注', value: contentData.totals.annotations, color: 'text-tinder-blue' },
                { label: '对比分析', value: contentData.totals.compares, color: 'text-tinder-purple' },
              ]" :key="item.label" class="flex items-center justify-between">
                <span class="text-xs text-text-secondary">{{ item.label }}</span>
                <span class="text-xs font-semibold" :class="item.color">{{ item.value }}</span>
              </div>
            </div>
          </div>

          <div class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="text-xs text-text-muted mb-2">信号说明</div>
            <div class="text-[11px] text-text-secondary leading-relaxed space-y-1">
              <p><span class="text-tinder-blue">卡片曝光</span>需前端埋点积累</p>
              <p><span class="text-tinder-green">详情浏览</span>来自事件表，实时</p>
              <p><span class="text-tinder-gold">收藏/笔记</span>来自结构表，始终准确</p>
              <p class="text-text-muted/60 mt-1">漏斗各步独立去重，非同一批用户</p>
            </div>
          </div>
        </div>

        <!-- Daily trend chart -->
        <div class="bg-bg-card rounded-xl p-4 border border-border">
          <div class="text-xs font-semibold text-text-primary mb-3">
            每日浏览 vs 关键行为趋势
            <span class="ml-2 text-text-muted font-normal text-[11px]">关注浏览激增但行动平稳的日期</span>
          </div>
          <div ref="contentChartRef" class="w-full h-52"></div>
        </div>

        <!-- ---- Anomaly drill-down: high view, low save ---- -->
        <div v-if="stepFunnelData && stepFunnelData.high_view_low_save.length > 0"
          class="bg-bg-card rounded-xl border border-border overflow-hidden">
          <div class="px-4 py-2 bg-red-500/10 border-b border-red-500/20 flex items-center justify-between">
            <span class="text-xs font-semibold text-red-400">异常下钻：高浏览低收藏论文</span>
            <span class="text-[10px] text-text-muted">收藏率 &lt; 30%，浏览用户 ≥ 2，最多显示10条</span>
          </div>
          <table class="w-full text-xs">
            <thead>
              <tr class="bg-bg-elevated border-b border-border text-text-muted">
                <th class="text-left px-3 py-2 font-medium">论文标题</th>
                <th class="text-center px-3 py-2 font-medium">浏览用户</th>
                <th class="text-center px-3 py-2 font-medium">收藏用户</th>
                <th class="text-center px-3 py-2 font-medium">收藏率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in stepFunnelData.high_view_low_save" :key="p.paper_id"
                class="border-b border-border/50 hover:bg-bg-hover/30">
                <td class="px-3 py-2.5">
                  <div class="text-text-primary truncate max-w-xs" :title="p.title">{{ p.title }}</div>
                  <div class="text-text-muted text-[10px] font-mono">{{ p.paper_id }}</div>
                </td>
                <td class="px-3 py-2.5 text-center text-text-secondary font-mono">{{ p.view_users }}</td>
                <td class="px-3 py-2.5 text-center font-mono text-tinder-gold">{{ p.save_users }}</td>
                <td class="px-3 py-2.5 text-center font-mono">
                  <span :class="p.save_rate >= 20 ? 'text-tinder-gold' : 'text-red-400'">
                    {{ p.save_rate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="px-4 py-2 text-[10px] text-text-muted/60 border-t border-border/30">
            这些论文用户会打开但不收藏——可能是标题吸引但内容不匹配，或缺少保存价值的摘要
          </div>
        </div>

        <!-- Top papers drill-down -->
        <div v-if="contentData.top_papers.length > 0" class="bg-bg-card rounded-xl border border-border overflow-hidden">
          <div class="px-4 py-2 bg-bg-elevated border-b border-border flex items-center justify-between">
            <span class="text-xs font-semibold text-text-primary">热门论文（按收藏排序）</span>
            <span class="text-[10px] text-text-muted">转化率 = 收藏 / 浏览，空 = 尚无浏览事件</span>
          </div>
          <table class="w-full text-xs">
            <thead>
              <tr class="bg-bg-elevated border-b border-border text-text-muted">
                <th class="text-left px-3 py-2 font-medium">#</th>
                <th class="text-left px-3 py-2 font-medium">论文</th>
                <th class="text-center px-3 py-2 font-medium">浏览</th>
                <th class="text-center px-3 py-2 font-medium">收藏</th>
                <th class="text-center px-3 py-2 font-medium">转化率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, idx) in contentData.top_papers" :key="p.paper_id"
                class="border-b border-border/50 hover:bg-bg-hover/30">
                <td class="px-3 py-2.5 text-text-muted">{{ idx + 1 }}</td>
                <td class="px-3 py-2.5">
                  <div class="text-text-primary font-medium truncate max-w-xs" :title="p.title">{{ p.title }}</div>
                  <div class="text-text-muted text-[10px] font-mono">{{ p.paper_id }}</div>
                </td>
                <td class="px-3 py-2.5 text-center text-text-secondary font-mono">{{ p.view_count }}</td>
                <td class="px-3 py-2.5 text-center font-mono">
                  <span class="text-tinder-gold font-semibold">{{ p.save_count }}</span>
                </td>
                <td class="px-3 py-2.5 text-center font-mono">
                  <span v-if="p.view_to_save_rate !== null"
                    :class="p.view_to_save_rate >= 30 ? 'text-tinder-green' : p.view_to_save_rate >= 10 ? 'text-tinder-gold' : 'text-text-muted'">
                    {{ p.view_to_save_rate }}%
                  </span>
                  <span v-else class="text-text-muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-center py-8 text-text-muted text-sm">暂无论文收藏数据</div>
      </template>
    </div>

    <!-- ====================================================================
         Module D: AI 功能采用
    ===================================================================== -->
    <div v-if="activeModule === 'ai'" class="space-y-4">
      <!-- Controls -->
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span>统计范围</span>
          <select v-model="aiDays" class="bg-bg-elevated text-text-secondary text-xs rounded-md px-2 py-1 border border-border focus:outline-none">
            <option :value="14">近14天</option>
            <option :value="30">近30天</option>
            <option :value="60">近60天</option>
            <option :value="90">近90天</option>
          </select>
        </div>
        <div class="ml-auto text-[10px] text-text-muted/70 bg-bg-elevated rounded px-2 py-1 border border-border/50">
          渗透率 = 使用过任一AI功能的去重用户 / 已激活用户总数
        </div>
      </div>

      <div v-if="aiLoading" class="flex items-center justify-center py-16">
        <div class="w-6 h-6 border-2 border-tinder-blue border-t-transparent rounded-full animate-spin"></div>
        <span class="ml-3 text-text-muted text-sm">加载 AI 功能采用数据…</span>
      </div>
      <div v-else-if="aiError" class="text-center py-10 text-red-400 text-sm">{{ aiError }}</div>

      <template v-else-if="aiData">
        <!-- Penetration headline -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="md:col-span-2 bg-bg-card rounded-xl p-5 border border-border flex flex-col justify-between">
            <div class="text-xs text-text-muted mb-1">
              AI 功能渗透率
              <span class="ml-1 text-text-muted/60">（近 {{ aiData.days }} 天）</span>
            </div>
            <div class="text-4xl font-bold" :class="penetrationRateColor(aiData.penetration_rate)">
              {{ aiData.penetration_rate }}%
            </div>
            <div class="text-[11px] text-text-muted mt-2">
              已激活用户 {{ aiData.total_activated }} 人 · AI 用户（估算）约 {{ Math.max(aiData.features.research.users, aiData.features.chat.users, aiData.features.idea.users) }} 人
            </div>
          </div>

          <!-- Per-feature breakdown -->
          <div v-for="feat in [
            { key: 'research', label: '深度研究', icon: '🔬', color: 'text-tinder-blue', bg: 'bg-tinder-blue/10',
              stat: `${aiData.features.research.sessions ?? 0} 次会话`, users: aiData.features.research.users },
            { key: 'chat', label: '论文聊天', icon: '💬', color: 'text-tinder-green', bg: 'bg-tinder-green/10',
              stat: `${aiData.features.chat.sessions ?? 0} 次会话 · ${aiData.features.chat.messages ?? 0} 条消息`, users: aiData.features.chat.users },
            { key: 'idea', label: '灵感生成', icon: '💡', color: 'text-purple-400', bg: 'bg-purple-500/10',
              stat: `${aiData.features.idea.generated ?? 0} 个灵感`, users: aiData.features.idea.users },
          ]" :key="feat.key" class="bg-bg-card rounded-xl p-4 border border-border">
            <div class="flex items-center gap-1.5 mb-2">
              <span class="text-sm">{{ feat.icon }}</span>
              <span class="text-xs font-semibold" :class="feat.color">{{ feat.label }}</span>
            </div>
            <div class="text-2xl font-bold" :class="feat.color">{{ feat.users }}</div>
            <div class="text-[10px] text-text-muted mt-1">去重用户数</div>
            <div class="text-[10px] text-text-muted/70 mt-0.5">{{ feat.stat }}</div>
          </div>
        </div>

        <!-- Daily trend chart -->
        <div class="bg-bg-card rounded-xl p-4 border border-border">
          <div class="text-xs font-semibold text-text-primary mb-3">
            AI 功能日活用户趋势
            <span class="ml-2 text-text-muted font-normal text-[11px]">每日使用过该功能的去重用户数</span>
          </div>
          <div ref="aiChartRef" class="w-full h-52"></div>
        </div>

        <!-- Feature comparison table -->
        <div class="bg-bg-card rounded-xl border border-border overflow-hidden">
          <div class="px-4 py-2 bg-bg-elevated border-b border-border">
            <span class="text-xs font-semibold text-text-primary">功能对比一览</span>
          </div>
          <table class="w-full text-xs">
            <thead>
              <tr class="bg-bg-elevated border-b border-border text-text-muted">
                <th class="text-left px-3 py-2 font-medium">功能</th>
                <th class="text-center px-3 py-2 font-medium">去重用户</th>
                <th class="text-center px-3 py-2 font-medium">操作量</th>
                <th class="text-center px-3 py-2 font-medium">用户占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="feat in [
                { label: '深度研究', users: aiData.features.research.users, ops: aiData.features.research.sessions ?? 0, color: 'text-tinder-blue' },
                { label: '论文聊天', users: aiData.features.chat.users, ops: (aiData.features.chat.sessions ?? 0), opSub: `(${aiData.features.chat.messages ?? 0}条消息)`, color: 'text-tinder-green' },
                { label: '灵感生成', users: aiData.features.idea.users, ops: aiData.features.idea.generated ?? 0, color: 'text-purple-400' },
              ]" :key="feat.label" class="border-b border-border/50">
                <td class="px-3 py-2.5 font-medium" :class="feat.color">{{ feat.label }}</td>
                <td class="px-3 py-2.5 text-center font-mono text-text-secondary">{{ feat.users }}</td>
                <td class="px-3 py-2.5 text-center font-mono text-text-muted">
                  {{ feat.ops }}
                  <span v-if="(feat as any).opSub" class="text-[10px] ml-0.5">{{ (feat as any).opSub }}</span>
                </td>
                <td class="px-3 py-2.5 text-center font-mono">
                  <span :class="aiData.total_activated > 0 && feat.users / aiData.total_activated >= 0.1 ? 'text-tinder-green' : 'text-text-muted'">
                    {{ aiData.total_activated > 0 ? Math.round(feat.users / aiData.total_activated * 100) + '%' : '—' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="px-4 py-2 text-[10px] text-text-muted/60 border-t border-border/30">
            {{ aiData.note }}
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
