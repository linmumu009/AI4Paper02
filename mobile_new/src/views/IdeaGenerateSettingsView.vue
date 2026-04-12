<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import { fetchIdeaPromptVersions } from '@shared/api'
import type { IdeaPromptVersion } from '@shared/types/idea'

defineOptions({ name: 'IdeaGenerateSettingsView' })

const router = useRouter()
const versions = ref<IdeaPromptVersion[]>([])
const loading = ref(true)
const expanded = ref<Set<number>>(new Set())

onMounted(async () => {
  try {
    const res = await fetchIdeaPromptVersions({ limit: 20 })
    versions.value = res.versions
  } finally {
    loading.value = false
  }
})

function toggle(id: number) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="生成设置" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载配置…" />
    <div v-else class="flex-1 overflow-y-auto pb-4">
      <p class="px-4 py-2 text-[12px] text-text-muted">提示词版本 ({{ versions.length }})</p>
      <div v-if="versions.length === 0" class="px-4 py-8 text-center text-[13px] text-text-muted">暂无提示词版本</div>
      <div v-for="v in versions" :key="v.id" class="border-b border-border">
        <button type="button" class="w-full flex items-center gap-3 px-4 py-3 active:bg-bg-hover" @click="toggle(v.id)">
          <div class="flex-1 text-left">
            <p class="text-[13px] font-medium text-text-primary">{{ v.stage }} · v{{ v.version }}</p>
            <p class="text-[11px] text-text-muted">{{ new Date(v.created_at).toLocaleDateString('zh-CN') }}</p>
          </div>
          <svg class="shrink-0 text-text-muted transition-transform" :class="expanded.has(v.id) ? 'rotate-90' : ''" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6" /></svg>
        </button>
        <div v-if="expanded.has(v.id)" class="px-4 pb-3">
          <pre class="text-[11px] font-mono bg-bg-elevated rounded-xl p-3 overflow-x-auto text-text-secondary whitespace-pre-wrap">{{ v.prompt_text.slice(0, 800) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
