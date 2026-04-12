<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import {
  fetchUserSettings,
  saveUserSettings,
  fetchUserLlmPresets,
  fetchUserPromptPresets,
} from '@shared/api'
import type { UserLlmPreset, UserPromptPreset } from '@shared/types/admin'
import { showToast } from 'vant'

defineOptions({ name: 'FeatureSettingsView' })

const router = useRouter()
const route = useRoute()
const feature = computed(() => route.params.feature as string)

// ── Feature meta ──────────────────────────────────────────────────────────
const FEATURE_META: Record<string, { label: string; color: string; stages?: string[] }> = {
  compare: { label: '对比分析配置', color: 'tinder-blue' },
  inspiration: { label: '灵感涌现配置', color: 'tinder-green' },
  idea_generate: {
    label: '灵感生成配置',
    color: 'tinder-gold',
    stages: ['ingest', 'question', 'candidate', 'review', 'revise', 'plan', 'eval'],
  },
  paper_recommend: { label: '论文推荐参数', color: 'tinder-pink' },
}

const meta = computed(() => FEATURE_META[feature.value] ?? { label: '功能配置', color: 'tinder-blue' })
const stages = computed(() => meta.value.stages ?? null)

// ── State ────────────────────────────────────────────────────────────────
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const defaults = ref<Record<string, any>>({})
const settings = ref<Record<string, any>>({})
const llmPresets = ref<UserLlmPreset[]>([])
const promptPresets = ref<UserPromptPreset[]>([])
const expandedStages = ref(new Set<string>())

// Picker state
const pickerType = ref<'llm' | 'prompt' | null>(null)
const pickerKey = ref<string>('')
const pickerVisible = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [settingsRes, llmRes, promptRes] = await Promise.all([
      fetchUserSettings(feature.value),
      fetchUserLlmPresets(),
      fetchUserPromptPresets(),
    ])
    defaults.value = settingsRes.defaults ?? {}
    settings.value = { ...(settingsRes.defaults ?? {}), ...(settingsRes.settings ?? {}) }
    llmPresets.value = llmRes.presets
    promptPresets.value = promptRes.presets
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

watch(feature, load)

async function doSave() {
  saving.value = true
  try {
    await saveUserSettings(feature.value, settings.value)
    showToast('已保存')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function resetField(key: string) {
  if (key in defaults.value) settings.value[key] = defaults.value[key]
}

// ── Picker helpers ─────────────────────────────────────────────────────
function openPicker(type: 'llm' | 'prompt', key: string) {
  pickerType.value = type
  pickerKey.value = key
  pickerVisible.value = true
}

function selectPreset(id: number | null) {
  settings.value[pickerKey.value] = id
  pickerVisible.value = false
}

function llmPresetName(id: number | null) {
  if (!id) return '（默认）'
  return llmPresets.value.find((p) => p.id === id)?.name ?? `预设 #${id}`
}

function promptPresetName(id: number | null) {
  if (!id) return '（默认）'
  return promptPresets.value.find((p) => p.id === id)?.name ?? `预设 #${id}`
}

// ── Stage helpers ─────────────────────────────────────────────────────
const STAGE_LABELS: Record<string, string> = {
  ingest: '摄入 (Ingest)',
  question: '问题生成 (Question)',
  candidate: '候选筛选 (Candidate)',
  review: '评审 (Review)',
  revise: '修订 (Revise)',
  plan: '规划 (Plan)',
  eval: '评估 (Eval)',
}

function stageLabel(s: string) { return STAGE_LABELS[s] ?? s }
function stageLlmKey(s: string) { return `${s}_llm_preset_id` }
function stagePromptKey(s: string) { return `${s}_prompt_preset_id` }

// For non-stage features: collect all settings keys of llm / prompt type
const simplePresetKeys = computed(() => {
  if (stages.value) return []
  return Object.keys(defaults.value).filter((k) => k.endsWith('_llm_preset_id') || k.endsWith('_prompt_preset_id'))
})

const otherKeys = computed(() => {
  if (stages.value) return Object.keys(defaults.value).filter((k) => !k.endsWith('_preset_id'))
  return Object.keys(defaults.value).filter((k) => !k.endsWith('_preset_id') && !stages.value?.some((s) => k.startsWith(s)))
})

function fieldLabel(key: string): string {
  const map: Record<string, string> = {
    llm_preset_id: '模型预设',
    prompt_preset_id: '提示词预设',
    max_words: '最大字数',
    mineru_token: 'MinerU Token',
    categories: '分类列表',
    extra_query: '额外查询条件',
    max_papers: '最大论文数',
    days: '天数范围',
  }
  for (const [k, v] of Object.entries(map)) { if (key === k || key.endsWith(`_${k}`)) return v }
  return key
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader :title="meta.label" @back="router.back()" />

    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else>
      <div class="flex-1 overflow-y-auto pb-32 px-4 pt-4 space-y-4">

        <!-- Simple features: direct preset selectors + other fields -->
        <template v-if="!stages">
          <!-- LLM / Prompt preset selectors -->
          <div
            v-for="key in simplePresetKeys"
            :key="key"
            class="card-section"
          >
            <p class="text-[12px] font-semibold text-text-muted mb-2">{{ fieldLabel(key) }}</p>
            <button
              type="button"
              class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-elevated border border-border active:bg-bg-hover"
              @click="openPicker(key.endsWith('_llm_preset_id') ? 'llm' : 'prompt', key)"
            >
              <span class="text-[13px] text-text-primary">
                {{ key.endsWith('_llm_preset_id') ? llmPresetName(settings[key]) : promptPresetName(settings[key]) }}
              </span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
          </div>

          <!-- Other fields -->
          <div
            v-for="key in otherKeys"
            :key="key"
            class="card-section"
          >
            <label class="text-[12px] font-semibold text-text-muted mb-2 block">{{ fieldLabel(key) }}</label>
            <input
              v-model="settings[key]"
              type="text"
              class="input-field"
              :placeholder="String(defaults[key] ?? '')"
            />
          </div>
        </template>

        <!-- Staged feature (idea_generate): accordion per stage -->
        <template v-else>
          <div
            v-for="stage in stages"
            :key="stage"
            class="card-section overflow-hidden"
          >
            <!-- Stage header -->
            <button
              type="button"
              class="w-full flex items-center gap-3 -m-4 p-4"
              @click="() => { if (expandedStages.has(stage)) expandedStages.delete(stage); else expandedStages.add(stage) }"
            >
              <div class="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0" :style="`background: var(--color-${meta.color})`">
                {{ stages.indexOf(stage) + 1 }}
              </div>
              <span class="flex-1 text-[14px] font-semibold text-text-primary text-left">{{ stageLabel(stage) }}</span>
              <svg
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                class="text-text-muted transition-transform shrink-0"
                :class="expandedStages.has(stage) ? 'rotate-180' : ''"
              ><polyline points="6 9 12 15 18 9" /></svg>
            </button>

            <!-- Stage content -->
            <div v-if="expandedStages.has(stage)" class="mt-4 space-y-3">
              <div>
                <p class="text-[12px] font-semibold text-text-muted mb-2">模型预设</p>
                <button
                  type="button"
                  class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-elevated border border-border active:bg-bg-hover"
                  @click="openPicker('llm', stageLlmKey(stage))"
                >
                  <span class="text-[13px] text-text-primary">{{ llmPresetName(settings[stageLlmKey(stage)]) }}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
                </button>
              </div>
              <div>
                <p class="text-[12px] font-semibold text-text-muted mb-2">提示词预设</p>
                <button
                  type="button"
                  class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl bg-bg-elevated border border-border active:bg-bg-hover"
                  @click="openPicker('prompt', stagePromptKey(stage))"
                >
                  <span class="text-[13px] text-text-primary">{{ promptPresetName(settings[stagePromptKey(stage)]) }}</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Save bar -->
      <div
        class="shrink-0 fixed bottom-0 left-0 right-0 bg-bg/90 backdrop-blur-md border-t border-border px-4 pt-3 z-10"
        style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px));"
      >
        <button type="button" class="btn-primary" :disabled="saving" @click="doSave">
          {{ saving ? '保存中…' : '保存配置' }}
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
        <!-- Clear / default option -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover"
          @click="selectPreset(null)"
        >
          <div class="w-8 h-8 rounded-xl bg-bg-elevated border border-border flex items-center justify-center shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </div>
          <span class="text-[14px] text-text-muted">（使用默认）</span>
        </button>

        <template v-if="pickerType === 'llm'">
          <button
            v-for="preset in llmPresets"
            :key="preset.id"
            type="button"
            class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover"
            @click="selectPreset(preset.id)"
          >
            <div class="w-8 h-8 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-blue">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[14px] text-text-primary truncate">{{ preset.name }}</p>
              <p class="text-[11px] text-text-muted font-mono truncate">{{ preset.model }}</p>
            </div>
            <svg v-if="settings[pickerKey] === preset.id" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-green shrink-0">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>
        </template>

        <template v-else>
          <button
            v-for="preset in promptPresets"
            :key="preset.id"
            type="button"
            class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover"
            @click="selectPreset(preset.id)"
          >
            <div class="w-8 h-8 rounded-xl bg-tinder-purple/10 flex items-center justify-center shrink-0">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-purple">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[14px] text-text-primary truncate">{{ preset.name }}</p>
              <p class="text-[11px] text-text-muted font-mono truncate line-clamp-1">{{ preset.prompt_content.slice(0, 60) }}…</p>
            </div>
            <svg v-if="settings[pickerKey] === preset.id" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-tinder-green shrink-0">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>
        </template>
      </div>
    </BottomSheet>
  </div>
</template>
