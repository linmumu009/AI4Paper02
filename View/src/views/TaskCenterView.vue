<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchTasks, retryTask, cancelTask, taskKindLabel, taskStatusLabel, isActiveTask } from '@shared/api/task-center'
import type { FetchTasksParams } from '@shared/api/task-center'
import type { TaskCenterItem, TaskStatus } from '@shared/types/task-center'
import EmbeddedPaperDetailPanel from '../components/EmbeddedPaperDetailPanel.vue'
import { usePollingTask } from '../composables/usePollingTask'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), {
  embedded: false,
})

// Inline paper detail (embedded mode only)
const selectedPaperId = ref<string | null>(null)

const router = useRouter()

const items = ref<TaskCenterItem[]>([])
const loading = ref(true)
const error = ref('')
const activeFilter = ref<TaskStatus | 'active' | 'all'>('all')
const retryingId = ref<string | null>(null)
const cancellingId = ref<string | null>(null)
const retryMsg = ref('')

const FILTERS: Array<{ key: TaskStatus | 'active' | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'active', label: '进行中' },
  { key: 'failed', label: '失败' },
  { key: 'completed', label: '已完成' },
]

async function loadTasks() {
  try {
    const params: FetchTasksParams =
      activeFilter.value === 'all'
        ? { limit: 200 }
        : activeFilter.value === 'completed'
        ? { status: 'completed' as TaskStatus, limit: 100, include_completed: true }
        : { status: activeFilter.value as TaskStatus, limit: 100 }
    const res = await fetchTasks(params)
    items.value = res.items
    error.value = ''
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const summary = computed(() => {
  const running = items.value.filter(i => i.status === 'running').length
  const pending = items.value.filter(i => i.status === 'pending').length
  const failed = items.value.filter(i => i.status === 'failed').length
  return { running, pending, failed }
})

const filteredItems = computed(() => {
  if (activeFilter.value === 'all') return items.value
  if (activeFilter.value === 'active') return items.value.filter(i => isActiveTask(i.status))
  return items.value.filter(i => i.status === activeFilter.value)
})

function hasActiveTasks() {
  return items.value.some(i => isActiveTask(i.status))
}

const { start: startPolling } = usePollingTask(async () => {
  if (!hasActiveTasks()) return false
  await loadTasks()
  return hasActiveTasks()
}, { intervalMs: 5000 })

async function onFilter(key: typeof activeFilter.value) {
  activeFilter.value = key
  loading.value = true
  await loadTasks()
}

function statusClass(status: TaskStatus): string {
  const map: Record<TaskStatus, string> = {
    running:   'bg-blue-500/15 text-blue-400 border-blue-500/20 animate-pulse',
    pending:   'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
    failed:    'bg-red-500/15 text-red-400 border-red-500/20',
    completed: 'bg-green-500/15 text-green-400 border-green-500/20',
    cancelled: 'bg-gray-500/15 text-text-muted border-gray-500/20',
    skipped:   'bg-gray-500/15 text-text-muted border-gray-500/20',
    none:      'bg-gray-500/15 text-text-muted border-gray-500/20',
  }
  return `px-2 py-0.5 rounded text-[11px] font-semibold border ${map[status] ?? 'bg-gray-500/15 text-text-muted border-gray-500/20'}`
}

function kindBadgeClass(kind: string): string {
  const map: Record<string, string> = {
    kb_process:          'text-blue-400 bg-blue-500/10',
    kb_translate:        'text-purple-400 bg-purple-500/10',
    kb_classify:         'text-yellow-400 bg-yellow-500/10',
    user_paper_process:  'text-blue-400 bg-blue-500/10',
    user_paper_translate:'text-purple-400 bg-purple-500/10',
    pipeline_run:        'text-text-muted bg-bg-elevated',
    deep_research:       'text-red-400 bg-red-500/10',
    paper_compare:       'text-green-400 bg-green-500/10',
  }
  return `text-[10px] font-semibold px-1.5 py-0.5 rounded ${map[kind] ?? 'text-text-muted bg-bg-elevated'}`
}

function navigateToEntity(item: TaskCenterItem) {
  if (item.entity_type === 'paper' && item.entity_id) {
    if (props.embedded) {
      selectedPaperId.value = item.entity_id
    } else {
      router.push(`/papers/${item.entity_id}`)
    }
  } else if (item.entity_type === 'research_session') {
    router.push('/research')
  }
}

async function onRetry(item: TaskCenterItem) {
  if (retryingId.value) return
  retryingId.value = item.id
  retryMsg.value = ''
  try {
    const res = await retryTask(item.id)
    retryMsg.value = res.message || '已重新提交'
    await loadTasks()
    startPolling()
    setTimeout(() => { retryMsg.value = '' }, 3000)
  } catch (e: any) {
    retryMsg.value = e?.response?.data?.detail || e?.message || '操作失败'
    setTimeout(() => { retryMsg.value = '' }, 5000)
  } finally {
    retryingId.value = null
  }
}

async function onCancel(item: TaskCenterItem) {
  if (cancellingId.value) return
  cancellingId.value = item.id
  retryMsg.value = ''
  try {
    const res = await cancelTask(item.id)
    retryMsg.value = res.message || '已停止'
    await loadTasks()
    setTimeout(() => { retryMsg.value = '' }, 3000)
  } catch (e: any) {
    retryMsg.value = e?.response?.data?.detail || e?.message || '操作失败'
    setTimeout(() => { retryMsg.value = '' }, 5000)
  } finally {
    cancellingId.value = null
  }
}

// Returns a display label that is kind-aware for 'running' status
function taskStatusDisplayLabel(item: TaskCenterItem): string {
  if (item.status === 'running') {
    if (item.kind === 'user_paper_translate' || item.kind === 'kb_translate') return '翻译中'
    if (item.kind === 'user_paper_process' || item.kind === 'kb_process') return '解析中'
    if (item.kind === 'kb_classify') return '分类中'
    if (item.kind === 'deep_research') return '研究中'
  }
  return taskStatusLabel(item.status)
}

onMounted(async () => {
  await loadTasks()
  if (hasActiveTasks()) startPolling()
})

</script>

<template>
  <!-- Embedded inline paper detail -->
  <EmbeddedPaperDetailPanel
    v-if="props.embedded && selectedPaperId"
    :paper-id="selectedPaperId"
    back-label="返回任务中心"
    class="h-full"
    @back="selectedPaperId = null"
  />

  <div
    v-else
    class="text-text-primary"
    :class="props.embedded ? 'min-h-0 bg-transparent' : 'min-h-screen bg-bg'"
  >
    <div
      class="mx-auto"
      :class="props.embedded ? 'max-w-5xl px-4 sm:px-8 py-4 sm:py-6' : 'max-w-4xl px-4 py-8'"
    >
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div v-if="props.embedded">
          <h2 class="text-lg font-bold text-text-primary">任务中心</h2>
          <p class="text-xs text-text-muted mt-1">统一查看论文解析、翻译、分类等后台任务进度</p>
        </div>
        <div v-else>
          <h1 class="text-xl font-bold">任务中心</h1>
          <p class="text-sm text-text-muted mt-0.5">统一查看论文解析、翻译、分类等后台任务进度</p>
        </div>
        <button
          type="button"
          class="text-sm text-text-muted hover:text-text-secondary px-3 py-1.5 rounded-lg bg-bg-elevated shrink-0"
          @click="loadTasks()"
        >
          刷新
        </button>
      </div>

      <!-- Summary cards -->
      <div v-if="!loading" class="grid grid-cols-3 gap-3 mb-6">
        <div class="rounded-xl border border-blue-500/20 bg-blue-500/5 px-4 py-3 text-center">
          <p class="text-2xl font-bold text-blue-400">{{ summary.running }}</p>
          <p class="text-xs text-text-muted mt-0.5">处理中</p>
        </div>
        <div class="rounded-xl border border-yellow-500/20 bg-yellow-500/5 px-4 py-3 text-center">
          <p class="text-2xl font-bold text-yellow-400">{{ summary.pending }}</p>
          <p class="text-xs text-text-muted mt-0.5">等待中</p>
        </div>
        <div class="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-center">
          <p class="text-2xl font-bold text-red-400">{{ summary.failed }}</p>
          <p class="text-xs text-text-muted mt-0.5">失败</p>
        </div>
      </div>

      <!-- Retry message toast -->
      <div v-if="retryMsg" class="mb-4 px-4 py-2 rounded-lg bg-bg-elevated text-sm text-text-secondary border border-border">
        {{ retryMsg }}
      </div>

      <!-- Filters -->
      <div class="flex gap-2 mb-4 flex-wrap">
        <button
          v-for="f in FILTERS"
          :key="f.key"
          type="button"
          class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
          :class="activeFilter === f.key
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
            : 'bg-bg-elevated text-text-secondary border border-border hover:bg-bg-card'"
          @click="onFilter(f.key)"
        >
          {{ f.label }}
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-16 text-text-muted gap-2">
        <span class="animate-spin text-lg">⟳</span>
        <span class="text-sm">加载中…</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="py-8 text-center">
        <p class="text-sm text-red-400">{{ error }}</p>
        <button type="button" class="mt-3 text-sm text-text-secondary underline" @click="loadTasks()">重试</button>
      </div>

      <!-- Empty -->
      <div v-else-if="filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-text-muted gap-2">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="opacity-40">
          <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        <p class="text-sm">暂无任务</p>
      </div>

      <!-- Task list (card rows) -->
      <div v-else class="space-y-2">
        <div
          v-for="item in filteredItems"
          :key="item.id"
          class="rounded-xl border border-border bg-bg-card px-4 py-3 hover:bg-bg-elevated transition-colors"
        >
          <!-- Top row: kind badge + title + status pill -->
          <div class="flex items-start gap-3">
            <!-- Kind badge -->
            <span :class="[kindBadgeClass(item.kind), 'shrink-0 mt-0.5']">{{ taskKindLabel(item.kind) }}</span>

            <!-- Title + subtitle + error -->
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-text-primary truncate" :title="item.title">{{ item.title }}</p>
              <p v-if="item.subtitle" class="text-[11px] text-text-muted mt-0.5">{{ item.subtitle }}</p>
              <p v-if="item.error" class="text-[11px] text-red-400 mt-0.5 line-clamp-2">{{ item.error }}</p>
            </div>

            <!-- Status pill – whitespace-nowrap prevents two-line wrap -->
            <span :class="[statusClass(item.status), 'shrink-0 whitespace-nowrap']">
              <span v-if="item.status === 'running'" class="inline-block animate-pulse mr-0.5">·</span>
              {{ taskStatusDisplayLabel(item) }}
            </span>
          </div>

          <!-- Progress bar (translate tasks in running state) -->
          <div v-if="item.status === 'running' && item.progress != null && item.progress > 0" class="mt-2 flex items-center gap-2">
            <div class="flex-1 h-1.5 rounded-full bg-bg overflow-hidden">
              <div class="h-full rounded-full bg-blue-400 transition-all" :style="{ width: `${item.progress}%` }" />
            </div>
            <span class="text-[11px] text-text-muted shrink-0">{{ item.progress }}%</span>
          </div>

          <!-- Step label -->
          <p v-if="item.step" class="mt-1.5 text-[11px] text-text-muted">{{ item.step }}</p>

          <!-- Actions -->
          <div class="flex items-center gap-2 mt-2.5">
            <button
              v-if="item.actions.includes('view') && item.entity_type === 'paper'"
              type="button"
              class="text-[11px] px-2.5 py-1 rounded-md bg-bg-elevated text-text-secondary hover:bg-bg border border-border"
              @click="navigateToEntity(item)"
            >
              查看
            </button>
            <button
              v-if="item.actions.includes('cancel')"
              type="button"
              class="text-[11px] px-2.5 py-1 rounded-md bg-red-500/10 text-red-400 hover:bg-red-500/20 disabled:opacity-50 border border-red-500/20"
              :disabled="cancellingId === item.id"
              @click="onCancel(item)"
            >
              {{ cancellingId === item.id ? '…' : '停止' }}
            </button>
            <button
              v-if="item.actions.includes('retry')"
              type="button"
              class="text-[11px] px-2.5 py-1 rounded-md bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 disabled:opacity-50 border border-blue-500/20"
              :disabled="retryingId === item.id"
              @click="onRetry(item)"
            >
              {{ retryingId === item.id ? '…' : '重试' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Pipeline console link for admins -->
      <div class="mt-6 text-center">
        <router-link
          to="/admin/users"
          class="text-sm text-text-muted hover:text-text-secondary underline"
        >
          管理员：前往 Pipeline Console 查看详细运行日志 →
        </router-link>
      </div>
    </div>
  </div>
</template>
