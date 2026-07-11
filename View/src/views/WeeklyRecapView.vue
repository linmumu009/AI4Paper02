<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchCurrentRecap,
  generateRecap,
  fetchRecapHistory,
  type WeeklyRecapResponse,
  type RecapPaperSummary,
  type RecapHistoryItem,
} from '@shared/api/recap'
import { deriveResearchOutcomes } from '@shared/composables/useResearchOutcome'
import { trackEvent } from '../composables/useAnalytics'

defineOptions({ name: 'WeeklyRecapView' })

const router = useRouter()
const showSidebar = ref(true)

const loading = ref(false)
const generating = ref(false)
const error = ref('')
const recap = ref<WeeklyRecapResponse | null>(null)
const history = ref<RecapHistoryItem[]>([])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [recapResult, historyResult] = await Promise.allSettled([
      fetchCurrentRecap(),
      fetchRecapHistory(12),
    ])
    if (recapResult.status === 'fulfilled') recap.value = recapResult.value
    else error.value = (recapResult.reason as any)?.message || '加载失败'
    if (historyResult.status === 'fulfilled') history.value = historyResult.value.recaps
    trackEvent('recap_view', { targetType: 'recap', meta: { status: recap.value?.status } })
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  error.value = ''
  try {
    recap.value = await generateRecap()
    // Reload history so the new recap is reflected in outcomes
    try {
      const h = await fetchRecapHistory(12)
      history.value = h.recaps
    } catch { /* best-effort */ }
    trackEvent('recap_generate', { targetType: 'recap' })
  } catch (e: any) {
    error.value = e?.message || '生成失败'
  } finally {
    generating.value = false
  }
}

onMounted(load)

function goToPaper(paperId: string) {
  trackEvent('recap_paper_click', { targetType: 'paper', targetId: paperId })
  router.push(`/papers/${paperId}`)
}

const weekLabel = computed(() => {
  if (!recap.value) return ''
  const s = recap.value.week_start
  const e = recap.value.week_end
  if (!s) return ''
  const startDate = new Date(s)
  const endDate = new Date(e)
  const fmt = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`
  return `${fmt(startDate)} – ${fmt(endDate)}`
})

const paperMap = computed<Record<string, RecapPaperSummary>>(() => {
  if (!recap.value) return {}
  const map: Record<string, RecapPaperSummary> = {}
  for (const p of recap.value.papers) {
    map[p.paper_id] = p
  }
  return map
})

function paperTitle(pid: string): string {
  const p = paperMap.value[pid]
  if (!p) return pid
  return p.title || p.title_en || pid
}

const outcomes = computed(() => deriveResearchOutcomes(history.value))

// Expanded state for collapsible outcome sections
const trendExpanded = ref(true)
const evolutionExpanded = ref(true)
</script>

<template>
  <div class="h-full flex overflow-hidden relative">

    <!-- Mobile overlay -->
    <div v-if="showSidebar" class="fixed inset-0 bg-black/50 z-20 lg:hidden" @click="showSidebar = false" />

    <!-- ===================== Sidebar ===================== -->
    <aside
      class="w-[80vw] max-w-[300px] lg:w-[var(--sidebar-w)] shrink-0 bg-bg-sidebar border-r border-border flex flex-col z-30 transition-transform duration-200 lg:relative lg:translate-x-0"
      :class="showSidebar ? 'fixed inset-y-0 left-0 translate-x-0' : 'fixed inset-y-0 left-0 -translate-x-full'"
    >
      <div class="shrink-0 px-4 py-3 border-b border-border flex items-center gap-2">
        <button
          type="button"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-bg-elevated transition-colors shrink-0 cursor-pointer"
          aria-label="返回"
          @click="router.back()"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <div class="flex-1 min-w-0">
          <h2 class="text-sm font-bold text-text-primary truncate">本周回顾</h2>
          <p v-if="weekLabel" class="text-xs text-text-muted">{{ weekLabel }}</p>
        </div>
        <!-- Collapse sidebar button (desktop) -->
        <button
          type="button"
          class="hidden lg:flex w-7 h-7 items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-bg-elevated transition-colors shrink-0 cursor-pointer"
          title="收起侧边栏"
          @click="showSidebar = false"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
          </svg>
        </button>
      </div>

      <!-- Paper list for the week -->
      <nav class="flex-1 overflow-y-auto py-2">
        <div v-if="recap?.papers?.length" class="px-2 space-y-0.5">
          <div class="px-3 pt-2 pb-1 text-[10.5px] font-semibold tracking-widest uppercase text-text-muted select-none">
            本周收藏 ({{ recap.papers.length }} 篇)
          </div>
          <button
            v-for="p in recap.papers"
            :key="p.paper_id"
            type="button"
            class="w-full text-left px-3 py-2 text-xs transition-colors flex items-start gap-2 bg-transparent border-none cursor-pointer rounded-lg hover:bg-bg-hover hover:text-text-primary text-text-secondary"
            @click="goToPaper(p.paper_id)"
          >
            <svg class="w-3 h-3 shrink-0 mt-0.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            <span class="line-clamp-2 leading-snug">{{ p.title || p.title_en || p.paper_id }}</span>
          </button>
        </div>
        <div v-else-if="!loading && !recap?.papers?.length" class="px-4 py-8 text-center text-xs text-text-muted">
          本周暂无收藏论文
        </div>
      </nav>
    </aside>

    <!-- Open sidebar button (desktop, when collapsed) -->
    <button
      v-if="!showSidebar"
      class="fixed top-[calc(var(--navbar-h)+2.5rem)] left-0 z-10 flex items-center justify-center w-[54px] h-[54px] bg-bg-card border border-border border-l-0 rounded-r-lg shadow-sm text-text-muted/60 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
      title="展开侧边栏"
      @click="showSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>
      </svg>
    </button>

    <!-- Mobile toggle -->
    <button
      v-if="!showSidebar"
      class="fixed top-[calc(var(--navbar-h)+1rem)] left-0 z-20 bg-bg-card border border-border border-l-0 rounded-r-lg px-1.5 py-2 text-text-muted hover:text-text-primary transition-colors lg:hidden cursor-pointer"
      @click="showSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>

    <!-- ===================== Main content ===================== -->
    <div class="flex-1 h-full overflow-y-auto min-w-0">
    <div class="max-w-3xl mx-auto px-4 py-8">

      <!-- Header -->
      <div class="flex items-center gap-3 mb-8">
        <div class="flex-1 min-w-0">
          <h1 class="text-xl font-bold text-text-primary">本周回顾</h1>
          <p v-if="weekLabel" class="text-xs text-text-muted mt-0.5">{{ weekLabel }}</p>
        </div>
        <button
          v-if="!loading && !generating"
          type="button"
          class="text-sm text-text-muted hover:text-text-secondary px-3 py-1.5 rounded-lg bg-bg-elevated border border-border transition-colors"
          @click="generate"
        >
          刷新 / 重新生成
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-24">
        <div class="w-6 h-6 rounded-full border-2 border-tinder-pink border-t-transparent animate-spin" />
      </div>

      <!-- Generating -->
      <div v-else-if="generating" class="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <div class="w-10 h-10 rounded-full border-2 border-tinder-purple border-t-transparent animate-spin" />
        <p class="text-sm text-text-muted">AI 正在整理本周研究脉络…</p>
        <p class="text-xs text-text-muted opacity-60">通常需要 10–30 秒</p>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center gap-4 py-24 text-center">
        <div class="w-12 h-12 rounded-full bg-tinder-pink/10 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" class="text-tinder-pink">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <p class="text-sm text-text-primary font-medium">{{ error }}</p>
        <button type="button" class="px-4 py-2 rounded-lg bg-tinder-pink/10 text-tinder-pink text-sm font-medium hover:bg-tinder-pink/20 transition-colors" @click="load">重试</button>
      </div>

      <!-- Insufficient papers -->
      <div v-else-if="recap?.status === 'insufficient_papers'" class="flex flex-col items-center gap-5 py-24 text-center">
        <div class="w-16 h-16 rounded-2xl bg-bg-elevated border border-border flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        </div>
        <div>
          <h2 class="text-lg font-bold text-text-primary mb-1">本周收藏还不够</h2>
          <p class="text-sm text-text-muted leading-relaxed">
            至少收藏 3 篇论文才能生成本周研究脉络。<br>目前已收藏 {{ recap.paper_count }} 篇。
          </p>
        </div>
        <button type="button" class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-sm text-text-secondary hover:text-text-primary transition-colors" @click="router.push('/')">去发现论文</button>
      </div>

      <!-- No LLM config -->
      <div v-else-if="recap?.status === 'no_llm_config'" class="flex flex-col items-center gap-5 py-24 text-center">
        <div class="w-16 h-16 rounded-2xl bg-bg-elevated border border-border flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="1.5" class="text-tinder-purple">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div>
          <h2 class="text-lg font-bold text-text-primary mb-1">需要配置 AI 模型</h2>
          <p class="text-sm text-text-muted leading-relaxed">
            本周回顾需要 AI 生成研究脉络。<br>请先在高级设置中配置「AI 问答」的模型参数。
          </p>
        </div>
        <button type="button" class="px-4 py-2 rounded-lg bg-tinder-purple/10 text-tinder-purple text-sm font-medium hover:bg-tinder-purple/20 transition-colors" @click="router.push('/advanced-settings')">
          前往高级设置
        </button>
      </div>

      <!-- Recap content -->
      <div v-else-if="recap?.status === 'ok' && recap.recap" class="space-y-6">

        <!-- ── 研究成果区域 ─────────────────────────────────────────────── -->

        <!-- 14天趋势摘要 (≥2 recaps) -->
        <div v-if="outcomes.trendSummary" class="bg-bg-card rounded-2xl border border-border overflow-hidden">
          <button
            type="button"
            class="w-full flex items-center justify-between px-5 py-3.5 text-left cursor-pointer hover:bg-bg-elevated/50 transition-colors"
            @click="trendExpanded = !trendExpanded"
          >
            <div class="flex items-center gap-2.5">
              <span class="text-base leading-none">📈</span>
              <div>
                <p class="text-sm font-semibold text-text-primary">近两周趋势</p>
                <p class="text-xs text-text-muted mt-0.5">
                  {{ outcomes.trendSummary.week_labels[0] }} → {{ outcomes.trendSummary.week_labels[1] }}
                </p>
              </div>
            </div>
            <svg
              class="w-4 h-4 text-text-muted transition-transform duration-200 shrink-0"
              :class="trendExpanded ? '' : '-rotate-90'"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          <div v-if="trendExpanded" class="px-5 pb-5 space-y-4 border-t border-border/60">
            <!-- Persistent themes -->
            <div v-if="outcomes.trendSummary.persistent_themes.length" class="pt-4">
              <p class="text-xs font-semibold text-text-muted mb-2 uppercase tracking-wide">持续关注</p>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="t in outcomes.trendSummary.persistent_themes"
                  :key="t"
                  class="px-2.5 py-1 rounded-full text-xs font-medium bg-tinder-purple/10 text-tinder-purple border border-tinder-purple/20"
                >{{ t }}</span>
              </div>
            </div>
            <!-- New themes -->
            <div v-if="outcomes.trendSummary.new_themes.length">
              <p class="text-xs font-semibold text-text-muted mb-2 uppercase tracking-wide">新兴方向</p>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="t in outcomes.trendSummary.new_themes"
                  :key="t"
                  class="px-2.5 py-1 rounded-full text-xs font-medium bg-tinder-green/10 text-tinder-green border border-tinder-green/20"
                >↑ {{ t }}</span>
              </div>
            </div>
            <!-- Faded themes -->
            <div v-if="outcomes.trendSummary.faded_themes.length">
              <p class="text-xs font-semibold text-text-muted mb-2 uppercase tracking-wide">减少关注</p>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="t in outcomes.trendSummary.faded_themes"
                  :key="t"
                  class="px-2.5 py-1 rounded-full text-xs font-medium bg-bg-elevated text-text-muted border border-border"
                >↓ {{ t }}</span>
              </div>
            </div>
            <!-- Empty state: all themes are new (no overlap) -->
            <div
              v-if="!outcomes.trendSummary.persistent_themes.length && !outcomes.trendSummary.new_themes.length && !outcomes.trendSummary.faded_themes.length"
              class="pt-4 text-sm text-text-muted"
            >
              主题变化数据不足，继续收藏论文后会更清晰。
            </div>
          </div>
        </div>

        <!-- 30天主题演化 (≥4 recaps) -->
        <div v-if="outcomes.topicEvolution" class="bg-bg-card rounded-2xl border border-border overflow-hidden">
          <button
            type="button"
            class="w-full flex items-center justify-between px-5 py-3.5 text-left cursor-pointer hover:bg-bg-elevated/50 transition-colors"
            @click="evolutionExpanded = !evolutionExpanded"
          >
            <div class="flex items-center gap-2.5">
              <span class="text-base leading-none">🗺️</span>
              <div>
                <p class="text-sm font-semibold text-text-primary">30 天主题演化</p>
                <p class="text-xs text-text-muted mt-0.5">
                  {{ outcomes.topicEvolution.weeks[0]?.week_label }} → {{ outcomes.topicEvolution.weeks[outcomes.topicEvolution.weeks.length - 1]?.week_label }}
                </p>
              </div>
            </div>
            <svg
              class="w-4 h-4 text-text-muted transition-transform duration-200 shrink-0"
              :class="evolutionExpanded ? '' : '-rotate-90'"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          <div v-if="evolutionExpanded" class="border-t border-border/60">
            <div class="grid grid-cols-2 sm:grid-cols-4 divide-x divide-border/60">
              <div
                v-for="(week, idx) in outcomes.topicEvolution.weeks"
                :key="idx"
                class="px-4 py-4 min-w-0"
              >
                <p class="text-[11px] font-semibold text-text-muted mb-1.5 tabular-nums">{{ week.week_label }}</p>
                <p class="text-[10px] text-text-muted mb-2">{{ week.paper_count }} 篇</p>
                <div class="space-y-1">
                  <span
                    v-for="theme in week.themes.slice(0, 3)"
                    :key="theme"
                    class="block text-xs text-text-secondary leading-snug truncate"
                  >{{ theme }}</span>
                  <span v-if="week.themes.length > 3" class="block text-[10px] text-text-muted">+{{ week.themes.length - 3 }} 个</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Summary card -->
        <div class="bg-bg-card rounded-2xl border border-border p-6">
          <h2 class="text-xl font-bold text-text-primary leading-snug mb-3">
            {{ recap.recap.title }}
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">{{ recap.recap.summary }}</p>
          <div class="mt-4 flex items-center gap-1.5 text-xs text-text-muted">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
            </svg>
            本周收藏 {{ recap.recap.paper_count }} 篇
          </div>
        </div>

        <!-- Themes -->
        <div v-if="recap.recap.themes?.length" class="space-y-3">
          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wide px-1">研究主题</h3>
          <div
            v-for="(theme, idx) in recap.recap.themes"
            :key="idx"
            class="bg-bg-card rounded-xl border border-border p-5"
          >
            <h4 class="text-sm font-semibold text-text-primary mb-1">{{ theme.name }}</h4>
            <p class="text-sm text-text-secondary leading-relaxed">{{ theme.insight }}</p>
            <div v-if="theme.paper_ids?.length" class="mt-3 flex flex-wrap gap-2">
              <button
                v-for="pid in theme.paper_ids"
                :key="pid"
                type="button"
                class="text-xs px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-muted hover:text-text-primary hover:border-border transition-colors cursor-pointer"
                :title="paperTitle(pid)"
                @click="goToPaper(pid)"
              >
                {{ paperTitle(pid).slice(0, 40) }}{{ paperTitle(pid).length > 40 ? '…' : '' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Connections -->
        <div v-if="recap.recap.connections?.length" class="space-y-2">
          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wide px-1">研究脉络联系</h3>
          <div class="bg-bg-card rounded-xl border border-border p-5 space-y-3">
            <div
              v-for="(connection, idx) in recap.recap.connections"
              :key="idx"
              class="flex gap-2.5"
            >
              <span class="text-tinder-purple shrink-0 mt-0.5 text-sm">›</span>
              <p class="text-sm text-text-secondary leading-relaxed">{{ connection }}</p>
            </div>
          </div>
        </div>

        <!-- Recommended revisit -->
        <div v-if="recap.recap.recommended_revisit?.length" class="space-y-2">
          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wide px-1">推荐重读</h3>
          <div class="bg-bg-card rounded-xl border border-border divide-y divide-border">
            <button
              v-for="pid in recap.recap.recommended_revisit"
              :key="pid"
              type="button"
              class="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-bg-elevated transition-colors"
              @click="goToPaper(pid)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              </svg>
              <span class="text-sm text-text-primary">{{ paperTitle(pid) }}</span>
            </button>
          </div>
        </div>

        <!-- Next questions -->
        <div v-if="recap.recap.next_questions?.length" class="space-y-2">
          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wide px-1">值得继续追问</h3>
          <div class="bg-bg-card rounded-xl border border-border p-5 space-y-3">
            <div
              v-for="(q, idx) in recap.recap.next_questions"
              :key="idx"
              class="flex gap-2.5"
            >
              <span class="text-tinder-blue shrink-0 mt-0.5 text-sm">?</span>
              <p class="text-sm text-text-secondary leading-relaxed">{{ q }}</p>
            </div>
          </div>
        </div>

        <!-- Collected papers this week -->
        <div class="space-y-2">
          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wide px-1">
            本周收藏（{{ recap.papers.length }} 篇）
          </h3>
          <div class="bg-bg-card rounded-xl border border-border divide-y divide-border">
            <button
              v-for="p in recap.papers"
              :key="p.paper_id"
              type="button"
              class="w-full flex items-start gap-3 px-5 py-3.5 text-left hover:bg-bg-elevated transition-colors"
              @click="goToPaper(p.paper_id)"
            >
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-text-primary truncate">{{ p.title || p.title_en }}</p>
                <p v-if="p.institution" class="text-xs text-text-muted mt-0.5">{{ p.institution }}</p>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0 mt-1">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>
        </div>

      </div>

      <!-- Empty state: no recap yet -->
      <div v-else-if="!loading && !recap" class="flex flex-col items-center gap-5 py-24 text-center">
        <div class="w-16 h-16 rounded-2xl bg-bg-elevated border border-border flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
        </div>
        <div>
          <h2 class="text-lg font-bold text-text-primary mb-1">还没有本周回顾</h2>
          <p class="text-sm text-text-muted leading-relaxed">收藏论文后，可手动生成本周研究脉络总结。</p>
        </div>
        <button type="button" class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-sm text-text-secondary hover:text-text-primary transition-colors" @click="generate">立即生成</button>
      </div>

      <!-- status=error fallback -->
      <div v-else-if="recap?.status === 'error'" class="flex flex-col items-center gap-4 py-24 text-center">
        <p class="text-sm text-text-muted">生成失败，请稍后重试。</p>
        <button type="button" class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-sm text-text-secondary hover:text-text-primary transition-colors" @click="generate">重新生成</button>
      </div>

    </div><!-- end max-w-3xl -->
  </div><!-- end flex-1 wrapper -->
  </div><!-- end outer flex -->
</template>
