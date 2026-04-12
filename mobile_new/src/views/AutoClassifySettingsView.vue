<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import {
  fetchUserSettings,
  saveUserSettings,
  fetchAutoClassifyPendingCount,
  fetchAutoClassifyUnclassifiedCount,
  syncAutoClassifyFolders,
  reclassifyAllKbPapers,
  fetchUserLlmPresets,
  fetchUserPromptPresets,
  fetchKbTree,
} from '@shared/api'
import type { UserLlmPreset, UserPromptPreset } from '@shared/types/admin'
import type { KbFolder, KbTree } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AutoClassifySettingsView' })

const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const syncing = ref(false)
const reclassifying = ref(false)
const error = ref('')

const pendingCount = ref(0)
const unclassifiedCount = ref(0)

const llmPresets = ref<UserLlmPreset[]>([])
const promptPresets = ref<UserPromptPreset[]>([])
const kbTree = ref<KbTree | null>(null)

const form = ref({
  enabled: false,
  llm_preset_id: null as number | null,
  prompt_preset_id: null as number | null,
  confidence_threshold: 0.65,
})

// Picker state
const pickerType = ref<'llm' | 'prompt' | null>(null)
const pickerVisible = ref(false)

// Folder management
const addFolderSheetVisible = ref(false)
const newFolderName = ref('')
const newFolderDesc = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [settingsRes, llmRes, promptRes, kbRes, pendingRes, unclassifiedRes] = await Promise.all([
      fetchUserSettings('auto_classify'),
      fetchUserLlmPresets(),
      fetchUserPromptPresets(),
      fetchKbTree('kb'),
      fetchAutoClassifyPendingCount('kb').catch(() => ({ pending: 0 })),
      fetchAutoClassifyUnclassifiedCount('kb').catch(() => ({ unclassified: 0 })),
    ])
    const merged = { ...(settingsRes.defaults ?? {}), ...(settingsRes.settings ?? {}) }
    form.value.enabled = merged.enabled ?? false
    form.value.llm_preset_id = merged.llm_preset_id ?? null
    form.value.prompt_preset_id = merged.prompt_preset_id ?? null
    form.value.confidence_threshold = merged.confidence_threshold ?? 0.65
    llmPresets.value = llmRes.presets
    promptPresets.value = promptRes.presets
    kbTree.value = kbRes
    pendingCount.value = pendingRes.pending
    unclassifiedCount.value = unclassifiedRes.unclassified
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function doSave() {
  saving.value = true
  try {
    await saveUserSettings('auto_classify', {
      enabled: form.value.enabled,
      llm_preset_id: form.value.llm_preset_id,
      prompt_preset_id: form.value.prompt_preset_id,
      confidence_threshold: form.value.confidence_threshold,
    })
    showToast('已保存')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function doSync() {
  try {
    await showDialog({
      title: '同步分类目录',
      message: '将把当前知识库文件夹结构同步到自动分类配置。继续？',
      confirmButtonText: '同步',
      cancelButtonText: '取消',
    })
    syncing.value = true
    const res = await syncAutoClassifyFolders('kb', false)
    showToast(`同步成功，已更新 ${res.enqueued ?? 0} 条`)
  } catch {
    // user cancelled or error
  } finally {
    syncing.value = false
  }
}

async function doReclassify() {
  try {
    await showDialog({
      title: '全部重新分类',
      message: '将对知识库中所有论文重新执行自动分类。此操作可能需要一段时间。',
      confirmButtonText: '开始',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    reclassifying.value = true
    const res = await reclassifyAllKbPapers('kb')
    showToast(`已加入队列，共 ${res.enqueued ?? 0} 篇`)
  } catch {
    // user cancelled
  } finally {
    reclassifying.value = false
  }
}

function openPicker(type: 'llm' | 'prompt') {
  pickerType.value = type
  pickerVisible.value = true
}

function selectPreset(id: number | null) {
  if (pickerType.value === 'llm') form.value.llm_preset_id = id
  else form.value.prompt_preset_id = id
  pickerVisible.value = false
}

function llmPresetName(id: number | null) {
  if (!id) return '（使用默认）'
  return llmPresets.value.find((p) => p.id === id)?.name ?? `预设 #${id}`
}

function promptPresetName(id: number | null) {
  if (!id) return '（使用默认）'
  return promptPresets.value.find((p) => p.id === id)?.name ?? `预设 #${id}`
}

function thresholdLabel(v: number): string {
  if (v >= 0.85) return '严格'
  if (v >= 0.6) return '均衡'
  return '宽松'
}

function flatFolders(tree: KbTree): KbFolder[] {
  const result: KbFolder[] = []
  function collect(folders: KbFolder[]) {
    for (const f of folders) { result.push(f); collect(f.children) }
  }
  collect(tree.folders)
  return result
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="自动分类设置" @back="router.back()" />

    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else>
      <div class="flex-1 overflow-y-auto pb-36 px-4 pt-4 space-y-4">

        <!-- Status counters -->
        <div class="flex gap-3">
          <div class="flex-1 card-section text-center py-4">
            <p class="text-[22px] font-bold text-tinder-blue">{{ pendingCount }}</p>
            <p class="text-[11px] text-text-muted mt-0.5">待分类</p>
          </div>
          <div class="flex-1 card-section text-center py-4">
            <p class="text-[22px] font-bold text-tinder-gold">{{ unclassifiedCount }}</p>
            <p class="text-[11px] text-text-muted mt-0.5">未分类</p>
          </div>
        </div>

        <!-- Enable switch -->
        <div class="card-section flex items-center justify-between">
          <div>
            <p class="text-[14px] font-semibold text-text-primary">启用自动分类</p>
            <p class="text-[12px] text-text-muted mt-0.5">收藏论文时自动归入对应文件夹</p>
          </div>
          <button
            type="button"
            class="relative inline-flex h-7 w-12 items-center rounded-full transition-colors"
            :class="form.enabled ? 'bg-tinder-green' : 'bg-bg-elevated border border-border'"
            @click="form.enabled = !form.enabled"
          >
            <span
              class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform"
              :class="form.enabled ? 'translate-x-6' : 'translate-x-1'"
            />
          </button>
        </div>

        <!-- AI model -->
        <div class="card-section space-y-3">
          <p class="text-[13px] font-semibold text-text-primary">AI 模型配置</p>
          <div>
            <p class="text-[12px] text-text-muted mb-1.5">模型预设</p>
            <button
              type="button"
              class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-elevated border border-border active:bg-bg-hover"
              @click="openPicker('llm')"
            >
              <span class="text-[13px] text-text-primary">{{ llmPresetName(form.llm_preset_id) }}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
          </div>
          <div>
            <p class="text-[12px] text-text-muted mb-1.5">提示词预设</p>
            <button
              type="button"
              class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-elevated border border-border active:bg-bg-hover"
              @click="openPicker('prompt')"
            >
              <span class="text-[13px] text-text-primary">{{ promptPresetName(form.prompt_preset_id) }}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
          </div>
        </div>

        <!-- Confidence threshold -->
        <div class="card-section">
          <div class="flex items-center justify-between mb-3">
            <p class="text-[13px] font-semibold text-text-primary">分类置信度阈值</p>
            <div class="flex items-center gap-2">
              <span class="text-[13px] font-bold text-tinder-blue">{{ (form.confidence_threshold * 100).toFixed(0) }}%</span>
              <span class="text-[11px] px-2 py-0.5 rounded-full bg-tinder-blue/10 text-tinder-blue">{{ thresholdLabel(form.confidence_threshold) }}</span>
            </div>
          </div>
          <input
            v-model.number="form.confidence_threshold"
            type="range"
            min="0.3"
            max="0.95"
            step="0.05"
            class="w-full accent-tinder-blue"
          />
          <div class="flex justify-between text-[11px] text-text-muted mt-1">
            <span>宽松 (30%)</span>
            <span>严格 (95%)</span>
          </div>
        </div>

        <!-- KB folders (read-only display) -->
        <div v-if="kbTree" class="card-section">
          <div class="flex items-center justify-between mb-3">
            <p class="text-[13px] font-semibold text-text-primary">知识库文件夹目录</p>
            <span class="text-[11px] text-text-muted">{{ flatFolders(kbTree).length }} 个文件夹</span>
          </div>
          <div v-if="flatFolders(kbTree).length === 0" class="text-[12px] text-text-muted py-2">
            知识库暂无文件夹，请先在知识库中创建文件夹
          </div>
          <div v-else class="space-y-1.5 max-h-48 overflow-y-auto">
            <div
              v-for="folder in flatFolders(kbTree)"
              :key="folder.id"
              class="flex items-center gap-2 py-1.5"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="#f5b731"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z" /></svg>
              <span class="text-[12px] text-text-secondary">{{ folder.name }}</span>
            </div>
          </div>
          <p class="text-[11px] text-text-muted mt-3 leading-relaxed">自动分类会根据文件夹名称将论文归类。点击「同步到配置」以更新映射关系。</p>
        </div>

        <!-- Batch operations -->
        <div class="card-section space-y-3">
          <p class="text-[13px] font-semibold text-text-primary">批量操作</p>
          <button
            type="button"
            class="w-full flex items-center gap-3 py-2.5 px-3 rounded-xl bg-tinder-blue/10 border border-tinder-blue/20 active:bg-tinder-blue/20"
            :disabled="syncing"
            @click="doSync"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue shrink-0">
              <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            <span class="text-[13px] font-medium text-tinder-blue">{{ syncing ? '同步中…' : '同步目录到配置' }}</span>
          </button>
          <button
            type="button"
            class="w-full flex items-center gap-3 py-2.5 px-3 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 active:bg-tinder-pink/20"
            :disabled="reclassifying"
            @click="doReclassify"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-pink shrink-0">
              <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
            <span class="text-[13px] font-medium text-tinder-pink">{{ reclassifying ? '处理中…' : '全部重新分类' }}</span>
          </button>
        </div>
      </div>

      <!-- Save bar -->
      <div
        class="shrink-0 fixed bottom-0 left-0 right-0 bg-bg/90 backdrop-blur-md border-t border-border px-4 pt-3 z-10"
        style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px));"
      >
        <button type="button" class="btn-primary" :disabled="saving" @click="doSave">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>
    </template>

    <!-- Preset picker -->
    <BottomSheet
      :visible="pickerVisible"
      :title="pickerType === 'llm' ? '选择模型预设' : '选择提示词预设'"
      height="60dvh"
      @close="pickerVisible = false"
    >
      <div class="pb-4">
        <button type="button" class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover" @click="selectPreset(null)">
          <span class="text-[14px] text-text-muted">（使用默认）</span>
        </button>
        <template v-if="pickerType === 'llm'">
          <button
            v-for="p in llmPresets"
            :key="p.id"
            type="button"
            class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover"
            @click="selectPreset(p.id)"
          >
            <span class="flex-1 text-[14px] text-text-primary text-left">{{ p.name }}</span>
            <svg v-if="form.llm_preset_id === p.id" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-green"><polyline points="20 6 9 17 4 12" /></svg>
          </button>
        </template>
        <template v-else>
          <button
            v-for="p in promptPresets"
            :key="p.id"
            type="button"
            class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover"
            @click="selectPreset(p.id)"
          >
            <span class="flex-1 text-[14px] text-text-primary text-left">{{ p.name }}</span>
            <svg v-if="form.prompt_preset_id === p.id" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-green"><polyline points="20 6 9 17 4 12" /></svg>
          </button>
        </template>
      </div>
    </BottomSheet>
  </div>
</template>
