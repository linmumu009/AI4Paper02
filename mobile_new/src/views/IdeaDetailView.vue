<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import {
  fetchIdeaCandidate,
  fetchIdeaAtom,
  updateIdeaCandidate,
  createIdeaFeedback,
} from '@shared/api'
import type { IdeaCandidate, IdeaAtom } from '@shared/types/idea'
import { showToast } from 'vant'

const props = defineProps<{ id: string }>()
const router = useRouter()

const candidate = ref<IdeaCandidate | null>(null)
const atoms = ref<IdeaAtom[]>([])
const loading = ref(true)
const error = ref('')

// Review sheet
const reviewSheetVisible = ref(false)
const reviewAction = ref<'collect' | 'discard'>('collect')
const submitting = ref(false)

// Collapsible sections
const mechanismOpen = ref(false)
const risksOpen = ref(false)
const evidenceOpen = ref(false)
const historyOpen = ref(false)

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿', review: '审阅中', published: '已发布', archived: '已归档',
}
const STATUS_COLOR: Record<string, string> = {
  draft: 'text-tinder-gold bg-tinder-gold/10',
  review: 'text-tinder-blue bg-tinder-blue/10',
  published: 'text-tinder-green bg-tinder-green/10',
  archived: 'text-text-muted bg-bg-elevated',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidate(Number(props.id))
    candidate.value = res.candidate
    if (res.candidate.input_atom_ids?.length) {
      const results = await Promise.allSettled(
        res.candidate.input_atom_ids.slice(0, 10).map((id) => fetchIdeaAtom(id)),
      )
      atoms.value = results
        .filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled')
        .map((r) => r.value.atom)
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function scoreColor(score?: number) {
  if (score === undefined || score === null) return 'text-text-muted'
  if (score >= 7) return 'text-tinder-green'
  if (score >= 5) return 'text-tinder-gold'
  return 'text-tinder-pink'
}

const overallScore = computed(() => candidate.value?.scores?.overall)

async function submitAction(action: 'collect' | 'discard') {
  if (!candidate.value) return
  submitting.value = true
  try {
    await createIdeaFeedback({ candidate_id: candidate.value.id, action, context: {} })
    if (action === 'collect') {
      await updateIdeaCandidate(candidate.value.id, { status: 'published' })
      candidate.value.status = 'published'
      showToast('已收藏到灵感库')
    } else {
      await updateIdeaCandidate(candidate.value.id, { status: 'archived' })
      candidate.value.status = 'archived'
      showToast('已归档')
    }
    reviewSheetVisible.value = false
  } catch {
    showToast('操作失败，请重试')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader :title="candidate?.title ?? '灵感详情'" glass @back="router.back()" />

    <!-- Loading -->
    <LoadingState v-if="loading" class="flex-1" message="加载中…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else-if="candidate">
      <div class="flex-1 overflow-y-auto pb-28">
        <div class="px-4 pt-2 pb-4 space-y-4">

          <!-- Title + status -->
          <div>
            <div class="flex items-start justify-between gap-2 mb-2">
              <h1 class="text-[17px] font-bold text-text-primary leading-snug flex-1">
                {{ candidate.title }}
              </h1>
              <span
                class="shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full"
                :class="STATUS_COLOR[candidate.status] ?? 'text-text-muted bg-bg-elevated'"
              >
                {{ STATUS_LABEL[candidate.status] ?? candidate.status }}
              </span>
            </div>
            <p class="text-[11px] text-text-muted">
              {{ new Date(candidate.created_at).toLocaleDateString('zh-CN') }}
            </p>
          </div>

          <!-- Score cards -->
          <div v-if="candidate.scores" class="grid grid-cols-4 gap-2">
            <div
              v-for="(key, label) in { '综合': 'overall', '新颖': 'novelty', '可行': 'feasibility', '影响': 'impact' }"
              :key="key"
              class="flex flex-col items-center gap-1 p-2.5 rounded-xl bg-bg-elevated border border-border"
            >
              <span class="text-[18px] font-bold" :class="scoreColor(candidate.scores[key])">
                {{ candidate.scores[key]?.toFixed(1) ?? '-' }}
              </span>
              <span class="text-[10px] text-text-muted">{{ label }}</span>
            </div>
          </div>

          <!-- Goal -->
          <div class="card-section">
            <p class="section-title">研究目标</p>
            <p class="section-body">{{ candidate.goal }}</p>
          </div>

          <!-- Mechanism (collapsible) -->
          <div class="card-section">
            <button type="button" class="collapsible-trigger" @click="mechanismOpen = !mechanismOpen">
              <span class="section-title mb-0">技术机制</span>
              <svg class="text-text-muted transition-transform" :class="mechanismOpen ? 'rotate-180' : ''" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div v-if="mechanismOpen" class="mt-3">
              <p class="section-body whitespace-pre-line">{{ candidate.mechanism }}</p>
            </div>
          </div>

          <!-- Risks (collapsible) -->
          <div v-if="candidate.risks" class="card-section">
            <button type="button" class="collapsible-trigger" @click="risksOpen = !risksOpen">
              <span class="section-title mb-0 text-tinder-pink">风险分析</span>
              <svg class="text-text-muted transition-transform" :class="risksOpen ? 'rotate-180' : ''" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div v-if="risksOpen" class="mt-3">
              <p class="section-body whitespace-pre-line">{{ candidate.risks }}</p>
            </div>
          </div>

          <!-- Evidence (collapsible) -->
          <div v-if="candidate.evidence?.length" class="card-section">
            <button type="button" class="collapsible-trigger" @click="evidenceOpen = !evidenceOpen">
              <span class="section-title mb-0">支撑证据 ({{ candidate.evidence.length }})</span>
              <svg class="text-text-muted transition-transform" :class="evidenceOpen ? 'rotate-180' : ''" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div v-if="evidenceOpen" class="mt-3 space-y-2">
              <div v-for="(ev, i) in candidate.evidence" :key="i" class="p-3 rounded-lg bg-bg border border-border">
                <p class="text-[12px] text-text-secondary leading-relaxed">{{ ev.text }}</p>
                <p v-if="ev.location" class="text-[10px] text-text-muted mt-1">{{ ev.location }}</p>
              </div>
            </div>
          </div>

          <!-- Source atoms -->
          <div v-if="atoms.length" class="card-section">
            <p class="section-title">来源论文原子 ({{ atoms.length }})</p>
            <div class="space-y-2 mt-2">
              <div v-for="atom in atoms" :key="atom.id" class="p-3 rounded-lg bg-bg border border-border">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-[10px] font-semibold uppercase tracking-wider text-tinder-blue">{{ atom.atom_type }}</span>
                  <span class="text-[10px] text-text-muted">{{ atom.section }}</span>
                </div>
                <p class="text-[12px] text-text-secondary leading-relaxed line-clamp-2">{{ atom.content }}</p>
              </div>
            </div>
          </div>

          <!-- Tags -->
          <div v-if="candidate.tags?.length" class="flex flex-wrap gap-2">
            <span
              v-for="tag in candidate.tags"
              :key="tag"
              class="text-[11px] px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-secondary"
            >
              #{{ tag }}
            </span>
          </div>

          <!-- Revision history (collapsible) -->
          <div v-if="candidate.revision_history?.length" class="card-section">
            <button type="button" class="collapsible-trigger" @click="historyOpen = !historyOpen">
              <span class="section-title mb-0">修订历史 ({{ candidate.revision_history.length }})</span>
              <svg class="text-text-muted transition-transform" :class="historyOpen ? 'rotate-180' : ''" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            <div v-if="historyOpen" class="mt-3 space-y-2">
              <div v-for="(entry, i) in candidate.revision_history" :key="i" class="p-3 rounded-lg bg-bg border border-border">
                <p class="text-[11px] font-semibold text-text-secondary mb-1">{{ entry.type }}</p>
                <p v-if="entry.summary" class="text-[12px] text-text-muted">{{ entry.summary }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom action bar -->
      <div
        class="shrink-0 px-4 pt-3 border-t border-border bg-bg-card"
        style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px));"
      >
        <div class="flex gap-3">
          <button
            type="button"
            class="flex-1 py-3 rounded-2xl bg-bg-elevated border border-border text-text-secondary font-medium text-[14px] active:bg-bg-hover"
            @click="reviewAction = 'discard'; reviewSheetVisible = true"
          >
            归档
          </button>
          <button
            type="button"
            class="flex-2 flex-grow-[2] py-3 rounded-2xl font-semibold text-[14px] text-white active:opacity-80"
            style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
            @click="reviewAction = 'collect'; reviewSheetVisible = true"
          >
            收藏到灵感库
          </button>
        </div>
      </div>
    </template>

    <!-- Review confirm sheet -->
    <BottomSheet
      :visible="reviewSheetVisible"
      :title="reviewAction === 'collect' ? '收藏这个灵感？' : '归档这个灵感？'"
      @close="reviewSheetVisible = false"
    >
      <div class="px-5 py-4 flex flex-col gap-4">
        <p class="text-[13px] text-text-secondary leading-relaxed">
          <template v-if="reviewAction === 'collect'">
            将该灵感状态更新为「已发布」，并记录收藏反馈。
          </template>
          <template v-else>
            将该灵感归档，不影响原始数据。
          </template>
        </p>
        <button
          type="button"
          class="btn-primary"
          :disabled="submitting"
          @click="submitAction(reviewAction)"
        >
          {{ submitting ? '处理中…' : '确认' }}
        </button>
        <button type="button" class="btn-ghost" @click="reviewSheetVisible = false">取消</button>
      </div>
    </BottomSheet>
  </div>
</template>
