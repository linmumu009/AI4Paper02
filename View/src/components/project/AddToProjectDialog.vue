<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { addResearchProjectAsset, fetchResearchProjects } from '../../api'
import type { ProjectAssetType, ResearchProjectSummary } from '../../types/paper'

const props = withDefaults(defineProps<{
  assetType: ProjectAssetType
  assetId: string
  sourceScope?: string
  assetTitle?: string
}>(), { sourceScope: '', assetTitle: '' })

const emit = defineEmits<{
  close: []
  added: [projectId: number]
}>()

const projects = ref<ResearchProjectSummary[]>([])
const selectedProjectId = ref<number | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  try {
    projects.value = await fetchResearchProjects(false)
    selectedProjectId.value = projects.value[0]?.id ?? null
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '课题加载失败'
  } finally {
    loading.value = false
  }
}

async function confirmAdd() {
  if (!selectedProjectId.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    await addResearchProjectAsset(selectedProjectId.value, {
      asset_type: props.assetType,
      asset_id: props.assetId,
      source_scope: props.sourceScope,
    })
    emit('added', selectedProjectId.value)
    emit('close')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '加入课题失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4" @click.self="emit('close')">
      <div class="w-full max-w-md rounded-2xl border border-border bg-bg-card p-5 shadow-2xl">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-bold text-text-primary">加入课题</h2>
            <p class="mt-1 line-clamp-2 text-xs text-text-muted">{{ assetTitle || assetId }}</p>
          </div>
          <button class="rounded-lg px-2 py-1 text-text-muted hover:bg-bg-hover" @click="emit('close')">✕</button>
        </div>

        <div v-if="loading" class="py-10 text-center text-sm text-text-muted">正在加载课题…</div>
        <div v-else-if="!projects.length" class="py-8 text-center">
          <p class="text-sm font-semibold text-text-primary">还没有可用课题</p>
          <p class="mt-1 text-xs text-text-muted">请先在研究库创建一个课题空间。</p>
          <router-link to="/projects" class="mt-4 inline-flex rounded-lg bg-brand-gradient px-4 py-2 text-xs font-semibold text-white no-underline" @click="emit('close')">前往研究库</router-link>
        </div>
        <template v-else>
          <div class="mt-4 max-h-72 space-y-2 overflow-y-auto">
            <label
              v-for="project in projects"
              :key="project.id"
              class="flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-3 transition"
              :class="selectedProjectId === project.id ? 'border-tinder-pink/50 bg-tinder-pink/10' : 'border-border hover:bg-bg-hover'"
            >
              <input v-model="selectedProjectId" type="radio" :value="project.id" class="accent-pink-500">
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-text-primary">{{ project.name }}</span>
                <span class="block text-[11px] text-text-muted">{{ project.asset_count }} 项研究资产</span>
              </span>
            </label>
          </div>
          <p v-if="error" class="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{{ error }}</p>
          <div class="mt-5 flex justify-end gap-2">
            <button class="rounded-lg border border-border px-4 py-2 text-xs text-text-secondary" @click="emit('close')">取消</button>
            <button :disabled="!selectedProjectId || saving" class="rounded-lg bg-brand-gradient px-4 py-2 text-xs font-semibold text-white disabled:opacity-50" @click="confirmAdd">{{ saving ? '加入中…' : '加入课题' }}</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>
