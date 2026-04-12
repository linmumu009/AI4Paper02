<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { fetchPromptConfigs, createPromptConfig, updatePromptConfig, deletePromptConfig } from '@shared/api'
import type { PromptConfig } from '@shared/types/admin'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AdminPromptConfigsView' })

const router = useRouter()
const configs = ref<PromptConfig[]>([])
const loading = ref(true)
const error = ref('')
const formVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const expandedIds = ref(new Set<number>())

const form = ref({ name: '', prompt_content: '', remark: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchPromptConfigs()
    configs.value = (res as any).configs ?? []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  editingId.value = null; form.value = { name: '', prompt_content: '', remark: '' }; formVisible.value = true
}

function openEdit(cfg: PromptConfig) {
  editingId.value = cfg.id; form.value = { name: cfg.name, prompt_content: cfg.prompt_content, remark: (cfg as any).remark ?? '' }; formVisible.value = true
}

async function confirmSave() {
  if (!form.value.name.trim() || !form.value.prompt_content.trim()) { showToast('名称和内容不能为空'); return }
  saving.value = true
  try {
    const payload: any = { name: form.value.name.trim(), prompt_content: form.value.prompt_content, remark: form.value.remark }
    if (editingId.value !== null) await updatePromptConfig(editingId.value, payload)
    else await createPromptConfig(payload)
    formVisible.value = false
    showToast(editingId.value !== null ? '已更新' : '已创建')
    await load()
  } catch (e: any) { showToast(e?.response?.data?.detail || '保存失败') } finally { saving.value = false }
}

async function confirmDelete(cfg: PromptConfig) {
  try {
    await showDialog({ title: '删除提示词配置', message: `确定删除「${cfg.name}」？`, confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    await deletePromptConfig(cfg.id)
    configs.value = configs.value.filter((c) => c.id !== cfg.id)
    showToast('已删除')
  } catch { /* cancelled */ }
}

const formTitle = computed(() => editingId.value !== null ? '编辑提示词配置' : '新建提示词配置')
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="提示词配置库" @back="router.back()">
      <template #right>
        <button type="button" class="w-10 h-10 flex items-center justify-center text-tinder-pink active:opacity-70" @click="openCreate">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
        </button>
      </template>
    </PageHeader>
    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />
    <div v-else class="flex-1 overflow-y-auto pb-6">
      <EmptyState v-if="configs.length === 0" title="还没有提示词配置" description="点击右上角「+」新建" />
      <div v-else class="space-y-3 px-4 pt-4">
        <div v-for="cfg in configs" :key="cfg.id" class="card-section">
          <div class="flex items-start gap-3">
            <div class="flex-1 min-w-0">
              <p class="text-[14px] font-semibold text-text-primary">{{ cfg.name }}</p>
              <button type="button" class="w-full text-left mt-1.5" @click="expandedIds.has(cfg.id) ? expandedIds.delete(cfg.id) : expandedIds.add(cfg.id)">
                <p class="text-[11px] text-text-muted font-mono leading-relaxed" :class="expandedIds.has(cfg.id) ? '' : 'line-clamp-2'">{{ cfg.prompt_content }}</p>
                <span class="text-[10px] text-tinder-blue mt-1 block">{{ expandedIds.has(cfg.id) ? '收起' : '展开' }}</span>
              </button>
            </div>
            <div class="flex gap-1.5 shrink-0">
              <button type="button" class="w-8 h-8 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-text-secondary active:bg-bg-hover" @click="openEdit(cfg)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
              </button>
              <button type="button" class="w-8 h-8 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 flex items-center justify-center text-tinder-pink active:bg-tinder-pink/20" @click="confirmDelete(cfg)">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <BottomSheet :visible="formVisible" :title="formTitle" height="90dvh" @close="formVisible = false">
      <div class="flex flex-col px-5 pb-8 pt-2 gap-4 overflow-y-auto">
        <div><label class="form-label">名称 *</label><input v-model="form.name" type="text" class="input-field" placeholder="提示词配置名称" maxlength="80" /></div>
        <div class="flex-1 flex flex-col">
          <label class="form-label">提示词内容 *</label>
          <textarea v-model="form.prompt_content" class="input-field flex-1 resize-none font-mono text-[13px]" placeholder="Prompt 内容…" style="min-height: 200px;" />
        </div>
        <button type="button" class="btn-primary shrink-0" :disabled="saving || !form.name.trim() || !form.prompt_content.trim()" @click="confirmSave">{{ saving ? '保存中…' : (editingId !== null ? '更新' : '创建') }}</button>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.form-label { display: block; font-size: 12px; font-weight: 500; color: var(--color-text-muted); margin-bottom: 6px; }
</style>
