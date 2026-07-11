<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { FunnelChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { fetchPipelineDataTracking } from '../../api'
import type { PipelineDataTrackingRecord } from '../../types/paper'
import { getApiErrorMessage, reportClientError } from '../../utils/apiError'

echarts.use([
  LineChart,
  FunnelChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  CanvasRenderer,
])

const loading = ref(false)
const error = ref('')
const userId = ref(0)
const days = ref(30)
const records = ref<PipelineDataTrackingRecord[]>([])
const selectedDate = ref<string | null>(null)
const trendChartEl = ref<HTMLElement | null>(null)
const funnelChartEl = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
let funnelChart: echarts.ECharts | null = null

const steps: { key: keyof PipelineDataTrackingRecord; label: string }[] = [
  { key: 'arxiv_search', label: 'arXiv 检索' },
  { key: 'dedup', label: '去重' },
  { key: 'theme_scored', label: '主题评分' },
  { key: 'theme_passed', label: '主题过滤' },
  { key: 'institution_info', label: '机构信息' },
  { key: 'final_selected', label: '最终选中' },
  { key: 'summary_raw', label: '摘要生成' },
  { key: 'summary_limit', label: '摘要精简' },
  { key: 'paper_assets', label: '资源提取' },
]

function disposeCharts() {
  trendChart?.dispose()
  trendChart = null
  funnelChart?.dispose()
  funnelChart = null
}

function renderTrendChart() {
  if (!trendChartEl.value) return
  trendChart ??= echarts.init(trendChartEl.value)
  const chronologicalRecords = [...records.value].reverse()
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: steps.map(step => step.label), type: 'scroll', bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: {
      type: 'category',
      data: chronologicalRecords.map(record => record.date),
      axisLabel: { rotate: 30, fontSize: 11 },
    },
    yAxis: { type: 'value', name: '论文数量' },
    series: steps.map(step => ({
      name: step.label,
      type: 'line' as const,
      smooth: true,
      connectNulls: false,
      data: chronologicalRecords.map(record => record[step.key] ?? null),
    })),
  }, true)
}

function renderFunnelChart(record: PipelineDataTrackingRecord) {
  if (!funnelChartEl.value) return
  funnelChart ??= echarts.init(funnelChartEl.value)
  const data = steps
    .filter(step => record[step.key] !== null && record[step.key] !== undefined)
    .map(step => ({ name: step.label, value: record[step.key] as number }))
  funnelChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    series: [{
      type: 'funnel',
      left: '5%',
      right: '5%',
      top: '5%',
      bottom: '5%',
      sort: 'none',
      gap: 4,
      label: { show: true, position: 'inside', formatter: '{b}\n{c}' },
      labelLine: { show: false },
      data,
    }],
  }, true)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetchPipelineDataTracking({ user_id: userId.value, days: days.value })
    records.value = response.records
    await nextTick()
    renderTrendChart()
    if (selectedDate.value) {
      const record = records.value.find(item => item.date === selectedDate.value)
      if (record) renderFunnelChart(record)
    }
  } catch (cause: unknown) {
    reportClientError('admin.dataTracking.load', cause, '加载失败')
    error.value = getApiErrorMessage(cause, '加载失败')
  } finally {
    loading.value = false
  }
}

function selectDate(date: string) {
  selectedDate.value = date
  nextTick(() => {
    const record = records.value.find(item => item.date === date)
    if (record) renderFunnelChart(record)
  })
}

watch([userId, days], load)
onMounted(load)
onBeforeUnmount(disposeCharts)
</script>

<template>
  <section class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
    <header class="shrink-0">
      <h1 class="text-lg font-bold text-text-primary">📈 数据追踪</h1>
      <p class="text-xs text-text-muted mt-0.5">查看每天 Pipeline 各步骤的论文数量变化</p>
    </header>

    <div class="flex flex-wrap items-center gap-3 shrink-0">
      <div class="flex items-center gap-2">
        <label for="data-tracking-user-id" class="text-xs text-text-secondary whitespace-nowrap">用户 ID</label>
        <input
          id="data-tracking-user-id"
          v-model.number="userId"
          type="number"
          min="0"
          class="w-20 px-2 py-1.5 text-sm rounded-lg border border-border bg-bg-secondary text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>
      <div class="flex items-center gap-2">
        <label for="data-tracking-days" class="text-xs text-text-secondary whitespace-nowrap">天数</label>
        <select
          id="data-tracking-days"
          v-model.number="days"
          class="px-2 py-1.5 text-sm rounded-lg border border-border bg-bg-secondary text-text-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option :value="7">最近 7 天</option>
          <option :value="14">最近 14 天</option>
          <option :value="30">最近 30 天</option>
          <option :value="60">最近 60 天</option>
          <option :value="90">最近 90 天</option>
        </select>
      </div>
      <button
        type="button"
        :disabled="loading"
        class="px-3 py-1.5 text-sm rounded-lg bg-primary text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
        @click="load"
      >
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div v-if="error" role="alert" class="text-red-400 text-sm shrink-0">{{ error }}</div>
    <div v-if="loading && !records.length" class="text-text-muted text-sm">加载中…</div>
    <div v-else-if="!loading && !records.length && !error" class="text-text-muted text-sm">
      暂无数据。请先运行 Pipeline 后再查看。
    </div>

    <template v-else-if="records.length">
      <div class="shrink-0 bg-bg-secondary rounded-xl border border-border p-4">
        <h2 class="text-sm font-semibold text-text-primary mb-3">各步骤论文数量趋势</h2>
        <div ref="trendChartEl" style="height: 300px; width: 100%;"></div>
      </div>

      <div class="shrink-0 bg-bg-secondary rounded-xl border border-border overflow-auto">
        <table class="w-full text-xs min-w-[700px]">
          <thead>
            <tr class="border-b border-border">
              <th class="py-2 px-3 text-left text-text-secondary font-medium whitespace-nowrap">日期</th>
              <th
                v-for="step in steps"
                :key="step.key"
                class="py-2 px-2 text-center text-text-secondary font-medium whitespace-nowrap"
              >{{ step.label }}</th>
              <th class="py-2 px-2 text-center text-text-secondary font-medium whitespace-nowrap">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="record in records"
              :key="record.date"
              class="border-b border-border/50 hover:bg-bg-primary/40 transition-colors"
              :class="selectedDate === record.date ? 'bg-primary/5' : ''"
            >
              <td class="py-2 px-3 font-mono text-text-primary whitespace-nowrap">{{ record.date }}</td>
              <td
                v-for="step in steps"
                :key="step.key"
                class="py-2 px-2 text-center whitespace-nowrap"
              >
                <span
                  v-if="record[step.key] !== null && record[step.key] !== undefined"
                  class="font-mono text-text-primary"
                >{{ record[step.key] }}</span>
                <span v-else class="text-text-muted">—</span>
              </td>
              <td class="py-2 px-2 text-center">
                <button
                  type="button"
                  class="px-2 py-0.5 text-[11px] rounded bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                  @click="selectDate(record.date)"
                >漏斗图</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="selectedDate" class="shrink-0 bg-bg-secondary rounded-xl border border-border p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-text-primary">{{ selectedDate }} 数据漏斗</h2>
          <button
            type="button"
            aria-label="关闭数据漏斗"
            class="text-text-muted hover:text-text-primary text-lg leading-none"
            @click="selectedDate = null"
          >×</button>
        </div>
        <div ref="funnelChartEl" style="height: 360px; width: 100%;"></div>
      </div>
    </template>
  </section>
</template>
