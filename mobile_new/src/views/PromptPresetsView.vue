<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import {
  fetchUserPromptPresets,
  createUserPromptPreset,
  updateUserPromptPreset,
  deleteUserPromptPreset,
} from '@shared/api'
import type { UserPromptPreset } from '@shared/types/admin'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'PromptPresetsView' })

const router = useRouter()

const presets = ref<UserPromptPreset[]>([])
const loading = ref(true)
const error = ref('')
const formVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const expandedIds = ref(new Set<number>())

const form = ref({
  name: '',
  prompt_content: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchUserPromptPresets()
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
  form.value = { name: '', prompt_content: '' }
  formVisible.value = true
}

function openEdit(preset: UserPromptPreset) {
  editingId.value = preset.id
  form.value = { name: preset.name, prompt_content: preset.prompt_content }
  formVisible.value = true
}

async function confirmSave() {
  if (!form.value.name.trim() || !form.value.prompt_content.trim()) {
    showToast('名称和内容不能为空')
    return
  }
  saving.value = true
  try {
    const payload = { name: form.value.name.trim(), prompt_content: form.value.prompt_content }
    if (editingId.value !== null) {
      const res = await updateUserPromptPreset(editingId.value, payload)
      const idx = presets.value.findIndex((p) => p.id === editingId.value)
      if (idx >= 0) presets.value[idx] = res.preset
    } else {
      const res = await createUserPromptPreset(payload as any)
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

async function confirmDelete(preset: UserPromptPreset) {
  try {
    await showDialog({
      title: '删除预设',
      message: `确定删除「${preset.name}」？`,
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteUserPromptPreset(preset.id)
    presets.value = presets.value.filter((p) => p.id !== preset.id)
    showToast('已删除')
  } catch {/* cancelled */}
}

function toggleExpand(id: number) {
  if (expandedIds.value.has(id)) expandedIds.value.delete(id)
  else expandedIds.value.add(id)
}

const formTitle = computed(() => editingId.value !== null ? '编辑提示词预设' : '新建提示词预设')
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="提示词预设" @back="router.back()">
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
        title="还没有提示词预设"
        description="点击右上角「+」新建一个 Prompt 预设"
      />
      <div v-else class="space-y-3 px-4 pt-4">
        <div
          v-for="preset in presets"
          :key="preset.id"
          class="card-section"
        >
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-2xl bg-tinder-purple/10 flex items-center justify-center shrink-0">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-purple">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-[14px] font-semibold text-text-primary">{{ preset.name }}</p>
              <!-- Preview / Expand -->
              <button type="button" class="w-full text-left mt-1.5" @click="toggleExpand(preset.id)">
                <p
                  class="text-[12px] text-text-muted leading-relaxed font-mono"
                  :class="expandedIds.has(preset.id) ? '' : 'line-clamp-2'"
                >{{ preset.prompt_content }}</p>
                <span class="text-[11px] text-tinder-blue mt-1 block">{{ expandedIds.has(preset.id) ? '收起' : '展开查看' }}</span>
              </button>
            </div>
          </div>

          <div class="flex gap-2 mt-3 pt-3 border-t border-border/50">
            <button
              type="button"
              class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-bg-elevated border border-border text-[12px] text-text-secondary active:bg-bg-hover"
              @click="openEdit(preset)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              编辑
            </button>
            <button
              type="button"
              class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 text-[12px] text-tinder-pink active:bg-tinder-pink/20"
              @click="confirmDelete(preset)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit BottomSheet (full height for textarea) -->
    <BottomSheet :visible="formVisible" :title="formTitle" height="90dvh" @close="formVisible = false">
      <div class="flex flex-col h-full px-5 pb-8 pt-2 gap-4 overflow-y-auto">
        <div>
          <label class="form-label">预设名称 <span class="text-tinder-pink">*</span></label>
          <input v-model="form.name" type="text" class="input-field" placeholder="例如：学术摘要助手" maxlength="50" />
        </div>
        <div class="flex-1 flex flex-col">
          <label class="form-label">提示词内容 <span class="text-tinder-pink">*</span></label>
          <textarea
            v-model="form.prompt_content"
            class="input-field flex-1 resize-none font-mono text-[13px] leading-relaxed"
            placeholder="在此输入 Prompt 内容…"
            style="min-height: 200px;"
          />
        </div>
        <button
          type="button"
          class="btn-primary shrink-0"
          :disabled="saving || !form.name.trim() || !form.prompt_content.trim()"
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
