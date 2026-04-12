<script setup lang="ts">
import { ref, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { fetchResearchStream, fetchResearchSessions, deleteResearchSession, fetchResearchSession, fetchResearchContinueRound3, fetchResearchFollowup, cancelResearchSession } from '../api'
import type { ResearchSseEvent, ResearchRankingItem, ResearchSession } from '../types/paper'
import { useResearchStream } from '../composables/useResearchStream'
import { useEngagement } from '../composables/useEngagement'
import { useEntitlements } from '../composables/useEntitlements'
import { useGlobalChat } from '../composables/useGlobalChat'
import RewardBoostBanner from './RewardBoostBanner.vue'
import UpgradePrompt from './UpgradePrompt.vue'
import QuotaWarningBanner from './QuotaWarningBanner.vue'
import PaperPickerDialog from './PaperPickerDialog.vue'
import ResearchStepper from './research/ResearchStepper.vue'
import ResearchInput from './research/ResearchInput.vue'
import ResearchRoundCard from './research/ResearchRoundCard.vue'
import ResearchRelevanceResult from './research/ResearchRelevanceResult.vue'
import ResearchStreamContent from './research/ResearchStreamContent.vue'
import ResearchEmptyState from './research/ResearchEmptyState.vue'
import ResearchHistoryDrawer from './research/ResearchHistoryDrawer.vue'
import ResearchSessionViewer from './research/ResearchSessionViewer.vue'
import ResearchFollowup from './research/ResearchFollowup.vue'
import ResearchFinalBanner from './research/ResearchFinalBanner.vue'
import type { StepDef, StepStatus } from './research/ResearchStepper.vue'

// ---------------------------------------------------------------------------
// Props / emits
// ---------------------------------------------------------------------------

const props = withDefaults(
  defineProps<{
    paperIds: string[]
    paperTitles?: Record<string, string>
    scope?: string
    /** When set, automatically opens this session ID on mount/change */
    initialSessionId?: number | null
  }>(),
  { scope: 'kb', initialSessionId: null },
)

const emit = defineEmits<{
  close: []
  removePaper: [paperId: string]
  saveToLibrary: [sessionId: number]
}>()

const { consumeStream } = useResearchStream()
const globalChat = useGlobalChat()

// Paper picker dialog
const showPicker = ref(false)

function handlePickerConfirm(ids: string[], titles: Record<string, string>) {
  showPicker.value = false
  globalChat.requestResearch(ids, titles, props.scope)
}

// ---------------------------------------------------------------------------
// Engagement reward
// ---------------------------------------------------------------------------

const engagement = useEngagement()
const useResearchReward = ref(false)

// Entitlements
const ent = useEntitlements()
const researchQuotaBlocked = computed(() => !ent.canUse('research'))
const researchQuotaSummary = computed(() => ent.quotaSummary('research'))

// Load research rewards lazily when the panel is mounted/active
watch(() => props.paperIds, (ids) => {
  if (ids.length > 0 && engagement.loaded.value) {
    void engagement.loadActiveRewards('research')
  }
}, { immediate: true })

// ---------------------------------------------------------------------------
// Round state
// ---------------------------------------------------------------------------

type RoundStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'

interface RoundState {
  status: RoundStatus
  title: string
  collapsed: boolean
  progressMsg: string
  rankings: ResearchRankingItem[]
  selectedIds: string[]
  paperTitles: Record<string, string>
  streamText: string
  action: string | null
  papersToRead: string[]
  decisionReason: string | null
}

function makeRound(title: string): RoundState {
  return {
    status: 'pending', title, collapsed: false, progressMsg: '',
    rankings: [], selectedIds: [], paperTitles: {},
    streamText: '', action: null, papersToRead: [], decisionReason: null,
  }
}

const question = ref('')
const topN = ref(5)
const isRunning = ref(false)
const isAborted = ref(false)
const runningSessionId = ref<number | null>(null)
const rounds = ref<RoundState[]>([
  makeRound('分析问题与论文相关性'),
  makeRound('基于 AI 摘要分析'),
  makeRound('深度阅读全文'),
])
const finalAnswerReached = ref(false)
const errorMsg = ref('')
const scrollRef = ref<HTMLElement | null>(null)
const currentSessionId = ref<number | null>(null)

// History
const showHistory = ref(false)
const sessions = ref<ResearchSession[]>([])
const loadingSessions = ref(false)
const viewedSession = ref<ResearchSession | null>(null)
const loadingViewSession = ref(false)

// Follow-up
const followupQuestion = ref('')

interface PrevResearchContext { question: string; finalText: string }
const prevResearch = ref<PrevResearchContext | null>(null)

// ---------------------------------------------------------------------------
// Stepper configuration
// ---------------------------------------------------------------------------

const stepDefs: StepDef[] = [
  { id: 'r1', label: '相关性排序', sublabel: 'R1', color: 'accent' },
  { id: 'r2', label: '摘要分析', sublabel: 'R2', color: 'blue' },
  { id: 'r3', label: '全文精读', sublabel: 'R3', color: 'purple' },
]
const stepStatuses = computed<StepStatus[]>(() =>
  rounds.value.map(r => r.status as StepStatus),
)

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const canStart = computed(() =>
  question.value.trim().length > 0 && props.paperIds.length > 0 && !isRunning.value,
)

const canForceFullRead = computed(() =>
  finalAnswerReached.value &&
  !isRunning.value &&
  !isAborted.value &&
  !researchQuotaBlocked.value &&
  rounds.value[1].status === 'done' &&
  rounds.value[1].action !== 'read_full' &&
  rounds.value[2].status === 'pending',
)

const showFollowup = computed(() =>
  finalAnswerReached.value && !isRunning.value && !isAborted.value,
)

const liveFinalText = computed(() =>
  rounds.value[2].streamText || rounds.value[1].streamText,
)

function titleFor(paperId: string, roundIdx = 0): string {
  const rt = rounds.value[roundIdx]?.paperTitles[paperId]
  if (rt) return rt
  return props.paperTitles?.[paperId] ?? paperId
}

function paperCount(scope: 'all' | 'selected' | 'to_read'): number {
  if (scope === 'all') return props.paperIds.length
  if (scope === 'selected') return rounds.value[0]?.selectedIds.length ?? 0
  return rounds.value[1]?.papersToRead.length ?? 0
}

// Show the results area (stepper + rounds) when any round is active
const showResults = computed(() =>
  rounds.value.some(r => r.status !== 'pending') || isAborted.value || !!errorMsg.value || !!viewedSession.value,
)

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------

function resetState({ keepPrev = false }: { keepPrev?: boolean } = {}) {
  rounds.value = [
    makeRound('分析问题与论文相关性'),
    makeRound('基于 AI 摘要分析'),
    makeRound('深度阅读全文'),
  ]
  finalAnswerReached.value = false
  errorMsg.value = ''
  isAborted.value = false
  viewedSession.value = null
  currentSessionId.value = null
  runningSessionId.value = null
  if (!keepPrev) {
    prevResearch.value = null
  }
}

// ---------------------------------------------------------------------------
// Streaming / events
// ---------------------------------------------------------------------------

let abortController: AbortController | null = null

async function scrollToBottom() {
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
}

async function handleEvent(evt: ResearchSseEvent) {
  switch (evt.type) {
    case 'session_created':
      currentSessionId.value = evt.session_id
      break
    case 'round_start': {
      const idx = evt.round - 1
      if (idx >= 0 && idx < rounds.value.length) {
        rounds.value[idx].status = 'running'
        rounds.value[idx].title = evt.title
        if ('paper_titles' in evt && evt.paper_titles) rounds.value[idx].paperTitles = evt.paper_titles
        if (idx > 0) rounds.value[idx - 1].collapsed = true
      }
      break
    }
    case 'relevance_result': {
      const r = rounds.value[0]
      if (r) {
        r.rankings = evt.rankings
        r.selectedIds = evt.selected_ids
        r.paperTitles = evt.paper_titles ?? {}
      }
      await scrollToBottom()
      break
    }
    case 'text': {
      const idx = evt.round - 1
      if (idx >= 0 && idx < rounds.value.length) {
        rounds.value[idx].streamText += evt.content
        await scrollToBottom()
      }
      break
    }
    case 'round_done': {
      const idx = evt.round - 1
      if (idx >= 0 && idx < rounds.value.length) {
        rounds.value[idx].status = 'done'
        if (evt.action) rounds.value[idx].action = evt.action
        if (evt.papers) rounds.value[idx].papersToRead = evt.papers
        if (evt.decision_reason) rounds.value[idx].decisionReason = evt.decision_reason
      }
      break
    }
    case 'progress': {
      const idx = evt.round - 1
      if (idx >= 0 && idx < rounds.value.length) rounds.value[idx].progressMsg = evt.message
      break
    }
    case 'final_answer':
      finalAnswerReached.value = true
      for (let i = rounds.value.length - 1; i >= 0; i--) {
        if (rounds.value[i].streamText || rounds.value[i].rankings.length > 0) {
          rounds.value[i].collapsed = false
          break
        }
      }
      await scrollToBottom()
      break
    case 'error': {
      const idx = evt.round != null ? evt.round - 1 : -1
      if (idx >= 0 && idx < rounds.value.length) rounds.value[idx].status = 'error'
      errorMsg.value = evt.content
      if (evt.running_session_id != null) runningSessionId.value = evt.running_session_id
      break
    }
  }
}

// ---------------------------------------------------------------------------
// Research actions
// ---------------------------------------------------------------------------

async function startResearch(options: { forceFullRead?: boolean } = {}) {
  if (!canStart.value) return
  resetState()
  isRunning.value = true
  errorMsg.value = ''
  abortController = new AbortController()
  try {
    const rewardToUse = useResearchReward.value ? engagement.bestResearchReward.value : undefined
    const rewardId = rewardToUse?.id
    const response = await fetchResearchStream({
      question: question.value.trim(),
      paper_ids: props.paperIds,
      scope: props.scope,
      config: { top_n: topN.value, ...(options.forceFullRead ? { force_full_read: true } : {}) },
      signal: abortController.signal,
      reward_id: rewardId,
    })
    // Refresh reward list if we used one
    if (rewardId !== undefined && rewardToUse) {
      useResearchReward.value = false
      engagement.notifyRewardUsed(rewardToUse.reward_name)
      void engagement.loadActiveRewards('research')
      void engagement.loadStatus(true)
    }
    await consumeStream(response, handleEvent, () => isAborted.value)
  } catch (err: any) {
    if (!isAborted.value) errorMsg.value = `研究失败: ${err?.message ?? err}`
  } finally {
    isRunning.value = false
    abortController = null
    if (showHistory.value) loadHistory()
    // Refresh quota display after consuming a research credit
    void ent.refreshEntitlements(true)
  }
}

function abort() {
  isAborted.value = true
  abortController?.abort()
  isRunning.value = false
  for (const r of rounds.value) {
    if (r.status === 'running' || r.status === 'pending') r.status = 'cancelled'
  }
}

async function continueRound3(sessionId: number) {
  if (isRunning.value) return
  if (researchQuotaBlocked.value) {
    errorMsg.value = '本月深度研究次数已用完，请升级套餐继续使用。'
    return
  }
  isRunning.value = true
  errorMsg.value = ''
  isAborted.value = false
  abortController = new AbortController()
  rounds.value[2] = { ...rounds.value[2], status: 'running', streamText: '', collapsed: false }
  try {
    const response = await fetchResearchContinueRound3(sessionId, abortController.signal)
    await consumeStream(response, handleEvent, () => isAborted.value)
  } catch (err: any) {
    if (!isAborted.value) errorMsg.value = `深度阅读失败: ${err?.message ?? err}`
  } finally {
    isRunning.value = false
    abortController = null
    if (showHistory.value) loadHistory()
    void ent.refreshEntitlements(true)
  }
}

async function startFollowup(parentSessionId: number, followupQ: string, context: string) {
  if (isRunning.value) return
  if (researchQuotaBlocked.value) {
    errorMsg.value = '本月深度研究次数已用完，请升级套餐继续使用。'
    return
  }
  isRunning.value = true
  errorMsg.value = ''
  abortController = new AbortController()
  try {
    const response = await fetchResearchFollowup(
      parentSessionId,
      { question: followupQ, context: context || undefined },
      abortController.signal,
    )
    await consumeStream(response, handleEvent, () => isAborted.value)
  } catch (err: any) {
    if (!isAborted.value) errorMsg.value = `追问失败: ${err?.message ?? err}`
  } finally {
    isRunning.value = false
    abortController = null
    if (showHistory.value) loadHistory()
    void ent.refreshEntitlements(true)
  }
}

async function cancelAndRestart() {
  const sid = runningSessionId.value
  if (!sid) return
  try {
    await cancelResearchSession(sid)
    runningSessionId.value = null
    errorMsg.value = ''
    await startResearch()
  } catch (err: any) {
    errorMsg.value = `取消旧会话失败: ${err?.message ?? err}`
  }
}

async function forceFullRead() {
  if (!canForceFullRead.value) return
  if (currentSessionId.value) await continueRound3(currentSessionId.value)
  else await startResearch({ forceFullRead: true })
}

async function submitFollowup() {
  const fq = followupQuestion.value.trim()
  if (!fq || isRunning.value) return
  if (researchQuotaBlocked.value) {
    errorMsg.value = '本月深度研究次数已用完，请升级套餐继续使用。'
    return
  }
  const prevSessionId = currentSessionId.value
  const prevFinalText = liveFinalText.value
  if (finalAnswerReached.value) {
    prevResearch.value = { question: question.value, finalText: prevFinalText.slice(0, 1500) }
  }
  question.value = fq
  followupQuestion.value = ''
  resetState({ keepPrev: true })
  if (prevSessionId) await startFollowup(prevSessionId, fq, prevFinalText.slice(0, 3000))
  else await startResearch()
}

// ---------------------------------------------------------------------------
// Copy result
// ---------------------------------------------------------------------------

async function copyResult() {
  const text = viewedSession.value
    ? sessionFinalText(viewedSession.value)
    : liveFinalText.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    try { document.execCommand('copy') } catch { /* ignore */ }
    document.body.removeChild(el)
  }
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

async function loadHistory() {
  loadingSessions.value = true
  try {
    const res = await fetchResearchSessions(20)
    sessions.value = res.sessions
  } catch { /* ignore */ }
  finally { loadingSessions.value = false }
}

async function removeSession(id: number) {
  try {
    await deleteResearchSession(id)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (viewedSession.value?.id === id) viewedSession.value = null
  } catch { /* ignore */ }
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value && sessions.value.length === 0) loadHistory()
}

async function viewSession(id: number) {
  if (isRunning.value) return
  loadingViewSession.value = true
  showHistory.value = false
  viewedSession.value = null
  try {
    viewedSession.value = await fetchResearchSession(id)
  } catch { /* ignore */ }
  finally { loadingViewSession.value = false }
}

function sessionFinalText(session: ResearchSession): string {
  if (!session.rounds) return ''
  const r3 = session.rounds.find(r => r.round_type === 'full_text')
  if (r3 && (r3.output as Record<string, unknown>).full_text)
    return (r3.output as Record<string, unknown>).full_text as string
  const r2 = session.rounds.find(r => r.round_type === 'summary_analysis')
  if (r2 && (r2.output as Record<string, unknown>).full_text)
    return (r2.output as Record<string, unknown>).full_text as string
  return ''
}

function handleStepClick(i: number) {
  rounds.value[i].collapsed = !rounds.value[i].collapsed
}

function onViewerSaveToLibrary(id: number) {
  emit('saveToLibrary', id)
  if (viewedSession.value?.id === id) {
    viewedSession.value = { ...viewedSession.value, saved: true }
  }
}

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------

watch(() => props.paperIds.length, (len) => {
  if (topN.value > len) topN.value = Math.max(1, len)
})

watch(() => props.paperIds, () => {
  if (!isRunning.value) resetState()
})

watch(() => props.initialSessionId, (id) => {
  if (id != null) viewSession(id)
}, { immediate: true })

onBeforeUnmount(() => {
  if (isRunning.value) {
    abort()
    if (currentSessionId.value) {
      cancelResearchSession(currentSessionId.value).catch(() => {})
    }
  }
})
</script>

<template>
  <div class="flex flex-col h-full bg-bg text-text-primary overflow-hidden relative">

    <!-- ===== Header (only shown when results are active) ===== -->
    <div
      v-if="showResults || isRunning"
      class="flex items-center justify-between px-5 py-3 border-b border-border/40 shrink-0"
    >
      <div class="flex items-center gap-2">
        <div class="flex items-center justify-center w-5 h-5 rounded-md bg-accent-primary/10">
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            class="text-accent-primary">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
            <path d="M11 8v6"/>
            <path d="M8 11h6"/>
          </svg>
        </div>
        <span class="font-medium text-xs text-text-secondary tracking-wide">深度研究 Q&amp;A</span>
      </div>

      <div class="flex items-center gap-1">
        <!-- History toggle -->
        <button
          class="p-1.5 rounded-lg hover:bg-bg-elevated transition-colors"
          :class="showHistory ? 'text-accent-primary bg-accent-primary/10' : 'text-text-muted hover:text-text-primary'"
          title="研究历史"
          @click="toggleHistory"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
            <path d="M12 7v5l4 2"/>
          </svg>
        </button>

        <!-- Close -->
        <button
          class="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
          title="关闭"
          @click="emit('close')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6 6 18"/>
            <path d="m6 6 12 12"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- ===== Empty state layout: vertically centered hero + input + suggestions ===== -->
    <template v-if="!showResults && !isRunning">
      <!-- History button — absolute top-right, out of content flow -->
      <button
        class="absolute top-3 right-3 z-10 flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors px-2.5 py-1.5 rounded-lg hover:bg-bg-elevated"
        :class="showHistory ? 'text-accent-primary bg-accent-primary/10' : ''"
        @click="toggleHistory"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>
        </svg>
        历史记录
      </button>

      <!-- Single scrollable column -->
      <div ref="scrollRef" class="flex-1 overflow-y-auto min-h-0">
        <div class="px-5 w-full max-w-2xl mx-auto flex flex-col">

          <!-- Top spacer: push content ~25% down -->
          <div class="pt-[10vh] sm:pt-[15vh]"></div>

          <!-- Hero title block (centered) -->
          <div class="flex flex-col items-center text-center mb-8 select-none">
            <div class="text-[26px] sm:text-[28px] font-bold text-text-primary leading-tight mb-2.5">深度研究</div>
            <div class="text-sm text-text-muted leading-relaxed">提出复杂问题，获取来源有据的完整报告。</div>
          </div>

          <!-- Input box -->
          <div class="mb-8">
            <ResearchInput
              v-model="question"
              :paper-ids="paperIds"
              :paper-titles="paperTitles"
              :scope="scope"
              v-model:top-n="topN"
              :is-running="isRunning"
              :can-start="canStart && !researchQuotaBlocked"
              :final-answer-reached="finalAnswerReached"
              :compact="false"
              @start="startResearch()"
              @abort="abort"
              @remove-paper="emit('removePaper', $event)"
              @pick-papers="showPicker = true"
            />
            <!-- Quota hint: only when blocked or limit exists -->
            <div v-if="researchQuotaBlocked && ent.loaded.value" class="mt-3">
              <UpgradePrompt feature="research" :inline="true" />
            </div>
            <div
              v-else-if="ent.loaded.value && ent.limit('research') !== null && !researchQuotaBlocked"
              class="mt-2 text-[11px] text-text-muted/50 text-right"
            >
              本月研究：{{ researchQuotaSummary }}
            </div>
          </div>

          <!-- Suggestion list -->
          <ResearchEmptyState @suggest="question = $event" />

          <!-- Bottom spacer -->
          <div class="pb-12"></div>
        </div>
      </div>

      <!-- Paper picker dialog -->
      <PaperPickerDialog
        v-if="showPicker"
        mode="research"
        @confirm="handlePickerConfirm"
        @cancel="showPicker = false"
      />
    </template>

    <!-- ===== Active state layout: compact header + results ===== -->
    <template v-else>
      <!-- Quota / reward banners -->
      <div v-if="researchQuotaBlocked && ent.loaded.value && !isRunning" class="px-3 pb-2">
        <UpgradePrompt feature="research" :inline="true" />
      </div>
      <div v-else-if="ent.loaded.value && !isRunning" class="px-3 pb-1">
        <QuotaWarningBanner feature="research" :compact="true" />
      </div>
      <div
        v-if="ent.loaded.value && ent.limit('research') !== null && !isRunning && !researchQuotaBlocked"
        class="px-3 pb-1 text-[11px] text-text-muted text-right"
      >
        本月研究：{{ researchQuotaSummary }}
      </div>
      <div
        v-if="engagement.bestResearchReward.value && !isRunning && !researchQuotaBlocked"
        class="px-3 pb-2"
      >
        <RewardBoostBanner
          :reward="engagement.bestResearchReward.value"
          v-model="useResearchReward"
        />
      </div>

      <!-- Compact input -->
      <ResearchInput
        v-model="question"
        :paper-ids="paperIds"
        :paper-titles="paperTitles"
        v-model:top-n="topN"
        :is-running="isRunning"
        :can-start="canStart && !researchQuotaBlocked"
        :final-answer-reached="finalAnswerReached"
        :compact="true"
        @start="startResearch()"
        @abort="abort"
        @remove-paper="emit('removePaper', $event)"
      />

      <!-- Results scroll area -->
      <div ref="scrollRef" class="flex-1 overflow-y-auto min-h-0">
        <div class="px-6 pt-7 pb-8 space-y-5 max-w-3xl mx-auto w-full">

        <!-- Progress stepper -->
        <ResearchStepper
          :steps="stepDefs"
          :statuses="stepStatuses"
          @step-click="handleStepClick"
        />

        <!-- Abort banner -->
        <div
          v-if="isAborted"
          class="flex items-center gap-2 px-3 py-2.5 rounded-xl bg-amber-500/8 border border-amber-500/20 text-sm text-amber-400"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" x2="12" y1="9" y2="13"/>
            <line x1="12" x2="12.01" y1="17" y2="17"/>
          </svg>
          研究已中止 — 已完成的部分结果仍可查看。
        </div>

        <!-- Error banner -->
        <div
          v-if="errorMsg"
          class="flex flex-col gap-2 px-3 py-2.5 rounded-xl bg-red-500/8 border border-red-500/20 text-sm text-red-400"
        >
          <div class="flex items-start gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 mt-0.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" x2="12" y1="8" y2="12"/>
              <line x1="12" x2="12.01" y1="16" y2="16"/>
            </svg>
            <span class="flex-1">{{ errorMsg }}</span>
            <div class="flex flex-col gap-1 shrink-0">
              <button
                v-if="!isRunning && question.trim() && !runningSessionId"
                class="text-xs px-2.5 py-1 rounded-lg border border-red-400/30 text-red-400 hover:bg-red-500/10 transition-colors whitespace-nowrap"
                @click="startResearch()"
              >重试</button>
              <button
                v-if="runningSessionId && !isRunning"
                class="text-xs px-2.5 py-1 rounded-lg border border-amber-400/30 text-amber-400 hover:bg-amber-500/10 transition-colors whitespace-nowrap"
                @click="cancelAndRestart"
              >终止旧会话并开始</button>
            </div>
          </div>
          <!-- 连接类错误：显示前往设置的快捷入口 -->
          <div
            v-if="errorMsg.includes('Connection error') || errorMsg.includes('无法连接') || errorMsg.includes('认证失败') || errorMsg.includes('Authentication')"
            class="flex items-center gap-2 pt-1 border-t border-red-500/15 text-xs text-red-400/70"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0">
              <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
            </svg>
            <span>请前往</span>
            <a
              href="/profile"
              class="underline underline-offset-2 text-red-400 hover:text-red-300 transition-colors"
            >个人中心 → AI 问答</a>
            <span>检查 LLM 配置。</span>
          </div>
        </div>

        <!-- R1: Relevance ranking -->
        <ResearchRoundCard
          v-if="rounds[0].status !== 'pending'"
          round-label="R1"
          :title="rounds[0].title"
          :status="rounds[0].status"
          color="accent"
          :collapsed="rounds[0].collapsed"
          :status-detail="rounds[0].status === 'done' ? `选出 ${paperCount('selected')} 篇` : undefined"
          @toggle-collapse="rounds[0].collapsed = !rounds[0].collapsed"
        >
          <ResearchRelevanceResult
            :rankings="rounds[0].rankings"
            :selected-ids="rounds[0].selectedIds"
            :is-running="rounds[0].status === 'running'"
            :progress-msg="rounds[0].progressMsg"
            :total-papers="paperIds.length"
            :title-for="(pid) => titleFor(pid, 0)"
          />
        </ResearchRoundCard>

        <!-- R2: Summary analysis -->
        <ResearchRoundCard
          v-if="rounds[1].status !== 'pending'"
          round-label="R2"
          :title="rounds[1].title"
          :status="rounds[1].status"
          color="blue"
          :collapsed="rounds[1].collapsed"
          :status-detail="rounds[1].status === 'done' && rounds[1].action === 'read_full' ? '建议精读全文' : undefined"
          @toggle-collapse="rounds[1].collapsed = !rounds[1].collapsed"
        >
          <template #default>
            <div class="text-xs text-text-muted mb-2 opacity-70">基于 {{ paperCount('selected') }} 篇摘要分析</div>
            <ResearchStreamContent
              :stream-text="rounds[1].streamText"
              :is-running="rounds[1].status === 'running'"
              :progress-msg="rounds[1].progressMsg || '正在分析摘要…'"
              :papers-to-read="rounds[1].papersToRead"
              :decision-reason="rounds[1].decisionReason ?? undefined"
              :show-read-full-suggestion="rounds[1].status === 'done' && rounds[1].action === 'read_full' && rounds[1].papersToRead.length > 0"
              :title-for="(pid) => titleFor(pid, 1)"
              :can-force-full-read="canForceFullRead"
              @force-full-read="forceFullRead"
            />
          </template>
        </ResearchRoundCard>

        <!-- R3: Full text -->
        <ResearchRoundCard
          v-if="rounds[2].status !== 'pending'"
          round-label="R3"
          :title="rounds[2].title"
          :status="rounds[2].status"
          color="purple"
          :collapsed="rounds[2].collapsed"
          :status-detail="rounds[2].status === 'done' ? `${paperCount('to_read')} 篇全文` : undefined"
          @toggle-collapse="rounds[2].collapsed = !rounds[2].collapsed"
        >
          <template #default>
            <div class="text-xs text-text-muted mb-2 opacity-70">精读 {{ paperCount('to_read') }} 篇论文全文</div>
            <ResearchStreamContent
              :stream-text="rounds[2].streamText"
              :is-running="rounds[2].status === 'running'"
              :progress-msg="rounds[2].progressMsg || '正在深度阅读论文全文…'"
              :truncation-warning="rounds[2].progressMsg && rounds[2].status !== 'running' ? rounds[2].progressMsg : undefined"
            />
          </template>
        </ResearchRoundCard>

        <!-- Final banner -->
        <ResearchFinalBanner
          v-if="finalAnswerReached"
          :has-text="!!liveFinalText"
          :session-id="currentSessionId"
          @copy="copyResult"
          @save-to-library="emit('saveToLibrary', $event)"
        />

        <!-- Follow-up section -->
        <ResearchFollowup
          v-if="showFollowup"
          v-model="followupQuestion"
          :is-running="isRunning"
          :prev-research="prevResearch"
          @submit="submitFollowup"
        />

        <!-- Viewed historical session -->
        <ResearchSessionViewer
          v-if="viewedSession"
          :session="viewedSession"
          :loading="loadingViewSession"
          :paper-titles="paperTitles"
          @back="viewedSession = null"
          @copy="copyResult"
          @save-to-library="onViewerSaveToLibrary"
        />

        </div>
      </div>
    </template>

    <!-- ===== History drawer (slide-over, always mounted) ===== -->
    <ResearchHistoryDrawer
      :open="showHistory"
      :sessions="sessions"
      :loading="loadingSessions"
      :viewed-session-id="viewedSession?.id"
      :is-running="isRunning"
      @close="showHistory = false"
      @refresh="loadHistory"
      @view="viewSession"
      @delete="removeSession"
    />

  </div>
</template>
