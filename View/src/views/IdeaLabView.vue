<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchIdeaCandidates,
  fetchIdeaStats,
  fetchIdeaAtom,
  fetchIdeaSourcePapers,
  fetchIdeaQuestion,
  createIdeaFeedback,
} from '../api'
import type { IdeaCandidate, IdeaAtom, IdeaSourcePaper, IdeaQuestion } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import IdeaSourcePaperCard from '../components/idea/IdeaSourcePaperCard.vue'
import IdeaDerivationBridge from '../components/idea/IdeaDerivationBridge.vue'
import IdeaProvenanceFlow from '../components/idea/IdeaProvenanceFlow.vue'
import { getStrategyLabel } from '../utils/strategyMeta'
import WorkbenchPageShell from '../components/workbench/WorkbenchPageShell.vue'

const router = useRouter()

// ── List data ──────────────────────────────────────────────────────
const candidates = ref<IdeaCandidate[]>([])
const loading = ref(false)
const error = ref('')
const statsData = ref<Record<string, any> | null>(null)

// ── Filters ────────────────────────────────────────────────────────
const searchQuery = ref('')
type Tab = 'all' | 'draft' | 'review' | 'approved' | 'archived' | 'implemented'
const activeTab = ref<Tab>('all')

const tabItems: { key: Tab; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'draft', label: '草稿' },
  { key: 'review', label: '评审中' },
  { key: 'approved', label: '已通过' },
  { key: 'archived', label: '已归档' },
  { key: 'implemented', label: '已落地' },
]

const filteredCandidates = computed(() => {
  let list = candidates.value
  if (activeTab.value !== 'all') {
    list = list.filter((c) => (c.status as string) === activeTab.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.goal.toLowerCase().includes(q) ||
        c.mechanism?.toLowerCase().includes(q) ||
        c.tags?.some((t) => t.toLowerCase().includes(q)),
    )
  }
  return list
})

const tabCounts = computed(() => {
  const counts: Record<string, number> = { all: candidates.value.length }
  for (const c of candidates.value) {
    const s = c.status as string
    counts[s] = (counts[s] || 0) + 1
  }
  return counts
})

// ── Selected candidate + provenance ────────────────────────────────
const selectedId = ref<number | null>(null)
const selectedAtoms = ref<IdeaAtom[]>([])
const atomsLoading = ref(false)
/** 来源论文元数据缓存：paper_id → IdeaSourcePaper */
const sourcePapersInfo = ref<Record<string, IdeaSourcePaper>>({})
const sourcePapersLoading = ref(false)
/** 当前候选关联的研究问题（含 question_text） */
const selectedQuestion = ref<IdeaQuestion | null>(null)
const questionLoading = ref(false)

const selectedCandidate = computed(() =>
  candidates.value.find((c) => c.id === selectedId.value) ?? null,
)

const sourcePapers = computed(() => {
  const seen = new Set<string>()
  const result: string[] = []
  for (const atom of selectedAtoms.value) {
    if (!seen.has(atom.paper_id)) {
      seen.add(atom.paper_id)
      result.push(atom.paper_id)
    }
  }
  return result
})

async function selectCandidate(id: number) {
  if (selectedId.value === id) return
  selectedId.value = id
  selectedAtoms.value = []
  sourcePapersInfo.value = {}
  selectedQuestion.value = null

  const cand = candidates.value.find((c) => c.id === id)
  if (!cand?.input_atom_ids?.length) return

  atomsLoading.value = true
  try {
    const results = await Promise.allSettled(
      cand.input_atom_ids.slice(0, 20).map((aid) => fetchIdeaAtom(aid).then((r) => r.atom)),
    )
    selectedAtoms.value = results
      .filter((r): r is PromiseFulfilledResult<IdeaAtom> => r.status === 'fulfilled')
      .map((r) => r.value)
  } finally {
    atomsLoading.value = false
  }

  // 原子加载完毕后，并行拉取：来源论文元数据 + 关联研究问题
  const uniquePaperIds = [...new Set(selectedAtoms.value.map((a) => a.paper_id).filter(Boolean))]

  await Promise.allSettled([
    // ① 来源论文标题
    (async () => {
      if (!uniquePaperIds.length) return
      sourcePapersLoading.value = true
      try {
        sourcePapersInfo.value = await fetchIdeaSourcePapers(uniquePaperIds)
      } catch {
        // 论文元数据加载失败不影响主流程
      } finally {
        sourcePapersLoading.value = false
      }
    })(),
    // ② 关联研究问题
    (async () => {
      if (!cand.question_id) return
      questionLoading.value = true
      try {
        const res = await fetchIdeaQuestion(cand.question_id)
        selectedQuestion.value = res.question
      } catch {
        // 问题加载失败不影响主流程
      } finally {
        questionLoading.value = false
      }
    })(),
  ])
}

watch([activeTab, searchQuery], () => {
  selectedId.value = null
  selectedAtoms.value = []
  sourcePapersInfo.value = {}
  selectedQuestion.value = null
})

// ── Data loading ───────────────────────────────────────────────────
async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidates({ limit: 500 })
    candidates.value = res.candidates
    if (res.candidates.length > 0 && selectedId.value === null) {
      void selectCandidate(res.candidates[0].id)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await fetchIdeaStats()
    statsData.value = res as any
  } catch {}
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) {
    await Promise.all([loadCandidates(), loadStats()])
  }
})

watch(() => isAuthenticated.value, (authed) => {
  if (authed) {
    loadCandidates()
    loadStats()
  } else {
    candidates.value = []
    statsData.value = null
    selectedId.value = null
    selectedAtoms.value = []
    selectedQuestion.value = null
  }
})

async function handleRefresh() {
  await loadCandidates()
  await loadStats()
}

// ── Actions ────────────────────────────────────────────────────────
function openCandidate(id: number) {
  router.push(`/idea/candidates/${id}`)
}

async function collectCandidate(id: number) {
  try {
    await createIdeaFeedback({ candidate_id: id, action: 'collect' })
  } catch {}
}

async function discardCandidate(id: number) {
  try {
    await createIdeaFeedback({ candidate_id: id, action: 'discard' })
    const idx = candidates.value.findIndex((c) => c.id === id)
    if (idx !== -1) {
      candidates.value.splice(idx, 1)
      if (selectedId.value === id) {
        const next = candidates.value[idx] ?? candidates.value[idx - 1] ?? null
        if (next) void selectCandidate(next.id)
        else { selectedId.value = null; selectedAtoms.value = []; sourcePapersInfo.value = {}; selectedQuestion.value = null }
      }
    }
  } catch {}
}

// ── Display helpers ────────────────────────────────────────────────
const statusLabel: Record<string, string> = {
  draft: '草稿', review: '评审中', approved: '已通过',
  published: '已发布', archived: '已归档', implemented: '已落地',
}
const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  review: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  approved: 'bg-green-500/15 text-green-400 border-green-500/30',
  published: 'bg-green-500/15 text-green-400 border-green-500/30',
  archived: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  implemented: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}
// strategy 中文标签：通过共享模块 getStrategyLabel 统一查询
const strategyLabel = new Proxy({} as Record<string, string>, {
  get: (_, key: string) => getStrategyLabel(key),
})
const atomTypeLabel: Record<string, string> = {
  claim: '论断', method: '方法', setup: '设置', limitation: '局限', tag: '标签',
}
const atomTypeIcon: Record<string, string> = {
  claim: '💬', method: '⚙️', setup: '📊', limitation: '⚠️', tag: '🏷️',
}

const pipelineSteps = [
  { icon: '📄', label: '知识库论文', desc: '将感兴趣的论文加入知识库，AI 读取全文内容。' },
  { icon: '🔬', label: '知识原子', desc: '从每篇论文提取核心论断、方法、实验设置与局限性。' },
  { icon: '❓', label: '研究问题', desc: '从局限和方法原子中生成尚未被解决的研究问题。' },
  { icon: '💡', label: '灵感候选', desc: '以迁移、缝合、修补等策略，组合原子并针对问题生成研究思路。' },
  { icon: '🔍', label: 'AI 评审', desc: '自动打新颖性、可行性、影响力评分，供人工参考筛选。' },
]

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch { return dateStr }
}

function scoreColorCls(v: number | null | undefined): string {
  if (v == null) return 'text-text-muted'
  if (v >= 8) return 'text-green-400'
  if (v >= 6) return 'text-yellow-400'
  return 'text-red-400'
}
</script>

<template>
  <WorkbenchPageShell icon="🧪" title="灵感工作台" compact>
    <template #title-extra>
      <span class="text-xs font-normal text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded-full border border-border">v2</span>
    </template>

    <template #subtitle>
      <div v-if="statsData" class="flex items-center gap-2.5 mb-2">
        <span class="text-xs text-text-muted">
          <span class="text-text-secondary font-semibold">{{ statsData.atom_count ?? 0 }}</span> 原子
        </span>
        <span class="text-text-muted opacity-40">·</span>
        <span class="text-xs text-text-muted">
          <span class="text-text-secondary font-semibold">{{ statsData.candidate_count ?? 0 }}</span> 灵感
        </span>
        <span class="text-text-muted opacity-40">·</span>
        <span class="text-xs text-text-muted">
          <span class="text-green-400 font-semibold">{{ statsData.published_count ?? 0 }}</span> 已通过
        </span>
        <span class="text-text-muted opacity-40">·</span>
        <span class="text-xs text-text-muted">
          <span class="text-purple-400 font-semibold">{{ statsData.exemplar_count ?? 0 }}</span> 范例
        </span>
      </div>
    </template>

    <template #header-right>
      <button
        class="shrink-0 px-3.5 py-1.5 rounded-full bg-brand-gradient text-white text-[11px] font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-1.5 disabled:opacity-50"
        :disabled="loading || !isAuthenticated"
        @click="handleRefresh"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
        </svg>
        更新候选
      </button>
    </template>

    <template #filters>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-0.5 overflow-x-auto no-scrollbar flex-1 min-w-0">
          <button
            v-for="tab in tabItems"
            :key="tab.key"
            class="shrink-0 text-xs px-2 py-1 rounded-full border transition-colors cursor-pointer"
            :class="activeTab === tab.key
              ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
              : 'bg-transparent text-text-muted border-transparent hover:text-text-secondary hover:bg-bg-hover'"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}<span v-if="tabCounts[tab.key]" class="ml-0.5 opacity-60">{{ tabCounts[tab.key] }}</span>
          </button>
        </div>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索候选..."
          class="shrink-0 w-32 px-2.5 py-1 text-xs rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light transition-colors"
        />
      </div>
    </template>

    <!-- ── Not authenticated ────────────────────────────────────── -->
    <div v-if="!isAuthenticated" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-4 text-center">
        <div class="w-14 h-14 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-2xl">🔒</div>
        <h3 class="text-sm font-semibold text-text-primary">登录后使用灵感工作台</h3>
        <p class="text-xs text-text-muted">灵感生成、评审、收藏等功能需要登录</p>
        <button
          class="px-5 py-2 rounded-full bg-brand-gradient text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="router.push('/login')"
        >去登录</button>
      </div>
    </div>

    <!-- ── Initial loading ──────────────────────────────────────── -->
    <div v-else-if="loading && candidates.length === 0" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">🧪</span>
        </div>
        <p class="text-sm text-text-muted">加载中...</p>
      </div>
    </div>

    <!-- ── Error ────────────────────────────────────────────────── -->
    <div v-else-if="error && candidates.length === 0" class="flex-1 flex items-center justify-center">
      <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">{{ error }}</div>
    </div>

    <!-- ── Main: list (left) + provenance panel (right) ─────────── -->
    <div v-else class="flex-1 flex overflow-hidden">

      <!-- § 候选列表 -->
      <div class="idea-list shrink-0 flex flex-col border-r border-border overflow-hidden">
        <!-- Empty -->
        <div v-if="filteredCandidates.length === 0" class="flex-1 flex flex-col items-center justify-center gap-3 px-4 text-center">
          <span class="text-4xl opacity-30">💡</span>
          <p class="text-xs text-text-muted">
            {{ candidates.length === 0 ? '还没有灵感候选' : '没有匹配的结果' }}
          </p>
          <button
            v-if="candidates.length === 0"
            class="text-xs px-4 py-1.5 rounded-full bg-brand-gradient text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="handleRefresh"
          >更新候选</button>
        </div>

        <!-- List -->
        <div v-else class="flex-1 overflow-y-auto scrollbar-thin">
          <button
            v-for="cand in filteredCandidates"
            :key="cand.id"
            class="w-full text-left px-3 py-3 border-b border-border transition-colors cursor-pointer focus:outline-none"
            :class="selectedId === cand.id
              ? 'bg-bg-elevated border-l-2 border-l-tinder-pink'
              : 'hover:bg-bg-hover border-l-2 border-l-transparent'"
            @click="selectCandidate(cand.id)"
          >
            <div class="flex items-start gap-1.5 mb-0.5">
              <p class="flex-1 text-[12px] font-semibold text-text-primary leading-snug line-clamp-2">{{ cand.title }}</p>
              <span
                v-if="cand.scores?.overall != null"
                class="shrink-0 text-[11px] font-bold leading-none mt-0.5"
                :class="scoreColorCls(cand.scores.overall)"
              >{{ cand.scores.overall.toFixed(1) }}</span>
            </div>
            <!-- Goal preview: gives immediate context without opening detail -->
            <p v-if="cand.goal" class="text-[11px] text-text-muted leading-snug line-clamp-1 mb-1.5 opacity-75">{{ cand.goal }}</p>
            <div class="flex items-center gap-1 flex-wrap">
              <span
                v-if="cand.strategy"
                class="text-[10px] px-1.5 py-0.5 rounded-full bg-tinder-pink/10 text-tinder-pink border border-tinder-pink/20"
              >{{ strategyLabel[cand.strategy] || cand.strategy }}</span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded-full border"
                :class="statusColor[cand.status as string] || 'bg-bg-elevated text-text-muted border-border'"
              >{{ statusLabel[cand.status as string] || cand.status }}</span>
              <span class="text-[10px] text-text-muted">{{ cand.input_atom_ids?.length ?? 0 }} 原子</span>
            </div>
          </button>
        </div>
      </div>

      <!-- § 溯源面板 (右栏) -->
      <div class="flex-1 min-w-0 flex flex-col overflow-hidden">

        <!-- Intro: 未选中候选时展示流程说明 -->
        <div v-if="!selectedCandidate" class="flex-1 overflow-y-auto p-5 sm:p-6">
          <div class="max-w-xl">
            <p class="wb-section-title mb-4">灵感是如何生成的</p>
            <div class="flex items-start gap-2 mb-6 flex-wrap">
              <template v-for="(step, i) in pipelineSteps" :key="step.label">
                <div class="flex flex-col items-center gap-1.5 min-w-[56px]">
                  <div class="w-9 h-9 rounded-xl border border-border bg-bg-elevated flex items-center justify-center text-lg shrink-0">{{ step.icon }}</div>
                  <span class="text-[10px] text-text-muted text-center leading-tight">{{ step.label }}</span>
                </div>
                <span v-if="i < pipelineSteps.length - 1" class="text-text-muted text-xs self-start mt-2.5 shrink-0">→</span>
              </template>
            </div>
            <div class="space-y-3.5">
              <div v-for="step in pipelineSteps" :key="step.label + '-desc'" class="flex gap-3 items-start">
                <span class="shrink-0 text-base">{{ step.icon }}</span>
                <div>
                  <p class="text-xs font-semibold text-text-secondary mb-0.5">{{ step.label }}</p>
                  <p class="text-xs text-text-muted leading-relaxed">{{ step.desc }}</p>
                </div>
              </div>
            </div>
            <p v-if="filteredCandidates.length > 0" class="mt-6 text-xs text-text-muted">
              ← 从左侧列表选择一条灵感，查看完整来源解释。
            </p>
          </div>
        </div>

        <!-- Detail: 候选已选中 -->
        <template v-else>
          <!-- 候选标题 + 元数据 header -->
          <div class="shrink-0 px-4 sm:px-5 py-3 border-b border-border flex items-start gap-3">
            <div class="flex-1 min-w-0">
              <h2 class="text-sm font-bold text-text-primary leading-snug mb-1.5">{{ selectedCandidate.title }}</h2>
              <div class="flex items-center gap-1.5 flex-wrap">
                <span
                  v-if="selectedCandidate.strategy"
                  class="text-xs px-2 py-0.5 rounded-full bg-tinder-pink/10 text-tinder-pink border border-tinder-pink/20"
                >{{ strategyLabel[selectedCandidate.strategy] || selectedCandidate.strategy }}</span>
                <span
                  class="text-xs px-2 py-0.5 rounded-full border"
                  :class="statusColor[selectedCandidate.status as string] || 'bg-bg-elevated text-text-muted border-border'"
                >{{ statusLabel[selectedCandidate.status as string] || selectedCandidate.status }}</span>
                <span class="text-xs text-text-muted">{{ formatDate(selectedCandidate.created_at) }}</span>
              </div>
            </div>
            <div
              v-if="selectedCandidate.scores?.overall != null"
              class="shrink-0 w-10 h-10 rounded-full border-2 bg-bg-elevated flex items-center justify-center text-xs font-bold"
              :class="selectedCandidate.scores.overall >= 8
                ? 'border-green-500/50 text-green-400'
                : selectedCandidate.scores.overall >= 6
                  ? 'border-yellow-500/50 text-yellow-400'
                  : 'border-gray-500/30 text-text-muted'"
            >{{ selectedCandidate.scores.overall.toFixed(1) }}</div>
          </div>

          <!-- 溯源内容（可滚动） -->
          <div class="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-5 scrollbar-thin">

            <IdeaProvenanceFlow
              :candidate="selectedCandidate"
              :atoms="selectedAtoms"
              :question="selectedQuestion"
              :question-loading="questionLoading"
              :source-papers="sourcePapers"
              :source-papers-info="sourcePapersInfo"
              :source-papers-loading="sourcePapersLoading"
            />

            <section>
              <p class="wb-section-title">📄 来源论文</p>
              <div v-if="atomsLoading" class="flex items-center gap-2 text-xs text-text-muted">
                <div class="w-3 h-3 rounded-full border-2 border-border-light border-t-tinder-pink animate-spin shrink-0" />
                加载来源原子中...
              </div>
              <div v-else-if="sourcePapers.length === 0" class="text-xs text-text-muted italic">
                暂无来源论文信息
              </div>
              <div v-else class="space-y-2">
                <IdeaSourcePaperCard
                  v-for="pid in sourcePapers"
                  :key="pid"
                  :paper-id="pid"
                  :paper-info="sourcePapersInfo[pid] ?? null"
                  :related-atoms="selectedAtoms.filter((a) => a.paper_id === pid)"
                  :loading="sourcePapersLoading"
                />
              </div>
            </section>

            <IdeaDerivationBridge
              v-if="!atomsLoading && selectedAtoms.length > 0"
              :candidate="selectedCandidate"
              :atoms="selectedAtoms"
            />

            <section>
              <p class="wb-section-title">💡 我们的研究方向</p>
              <div class="space-y-2">
                <div v-if="selectedCandidate.goal" class="bg-bg-card border border-border rounded-lg p-3.5">
                  <p class="text-xs font-semibold text-tinder-blue mb-1.5">🎯 研究目标</p>
                  <p class="text-sm text-text-secondary leading-relaxed">{{ selectedCandidate.goal }}</p>
                </div>
                <div v-if="selectedCandidate.mechanism" class="bg-bg-card border border-border rounded-lg p-3.5">
                  <p class="text-xs font-semibold text-tinder-blue mb-1.5">⚙️ 核心机制</p>
                  <p class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">{{ selectedCandidate.mechanism }}</p>
                </div>
              </div>
            </section>

            <section>
              <p class="wb-section-title">📊 评分</p>
              <div v-if="selectedCandidate.scores" class="grid grid-cols-4 gap-1.5 mb-3">
                <div
                  v-for="(label, key) in { overall: '综合', novelty: '新颖', feasibility: '可行', impact: '影响' }"
                  :key="key"
                  class="bg-bg-card border border-border rounded-lg p-2 text-center"
                >
                  <div
                    class="text-sm font-bold"
                    :class="scoreColorCls((selectedCandidate.scores as any)[key])"
                  >{{ (selectedCandidate.scores as any)[key]?.toFixed(1) ?? '—' }}</div>
                  <div class="text-[10px] text-text-muted mt-0.5">{{ label }}</div>
                </div>
              </div>
              <div v-if="selectedCandidate.evidence?.length" class="space-y-1.5">
                <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-1">综合支持证据</p>
                <div
                  v-for="(ev, i) in selectedCandidate.evidence.slice(0, 3)"
                  :key="i"
                  class="flex items-start gap-2 px-3 py-2 bg-bg-card border border-border rounded-lg"
                >
                  <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-gold mt-1.5" />
                  <div class="flex-1 min-w-0">
                    <p v-if="ev.location" class="text-xs text-text-muted mb-0.5">{{ ev.location }}</p>
                    <p class="text-xs text-text-secondary leading-relaxed">{{ ev.text }}</p>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="selectedCandidate.tags?.length">
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="tag in selectedCandidate.tags"
                  :key="tag"
                  class="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted"
                >{{ tag }}</span>
              </div>
            </section>

          </div>

          <!-- § 决策动作栏 -->
          <div class="shrink-0 px-4 py-3 border-t border-border bg-bg-card/60 flex items-center gap-2 flex-wrap">
            <button
              class="text-xs px-3.5 py-1.5 rounded-full border border-border bg-bg-elevated text-text-secondary cursor-pointer hover:border-border-light hover:bg-bg-hover transition-colors"
              @click="openCandidate(selectedCandidate.id)"
            >📋 查看详情</button>
            <button
              class="text-xs px-3.5 py-1.5 rounded-full border border-green-500/30 bg-green-500/10 text-green-400 cursor-pointer hover:bg-green-500/20 transition-colors"
              @click="collectCandidate(selectedCandidate.id)"
            >❤️ 收藏</button>
            <button
              class="text-xs px-3.5 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-red-400 hover:border-red-500/30 hover:bg-red-500/10 transition-colors"
              @click="discardCandidate(selectedCandidate.id)"
            >🗑 丢弃</button>
            <span class="ml-auto text-xs text-text-muted">
              {{ selectedCandidate.input_atom_ids?.length ?? 0 }} 原子 · {{ formatDate(selectedCandidate.created_at) }}
            </span>
          </div>
        </template>
      </div>
    </div>

  </WorkbenchPageShell>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

.scrollbar-thin {
  scrollbar-width: thin;
  scrollbar-color: var(--color-border-light) transparent;
}
.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: var(--color-border-light); border-radius: 2px; }

/* Candidate list column width — responsive */
.idea-list {
  width: clamp(200px, 26vw, 300px);
}

/* Narrow workbench viewport: shrink list column so detail panel stays readable */
@media (max-width: 768px) {
  .idea-list {
    width: clamp(150px, 30vw, 220px);
  }
}
</style>
