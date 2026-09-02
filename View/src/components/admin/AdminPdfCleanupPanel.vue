<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  fetchPdfCleanupStatus,
  runPdfCleanup,
  savePdfCleanupConfig,
  type PdfCleanupRunResponse,
  type PdfCleanupStatus,
} from '../../api'
import { getApiErrorMessage, reportClientError } from '../../utils/apiError'

const status = ref<PdfCleanupStatus | null>(null)
const loading = ref(false)
const running = ref(false)
const saving = ref(false)
const error = ref('')
const successMessage = ref('')
const lastResult = ref<PdfCleanupRunResponse | null>(null)
const form = ref({
  retention_days: 14,
  auto_enabled: false,
  auto_hour: 3,
  auto_minute: 0,
  pressure_enabled: true,
  min_free_gb: 10,
  pressure_retention_days: 1,
})
let successTimer: ReturnType<typeof setTimeout> | null = null

function showSuccess(message: string) {
  successMessage.value = message
  if (successTimer) clearTimeout(successTimer)
  successTimer = setTimeout(() => {
    successMessage.value = ''
    successTimer = null
  }, 3000)
}

function normalizeResult(result: PdfCleanupRunResponse): PdfCleanupRunResponse {
  return {
    ...result,
    scanned: result.scanned ?? 0,
    deletable: result.deletable ?? 0,
    deleted: result.deleted ?? 0,
    skipped_saved: result.skipped_saved ?? 0,
    skipped_recent: result.skipped_recent ?? 0,
    reclaimable_bytes: result.reclaimable_bytes ?? result.freed_bytes ?? 0,
    freed_bytes: result.freed_bytes ?? 0,
    freed_mb: result.freed_mb ?? 0,
    errors: Array.isArray(result.errors) ? result.errors : [],
    started_at: result.started_at ?? '',
    finished_at: result.finished_at ?? '',
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetchPdfCleanupStatus()
    status.value = response
    form.value = {
      retention_days: response.retention_days,
      auto_enabled: response.auto_enabled,
      auto_hour: response.auto_hour,
      auto_minute: response.auto_minute,
      pressure_enabled: response.pressure_enabled,
      min_free_gb: response.min_free_gb,
      pressure_retention_days: response.pressure_retention_days,
    }
    if (response.last_result) {
      lastResult.value = normalizeResult({ ok: true, ...response.last_result })
    }
  } catch (cause: unknown) {
    reportClientError('admin.pdfCleanup.load', cause, '加载失败')
    error.value = getApiErrorMessage(cause, '加载失败')
  } finally {
    loading.value = false
  }
}

async function run(dryRun: boolean) {
  running.value = true
  error.value = ''
  try {
    lastResult.value = normalizeResult(await runPdfCleanup(dryRun, undefined))
    showSuccess(dryRun ? '预览完成' : '清理完成')
  } catch (cause: unknown) {
    reportClientError('admin.pdfCleanup.run', cause, '操作失败')
    error.value = getApiErrorMessage(cause, '操作失败')
  } finally {
    running.value = false
  }
}

async function saveConfig() {
  saving.value = true
  error.value = ''
  try {
    await savePdfCleanupConfig(form.value)
    showSuccess('配置已保存')
    await load()
  } catch (cause: unknown) {
    reportClientError('admin.pdfCleanup.save', cause, '保存失败')
    error.value = getApiErrorMessage(cause, '保存失败')
  } finally {
    saving.value = false
  }
}

async function confirmRun() {
  if (!window.confirm('确认删除超期且未被任何用户收藏的推荐 PDF、MinerU 解析和中间资源？知识库副本与用户上传文件不会被删除。')) return
  await run(false)
}

const sourceLabels: Record<string, string> = {
  raw_pdf: '原始 PDF',
  file_collect: '推荐聚合文件',
  full_mineru_cache: 'MinerU 完整解析',
  selectedpaper_to_mineru: '入选论文解析',
}

onMounted(load)
onBeforeUnmount(() => {
  if (successTimer) clearTimeout(successTimer)
})
</script>

<template>
  <section class="flex-1 overflow-auto p-3 sm:p-6 pb-24">
    <div class="max-w-2xl mx-auto space-y-5">
      <header class="flex items-center justify-between">
        <div>
          <h2 class="text-base font-semibold text-text-primary">🗑️ 推荐资源缓存清理</h2>
          <p class="text-xs text-text-muted mt-0.5">统一清理超期且未收藏的 PDF、MinerU 解析和推荐中间文件；知识库副本与用户上传文件永久排除</p>
        </div>
        <button
          type="button"
          :disabled="loading"
          class="px-3 py-1.5 rounded-lg text-xs border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-50"
          @click="load"
        >
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
      </header>

      <div v-if="error" role="alert" class="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-400">
        {{ error }}
      </div>
      <div v-if="successMessage" role="status" class="rounded-lg bg-green-500/10 border border-green-500/30 px-4 py-3 text-sm text-green-400">
        ✓ {{ successMessage }}
      </div>

      <div class="rounded-xl bg-bg-card border border-border p-5 space-y-4">
        <h3 class="text-sm font-semibold text-text-primary">清理配置</h3>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label for="pdf-retention-days" class="text-xs text-text-muted block mb-1">保留天数 N（超过此天数且无收藏则清理）</label>
            <input
              id="pdf-retention-days"
              v-model.number="form.retention_days"
              type="number"
              min="1"
              max="3650"
              class="w-full px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm"
            />
          </div>
          <label class="flex items-center gap-3 pt-5 cursor-pointer">
            <span class="relative inline-flex items-center">
              <input v-model="form.auto_enabled" type="checkbox" class="sr-only peer" />
              <span class="w-10 h-5 bg-bg-elevated rounded-full peer peer-checked:bg-blue-500 peer-focus:outline-none transition-colors"></span>
              <span class="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-5"></span>
            </span>
            <span class="text-sm text-text-secondary">启用自动清理</span>
          </label>
        </div>

        <div v-if="form.auto_enabled" class="grid grid-cols-2 gap-4">
          <div>
            <label for="pdf-cleanup-hour" class="text-xs text-text-muted block mb-1">触发时间（小时，本地时区）</label>
            <input id="pdf-cleanup-hour" v-model.number="form.auto_hour" type="number" min="0" max="23" class="w-full px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
          </div>
          <div>
            <label for="pdf-cleanup-minute" class="text-xs text-text-muted block mb-1">触发时间（分钟）</label>
            <input id="pdf-cleanup-minute" v-model.number="form.auto_minute" type="number" min="0" max="59" class="w-full px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
          </div>
        </div>

        <div class="rounded-lg border border-border bg-bg-elevated/50 p-3 space-y-3">
          <label class="flex items-start gap-3 cursor-pointer">
            <span class="relative inline-flex items-center mt-0.5">
              <input v-model="form.pressure_enabled" type="checkbox" class="sr-only peer" />
              <span class="w-10 h-5 bg-bg-elevated rounded-full peer peer-checked:bg-amber-500 peer-focus:outline-none transition-colors"></span>
              <span class="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-5"></span>
            </span>
            <span>
              <span class="block text-sm text-text-secondary">启用磁盘低空间保护</span>
              <span class="block text-[11px] text-text-muted mt-0.5">空间不足时无需等待固定时刻，自动缩短未收藏公共缓存的保留期；收藏、知识库和用户上传文件不会删除</span>
            </span>
          </label>
          <div v-if="form.pressure_enabled" class="grid grid-cols-2 gap-4">
            <div>
              <label for="pdf-cleanup-min-free" class="text-xs text-text-muted block mb-1">至少保留空间（GB）</label>
              <input id="pdf-cleanup-min-free" v-model.number="form.min_free_gb" type="number" min="1" max="1000" step="0.5" class="w-full px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label for="pdf-pressure-retention" class="text-xs text-text-muted block mb-1">保护触发时保留天数</label>
              <input id="pdf-pressure-retention" v-model.number="form.pressure_retention_days" type="number" min="1" max="3650" class="w-full px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
          </div>
        </div>

        <button type="button" :disabled="saving" class="px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-500 hover:bg-blue-600 text-white disabled:opacity-50" @click="saveConfig">
          {{ saving ? '保存中...' : '💾 保存配置' }}
        </button>
      </div>

      <div class="rounded-xl bg-bg-card border border-border p-5 space-y-3">
        <h3 class="text-sm font-semibold text-text-primary">手动触发</h3>
        <p class="text-xs text-text-muted">使用当前配置的保留天数。预览会显示预计释放空间，不会删除任何文件。</p>
        <div class="flex gap-3">
          <button type="button" :disabled="running" class="px-4 py-1.5 rounded-lg text-sm border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-50" @click="run(true)">
            {{ running ? '处理中...' : '🔍 预览清理（dry-run）' }}
          </button>
          <button type="button" :disabled="running" class="px-4 py-1.5 rounded-lg text-sm bg-red-500/80 hover:bg-red-600 text-white disabled:opacity-50" @click="confirmRun">
            {{ running ? '处理中...' : '🗑️ 立即清理' }}
          </button>
        </div>
      </div>

      <div v-if="status" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-sm font-semibold text-text-primary">调度线程状态</h3>
        <div class="flex items-center gap-2">
          <span :class="status.scheduler_alive ? 'bg-green-500' : 'bg-gray-500'" class="w-2 h-2 rounded-full"></span>
          <span class="text-xs text-text-secondary">{{ status.scheduler_alive ? '运行中' : '未运行' }}</span>
        </div>
        <div v-if="status.disk?.available" class="rounded-lg bg-bg-elevated px-3 py-2.5 text-xs">
          <div class="flex items-center justify-between gap-3">
            <span class="text-text-muted">服务器磁盘</span>
            <span :class="status.disk.pressure_active ? 'text-amber-400' : 'text-green-400'" class="font-medium">
              剩余 {{ formatBytes(status.disk.free_bytes ?? 0) }} · 已用 {{ status.disk.used_percent ?? 0 }}%
            </span>
          </div>
          <p class="mt-1 text-[11px] text-text-muted">
            低于 {{ status.min_free_gb }} GB 时{{ status.pressure_enabled ? `自动按 ${status.pressure_retention_days} 天保留期清理` : '不会自动处理（保护已关闭）' }}
          </p>
        </div>
        <div v-if="status.disk?.pressure_active" role="alert" class="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-300">
          当前已进入低空间保护区间，调度器会优先回收未收藏公共缓存。
        </div>
      </div>

      <div v-if="lastResult" class="rounded-xl bg-bg-card border border-border p-5 space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-text-primary">最近一次结果</h3>
          <span v-if="lastResult.dry_run" class="text-[11px] text-amber-400 border border-amber-500/30 rounded px-1.5 py-0.5">预览模式</span>
          <span v-else-if="lastResult.trigger === 'disk_pressure'" class="text-[11px] text-amber-400 border border-amber-500/30 rounded px-1.5 py-0.5">低空间保护</span>
          <span v-else class="text-[11px] text-green-400 border border-green-500/30 rounded px-1.5 py-0.5">实际清理</span>
        </div>
        <div class="grid grid-cols-3 gap-3 text-center">
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-text-primary">{{ lastResult.scanned }}</div><div class="text-[11px] text-text-muted">扫描缓存项</div></div>
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-amber-400">{{ lastResult.deletable }}</div><div class="text-[11px] text-text-muted">可清理</div></div>
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-red-400">{{ lastResult.deleted }}</div><div class="text-[11px] text-text-muted">已删除</div></div>
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-blue-400">{{ lastResult.skipped_saved }}</div><div class="text-[11px] text-text-muted">跳过（已收藏）</div></div>
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-text-secondary">{{ lastResult.skipped_recent }}</div><div class="text-[11px] text-text-muted">跳过（未到期）</div></div>
          <div class="rounded-lg bg-bg-elevated p-3"><div class="text-lg font-bold text-green-400">{{ formatBytes(lastResult.freed_bytes) }}</div><div class="text-[11px] text-text-muted">{{ lastResult.dry_run ? '预计释放' : '释放空间' }}</div></div>
        </div>
        <div v-if="lastResult.sources" class="rounded-lg border border-border bg-bg-elevated/60 px-3 py-2.5">
          <p class="mb-2 text-[11px] font-semibold text-text-secondary">按资源类型</p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            <div
              v-for="(item, key) in lastResult.sources"
              :key="key"
              class="flex items-center justify-between gap-3 text-[11px]"
            >
              <span class="text-text-muted">{{ sourceLabels[key] ?? key }}</span>
              <span class="font-mono text-text-secondary">可清理 {{ item.deletable }} · {{ formatBytes(item.reclaimable_bytes) }}</span>
            </div>
          </div>
        </div>
        <div class="text-[11px] text-text-muted">
          开始 {{ new Date(lastResult.started_at).toLocaleString('zh-CN') }}
          · 结束 {{ new Date(lastResult.finished_at).toLocaleString('zh-CN') }}
          · 保留 {{ lastResult.retention_days }} 天
        </div>
        <div v-if="lastResult.errors?.length" class="rounded-lg bg-red-500/10 border border-red-500/20 p-3">
          <p class="text-[11px] font-semibold text-red-400 mb-1">错误（{{ lastResult.errors.length }}）</p>
          <ul class="space-y-0.5">
            <li v-for="(item, index) in lastResult.errors.slice(0, 10)" :key="index" class="text-[11px] text-red-300 font-mono truncate">{{ item }}</li>
            <li v-if="lastResult.errors.length > 10" class="text-[11px] text-text-muted">... 还有 {{ lastResult.errors.length - 10 }} 条</li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
