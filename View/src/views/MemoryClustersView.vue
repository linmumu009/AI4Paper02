<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchResearchMemoryClusters } from '@shared/api'
import type { ResearchMemoryCluster } from '@shared/types/idea'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import WorkbenchPageShell from '../components/workbench/WorkbenchPageShell.vue'

const props = defineProps<{ embedded?: boolean }>()

const router = useRouter()

const clusters = ref<ResearchMemoryCluster[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  if (!isAuthenticated.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchResearchMemoryClusters(20)
    clusters.value = res.clusters
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) await load()
})

function goToPaper(paperId: string) {
  router.push(`/papers/${paperId}`)
}
</script>

<template>
  <WorkbenchPageShell
    icon="🗺️"
    title="研究记忆图谱"
    description="基于知识库论文的标签共现，自动聚合主题研究方向。"
    :back-to="!props.embedded ? '/workbench' : undefined"
  >
    <template #header-right>
      <button
        class="text-xs px-2.5 py-1 rounded border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
        @click="load"
      >刷新</button>
    </template>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 sm:p-6">
      <div v-if="loading" class="flex items-center justify-center min-h-[200px]">
        <div class="flex flex-col items-center gap-3">
          <div class="relative w-12 h-12 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-tinder-pink border-r-tinder-blue animate-spin" />
            <span class="text-xl">🗺️</span>
          </div>
          <p class="text-sm text-text-muted">聚类中...</p>
        </div>
      </div>

      <div v-else-if="error" class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>

      <div v-else-if="!isAuthenticated" class="flex items-center justify-center min-h-[200px]">
        <p class="text-sm text-text-muted">登录后可查看研究图谱。</p>
      </div>

      <div v-else-if="clusters.length === 0" class="flex items-center justify-center min-h-[200px]">
        <div class="text-center">
          <p class="text-3xl mb-3">🗺️</p>
          <p class="text-sm text-text-muted">
            暂无主题簇。请先在论文详情中生成研究记忆，系统会自动识别跨论文的主题方向。
          </p>
        </div>
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="cluster in clusters"
          :key="cluster.cluster_id"
          class="bg-bg-card border border-border rounded-xl p-4 flex flex-col gap-3 hover:border-border-light transition-colors"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <h3 class="text-sm font-semibold text-text-primary capitalize">{{ cluster.label }}</h3>
              <p class="text-xs text-text-muted mt-0.5">{{ cluster.paper_count }} 篇论文 · {{ cluster.atom_ids.length }} 个原子</p>
            </div>
            <span class="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-tinder-blue/10 text-tinder-blue border border-tinder-blue/20">
              {{ cluster.paper_count }} 篇
            </span>
          </div>

          <p v-if="cluster.summary_snippet" class="text-xs text-text-secondary leading-relaxed line-clamp-2 italic">
            "{{ cluster.summary_snippet }}"
          </p>

          <div class="flex flex-wrap gap-1">
            <span
              v-for="tag in cluster.top_tags"
              :key="tag"
              class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted border border-border"
            >{{ tag }}</span>
          </div>

          <div class="space-y-1">
            <button
              v-for="pid in cluster.paper_ids.slice(0, 3)"
              :key="pid"
              class="w-full text-left text-xs text-tinder-blue truncate px-2 py-1 rounded hover:bg-tinder-blue/5 transition-colors cursor-pointer bg-transparent border-none"
              @click="goToPaper(pid)"
            >
              📄 {{ pid }}
            </button>
            <p v-if="cluster.paper_ids.length > 3" class="text-[10px] text-text-muted pl-2">
              +{{ cluster.paper_ids.length - 3 }} 篇...
            </p>
          </div>
        </div>
      </div>
    </div>
  </WorkbenchPageShell>
</template>
