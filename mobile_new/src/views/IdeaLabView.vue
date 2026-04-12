<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import FloatingButton from '@/components/FloatingButton.vue'
import { fetchIdeaCandidates, fetchIdeaStats, generateIdeasStream } from '@shared/api'
import type { IdeaCandidate } from '@shared/types/idea'
import { showToast } from 'vant'

defineOptions({ name: 'IdeaLabView' })

const router = useRouter()
const candidates = ref<IdeaCandidate[]>([])
const loading = ref(true)
const error = ref('')
const atomCount = ref(0)
const generating = ref(false)
const generatingLog = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [cRes, stats] = await Promise.allSettled([
      fetchIdeaCandidates({ status: 'draft', limit: 50 }),
      fetchIdeaStats(),
    ])
    if (cRes.status === 'fulfilled') candidates.value = cRes.value.candidates
    else error.value = (cRes.reason as any)?.message || '加载失败'
    if (stats.status === 'fulfilled') atomCount.value = stats.value.atom_count
  } finally {
    loading.value = false
  }
}

onMounted(load)

function scoreColor(score?: number) {
  if (!score) return 'text-text-muted'
  if (score >= 7) return 'text-tinder-green'
  if (score >= 5) return 'text-tinder-gold'
  return 'text-tinder-pink'
}

async function doGenerate() {
  if (generating.value || atomCount.value === 0) {
    if (atomCount.value === 0) showToast('请先收藏论文到知识库')
    return
  }
  generating.value = true
  generatingLog.value = '连接中…'
  try {
    const resp = await generateIdeasStream({})
    if (!resp.ok) { generatingLog.value = '失败'; return }
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') continue
          try {
            const obj = JSON.parse(payload)
            if (obj.log) generatingLog.value = obj.log
          } catch { /* ignore */ }
        }
      }
    }
    generatingLog.value = ''
    await load()
    showToast('生成完成')
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="灵感实验室" @back="router.back()">
      <template #right>
        <button
          type="button"
          class="w-8 h-8 flex items-center justify-center rounded-lg active:bg-bg-hover"
          aria-label="生成设置"
          @click="router.push({ name: 'idea-generate-settings' })"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-text-secondary">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </template>
    </PageHeader>
    <LoadingState v-if="loading" class="flex-1" message="加载中…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />
    <div v-else class="flex-1 overflow-y-auto pb-6">
      <!-- Generating status -->
      <div v-if="generating" class="px-4 py-3 bg-tinder-blue/10 border-b border-tinder-blue/20 flex items-center gap-2">
        <div class="w-4 h-4 border-2 border-tinder-blue border-t-transparent rounded-full animate-spin shrink-0" />
        <p class="text-[12px] text-tinder-blue">{{ generatingLog }}</p>
      </div>
      <!-- Stats -->
      <div class="px-4 py-2 flex gap-4 border-b border-border">
        <span class="text-[12px] text-text-muted">原子 <span class="text-text-secondary font-medium">{{ atomCount }}</span></span>
        <span class="text-[12px] text-text-muted">草稿 <span class="text-text-secondary font-medium">{{ candidates.length }}</span></span>
      </div>
      <!-- Idea cards -->
      <div v-if="candidates.length === 0" class="flex flex-col items-center justify-center h-40 text-text-muted gap-2">
        <p class="text-sm">还没有草稿灵感</p>
        <p class="text-xs">点击右下角生成按钮</p>
      </div>
      <div
        v-for="idea in candidates"
        :key="idea.id"
        class="px-4 py-3.5 border-b border-border cursor-pointer active:bg-bg-hover"
        @click="router.push(`/idea/candidates/${idea.id}`)"
      >
        <div class="flex items-start gap-2 mb-1">
          <p class="text-[14px] font-semibold text-text-primary flex-1 line-clamp-2 leading-snug">{{ idea.title }}</p>
          <span v-if="idea.scores?.overall" class="shrink-0 text-[13px] font-bold" :class="scoreColor(idea.scores.overall)">{{ idea.scores.overall.toFixed(1) }}</span>
        </div>
        <p class="text-[12px] text-text-muted line-clamp-2 leading-relaxed">{{ idea.goal }}</p>
      </div>
    </div>
    <FloatingButton label="生成灵感" :disabled="generating" @click="doGenerate">
      <svg v-if="generating" class="animate-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
    </FloatingButton>
  </div>
</template>
