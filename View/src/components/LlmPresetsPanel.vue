<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import {
  fetchUserLlmPresets, createUserLlmPreset, updateUserLlmPreset, deleteUserLlmPreset,
  fetchUserSettings,
} from '../api'
import type { UserLlmPreset } from '../types/paper'
import { useEntitlements } from '../composables/useEntitlements'
import UpgradePrompt from './UpgradePrompt.vue'

const { isGated, loaded: entLoaded } = useEntitlements()
const isLlmPresetGated = computed(() => entLoaded.value && isGated('llm_preset'))

// ---------------------------------------------------------------------------
// Preset list state
// ---------------------------------------------------------------------------

const presets = ref<UserLlmPreset[]>([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')

const filteredPresets = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return presets.value
  return presets.value.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.model || '').toLowerCase().includes(q) ||
    (p.base_url || '').toLowerCase().includes(q)
  )
})

async function loadPresets() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchUserLlmPresets()
    presets.value = res.presets
  } catch (e: any) {
    error.value = e?.message || '加载模型预设失败'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Usage indicator: fetch which features use each preset
// ---------------------------------------------------------------------------

const FEATURE_LABELS: Record<string, string> = {
  compare: '对比分析',
  inspiration: '灵感涌现',
  idea_generate: '灵感生成',
  paper_recommend: '推荐论文',
}

// map: presetId → feature labels[]
const presetUsage = ref<Record<number, string[]>>({})

async function loadUsage() {
  const usage: Record<number, string[]> = {}
  const features = ['compare', 'inspiration', 'idea_generate', 'paper_recommend']
  await Promise.allSettled(
    features.map(async (feature) => {
      try {
        const res = await fetchUserSettings(feature)
        const settings = res.settings || {}
        // collect all *_llm_preset_id fields
        for (const key of Object.keys(settings)) {
          if (key.endsWith('_llm_preset_id') || key === 'llm_preset_id') {
            const id = Number(settings[key])
            if (id) {
              if (!usage[id]) usage[id] = []
              const label = FEATURE_LABELS[feature] || feature
              if (!usage[id].includes(label)) usage[id].push(label)
            }
          }
        }
      } catch {}
    })
  )
  presetUsage.value = usage
}

// ---------------------------------------------------------------------------
// Form / Drawer state
// ---------------------------------------------------------------------------

const showDrawer = ref(false)
const editingPreset = ref<UserLlmPreset | null>(null)
const llmForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  max_tokens: null as number | null,
  temperature: null as number | null,
  input_hard_limit: null as number | null,
  input_safety_margin: null as number | null,
})
const formSaving = ref(false)
const formError = ref('')
const showApiKey = ref(false)

function openDrawer(preset?: UserLlmPreset) {
  if (preset) {
    editingPreset.value = preset
    llmForm.name = preset.name
    llmForm.base_url = preset.base_url || ''
    llmForm.api_key = preset.api_key || ''
    llmForm.model = preset.model || ''
    llmForm.max_tokens = preset.max_tokens ?? null
    llmForm.temperature = preset.temperature ?? null
    llmForm.input_hard_limit = preset.input_hard_limit ?? null
    llmForm.input_safety_margin = preset.input_safety_margin ?? null
  } else {
    editingPreset.value = null
    llmForm.name = ''
    llmForm.base_url = ''
    llmForm.api_key = ''
    llmForm.model = ''
    llmForm.max_tokens = null
    llmForm.temperature = null
    llmForm.input_hard_limit = null
    llmForm.input_safety_margin = null
  }
  showApiKey.value = false
  formError.value = ''
  showDrawer.value = true
}

function closeDrawer() {
  showDrawer.value = false
  editingPreset.value = null
}

async function savePreset() {
  if (!llmForm.name.trim()) return
  formSaving.value = true
  formError.value = ''
  try {
    const payload = {
      name: llmForm.name.trim(),
      base_url: llmForm.base_url,
      api_key: llmForm.api_key,
      model: llmForm.model,
      max_tokens: llmForm.max_tokens,
      temperature: llmForm.temperature,
      input_hard_limit: llmForm.input_hard_limit,
      input_safety_margin: llmForm.input_safety_margin,
    }
    if (editingPreset.value) {
      await updateUserLlmPreset(editingPreset.value.id, payload)
    } else {
      await createUserLlmPreset(payload)
    }
    await loadPresets()
    closeDrawer()
  } catch (e: any) {
    formError.value = e?.message || '保存失败'
  } finally {
    formSaving.value = false
  }
}

// ---------------------------------------------------------------------------
// Delete confirm modal
// ---------------------------------------------------------------------------

const deleteTarget = ref<UserLlmPreset | null>(null)
const deleting = ref(false)
const deleteError = ref('')

function askDelete(preset: UserLlmPreset) {
  deleteTarget.value = preset
  deleteError.value = ''
}

function cancelDelete() {
  deleteTarget.value = null
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await deleteUserLlmPreset(deleteTarget.value.id)
    deleteTarget.value = null
    await loadPresets()
    await loadUsage()
  } catch (e: any) {
    deleteError.value = e?.message || '删除失败'
  } finally {
    deleting.value = false
  }
}

// ---------------------------------------------------------------------------
// Copy preset
// ---------------------------------------------------------------------------

const copying = ref<number | null>(null)

async function copyPreset(preset: UserLlmPreset) {
  copying.value = preset.id
  try {
    await createUserLlmPreset({
      name: preset.name + ' (副本)',
      base_url: preset.base_url,
      api_key: preset.api_key,
      model: preset.model,
      max_tokens: preset.max_tokens ?? null,
      temperature: preset.temperature ?? null,
      input_hard_limit: preset.input_hard_limit ?? null,
      input_safety_margin: preset.input_safety_margin ?? null,
    })
    await loadPresets()
  } catch (e: any) {
    error.value = e?.message || '复制失败'
  } finally {
    copying.value = null
  }
}

// ---------------------------------------------------------------------------
// More menu per card
// ---------------------------------------------------------------------------

const openMenuId = ref<number | null>(null)

function toggleMenu(id: number) {
  openMenuId.value = openMenuId.value === id ? null : id
}

function closeAllMenus() {
  openMenuId.value = null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function maskKey(key: string): string {
  if (!key) return '—'
  if (key.length <= 8) return '••••••••'
  return key.slice(0, 4) + '••••' + key.slice(-4)
}

function domainFromUrl(url: string): string {
  if (!url) return '—'
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

onMounted(async () => {
  await loadPresets()
  loadUsage()
})
</script>

<template>
  <div
    class="relative h-full px-4 sm:px-8 py-6 sm:py-8 max-w-3xl mx-auto"
    @click="closeAllMenus"
  >
    <!-- ====== Entitlement gate: Free tier cannot manage presets ====== -->
    <div v-if="isLlmPresetGated" class="flex flex-col items-center justify-center min-h-[320px] gap-4">
      <UpgradePrompt feature="llm_preset" class="w-full max-w-md" />
    </div>

    <template v-else>
    <!-- ====== Header ====== -->
    <div class="flex items-center justify-between mb-5">
      <div>
        <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
            <line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" />
            <line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" />
            <line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" />
            <line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" />
          </svg>
          模型预设
        </h2>
        <p class="text-xs text-text-muted mt-0.5">管理 LLM 连接预设，在功能配置中快速切换使用</p>
      </div>
      <button
        class="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white hover:opacity-90 shadow-lg shadow-[#8b5cf6]/20 transition-all flex items-center gap-1.5 shrink-0"
        @click.stop="openDrawer()"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        新建预设
      </button>
    </div>

    <!-- ====== Search (shown when >= 3 presets) ====== -->
    <div v-if="presets.length >= 3" class="mb-4">
      <div class="relative">
        <svg xmlns="http://www.w3.org/2000/svg" class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索预设名称、模型或 API URL..."
          class="w-full pl-9 pr-4 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
          @click.stop
        />
      </div>
    </div>

    <!-- ====== Loading ====== -->
    <div v-if="loading" class="flex items-center justify-center py-24">
      <div class="relative w-10 h-10 flex items-center justify-center">
        <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#8b5cf6] animate-spin"></div>
      </div>
    </div>

    <!-- ====== Error ====== -->
    <div v-else-if="error && presets.length === 0" class="text-center py-20">
      <p class="text-sm text-red-400">{{ error }}</p>
      <button class="mt-3 text-xs text-[#8b5cf6] hover:underline" @click="loadPresets">重试</button>
    </div>

    <!-- ====== Empty state ====== -->
    <div v-else-if="presets.length === 0" class="text-center py-24">
      <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[#8b5cf6]/10 flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-[#8b5cf6]/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
        </svg>
      </div>
      <h3 class="text-sm font-semibold text-text-secondary mb-1">还没有模型预设</h3>
      <p class="text-xs text-text-muted mb-4">创建模型预设后，可以在功能配置中快速选用</p>
      <button
        class="px-4 py-2 rounded-lg text-sm font-medium bg-[#8b5cf6]/10 text-[#8b5cf6] hover:bg-[#8b5cf6]/20 transition-colors"
        @click="openDrawer()"
      >创建第一个预设</button>
    </div>

    <!-- ====== No search results ====== -->
    <div v-else-if="filteredPresets.length === 0" class="text-center py-16">
      <p class="text-sm text-text-muted">没有匹配「{{ searchQuery }}」的预设</p>
      <button class="mt-2 text-xs text-[#8b5cf6] hover:underline" @click="searchQuery = ''">清除搜索</button>
    </div>

    <!-- ====== Preset Cards ====== -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div
        v-for="preset in filteredPresets"
        :key="preset.id"
        class="group relative rounded-xl border border-border bg-bg-card overflow-hidden hover:border-[#8b5cf6]/40 hover:shadow-lg hover:shadow-[#8b5cf6]/5 transition-all duration-200"
        :class="editingPreset?.id === preset.id ? 'border-[#8b5cf6]/60 shadow-md shadow-[#8b5cf6]/10' : ''"
      >
        <!-- Left accent bar -->
        <div class="absolute left-0 inset-y-0 w-0.5 bg-gradient-to-b from-[#6366f1] to-[#8b5cf6]"></div>

        <div class="pl-4 pr-4 pt-4 pb-3">
          <!-- Card header -->
          <div class="flex items-start justify-between gap-2 mb-3">
            <!-- Icon + name -->
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-[#6366f1]/20 to-[#8b5cf6]/20 flex items-center justify-center shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
                </svg>
              </div>
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-text-primary leading-tight truncate">{{ preset.name }}</h4>
                <div v-if="preset.model" class="mt-0.5">
                  <span class="inline-block text-[10px] font-mono bg-[#8b5cf6]/10 text-[#8b5cf6] px-1.5 py-0.5 rounded leading-none truncate max-w-[140px]">{{ preset.model }}</span>
                </div>
              </div>
            </div>
            <!-- Action buttons (always visible) -->
            <div class="flex items-center gap-1 shrink-0">
              <button
                class="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
                title="编辑"
                @click.stop="openDrawer(preset)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
              <!-- More menu -->
              <div class="relative">
                <button
                  class="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
                  title="更多操作"
                  @click.stop="toggleMenu(preset.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="5" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="19" r="1" fill="currentColor" />
                  </svg>
                </button>
                <!-- Dropdown -->
                <Transition
                  enter-active-class="transition duration-100 ease-out"
                  enter-from-class="opacity-0 scale-95"
                  enter-to-class="opacity-100 scale-100"
                  leave-active-class="transition duration-75 ease-in"
                  leave-from-class="opacity-100 scale-100"
                  leave-to-class="opacity-0 scale-95"
                >
                  <div
                    v-if="openMenuId === preset.id"
                    class="absolute right-0 top-full mt-1 w-36 bg-bg-elevated border border-border rounded-lg shadow-xl z-20 overflow-hidden"
                    @click.stop
                  >
                    <button
                      class="w-full flex items-center gap-2 px-3 py-2 text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
                      :disabled="copying === preset.id"
                      @click="copyPreset(preset); closeAllMenus()"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                      {{ copying === preset.id ? '复制中...' : '复制预设' }}
                    </button>
                    <div class="border-t border-border"></div>
                    <button
                      class="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-400 hover:bg-red-500/10 transition-colors"
                      @click="askDelete(preset); closeAllMenus()"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6" /><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                      删除预设
                    </button>
                  </div>
                </Transition>
              </div>
            </div>
          </div>

          <!-- Card details -->
          <div class="space-y-1.5 text-xs">
            <div class="flex items-center gap-2 text-text-muted">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0 text-text-muted/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
              </svg>
              <span class="text-text-secondary font-mono truncate">{{ domainFromUrl(preset.base_url) }}</span>
            </div>
            <div class="flex items-center gap-2 text-text-muted">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0 text-text-muted/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <span class="text-text-secondary font-mono">{{ maskKey(preset.api_key) }}</span>
            </div>
          </div>

          <!-- Parameter badges -->
          <div v-if="preset.temperature != null || preset.max_tokens != null" class="flex flex-wrap gap-1.5 mt-2.5">
            <span v-if="preset.temperature != null" class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">
              <span class="text-text-muted/60">temp</span> {{ preset.temperature }}
            </span>
            <span v-if="preset.max_tokens != null" class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">
              <span class="text-text-muted/60">tokens</span> {{ preset.max_tokens }}
            </span>
          </div>

          <!-- Usage indicator -->
          <div v-if="presetUsage[preset.id]?.length" class="mt-3 pt-2.5 border-t border-border">
            <div class="flex items-center gap-1.5 flex-wrap">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-[#8b5cf6]/70 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span
                v-for="label in presetUsage[preset.id]"
                :key="label"
                class="text-[10px] px-1.5 py-0.5 rounded-full bg-[#8b5cf6]/10 text-[#8b5cf6]"
              >{{ label }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ====== Slide-over Drawer ====== -->
    <Teleport to="body">
      <!-- Backdrop -->
      <Transition
        enter-active-class="transition duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showDrawer"
          class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          @click="closeDrawer"
        ></div>
      </Transition>

      <!-- Drawer panel -->
      <Transition
        enter-active-class="transition duration-250 ease-out"
        enter-from-class="translate-x-full opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-full opacity-0"
      >
        <div
          v-if="showDrawer"
          class="fixed right-0 top-0 bottom-0 z-50 w-full md:w-[420px] bg-bg-card border-l border-border shadow-2xl flex flex-col"
          @click.stop
        >
          <!-- Drawer header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-border">
            <div class="flex items-center gap-2.5">
              <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-[#6366f1]/20 to-[#8b5cf6]/20 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
                </svg>
              </div>
              <h3 class="text-sm font-semibold text-text-primary">
                {{ editingPreset ? '编辑模型预设' : '新建模型预设' }}
              </h3>
            </div>
            <button
              class="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
              @click="closeDrawer"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <!-- Drawer body (scrollable) -->
          <div class="flex-1 overflow-y-auto px-6 py-5 space-y-5">

            <!-- Error -->
            <div v-if="formError" class="px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
              {{ formError }}
            </div>

            <!-- Name -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">
                预设名称 <span class="text-[#8b5cf6]">*</span>
              </label>
              <input
                v-model="llmForm.name"
                type="text"
                placeholder="例如: GPT-4o、Claude Sonnet、通义千问..."
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
            </div>

            <!-- Model -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">模型名称</label>
              <input
                v-model="llmForm.model"
                type="text"
                placeholder="gpt-4o / claude-sonnet-4-20250514 / qwen-plus ..."
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
            </div>

            <!-- API URL -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
              <input
                v-model="llmForm.base_url"
                type="text"
                placeholder="https://api.openai.com/v1"
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors font-mono"
              />
            </div>

            <!-- API Key -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
              <div class="relative">
                <input
                  v-model="llmForm.api_key"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="sk-..."
                  class="w-full px-3 py-2.5 pr-10 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors font-mono"
                />
                <button
                  type="button"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
                  @click="showApiKey = !showApiKey"
                >
                  <svg v-if="showApiKey" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                </button>
              </div>
              <!-- Key status indicator -->
              <div class="flex items-center gap-1.5 mt-1.5">
                <div
                  class="w-1.5 h-1.5 rounded-full transition-colors"
                  :class="llmForm.api_key ? 'bg-[#10b981]' : 'bg-border'"
                ></div>
                <span class="text-[11px] text-text-muted">{{ llmForm.api_key ? 'API Key 已填写' : '未填写 API Key' }}</span>
              </div>
            </div>

            <!-- Advanced params -->
            <div>
              <div class="text-xs font-medium text-text-secondary mb-3">高级参数（可选）</div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-[11px] text-text-muted mb-1">Temperature</label>
                  <input
                    v-model.number="llmForm.temperature"
                    type="number"
                    step="0.1" min="0" max="2"
                    placeholder="默认 1.0"
                    class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
                  />
                </div>
                <div>
                  <label class="block text-[11px] text-text-muted mb-1">Max Tokens</label>
                  <input
                    v-model.number="llmForm.max_tokens"
                    type="number"
                    step="256" min="256"
                    placeholder="默认 4096"
                    class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
                  />
                </div>
                <div>
                  <label class="block text-[11px] text-text-muted mb-1">Input Hard Limit</label>
                  <input
                    v-model.number="llmForm.input_hard_limit"
                    type="number"
                    step="1024"
                    placeholder="129024"
                    class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
                  />
                </div>
                <div>
                  <label class="block text-[11px] text-text-muted mb-1">Safety Margin</label>
                  <input
                    v-model.number="llmForm.input_safety_margin"
                    type="number"
                    step="256"
                    placeholder="4096"
                    class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
                  />
                </div>
              </div>
            </div>
          </div>

          <!-- Drawer footer (sticky) -->
          <div class="px-6 py-4 border-t border-border bg-bg-card flex items-center justify-end gap-2">
            <button
              class="px-4 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover transition-colors"
              @click="closeDrawer"
            >取消</button>
            <button
              class="px-5 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white hover:opacity-90 shadow-lg shadow-[#8b5cf6]/20 transition-all disabled:opacity-50 flex items-center gap-2"
              :disabled="!llmForm.name.trim() || formSaving"
              @click="savePreset"
            >
              <svg v-if="formSaving" xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
              {{ formSaving ? '保存中...' : '保存预设' }}
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ====== Delete Confirm Modal ====== -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="deleteTarget"
          class="fixed inset-0 z-[60] flex items-center justify-center p-4"
          @click.self="cancelDelete"
        >
          <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
          <Transition
            enter-active-class="transition duration-150 ease-out"
            enter-from-class="opacity-0 scale-95"
            enter-to-class="opacity-100 scale-100"
          >
            <div
              v-if="deleteTarget"
              class="relative bg-bg-card rounded-2xl border border-border p-6 max-w-sm w-full shadow-2xl"
              @click.stop
            >
              <!-- Icon -->
              <div class="w-11 h-11 mx-auto mb-4 rounded-full bg-red-500/10 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6" /><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
              </div>
              <h3 class="text-sm font-semibold text-text-primary text-center mb-2">确认删除</h3>
              <p class="text-xs text-text-muted text-center mb-1">
                确定要删除模型预设
              </p>
              <p class="text-sm font-medium text-text-primary text-center mb-1">「{{ deleteTarget.name }}」</p>
              <p class="text-xs text-text-muted text-center mb-5">此操作不可撤销，已引用该预设的功能配置将自动清除绑定。</p>

              <div v-if="deleteError" class="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                {{ deleteError }}
              </div>

              <div class="flex gap-3">
                <button
                  class="flex-1 px-4 py-2.5 rounded-xl text-sm text-text-secondary border border-border hover:bg-bg-hover transition-colors"
                  @click="cancelDelete"
                >取消</button>
                <button
                  class="flex-1 px-4 py-2.5 rounded-xl text-sm font-medium bg-red-500 hover:bg-red-600 text-white transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                  :disabled="deleting"
                  @click="confirmDelete"
                >
                  <svg v-if="deleting" xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  {{ deleting ? '删除中...' : '确认删除' }}
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </Transition>
    </Teleport>
    </template><!-- end v-else (entitlement gate) -->
  </div>
</template>
