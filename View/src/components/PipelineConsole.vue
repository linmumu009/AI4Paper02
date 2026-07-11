<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  fetchPipelineRuns,
  fetchPipelineRunSteps,
  fetchPipelineRunEvents,
  fetchPipelineRunArtifacts,
  fetchPipelineRunLog,
  rerunPipeline,
  type PipelineRunRecord,
  type PipelineStepRun,
  type PipelineArtifact,
  type PipelineEvent,
} from '../api'
import { usePollingTask } from '../composables/usePollingTask'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const runs = ref<PipelineRunRecord[]>([])
const selectedRun = ref<PipelineRunRecord | null>(null)
const selectedStep = ref<PipelineStepRun | null>(null)

const steps = ref<PipelineStepRun[]>([])
const events = ref<PipelineEvent[]>([])
const artifacts = ref<PipelineArtifact[]>([])

const loading = ref(false)
const stepsLoading = ref(false)
const detailPanel = ref<'log' | 'events' | 'artifacts'>('log')
const error = ref('')
const rerunError = ref('')
const rerunSuccess = ref('')

const filterDate = ref('')
const showRerunModal = ref(false)
const rerunRunId = ref(0)
const rerunFromStep = ref('')
const rerunOnlyStep = ref('')
const rerunForce = ref(true)
const rerunLoading = ref(false)

// Diagnostic expand state for step detail
const showInputParams = ref(false)
const showMetrics = ref(false)
const expandedPayloads = ref<Record<number, boolean>>({})

// Log panel state
const logLines = ref<string[]>([])
const logLoading = ref(false)
const logTotalLines = ref(0)
const showFullLogModal = ref(false)
const fullLogLines = ref<string[]>([])
const fullLogLoading = ref(false)

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
const STATUS_CLASS: Record<string, string> = {
  completed:   'bg-green-500/15 text-green-400 border-green-500/20',
  running:     'bg-blue-500/15 text-blue-400 border-blue-500/20 animate-pulse',
  skipped:     'bg-gray-500/15 text-text-muted border-gray-500/20',
  soft_failed: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  failed:      'bg-red-500/15 text-red-400 border-red-500/20',
  pending:     'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
  cancelled:   'bg-gray-500/15 text-text-muted border-gray-500/20',
}
const STATUS_ICON: Record<string, string> = {
  completed: '✓', running: '◉', skipped: '⊘', soft_failed: '⚠',
  failed: '✗', pending: '○', cancelled: '⊗',
}
const STATUS_LABEL: Record<string, string> = {
  completed: '已完成', running: '运行中', skipped: '已跳过',
  soft_failed: '软失败', failed: '失败', pending: '等待中', cancelled: '已取消',
}

function statusClass(s: string) {
  return STATUS_CLASS[s] || 'bg-gray-500/15 text-text-muted border-gray-500/20'
}
function statusIcon(s: string) { return STATUS_ICON[s] || '?' }
function statusLabelOf(s: string) { return STATUS_LABEL[s] || s }

function fmtDuration(ms: number | null | undefined): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = Math.round((ms % 60000) / 1000)
  return `${m}m${s}s`
}
function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}
function fmtBytes(b: number | null | undefined): string {
  if (!b) return '-'
  if (b < 1024) return `${b}B`
  if (b < 1048576) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / 1048576).toFixed(1)}MB`
}
function hasContent(obj: Record<string, any> | null | undefined): boolean {
  return !!obj && Object.keys(obj).length > 0
}

// ---------------------------------------------------------------------------
// Phase label / user label
// ---------------------------------------------------------------------------
function userLabel(run: { user_id: number; username?: string; nickname?: string }): string {
  if (run.user_id === 0) return '系统'
  const name = run.nickname || run.username
  if (name) return `${name} #${run.user_id}`
  return `#${run.user_id}`
}

function phaseLabel(run: PipelineRunRecord): string {
  const p = run.phase || run.run_type || ''
  if (p === 'shared') return '共享'
  if (p === 'per_user') return userLabel(run)
  if (p === 'orchestrator') return '编排'
  return p || run.pipeline
}

// ---------------------------------------------------------------------------
// Computed: health summary
// ---------------------------------------------------------------------------
const latestRun = computed(() => runs.value[0] || null)
const isRunning = computed(() => runs.value.some(r => r.status === 'running'))
const failedCount = computed(() => runs.value.filter(r => r.status === 'failed').length)

const systemHealth = computed((): 'running' | 'failed' | 'ok' => {
  if (isRunning.value) return 'running'
  if (failedCount.value > 0) return 'failed'
  return 'ok'
})

const latestRunDuration = computed((): string | null => {
  const r = latestRun.value
  if (!r?.started_at || !r?.finished_at) return null
  try {
    const ms = new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()
    return fmtDuration(ms)
  } catch { return null }
})

// First failed step in the currently-selected run (for the diagnosis hint bar)
const firstFailedStepInSelected = computed((): PipelineStepRun | null =>
  steps.value.find(s => s.status === 'failed') || null
)

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadRuns(resetSelection = false) {
  loading.value = true
  error.value = ''
  if (resetSelection) selectedRun.value = null
  try {
    const params: { limit: number; date?: string } = { limit: 30 }
    if (filterDate.value) params.date = filterDate.value
    const res = await fetchPipelineRuns(params)
    runs.value = res.runs

    // Keep selected run in sync when polling
    if (selectedRun.value) {
      const updated = runs.value.find(r => r.id === selectedRun.value!.id)
      if (updated) selectedRun.value = updated
    }

    // Auto-select: first failed run, otherwise first run
    if (runs.value.length > 0 && !selectedRun.value) {
      const target = runs.value.find(r => r.status === 'failed' || r.status === 'soft_failed')
        || runs.value[0]
      await selectRun(target)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载运行列表失败'
  } finally {
    loading.value = false
  }
}

async function fetchRunLog(runId: number, full = false) {
  if (full) {
    fullLogLoading.value = true
    try {
      const res = await fetchPipelineRunLog(runId, { full: true })
      fullLogLines.value = res.lines
    } catch {
      fullLogLines.value = []
    } finally {
      fullLogLoading.value = false
    }
  } else {
    logLoading.value = true
    try {
      const res = await fetchPipelineRunLog(runId, { tail: 500 })
      logLines.value = res.lines
      logTotalLines.value = res.total_lines
    } catch {
      logLines.value = []
      logTotalLines.value = 0
    } finally {
      logLoading.value = false
    }
  }
}

async function openFullLog() {
  if (!selectedRun.value) return
  showFullLogModal.value = true
  fullLogLines.value = []
  await fetchRunLog(selectedRun.value.id, true)
}

async function selectRun(run: PipelineRunRecord) {
  selectedRun.value = run
  selectedStep.value = null
  steps.value = []
  events.value = []
  artifacts.value = []
  logLines.value = []
  logTotalLines.value = 0
  showInputParams.value = false
  showMetrics.value = false
  expandedPayloads.value = {}
  stepsLoading.value = true
  // Start loading log immediately (don't await — run in parallel with steps)
  fetchRunLog(run.id)
  try {
    const res = await fetchPipelineRunSteps(run.id)
    steps.value = res.steps

    // Auto-select: first failed/soft_failed step, otherwise first step
    if (steps.value.length > 0) {
      const toSelect = steps.value.find(s => s.status === 'failed' || s.status === 'soft_failed')
        || steps.value[0]
      await selectStep(toSelect)
    }
  } catch {
    steps.value = []
  } finally {
    stepsLoading.value = false
  }
}

async function selectStep(step: PipelineStepRun) {
  selectedStep.value = step
  showInputParams.value = false
  showMetrics.value = false
  expandedPayloads.value = {}
  if (!selectedRun.value) return
  const runId = selectedRun.value.id
  try {
    if (detailPanel.value === 'events') {
      const res = await fetchPipelineRunEvents(runId, { step_run_id: step.id, limit: 200 })
      events.value = res.events
    } else if (detailPanel.value === 'artifacts') {
      const res = await fetchPipelineRunArtifacts(runId)
      artifacts.value = res.artifacts.filter(a => a.step_run_id === step.id)
    }
    // 'log' tab shows run-level log, no step-specific fetch needed
  } catch {
    events.value = []
    artifacts.value = []
  }
}

watch(detailPanel, async (val) => {
  if (!selectedRun.value) return
  const runId = selectedRun.value.id
  if (val === 'log') {
    await fetchRunLog(runId)
    return
  }
  if (!selectedStep.value) return
  try {
    if (val === 'events') {
      const res = await fetchPipelineRunEvents(runId, { step_run_id: selectedStep.value.id, limit: 200 })
      events.value = res.events
    } else {
      const res = await fetchPipelineRunArtifacts(runId)
      artifacts.value = res.artifacts.filter(a => a.step_run_id === selectedStep.value!.id)
    }
  } catch {
    events.value = []
    artifacts.value = []
  }
})

// ---------------------------------------------------------------------------
// Rerun modal
// ---------------------------------------------------------------------------
function openRerunModal(runId: number, fromStep = '') {
  rerunRunId.value = runId
  rerunFromStep.value = fromStep
  rerunOnlyStep.value = ''
  rerunForce.value = true
  rerunError.value = ''
  rerunSuccess.value = ''
  showRerunModal.value = true
}

async function submitRerun() {
  rerunLoading.value = true
  rerunError.value = ''
  rerunSuccess.value = ''
  try {
    const res = await rerunPipeline({
      run_id: rerunRunId.value,
      from_step: rerunFromStep.value || null,
      only_step: rerunOnlyStep.value || null,
      force: rerunForce.value,
    })
    rerunSuccess.value = `已启动重跑 (new run_id=${res.new_run_id})`
    setTimeout(() => {
      showRerunModal.value = false
      selectedRun.value = null
      loadRuns()
    }, 1500)
  } catch (e: any) {
    rerunError.value = e?.response?.data?.detail || e?.message || '重跑失败'
  } finally {
    rerunLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Level + event styling
// ---------------------------------------------------------------------------
function levelClass(level: string): string {
  const map: Record<string, string> = {
    debug:   'text-text-muted/60',
    info:    'text-green-400/80',
    warning: 'text-yellow-400',
    error:   'text-red-400',
  }
  return map[level] || 'text-text-secondary'
}

function togglePayload(evId: number) {
  expandedPayloads.value = { ...expandedPayloads.value, [evId]: !expandedPayloads.value[evId] }
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------
const { start: startPoll } = usePollingTask(async () => {
  if (!isRunning.value) return false
  await loadRuns()
  return isRunning.value
}, { intervalMs: 5000 })

onMounted(async () => {
  await loadRuns()
  startPoll()
})
</script>

<template>
  <div class="flex flex-col h-full gap-3">

    <!-- ------------------------------------------------------------------ -->
    <!-- Diagnostic header (2 rows) -->
    <!-- ------------------------------------------------------------------ -->
    <div class="shrink-0 flex flex-col gap-2">

      <!-- Row 1: health badge + latest run stats + controls -->
      <div class="flex items-center gap-3 flex-wrap">
        <!-- System health badge -->
        <div
          class="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium"
          :class="systemHealth === 'running'
            ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
            : systemHealth === 'failed'
              ? 'bg-red-500/10 border-red-500/30 text-red-400'
              : 'bg-green-500/10 border-green-500/30 text-green-400'"
        >
          <span
            class="inline-block w-2 h-2 rounded-full"
            :class="systemHealth === 'running'
              ? 'bg-blue-400 animate-pulse'
              : systemHealth === 'failed' ? 'bg-red-400' : 'bg-green-400'"
          ></span>
          <span>{{ systemHealth === 'running' ? '运行中' : systemHealth === 'failed' ? `${failedCount} 次失败` : '正常' }}</span>
        </div>

        <!-- Latest run inline summary -->
        <div v-if="latestRun" class="flex items-center gap-2 text-xs text-text-muted">
          <span>最近：{{ latestRun.date_str }}</span>
          <span class="px-1.5 py-0.5 rounded border text-[10px]" :class="statusClass(latestRun.status)">
            {{ statusLabelOf(latestRun.status) }}
          </span>
          <span v-if="latestRunDuration" class="text-text-muted/60">{{ latestRunDuration }}</span>
          <template v-if="latestRun.step_completed !== undefined || latestRun.step_failed !== undefined">
            <span class="text-text-muted/30">|</span>
            <span v-if="(latestRun.step_completed || 0) > 0" class="text-green-400">✓{{ latestRun.step_completed }}</span>
            <span v-if="(latestRun.step_failed || 0) > 0" class="text-red-400">✗{{ latestRun.step_failed }}</span>
            <span v-if="(latestRun.step_soft_failed || 0) > 0" class="text-orange-400">⚠{{ latestRun.step_soft_failed }}</span>
            <span v-if="(latestRun.step_skipped || 0) > 0" class="text-text-muted/60">⊘{{ latestRun.step_skipped }}</span>
            <span v-if="(latestRun.child_runs?.length || 0) > 0" class="text-blue-400/80">{{ latestRun.child_runs!.length }} 子运行</span>
          </template>
        </div>

        <!-- Controls -->
        <div class="ml-auto flex items-center gap-2">
          <input
            v-model="filterDate"
            type="date"
            class="px-2 py-1 rounded-lg bg-bg-elevated border border-border text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50"
            @change="loadRuns(true)"
          />
          <button
            class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:bg-bg-hover transition-colors"
            :disabled="loading"
            @click="loadRuns(true)"
          >
            {{ loading ? '加载中…' : '🔄 刷新' }}
          </button>
        </div>
      </div>

      <!-- Row 2: failure diagnosis hint (only when selected run has a failed step) -->
      <div
        v-if="firstFailedStepInSelected && selectedRun"
        class="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/20 bg-red-500/5 text-xs"
      >
        <span class="text-red-400 shrink-0 font-medium">✗ 失败步骤</span>
        <span class="font-mono text-red-300">{{ firstFailedStepInSelected.step_name }}</span>
        <span
          v-if="firstFailedStepInSelected.error_message"
          class="text-red-400/60 truncate max-w-xs"
        >— {{ firstFailedStepInSelected.error_message }}</span>
        <button
          class="ml-auto shrink-0 text-[10px] text-orange-400 border border-orange-500/30 rounded px-2 py-0.5 hover:bg-orange-500/10 transition-colors"
          @click="openRerunModal(selectedRun.id, firstFailedStepInSelected.step_name)"
        >
          ↩ 从此步重跑
        </button>
      </div>
    </div>

    <div v-if="error" class="shrink-0 text-sm text-red-400 px-1">{{ error }}</div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Main 3-column layout -->
    <!-- ------------------------------------------------------------------ -->
    <div class="flex-1 flex gap-3 min-h-0 overflow-hidden">

      <!-- Col 1: Run list -->
      <div class="w-56 shrink-0 flex flex-col gap-1 overflow-auto">
        <div class="text-xs text-text-muted font-medium px-1 mb-1">运行记录</div>
        <div v-if="!runs.length && !loading" class="text-xs text-text-muted/60 px-1 italic">暂无记录</div>

        <button
          v-for="run in runs"
          :key="run.id"
          class="flex flex-col gap-0.5 px-2.5 py-2 rounded-lg border text-left transition-all cursor-pointer"
          :class="selectedRun?.id === run.id
            ? 'bg-blue-500/10 border-blue-500/30'
            : 'bg-bg-elevated border-border hover:border-border-hover'"
          @click="selectRun(run)"
        >
          <div class="flex items-center justify-between gap-1">
            <span class="text-[10px] font-mono text-text-muted">#{{ run.id }}</span>
            <span class="px-1.5 py-0.5 rounded border text-[9px] font-medium" :class="statusClass(run.status)">
              {{ statusLabelOf(run.status) }}
            </span>
          </div>
          <div class="text-xs font-medium text-text-primary truncate">{{ phaseLabel(run) }}</div>
          <div class="text-[10px] text-text-muted">{{ run.date_str }}</div>
          <div class="flex items-center gap-1.5 flex-wrap mt-0.5">
            <span v-if="(run.step_failed || 0) > 0" class="text-[9px] text-red-400">✗{{ run.step_failed }}</span>
            <span v-if="(run.step_soft_failed || 0) > 0" class="text-[9px] text-orange-400">⚠{{ run.step_soft_failed }}</span>
            <span v-if="(run.step_completed || 0) > 0" class="text-[9px] text-green-400">✓{{ run.step_completed }}</span>
            <span v-if="(run.step_skipped || 0) > 0" class="text-[9px] text-text-muted/60">⊘{{ run.step_skipped }}</span>
            <span v-if="(run.child_runs?.length || 0) > 0" class="text-[9px] text-blue-400/80">{{ run.child_runs!.length }} 子</span>
          </div>
        </button>
      </div>

      <!-- Col 2: Step timeline -->
      <div class="w-60 shrink-0 flex flex-col min-h-0 overflow-hidden">
        <div class="text-xs text-text-muted font-medium px-1 mb-1 shrink-0 flex items-center justify-between">
          <span>Step 时间线</span>
          <button
            v-if="selectedRun"
            class="text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
            @click="openRerunModal(selectedRun.id)"
          >↩ 重跑</button>
        </div>
        <div class="flex-1 overflow-auto flex flex-col gap-1">
          <div v-if="!selectedRun" class="text-xs text-text-muted/60 px-1 italic">← 选择运行记录</div>
          <div v-else-if="stepsLoading" class="text-xs text-text-muted/60 px-1 italic">加载中…</div>
          <div v-else-if="!steps.length" class="text-xs text-text-muted/60 px-1 italic">暂无 step 记录</div>

          <button
            v-for="step in steps"
            :key="step.id"
            class="flex items-start gap-2 px-2.5 py-2 rounded-lg border text-left transition-all cursor-pointer"
            :class="selectedStep?.id === step.id
              ? 'bg-blue-500/10 border-blue-500/30'
              : 'bg-bg-elevated border-border hover:border-border-hover'"
            @click="selectStep(step)"
          >
            <span
              class="shrink-0 w-5 h-5 rounded text-[11px] font-bold flex items-center justify-center border mt-0.5"
              :class="statusClass(step.status)"
            >{{ statusIcon(step.status) }}</span>
            <div class="flex-1 min-w-0">
              <div class="text-xs font-medium text-text-primary truncate">{{ step.step_name }}</div>
              <div class="text-[10px] text-text-muted flex items-center gap-1.5 mt-0.5">
                <span>{{ fmtDuration(step.duration_ms) }}</span>
                <span v-if="step.exit_code !== null && step.exit_code !== 0" class="text-red-400">exit={{ step.exit_code }}</span>
              </div>
              <div v-if="step.skip_reason" class="text-[9px] text-yellow-500/80 truncate mt-0.5">{{ step.skip_reason }}</div>
              <div v-if="step.error_message" class="text-[9px] text-red-400 truncate mt-0.5">{{ step.error_message }}</div>
            </div>
            <button
              v-if="step.status === 'failed' || step.status === 'soft_failed'"
              class="shrink-0 text-[9px] text-orange-400 border border-orange-500/30 rounded px-1 py-0.5 hover:bg-orange-500/10 transition-colors"
              @click.stop="openRerunModal(selectedRun!.id, step.step_name)"
            >重跑</button>
          </button>
        </div>
      </div>

      <!-- Col 3: Detail panel (log / events / artifacts) -->
      <div class="flex-1 flex flex-col min-h-0 overflow-hidden bg-bg-card rounded-xl border border-border">

        <!-- Empty state: no run selected -->
        <div v-if="!selectedRun" class="flex-1 flex flex-col items-center justify-center gap-2 text-xs text-text-muted/60 italic">
          <span class="text-xl opacity-40">🔍</span>
          <span>从左侧选择一次运行记录</span>
        </div>

        <template v-else>
          <!-- Tab bar (always visible when run is selected) -->
          <div class="shrink-0 flex items-center gap-1 px-3 py-2 border-b border-border">
            <button
              class="px-2 py-1 text-xs rounded border transition-colors"
              :class="detailPanel === 'log'
                ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                : 'bg-bg-elevated border-border text-text-muted hover:text-text-secondary'"
              @click="detailPanel = 'log'"
            >日志</button>
            <button
              class="px-2 py-1 text-xs rounded border transition-colors"
              :class="detailPanel === 'events'
                ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                : 'bg-bg-elevated border-border text-text-muted hover:text-text-secondary'"
              @click="detailPanel = 'events'"
            >事件</button>
            <button
              class="px-2 py-1 text-xs rounded border transition-colors"
              :class="detailPanel === 'artifacts'
                ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                : 'bg-bg-elevated border-border text-text-muted hover:text-text-secondary'"
              @click="detailPanel = 'artifacts'"
            >产物</button>
            <!-- Right side: log info + full log button -->
            <div v-if="detailPanel === 'log'" class="ml-auto flex items-center gap-2">
              <span v-if="logTotalLines > 0 && !logLoading" class="text-[10px] text-text-muted/50">
                最后 {{ logLines.length }} / {{ logTotalLines }} 行
              </span>
              <button
                class="text-[10px] px-2 py-0.5 rounded border border-border text-text-muted hover:text-text-secondary hover:bg-bg-elevated transition-colors"
                @click="openFullLog"
              >完整日志</button>
            </div>
          </div>

          <!-- Log tab -->
          <div v-if="detailPanel === 'log'" class="flex-1 overflow-auto px-4 py-3">
            <div v-if="logLoading" class="text-xs text-text-muted/60 italic">加载中…</div>
            <div v-else-if="!logLines.length" class="text-xs text-text-muted/60 italic">
              暂无日志记录（此 run 尚未绑定日志文件）
            </div>
            <pre
              v-else
              class="text-[10px] font-mono text-text-secondary leading-relaxed whitespace-pre-wrap break-all"
            >{{ logLines.join('\n') }}</pre>
          </div>

          <!-- Events / Artifacts tabs require a step to be selected -->
          <template v-if="detailPanel !== 'log'">
            <div v-if="!selectedStep" class="flex-1 flex flex-col items-center justify-center gap-2 text-xs text-text-muted/60 italic">
              <span class="text-xl opacity-40">🔍</span>
              <span>点击左侧 Step 查看诊断详情</span>
            </div>

            <template v-else>
              <!-- Step header -->
              <div class="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-border">
                <span
                  class="w-6 h-6 rounded text-sm font-bold flex items-center justify-center border shrink-0"
                  :class="statusClass(selectedStep.status)"
                >{{ statusIcon(selectedStep.status) }}</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-semibold text-text-primary">{{ selectedStep.step_name }}</div>
                  <div class="text-xs text-text-muted flex items-center gap-2 flex-wrap">
                    <span>{{ fmtTime(selectedStep.started_at) }} → {{ fmtTime(selectedStep.finished_at) }}</span>
                    <span class="text-text-muted/60">{{ fmtDuration(selectedStep.duration_ms) }}</span>
                    <span class="px-1.5 py-0.5 rounded border text-[10px]" :class="statusClass(selectedStep.status)">
                      {{ statusLabelOf(selectedStep.status) }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Diagnostic info block -->
              <div class="shrink-0 px-4 pt-3 flex flex-col gap-2">

                <!-- Error summary with inline rerun -->
                <div
                  v-if="selectedStep.error_message"
                  class="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs"
                >
                  <div class="flex items-center justify-between mb-1">
                    <span class="font-medium text-red-400">{{ selectedStep.error_type || 'Error' }}</span>
                    <button
                      class="text-[10px] text-orange-400 border border-orange-500/30 rounded px-2 py-0.5 hover:bg-orange-500/10 transition-colors"
                      @click="openRerunModal(selectedRun!.id, selectedStep.step_name)"
                    >↩ 重跑此步</button>
                  </div>
                  <div class="text-red-300/90 break-words">{{ selectedStep.error_message }}</div>
                </div>

                <!-- Metrics (collapsible) -->
                <div v-if="hasContent(selectedStep.metrics)" class="rounded-lg border border-border overflow-hidden">
                  <button
                    class="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-text-muted hover:bg-bg-hover transition-colors text-left"
                    @click="showMetrics = !showMetrics"
                  >
                    <span class="text-[10px] w-2">{{ showMetrics ? '▾' : '▸' }}</span>
                    <span>📊 指标</span>
                    <span class="text-text-muted/50 text-[10px] font-mono">{{ Object.keys(selectedStep.metrics).length }} 项</span>
                  </button>
                  <div v-if="showMetrics" class="px-3 pb-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border/50">
                    <div v-for="(v, k) in selectedStep.metrics" :key="String(k)" class="flex items-baseline gap-1.5 text-xs mt-1">
                      <span class="text-text-muted/70 shrink-0 truncate">{{ k }}</span>
                      <span class="font-mono text-text-primary">{{ JSON.stringify(v) }}</span>
                    </div>
                  </div>
                </div>

                <!-- Input params (collapsible) -->
                <div v-if="hasContent(selectedStep.input_params)" class="rounded-lg border border-border overflow-hidden">
                  <button
                    class="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-text-muted hover:bg-bg-hover transition-colors text-left"
                    @click="showInputParams = !showInputParams"
                  >
                    <span class="text-[10px] w-2">{{ showInputParams ? '▾' : '▸' }}</span>
                    <span>⚙ 输入参数</span>
                    <span class="text-text-muted/50 text-[10px] font-mono">{{ Object.keys(selectedStep.input_params).length }} 项</span>
                  </button>
                  <div v-if="showInputParams" class="px-3 pb-2 flex flex-col gap-1 border-t border-border/50">
                    <div v-for="(v, k) in selectedStep.input_params" :key="String(k)" class="flex items-start gap-1.5 text-xs mt-1">
                      <span class="text-text-muted/70 shrink-0 font-mono">{{ k }}:</span>
                      <span class="font-mono text-text-secondary break-all">{{ JSON.stringify(v) }}</span>
                    </div>
                  </div>
                </div>

                <!-- Log file path -->
                <div
                  v-if="selectedStep.log_file"
                  class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-[10px]"
                >
                  <span class="text-text-muted shrink-0">📄 log</span>
                  <span class="font-mono text-text-secondary/80 truncate flex-1" :title="selectedStep.log_file">
                    {{ selectedStep.log_file }}
                  </span>
                </div>
              </div>

              <!-- Events list -->
              <div v-if="detailPanel === 'events'" class="flex-1 overflow-auto px-4 py-3">
                <div v-if="!events.length" class="text-xs text-text-muted/60 italic">暂无结构化事件</div>
                <div v-for="ev in events" :key="ev.id" class="mb-2">
                  <div class="flex items-start gap-2">
                    <span class="shrink-0 text-[10px] text-text-muted/60 font-mono w-16 pt-0.5">{{ fmtTime(ev.created_at) }}</span>
                    <span
                      class="shrink-0 text-[9px] px-1 py-0.5 rounded border"
                      :class="levelClass(ev.level)"
                    >{{ ev.level }}</span>
                    <span
                      v-if="ev.event_type && ev.event_type !== 'custom'"
                      class="shrink-0 text-[9px] px-1 py-0.5 rounded border border-border/50 text-text-muted/60"
                    >{{ ev.event_type }}</span>
                    <span class="flex-1 text-xs break-all" :class="levelClass(ev.level)">{{ ev.message }}</span>
                    <button
                      v-if="hasContent(ev.payload)"
                      class="shrink-0 text-[9px] text-text-muted/50 hover:text-text-muted border border-border/40 rounded px-1 py-0.5 transition-colors"
                      @click="togglePayload(ev.id)"
                    >{{ expandedPayloads[ev.id] ? '收起' : 'payload' }}</button>
                  </div>
                  <div v-if="expandedPayloads[ev.id]" class="ml-16 mt-1">
                    <pre class="text-[9px] text-text-muted font-mono px-2 py-1.5 rounded bg-bg-elevated border border-border overflow-x-auto leading-relaxed">{{ JSON.stringify(ev.payload, null, 2) }}</pre>
                  </div>
                </div>
              </div>

              <!-- Artifacts list -->
              <div v-if="detailPanel === 'artifacts'" class="flex-1 overflow-auto px-4 py-3">
                <div v-if="!artifacts.length" class="text-xs text-text-muted/60 italic">暂无产物记录</div>
                <div
                  v-for="art in artifacts"
                  :key="art.id"
                  class="flex items-center gap-3 px-3 py-2 mb-1.5 rounded-lg bg-bg-elevated border border-border text-xs"
                >
                  <span class="shrink-0 text-text-muted">{{ art.storage === 'file' ? '📄' : '🗄️' }}</span>
                  <div class="flex-1 min-w-0">
                    <div class="text-text-primary truncate font-mono text-[11px]">{{ art.path_or_table }}</div>
                    <div class="text-text-muted text-[10px]">{{ art.artifact_type }}</div>
                  </div>
                  <div class="shrink-0 flex flex-col items-end gap-0.5">
                    <span v-if="art.record_count !== null" class="text-green-400">{{ art.record_count }} 条</span>
                    <span v-if="art.byte_size" class="text-text-muted">{{ fmtBytes(art.byte_size) }}</span>
                  </div>
                </div>
              </div>
            </template>
          </template>
        </template>
      </div>
    </div>

    <!-- ------------------------------------------------------------------ -->
    <!-- Full log modal -->
    <!-- ------------------------------------------------------------------ -->
    <Teleport to="body">
      <div
        v-if="showFullLogModal"
        class="fixed inset-0 z-50 flex items-start justify-center pt-12 pb-8 px-4 bg-black/70 backdrop-blur-sm"
        @click.self="showFullLogModal = false"
      >
        <div class="bg-bg-card rounded-2xl border border-border shadow-2xl w-full max-w-4xl flex flex-col max-h-[80vh]">
          <div class="shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-border">
            <div class="flex items-center gap-3">
              <span class="text-sm font-semibold text-text-primary">完整运行日志</span>
              <span v-if="selectedRun" class="text-xs text-text-muted font-mono">run #{{ selectedRun.id }}</span>
            </div>
            <button class="text-text-muted hover:text-text-primary text-lg transition-colors" @click="showFullLogModal = false">✕</button>
          </div>
          <div class="flex-1 overflow-auto p-4">
            <div v-if="fullLogLoading" class="text-xs text-text-muted/60 italic">加载中…</div>
            <div v-else-if="!fullLogLines.length" class="text-xs text-text-muted/60 italic">暂无日志内容</div>
            <pre
              v-else
              class="text-[10px] font-mono text-text-secondary leading-relaxed whitespace-pre-wrap break-all"
            >{{ fullLogLines.join('\n') }}</pre>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ------------------------------------------------------------------ -->
    <!-- Rerun modal -->
    <!-- ------------------------------------------------------------------ -->
    <Teleport to="body">
      <div
        v-if="showRerunModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showRerunModal = false"
      >
        <div class="bg-bg-card rounded-2xl border border-border shadow-2xl w-full max-w-md mx-4 p-6">
          <div class="flex items-center justify-between mb-5">
            <h3 class="text-base font-semibold text-text-primary">↩ 重跑 Pipeline</h3>
            <button class="text-text-muted hover:text-text-primary text-lg" @click="showRerunModal = false">✕</button>
          </div>

          <div class="space-y-4">
            <div class="px-3 py-2 rounded-lg bg-bg-elevated border border-border text-xs text-text-muted">
              基于 run_id=<span class="font-mono text-text-primary">{{ rerunRunId }}</span> 创建新的重跑记录
            </div>

            <div>
              <label class="block text-xs text-text-muted mb-1">从此 step 开始（--from-step）</label>
              <select
                v-model="rerunFromStep"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="">从头开始</option>
                <option v-for="s in steps" :key="s.id" :value="s.step_name">
                  {{ s.step_name }} ({{ statusLabelOf(s.status) }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-xs text-text-muted mb-1">只跑此 step（--only-step）</label>
              <select
                v-model="rerunOnlyStep"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="">运行所有 step</option>
                <option v-for="s in steps" :key="s.id" :value="s.step_name">{{ s.step_name }}</option>
              </select>
            </div>

            <label class="flex items-center gap-2 cursor-pointer select-none">
              <input
                v-model="rerunForce"
                type="checkbox"
                class="w-4 h-4 rounded border-border text-orange-500 focus:ring-orange-500/30 bg-bg-elevated cursor-pointer"
              />
              <span class="text-sm text-text-secondary">强制重新执行（忽略幂等检查）</span>
            </label>

            <div v-if="rerunError" class="text-sm text-red-400">{{ rerunError }}</div>
            <div v-if="rerunSuccess" class="text-sm text-green-400">{{ rerunSuccess }}</div>
          </div>

          <div class="flex gap-3 mt-6">
            <button
              class="flex-1 py-2 rounded-lg border border-border text-sm text-text-secondary hover:bg-bg-hover transition-colors"
              @click="showRerunModal = false"
            >取消</button>
            <button
              :disabled="rerunLoading"
              class="flex-1 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              @click="submitRerun"
            >{{ rerunLoading ? '启动中…' : '↩ 确认重跑' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
