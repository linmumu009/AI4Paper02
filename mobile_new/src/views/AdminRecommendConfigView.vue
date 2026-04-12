<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import {
  getPipelineRunStatus,
  runPipeline,
  stopPipeline,
  getScheduleConfig,
  updateScheduleConfig,
} from '@shared/api'
import type { PipelineRunStatus, ScheduleConfig } from '@shared/types/admin'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AdminRecommendConfigView' })

const router = useRouter()
const pipelineStatus = ref<PipelineRunStatus | null>(null)
const scheduleConfig = ref<ScheduleConfig | null>(null)
const loading = ref(true)
const error = ref('')
const running = ref(false)
const stopping = ref(false)
const savingSchedule = ref(false)

// Schedule edit state
const scheduleHour = ref(8)
const scheduleMinute = ref(0)
const scheduleEnabled = ref(true)

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [status, schedule] = await Promise.allSettled([
      getPipelineRunStatus(),
      getScheduleConfig(),
    ])
    if (status.status === 'fulfilled') pipelineStatus.value = status.value
    if (schedule.status === 'fulfilled') {
      scheduleConfig.value = schedule.value
      scheduleHour.value = schedule.value.hour
      scheduleMinute.value = schedule.value.minute
      scheduleEnabled.value = schedule.value.enabled
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

async function doRunPipeline() {
  try {
    await showDialog({
      title: '手动触发流水线',
      message: '确定现在运行论文推荐流水线？',
      confirmButtonText: '运行',
      cancelButtonText: '取消',
    })
    running.value = true
    await runPipeline({})
    showToast('流水线已启动')
    await loadData()
  } catch { /* user cancelled or failed */ } finally {
    running.value = false
  }
}

async function doStopPipeline() {
  stopping.value = true
  try {
    await stopPipeline()
    showToast('已停止')
    await loadData()
  } catch { showToast('停止失败') } finally {
    stopping.value = false
  }
}

async function saveSchedule() {
  savingSchedule.value = true
  try {
    await updateScheduleConfig({
      enabled: scheduleEnabled.value,
      hour: scheduleHour.value,
      minute: scheduleMinute.value,
    })
    showToast('定时配置已保存')
    await loadData()
  } catch { showToast('保存失败') } finally {
    savingSchedule.value = false
  }
}

</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="推荐配置" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadData" />
    <div v-else class="flex-1 overflow-y-auto pb-8 px-4 pt-4 space-y-4">

      <!-- Pipeline status -->
      <div class="card-section">
        <p class="section-title">流水线状态</p>
        <div v-if="pipelineStatus" class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-[13px] text-text-secondary">状态</span>
            <span class="text-[13px] font-semibold" :class="pipelineStatus.running ? 'text-tinder-blue' : pipelineStatus.exit_code && pipelineStatus.exit_code !== 0 ? 'text-tinder-pink' : 'text-tinder-green'">
              {{ pipelineStatus.running ? '运行中' : pipelineStatus.exit_code === 0 ? '已完成' : pipelineStatus.exit_code ? '异常' : '空闲' }}
            </span>
          </div>
          <div v-if="pipelineStatus.current_step" class="flex items-center justify-between">
            <span class="text-[13px] text-text-secondary">当前步骤</span>
            <span class="text-[12px] text-text-muted">{{ pipelineStatus.current_step }}</span>
          </div>
          <div v-if="pipelineStatus.started_at" class="flex items-center justify-between">
            <span class="text-[13px] text-text-secondary">开始时间</span>
            <span class="text-[12px] text-text-muted">{{ new Date(pipelineStatus.started_at).toLocaleTimeString('zh-CN') }}</span>
          </div>
        </div>
        <div class="flex gap-3 mt-4">
          <button
            type="button"
            class="flex-1 btn-primary py-2.5 text-[13px]"
            :disabled="running || !!pipelineStatus?.running"
            @click="doRunPipeline"
          >
            {{ running ? '启动中…' : '手动触发' }}
          </button>
          <button
            v-if="pipelineStatus?.running"
            type="button"
            class="flex-1 btn-ghost py-2.5 text-[13px] text-tinder-pink"
            :disabled="stopping"
            @click="doStopPipeline"
          >
            {{ stopping ? '停止中…' : '停止' }}
          </button>
        </div>
      </div>

      <!-- Schedule config -->
      <div class="card-section">
        <p class="section-title">定时配置</p>
        <div class="flex items-center justify-between mb-3">
          <span class="text-[13px] text-text-secondary">启用定时</span>
          <button
            type="button"
            class="w-12 h-6 rounded-full transition-all relative"
            :class="scheduleEnabled ? 'bg-tinder-pink' : 'bg-bg-elevated border border-border'"
            @click="scheduleEnabled = !scheduleEnabled"
          >
            <div class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all" :class="scheduleEnabled ? 'right-0.5' : 'left-0.5'" />
          </button>
        </div>
        <div class="flex gap-3 mb-4">
          <div class="flex-1">
            <label class="text-[11px] text-text-muted mb-1 block">小时 (0-23)</label>
            <input v-model.number="scheduleHour" type="number" min="0" max="23" class="input-field text-center" />
          </div>
          <div class="flex-1">
            <label class="text-[11px] text-text-muted mb-1 block">分钟 (0-59)</label>
            <input v-model.number="scheduleMinute" type="number" min="0" max="59" class="input-field text-center" />
          </div>
        </div>
        <button type="button" class="btn-primary text-[13px] py-2.5" :disabled="savingSchedule" @click="saveSchedule">
          {{ savingSchedule ? '保存中…' : '保存定时设置' }}
        </button>
      </div>

      <button type="button" class="btn-ghost w-full text-[13px]" @click="router.push('/admin/idea-system-config')">
        查看系统配置
      </button>
    </div>
  </div>
</template>
