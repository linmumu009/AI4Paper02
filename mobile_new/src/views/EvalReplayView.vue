<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { fetchIdeaBenchmarks } from '@shared/api'
import type { IdeaBenchmark } from '@shared/types/idea'

defineOptions({ name: 'EvalReplayView' })

const router = useRouter()
const benchmarks = ref<IdeaBenchmark[]>([])
const loading = ref(true)
const error = ref('')
const expanded = ref<Set<number>>(new Set())

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaBenchmarks()
    benchmarks.value = res.benchmarks
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function toggle(id: number) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="评测回放" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载评测记录…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />
    <div v-else class="flex-1 overflow-y-auto pb-4">
      <p class="px-4 py-2 text-[12px] text-text-muted">共 {{ benchmarks.length }} 个评测</p>
      <div v-if="benchmarks.length === 0" class="flex flex-col items-center justify-center h-40 text-text-muted">
        <p class="text-sm">还没有评测记录</p>
      </div>
      <div
        v-for="bm in benchmarks"
        :key="bm.id"
        class="border-b border-border"
      >
        <button
          type="button"
          class="w-full flex items-start gap-3 px-4 py-3 active:bg-bg-hover text-left"
          @click="toggle(bm.id)"
        >
          <div class="flex-1 min-w-0">
            <p class="text-[13px] font-semibold text-text-primary">{{ bm.name }}</p>
            <p class="text-[11px] text-text-muted mt-0.5">{{ bm.model_version }} · {{ bm.question_ids.length }} 题 · {{ new Date(bm.created_at).toLocaleDateString('zh-CN') }}</p>
          </div>
          <svg class="shrink-0 text-text-muted transition-transform mt-1" :class="expanded.has(bm.id) ? 'rotate-90' : ''" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6" /></svg>
        </button>
        <div v-if="expanded.has(bm.id)" class="px-4 pb-3">
          <pre class="text-[11px] font-mono bg-bg-elevated rounded-xl p-3 overflow-x-auto text-text-muted">{{ JSON.stringify(bm.results, null, 2).slice(0, 1000) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
