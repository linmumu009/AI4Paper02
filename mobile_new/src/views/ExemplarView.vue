<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { fetchIdeaExemplars } from '@shared/api'
import type { IdeaExemplar } from '@shared/types/idea'

defineOptions({ name: 'ExemplarView' })

const router = useRouter()
const exemplars = ref<IdeaExemplar[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaExemplars()
    exemplars.value = res.exemplars
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="范例库" @back="router.back()" />
    <LoadingState v-if="loading" class="flex-1" message="加载范例…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />
    <div v-else class="flex-1 overflow-y-auto pb-4">
      <p class="px-4 py-2 text-[12px] text-text-muted">共 {{ exemplars.length }} 个范例</p>
      <div
        v-for="ex in exemplars"
        :key="ex.id"
        class="px-4 py-4 border-b border-border cursor-pointer active:bg-bg-hover"
        @click="ex.candidate_id && router.push(`/idea/candidates/${ex.candidate_id}`)"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="text-[12px] font-semibold text-tinder-gold">⭐ {{ ex.score?.toFixed(1) ?? '-' }}</span>
          <span class="text-[11px] text-text-muted">{{ new Date(ex.created_at).toLocaleDateString('zh-CN') }}</span>
        </div>
        <p v-if="ex.notes" class="text-[13px] text-text-secondary leading-relaxed">{{ ex.notes }}</p>
        <div v-if="ex.pattern && Object.keys(ex.pattern).length" class="mt-2 p-2 rounded-lg bg-bg-elevated text-[11px] font-mono text-text-muted overflow-hidden">
          {{ JSON.stringify(ex.pattern).slice(0, 200) }}…
        </div>
      </div>
    </div>
  </div>
</template>
