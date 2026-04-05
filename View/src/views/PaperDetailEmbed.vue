<script setup lang="ts">
/**
 * 嵌入用论文详情（仅加载 + 正文），供 ContentLayout 使用，避免 ContentLayout ↔ PaperDetail 循环依赖。
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import PaperDetailBody from '../components/PaperDetailBody.vue'
import { fetchPaperDetail } from '../api'
import type { PaperDetailResponse, PaperSummary, PaperAssets, UserPaper } from '../types/paper'

const props = defineProps<{
  id?: string
  userPaperData?: UserPaper
  source?: 'recommendation' | 'user_upload'
}>()

const emit = defineEmits<{
  noteSaved: []
  openPdf: []
  openChat: []
}>()

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')

const effectiveDetail = computed<PaperDetailResponse | null>(() => {
  if (props.userPaperData?.summary) {
    const up = props.userPaperData
    const summary = up.summary as PaperSummary
    return {
      summary,
      paper_assets: (up.paper_assets as PaperAssets | null) ?? null,
      date: '',
      images: [],
      arxiv_url: up.external_url || (up.source_ref ? `https://arxiv.org/abs/${up.source_ref}` : ''),
      pdf_url: up.pdf_static_url || '',
    }
  }
  return detail.value
})

const effectiveSource = computed(() => props.source || (props.userPaperData ? 'user_upload' : undefined))

async function load(paperId: string) {
  if (props.userPaperData) return
  loading.value = true
  error.value = ''
  try {
    detail.value = await fetchPaperDetail(paperId)
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? '论文未找到' : (e?.message || '加载失败')
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (props.userPaperData) {
    loading.value = false
    return
  }
  const id = props.id as string
  if (id) load(id)
})

watch(
  () => [props.id, props.userPaperData] as const,
  ([pid, upd]) => {
    if (upd) {
      loading.value = false
      return
    }
    if (pid) load(pid as string)
  },
)
</script>

<template>
  <div class="h-full overflow-y-auto p-3 sm:p-6">
    <div v-if="loading" class="flex justify-center py-20">
      <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>
    <div v-else-if="error" class="text-center py-20">
      <p class="text-tinder-pink text-lg mb-4">{{ error }}</p>
    </div>
    <PaperDetailBody
      v-else-if="effectiveDetail"
      :detail="effectiveDetail"
      :effective-source="effectiveSource"
      @open-pdf="emit('openPdf')"
      @open-chat="emit('openChat')"
    />
  </div>
</template>
