<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import {
  fetchUserPromptPresets, createUserPromptPreset, updateUserPromptPreset, deleteUserPromptPreset,
  fetchUserSettings,
} from '../api'
import type { UserPromptPreset } from '../types/paper'
import { useEntitlements } from '../composables/useEntitlements'
import UpgradePrompt from './UpgradePrompt.vue'

const { isGated, loaded: entLoaded } = useEntitlements()
const isPromptPresetGated = computed(() => entLoaded.value && isGated('prompt_preset'))

// ---------------------------------------------------------------------------
// Preset list state
// ---------------------------------------------------------------------------

const presets = ref<UserPromptPreset[]>([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')

const filteredPresets = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return presets.value
  return presets.value.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.prompt_content || '').toLowerCase().includes(q)
  )
})

async function loadPresets() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchUserPromptPresets()
    presets.value = res.presets
  } catch (e: any) {
    error.value = e?.message || '加载提示词预设失败'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Content helpers
// ---------------------------------------------------------------------------

function charCount(content: string): string {
  const len = content?.length ?? 0
  if (len >= 1000) return (len / 1000).toFixed(1) + 'k 字'
  return len + ' 字'
}

function lineCount(content: string): number {
  if (!content) return 0
  return content.split('\n').length
}

// ---------------------------------------------------------------------------
// Usage indicator
// ---------------------------------------------------------------------------

const FEATURE_LABELS: Record<string, string> = {
  compare: '对比分析',
  inspiration: '灵感涌现',
  idea_generate: '灵感生成',
  paper_recommend: '推荐论文',
}

const presetUsage = ref<Record<number, string[]>>({})

async function loadUsage() {
  const usage: Record<number, string[]> = {}
  const features = ['compare', 'inspiration', 'idea_generate', 'paper_recommend']
  await Promise.allSettled(
    features.map(async (feature) => {
      try {
        const res = await fetchUserSettings(feature)
        const settings = res.settings || {}
        for (const key of Object.keys(settings)) {
          if (key.endsWith('_prompt_preset_id') || key === 'prompt_preset_id') {
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
// Expanded preview state
// ---------------------------------------------------------------------------

const expandedIds = ref<Set<number>>(new Set())

function toggleExpand(id: number) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

// ---------------------------------------------------------------------------
// Form / Drawer state
// ---------------------------------------------------------------------------

const showDrawer = ref(false)
const editingPreset = ref<UserPromptPreset | null>(null)
const promptForm = reactive({
  name: '',
  prompt_content: '',
})
const formSaving = ref(false)
const formError = ref('')

const contentCharCount = computed(() => {
  const len = promptForm.prompt_content?.length ?? 0
  return len
})

const contentLineCount = computed(() => {
  if (!promptForm.prompt_content) return 0
  return promptForm.prompt_content.split('\n').length
})

function openDrawer(preset?: UserPromptPreset) {
  if (preset) {
    editingPreset.value = preset
    promptForm.name = preset.name
    promptForm.prompt_content = preset.prompt_content
  } else {
    editingPreset.value = null
    promptForm.name = ''
    promptForm.prompt_content = ''
  }
  formError.value = ''
  showDrawer.value = true
}

function closeDrawer() {
  showDrawer.value = false
  editingPreset.value = null
}

async function savePreset() {
  if (!promptForm.name.trim()) return
  formSaving.value = true
  formError.value = ''
  try {
    const payload = {
      name: promptForm.name.trim(),
      prompt_content: promptForm.prompt_content,
    }
    if (editingPreset.value) {
      await updateUserPromptPreset(editingPreset.value.id, payload)
    } else {
      await createUserPromptPreset(payload)
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

const deleteTarget = ref<UserPromptPreset | null>(null)
const deleting = ref(false)
const deleteError = ref('')

function askDelete(preset: UserPromptPreset) {
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
    await deleteUserPromptPreset(deleteTarget.value.id)
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

async function copyPreset(preset: UserPromptPreset) {
  copying.value = preset.id
  try {
    await createUserPromptPreset({
      name: preset.name + ' (副本)',
      prompt_content: preset.prompt_content,
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
    <div v-if="isPromptPresetGated" class="flex flex-col items-center justify-center min-h-[320px] gap-4">
      <UpgradePrompt feature="prompt_preset" class="w-full max-w-md" />
    </div>

    <template v-else>
    <!-- ====== Header ====== -->
    <div class="flex items-center justify-between mb-5">
      <div>
        <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#10b981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" />
            <path d="M19 17V5a2 2 0 0 0-2-2H4" />
          </svg>
          提示词预设
        </h2>
        <p class="text-xs text-text-muted mt-0.5">管理 System Prompt 预设，在功能配置中快速切换使用</p>
      </div>
      <button
        class="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#059669] to-[#10b981] text-white hover:opacity-90 shadow-lg shadow-[#10b981]/20 transition-all flex items-center gap-1.5 shrink-0"
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
          placeholder="搜索预设名称或内容..."
          class="w-full pl-9 pr-4 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#10b981] transition-colors"
          @click.stop
        />
      </div>
    </div>

    <!-- ====== Loading ====== -->
    <div v-if="loading" class="flex items-center justify-center py-24">
      <div class="relative w-10 h-10 flex items-center justify-center">
        <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#10b981] animate-spin"></div>
      </div>
    </div>

    <!-- ====== Error ====== -->
    <div v-else-if="error && presets.length === 0" class="text-center py-20">
      <p class="text-sm text-red-400">{{ error }}</p>
      <button class="mt-3 text-xs text-[#10b981] hover:underline" @click="loadPresets">重试</button>
    </div>

    <!-- ====== Empty state ====== -->
    <div v-else-if="presets.length === 0" class="text-center py-24">
      <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[#10b981]/10 flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-[#10b981]/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" />
          <path d="M19 17V5a2 2 0 0 0-2-2H4" />
        </svg>
      </div>
      <h3 class="text-sm font-semibold text-text-secondary mb-1">还没有提示词预设</h3>
      <p class="text-xs text-text-muted mb-4">创建提示词预设后，可以在功能配置中快速选用</p>
      <button
        class="px-4 py-2 rounded-lg text-sm font-medium bg-[#10b981]/10 text-[#10b981] hover:bg-[#10b981]/20 transition-colors"
        @click="openDrawer()"
      >创建第一个预设</button>
    </div>

    <!-- ====== No search results ====== -->
    <div v-else-if="filteredPresets.length === 0" class="text-center py-16">
      <p class="text-sm text-text-muted">没有匹配「{{ searchQuery }}」的预设</p>
      <button class="mt-2 text-xs text-[#10b981] hover:underline" @click="searchQuery = ''">清除搜索</button>
    </div>

    <!-- ====== Preset Cards ====== -->
    <div v-else class="space-y-4">
      <div
        v-for="preset in filteredPresets"
        :key="preset.id"
        class="relative rounded-xl border border-border bg-bg-card overflow-hidden hover:border-[#10b981]/40 hover:shadow-lg hover:shadow-[#10b981]/5 transition-all duration-200"
        :class="editingPreset?.id === preset.id ? 'border-[#10b981]/60 shadow-md shadow-[#10b981]/10' : ''"
      >
        <!-- Left accent bar -->
        <div class="absolute left-0 inset-y-0 w-0.5 bg-gradient-to-b from-[#059669] to-[#10b981]"></div>

        <div class="pl-4 pr-4 pt-4 pb-3">
          <!-- Card header -->
          <div class="flex items-start justify-between gap-2 mb-2.5">
            <!-- Icon + name + stats -->
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-[#059669]/20 to-[#10b981]/20 flex items-center justify-center shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#10b981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" />
                  <path d="M19 17V5a2 2 0 0 0-2-2H4" />
                </svg>
              </div>
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-text-primary leading-tight truncate">{{ preset.name }}</h4>
                <p class="text-[10px] text-text-muted mt-0.5">
                  {{ charCount(preset.prompt_content) }} · {{ lineCount(preset.prompt_content) }} 行
                </p>
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
                    <circle cx="12" cy="5" r="1" fill="currentColor" />
                    <circle cx="12" cy="12" r="1" fill="currentColor" />
                    <circle cx="12" cy="19" r="1" fill="currentColor" />
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

          <!-- Content preview -->
          <div
            class="relative bg-bg-elevated rounded-lg p-3 cursor-pointer select-none"
            @click.stop="toggleExpand(preset.id)"
          >
            <p
              class="text-xs text-text-secondary font-mono leading-relaxed whitespace-pre-wrap break-all transition-all duration-200"
              :class="expandedIds.has(preset.id) ? '' : 'line-clamp-3'"
            >{{ preset.prompt_content || '（暂无内容）' }}</p>
            <!-- Expand/collapse indicator -->
            <div
              v-if="!expandedIds.has(preset.id) && preset.prompt_content && preset.prompt_content.split('\n').length > 3"
              class="absolute bottom-0 inset-x-0 h-8 flex items-end justify-center pb-1.5 bg-gradient-to-t from-bg-elevated to-transparent rounded-b-lg"
            >
              <span class="text-[10px] text-text-muted flex items-center gap-0.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
                点击展开
              </span>
            </div>
            <div
              v-if="expandedIds.has(preset.id)"
              class="mt-1.5 flex justify-center"
            >
              <span class="text-[10px] text-text-muted flex items-center gap-0.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15" /></svg>
                收起
              </span>
            </div>
          </div>

          <!-- Usage indicator -->
          <div v-if="presetUsage[preset.id]?.length" class="mt-2.5 pt-2.5 border-t border-border">
            <div class="flex items-center gap-1.5 flex-wrap">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-[#10b981]/70 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span
                v-for="label in presetUsage[preset.id]"
                :key="label"
                class="text-[10px] px-1.5 py-0.5 rounded-full bg-[#10b981]/10 text-[#10b981]"
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
          class="fixed right-0 top-0 bottom-0 z-50 w-full md:w-[480px] bg-bg-card border-l border-border shadow-2xl flex flex-col"
          @click.stop
        >
          <!-- Drawer header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-border">
            <div class="flex items-center gap-2.5">
              <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-[#059669]/20 to-[#10b981]/20 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-[#10b981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" />
                  <path d="M19 17V5a2 2 0 0 0-2-2H4" />
                </svg>
              </div>
              <h3 class="text-sm font-semibold text-text-primary">
                {{ editingPreset ? '编辑提示词预设' : '新建提示词预设' }}
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
                预设名称 <span class="text-[#10b981]">*</span>
              </label>
              <input
                v-model="promptForm.name"
                type="text"
                placeholder="例如: 论文对比、深入分析、简要概括..."
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#10b981] transition-colors"
              />
            </div>

            <!-- Prompt content -->
            <div class="flex-1">
              <div class="flex items-center justify-between mb-1.5">
                <label class="block text-xs font-medium text-text-secondary">提示词内容</label>
                <span class="text-[10px] text-text-muted tabular-nums">
                  {{ contentCharCount }} 字 · {{ contentLineCount }} 行
                </span>
              </div>
              <textarea
                v-model="promptForm.prompt_content"
                rows="18"
                placeholder="输入系统提示词内容..."
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#10b981] transition-colors resize-y leading-relaxed font-mono min-h-[300px]"
              ></textarea>
            </div>
          </div>

          <!-- Drawer footer (sticky) -->
          <div class="px-6 py-4 border-t border-border bg-bg-card flex items-center justify-end gap-2">
            <button
              class="px-4 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover transition-colors"
              @click="closeDrawer"
            >取消</button>
            <button
              class="px-5 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#059669] to-[#10b981] text-white hover:opacity-90 shadow-lg shadow-[#10b981]/20 transition-all disabled:opacity-50 flex items-center gap-2"
              :disabled="!promptForm.name.trim() || formSaving"
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
                确定要删除提示词预设
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
