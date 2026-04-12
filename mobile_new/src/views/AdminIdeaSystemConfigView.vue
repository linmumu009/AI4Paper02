<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { getSystemConfig, updateSystemConfig } from '@shared/api'
import type { SystemConfigResponse } from '@shared/types/admin'
import { showToast } from 'vant'

defineOptions({ name: 'AdminIdeaSystemConfigView' })

const router = useRouter()
const config = ref<SystemConfigResponse | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const editKey = ref('')
const editValue = ref('')

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    config.value = await getSystemConfig()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadConfig)

async function saveConfig(key: string, value: string) {
  if (saving.value) return
  saving.value = true
  try {
    let parsedValue: any = value
    try { parsedValue = JSON.parse(value) } catch { /* keep as string */ }
    await updateSystemConfig({ [key]: parsedValue })
    showToast('已保存')
    await loadConfig()
    editKey.value = ''
  } catch {
    showToast('保存失败')
  } finally {
    saving.value = false
  }
}

function startEdit(key: string, currentValue: any) {
  editKey.value = key
  editValue.value = typeof currentValue === 'object' ? JSON.stringify(currentValue, null, 2) : String(currentValue ?? '')
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="系统配置" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadConfig" />
    <div v-else-if="config" class="flex-1 overflow-y-auto pb-8">
      <div
        v-for="group in config.groups"
        :key="group.group"
        class="mb-4"
      >
        <p class="px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-wider">{{ group.name }}</p>
        <div
          v-for="item in group.items"
          :key="item.key"
          class="px-4 py-3 border-b border-border"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="flex-1 min-w-0">
              <p class="text-[12px] font-mono font-medium text-tinder-blue truncate">{{ item.key }}</p>
              <p v-if="item.description" class="text-[11px] text-text-muted mt-0.5">{{ item.description }}</p>
              <div v-if="editKey === item.key" class="mt-2 flex flex-col gap-2">
                <textarea
                  v-model="editValue"
                  class="input-field text-[12px] font-mono resize-none"
                  rows="3"
                />
                <div class="flex gap-2">
                  <button type="button" class="btn-primary py-2 text-[13px] flex-1" :disabled="saving" @click="saveConfig(item.key, editValue)">
                    保存
                  </button>
                  <button type="button" class="btn-ghost py-2 text-[13px] flex-1" @click="editKey = ''">取消</button>
                </div>
              </div>
              <p v-else class="text-[12px] text-text-secondary mt-0.5 break-all line-clamp-3">
                {{ typeof item.value === 'object' ? JSON.stringify(item.value) : String(item.value ?? config.defaults[item.key] ?? '-') }}
              </p>
            </div>
            <button
              v-if="editKey !== item.key"
              type="button"
              class="shrink-0 text-[12px] text-tinder-blue px-2 py-1 rounded-lg bg-tinder-blue/10"
              @click="startEdit(item.key, item.value ?? config.defaults[item.key])"
            >
              编辑
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
