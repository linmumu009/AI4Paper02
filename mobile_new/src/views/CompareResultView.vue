<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import { fetchCompareResult, deleteCompareResult } from '@shared/api'
import type { KbCompareResult } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'CompareResultView' })

const props = defineProps<{ id: string }>()
const router = useRouter()

const result = ref<KbCompareResult | null>(null)
const loading = ref(true)
const error = ref('')
const menuVisible = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    result.value = await fetchCompareResult(Number(props.id))
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function doDelete() {
  menuVisible.value = false
  try {
    await showDialog({
      title: '删除对比结果',
      message: '确定删除此对比结果？',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await deleteCompareResult(Number(props.id))
    showToast('已删除')
    router.back()
  } catch {
    // user cancelled
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader :title="result?.title || '对比结果'" @back="router.back()">
      <template #right>
        <button
          type="button"
          class="w-10 h-10 flex items-center justify-center text-text-secondary"
          aria-label="更多操作"
          @click="menuVisible = true"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" class="flex-1" message="加载对比结果…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else-if="result">
      <!-- Meta bar -->
      <div class="px-4 py-2 flex items-center gap-3 shrink-0 border-b border-border">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
          <rect x="2" y="3" width="7" height="7" rx="1" /><rect x="15" y="3" width="7" height="7" rx="1" />
          <rect x="2" y="14" width="7" height="7" rx="1" /><rect x="15" y="14" width="7" height="7" rx="1" />
        </svg>
        <span class="text-[12px] text-text-muted">{{ result.paper_ids.length }} 篇论文</span>
        <span class="text-[12px] text-text-muted ml-auto">
          {{ new Date(result.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) }}
        </span>
      </div>

      <!-- Markdown content -->
      <div class="flex-1 overflow-y-auto px-4 py-4 pb-8">
        <MarkdownRenderer :content="result.markdown" />
      </div>
    </template>

    <!-- Menu sheet -->
    <BottomSheet :visible="menuVisible" @close="menuVisible = false">
      <div class="pb-4">
        <button
          type="button"
          class="w-full flex items-center gap-3 px-5 py-4 text-[15px] text-tinder-pink active:bg-bg-hover"
          @click="doDelete"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
          删除对比结果
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
