<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import FloatingButton from '@/components/FloatingButton.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import { fetchIdeaCandidates, fetchIdeaStats, generateIdeasStream } from '@shared/api'
import type { IdeaCandidate } from '@shared/types/idea'
import { showToast } from 'vant'

defineOptions({ name: 'IdeaView' })

const router = useRouter()

const candidates = ref<IdeaCandidate[]>([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')
const activeTab = ref<'all' | 'draft' | 'published' | 'archived'>('all')
const statsLoaded = ref(false)
const atomCount = ref(0)
const generating = ref(false)
const generateSheetVisible = ref(false)
const generateLog = ref('')

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  review: '审阅中',
  published: '已发布',
  archived: '已归档',
}
const STATUS_COLOR: Record<string, string> = {
  draft: 'text-tinder-gold',
  review: 'text-tinder-blue',
  published: 'text-tinder-green',
  archived: 'text-text-muted',
}

async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    const [res, stats] = await Promise.all([
      fetchIdeaCandidates({ limit: 100 }),
      fetchIdeaStats(),
    ])
    candidates.value = res.candidates
    atomCount.value = stats.atom_count
    statsLoaded.value = true
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadCandidates)

const filtered = computed(() => {
  let list = candidates.value
  if (activeTab.value !== 'all') {
    list = list.filter((c) => c.status === activeTab.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.goal.toLowerCase().includes(q),
    )
  }
  return list
})

const tabCounts = computed(() => ({
  all: candidates.value.length,
  draft: candidates.value.filter((c) => c.status === 'draft').length,
  published: candidates.value.filter((c) => c.status === 'published').length,
  archived: candidates.value.filter((c) => c.status === 'archived').length,
}))

function scoreColor(score?: number) {
  if (score === undefined || score === null) return 'text-text-muted'
  if (score >= 7) return 'text-tinder-green'
  if (score >= 5) return 'text-tinder-gold'
  return 'text-tinder-pink'
}

async function doGenerate() {
  if (generating.value) return
  if (atomCount.value === 0) {
    showToast('需要先在知识库中收藏一些论文')
    return
  }
  generateSheetVisible.value = true
  generating.value = true
  generateLog.value = '正在连接…'
  try {
    const response = await generateIdeasStream({})
    if (!response.ok) {
      generateLog.value = '生成失败，请重试'
      return
    }
    const reader = response.body?.getReader()
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
            if (obj.log) generateLog.value = obj.log
            if (obj.message) generateLog.value = obj.message
          } catch {
            // ignore parse errors
          }
        }
      }
    }
    generateLog.value = '生成完成！'
    await loadCandidates()
  } catch (e: any) {
    generateLog.value = `出错了：${e?.message || '未知错误'}`
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader title="灵感">
      <template #right>
        <button
          type="button"
          class="top-nav-btn"
          aria-label="生成设置"
          @click="router.push({ name: 'idea-generate-settings' })"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <button
          type="button"
          class="top-nav-btn"
          aria-label="灵感工作台"
          @click="router.push('/workbench')"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <!-- Search -->
    <div class="px-4 pb-2 shrink-0">
      <SearchBar v-model="searchQuery" placeholder="搜索灵感标题、目标…" />
    </div>

    <!-- Tabs -->
    <div class="tab-underline shrink-0 mx-4">
      <button
        v-for="tab in (['all', 'draft', 'published', 'archived'] as const)"
        :key="tab"
        type="button"
        class="tab-underline-item"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ tab === 'all' ? '全部' : STATUS_LABEL[tab] }}
        <span v-if="tabCounts[tab] > 0" class="ml-1 text-[11px] opacity-60">{{ tabCounts[tab] }}</span>
      </button>
    </div>

    <!-- Loading -->
    <LoadingState v-if="loading" class="flex-1" message="加载灵感库…" />

    <!-- Error -->
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadCandidates" />

    <!-- Content -->
    <div v-else class="flex-1 overflow-y-auto">
      <!-- Stats hint (when empty and no atoms yet) -->
      <div v-if="statsLoaded && atomCount === 0 && candidates.length === 0" class="p-4">
        <EmptyState
          title="灵感库还是空的"
          description="先去推荐页收藏论文到知识库，系统会自动提取灵感原子，然后你可以生成研究灵感。"
        />
        <button type="button" class="btn-primary mt-4" @click="router.push('/recommend')">
          去看今日推荐
        </button>
      </div>

      <!-- Has atoms but no candidates -->
      <div v-else-if="filtered.length === 0 && candidates.length === 0" class="p-4">
        <EmptyState
          title="还没有灵感候选"
          description="点击右下角按钮，基于知识库中的论文生成研究灵感。"
        />
      </div>

      <!-- Search empty -->
      <div v-else-if="filtered.length === 0" class="flex flex-col items-center justify-center h-40 text-text-muted">
        <p class="text-sm">没有匹配的结果</p>
      </div>

      <!-- Idea list -->
      <div v-else class="pb-6">
        <!-- Stats bar -->
        <div v-if="statsLoaded" class="px-4 py-2 flex gap-4">
          <div class="text-[12px] text-text-muted">
            共 <span class="text-text-secondary font-medium">{{ candidates.length }}</span> 个灵感
          </div>
          <div class="text-[12px] text-text-muted">
            知识原子 <span class="text-text-secondary font-medium">{{ atomCount }}</span>
          </div>
        </div>

        <!-- Cards -->
        <div
          v-for="idea in filtered"
          :key="idea.id"
          class="mx-4 mb-3 card-section cursor-pointer active:scale-[0.99] transition-transform"
          @click="router.push(`/idea/candidates/${idea.id}`)"
        >
          <!-- Status + Score row -->
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] font-semibold uppercase tracking-wider" :class="STATUS_COLOR[idea.status]">
              {{ STATUS_LABEL[idea.status] ?? idea.status }}
            </span>
            <div v-if="idea.scores?.overall !== undefined" class="flex items-center gap-1">
              <span class="text-[12px] font-bold" :class="scoreColor(idea.scores.overall)">
                {{ idea.scores.overall.toFixed(1) }}
              </span>
              <span class="text-[10px] text-text-muted">/ 10</span>
            </div>
          </div>

          <!-- Title -->
          <h3 class="text-[14px] font-semibold text-text-primary line-clamp-2 leading-snug mb-2">
            {{ idea.title }}
          </h3>

          <!-- Goal preview -->
          <p class="text-[12px] text-text-secondary line-clamp-2 leading-relaxed mb-3">
            {{ idea.goal }}
          </p>

          <!-- Score breakdown + date -->
          <div class="flex items-center gap-3 flex-wrap">
            <div v-for="(key, label) in { '新颖': 'novelty', '可行': 'feasibility', '影响': 'impact' }" :key="key" class="flex items-center gap-1">
              <span class="text-[10px] text-text-muted">{{ label }}</span>
              <span class="text-[11px] font-medium" :class="scoreColor(idea.scores?.[key])">
                {{ idea.scores?.[key]?.toFixed(1) ?? '-' }}
              </span>
            </div>
            <span class="ml-auto text-[11px] text-text-muted">
              {{ new Date(idea.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- FAB: generate -->
    <FloatingButton
      label="生成新灵感"
      :disabled="generating"
      :style="{ bottom: 'calc(max(16px, env(safe-area-inset-bottom, 16px)) + 8px)' }"
      @click="doGenerate"
    />

    <!-- Generate progress sheet -->
    <BottomSheet
      :visible="generateSheetVisible"
      title="生成灵感"
      @close="!generating && (generateSheetVisible = false)"
    >
      <div class="px-5 py-4 flex flex-col items-center gap-4 min-h-[160px]">
        <div v-if="generating" class="w-8 h-8 border-2 border-tinder-pink border-t-transparent rounded-full animate-spin" />
        <svg v-else class="text-tinder-green" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
        <p class="text-[14px] text-text-secondary text-center leading-relaxed">{{ generateLog }}</p>
        <button
          v-if="!generating"
          type="button"
          class="btn-primary"
          @click="generateSheetVisible = false"
        >
          完成
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
