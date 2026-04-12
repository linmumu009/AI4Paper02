<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  fetchUserLlmPresets,
  createUserLlmPreset,
  updateUserLlmPreset,
  deleteUserLlmPreset,
} from '@shared/api'
import type { UserLlmPreset } from '@shared/types/admin'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'LlmPresetsView' })

const router = useRouter()

const presets = ref<UserLlmPreset[]>([])
const loading = ref(true)
const error = ref('')
const formVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const showAdvanced = ref(false)
const showApiKey = ref(false)

const form = ref({
  name: '',
  model: '',
  base_url: '',
  api_key: '',
  temperature: null as number | null,
  max_tokens: null as number | null,
  input_hard_limit: null as number | null,
  input_safety_margin: null as number | null,
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchUserLlmPresets()
    presets.value = res.presets
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  editingId.value = null
  form.value = { name: '', model: '', base_url: '', api_key: '', temperature: null, max_tokens: null, input_hard_limit: null, input_safety_margin: null }
  showAdvanced.value = false
  showApiKey.value = false
  formVisible.value = true
}

function openEdit(preset: UserLlmPreset) {
  editingId.value = preset.id
  form.value = {
    name: preset.name,
    model: preset.model,
    base_url: preset.base_url,
    api_key: preset.api_key,
    temperature: preset.temperature ?? null,
    max_tokens: preset.max_tokens ?? null,
    input_hard_limit: preset.input_hard_limit ?? null,
    input_safety_margin: preset.input_safety_margin ?? null,
  }
  showAdvanced.value = !!(preset.temperature || preset.max_tokens || preset.input_hard_limit || preset.input_safety_margin)
  showApiKey.value = false
  formVisible.value = true
}

async function confirmSave() {
  if (!form.value.name.trim() || !form.value.model.trim()) {
    showToast('名称和模型不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      model: form.value.model.trim(),
      base_url: form.value.base_url.trim(),
      api_key: form.value.api_key,
      temperature: form.value.temperature,
      max_tokens: form.value.max_tokens,
      input_hard_limit: form.value.input_hard_limit,
      input_safety_margin: form.value.input_safety_margin,
    }
    if (editingId.value !== null) {
      const res = await updateUserLlmPreset(editingId.value, payload)
      const idx = presets.value.findIndex((p) => p.id === editingId.value)
      if (idx >= 0) presets.value[idx] = res.preset
    } else {
      const res = await createUserLlmPreset(payload as any)
      presets.value.push(res.preset)
    }
    formVisible.value = false
    showToast(editingId.value !== null ? '已更新' : '已创建')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(preset: UserLlmPreset) {
  try {
    await showDialog({
      title: '删除预设',
      message: `确定删除「${preset.name}」？`,
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteUserLlmPreset(preset.id)
    presets.value = presets.value.filter((p) => p.id !== preset.id)
    showToast('已删除')
  } catch {/* user cancelled */}
}

const formTitle = computed(() => editingId.value !== null ? '编辑模型预设' : '新建模型预设')
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="模型预设" @back="router.back()">
      <template #right>
        <button
          type="button"
          class="w-10 h-10 flex items-center justify-center text-tinder-pink active:opacity-70"
          aria-label="新建预设"
          @click="openCreate"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" class="flex-1" message="加载预设…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <div v-else class="flex-1 overflow-y-auto pb-6">
      <EmptyState
        v-if="presets.length === 0"
        title="还没有模型预设"
        description="点击右上角「+」新建一个 LLM 模型预设"
      />
      <div v-else class="space-y-3 px-4 pt-4">
        <div
          v-for="preset in presets"
          :key="preset.id"
          class="card-section"
        >
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-2xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-blue">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[14px] font-semibold text-text-primary truncate">{{ preset.name }}</p>
              <p class="text-[12px] text-text-muted mt-0.5 font-mono truncate">{{ preset.model }}</p>
              <p v-if="preset.base_url" class="text-[11px] text-text-muted/70 mt-0.5 truncate">{{ preset.base_url }}</p>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <button
                type="button"
                class="w-8 h-8 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-text-secondary active:bg-bg-hover"
                @click="openEdit(preset)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
              <button
                type="button"
                class="w-8 h-8 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 flex items-center justify-center text-tinder-pink active:bg-tinder-pink/20"
                @click="confirmDelete(preset)"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit BottomSheet -->
    <BottomSheet :visible="formVisible" :title="formTitle" height="90dvh" @close="formVisible = false">
      <div class="px-5 pb-8 pt-2 space-y-4 overflow-y-auto">
        <!-- Name -->
        <div>
          <label class="form-label">预设名称 <span class="text-tinder-pink">*</span></label>
          <input v-model="form.name" type="text" class="input-field" placeholder="例如：GPT-4o 快速模式" maxlength="50" />
        </div>

        <!-- Model -->
        <div>
          <label class="form-label">模型标识符 <span class="text-tinder-pink">*</span></label>
          <input v-model="form.model" type="text" class="input-field font-mono" placeholder="例如：gpt-4o-mini" autocomplete="off" autocorrect="off" />
        </div>

        <!-- Base URL -->
        <div>
          <label class="form-label">API 地址（留空使用默认）</label>
          <input v-model="form.base_url" type="url" class="input-field font-mono" placeholder="https://api.openai.com/v1" autocomplete="off" />
        </div>

        <!-- API Key -->
        <div>
          <label class="form-label">API Key</label>
          <div class="relative">
            <input
              v-model="form.api_key"
              :type="showApiKey ? 'text' : 'password'"
              class="input-field pr-10 font-mono"
              placeholder="sk-..."
              autocomplete="new-password"
            />
            <button
              type="button"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
              @click="showApiKey = !showApiKey"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path v-if="showApiKey" d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line v-if="showApiKey" x1="1" y1="1" x2="23" y2="23" />
                <path v-else d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle v-if="!showApiKey" cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Advanced toggle -->
        <button
          type="button"
          class="flex items-center gap-2 text-[13px] text-text-muted active:text-tinder-blue"
          @click="showAdvanced = !showAdvanced"
        >
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
            class="transition-transform"
            :class="showAdvanced ? 'rotate-180' : ''"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
          高级参数
        </button>

        <div v-if="showAdvanced" class="space-y-3 pl-1">
          <div>
            <label class="form-label">Temperature（默认由服务端决定）</label>
            <input v-model.number="form.temperature" type="number" step="0.1" min="0" max="2" class="input-field" placeholder="0.7" />
          </div>
          <div>
            <label class="form-label">Max Tokens</label>
            <input v-model.number="form.max_tokens" type="number" min="1" inputmode="numeric" class="input-field" placeholder="4096" />
          </div>
          <div>
            <label class="form-label">输入硬上限 (input_hard_limit)</label>
            <input v-model.number="form.input_hard_limit" type="number" min="1" inputmode="numeric" class="input-field" placeholder="128000" />
          </div>
          <div>
            <label class="form-label">输入安全余量 (input_safety_margin)</label>
            <input v-model.number="form.input_safety_margin" type="number" min="0" inputmode="numeric" class="input-field" placeholder="500" />
          </div>
        </div>

        <button
          type="button"
          class="btn-primary"
          :disabled="saving || !form.name.trim() || !form.model.trim()"
          @click="confirmSave"
        >
          {{ saving ? '保存中…' : (editingId !== null ? '更新预设' : '创建预设') }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}
</style>
