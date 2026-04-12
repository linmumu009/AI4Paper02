<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { fetchPipelineDataTracking } from '@shared/api'
import type { PipelineDataTrackingRecord } from '@shared/types/admin'

defineOptions({ name: 'AdminDataTrackingView' })

const router = useRouter()
const records = ref<PipelineDataTrackingRecord[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchPipelineDataTracking()
    records.value = (res.records ?? []).slice(-14).reverse()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmt(n: number | null | undefined): string { return n == null ? '-' : String(n) }

function barPct(val: number | null, max: number): string {
  if (!val || !max) return '0%'
  return `${Math.round((val / max) * 100)}%`
}

const COLS = [
  { key: 'arxiv_search', label: '搜索', color: 'bg-tinder-blue' },
  { key: 'dedup', label: '去重后', color: 'bg-tinder-purple' },
  { key: 'theme_scored', label: '主题评分', color: 'bg-tinder-gold' },
  { key: 'theme_passed', label: '通过筛选', color: 'bg-tinder-green' },
  { key: 'final_selected', label: '最终入库', color: 'bg-tinder-pink' },
  { key: 'summary_raw', label: '总结原始', color: 'bg-text-muted' },
]
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="数据追踪" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载数据追踪…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />
    <div v-else class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      <p class="text-[12px] text-text-muted">最近 {{ records.length }} 天的 Pipeline 数据流转追踪</p>

      <!-- Daily funnel cards -->
      <div
        v-for="rec in records"
        :key="rec.date"
        class="card-section"
      >
        <p class="text-[13px] font-semibold text-text-primary mb-3">{{ rec.date }}</p>
        <div class="space-y-2">
          <div v-for="col in COLS" :key="col.key" class="flex items-center gap-2">
            <span class="text-[11px] text-text-muted w-16 shrink-0">{{ col.label }}</span>
            <div class="flex-1 h-2 bg-bg-elevated rounded-full overflow-hidden">
              <div
                class="h-full rounded-full"
                :class="col.color"
                :style="{ width: barPct((rec as any)[col.key], rec.arxiv_search ?? 1) }"
              />
            </div>
            <span class="text-[11px] font-mono text-text-secondary w-8 text-right shrink-0">{{ fmt((rec as any)[col.key]) }}</span>
          </div>
        </div>
        <div class="flex items-center justify-between mt-2 pt-2 border-t border-border/50">
          <span class="text-[11px] text-text-muted">论文资产</span>
          <span class="text-[11px] font-mono text-tinder-green">{{ fmt(rec.paper_assets) }}</span>
        </div>
      </div>

      <div v-if="records.length === 0" class="text-center py-8 text-[13px] text-text-muted">暂无追踪数据</div>
    </div>
  </div>
</template>
