<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import SwipeCard from '@/components/SwipeCard.vue'
import IdeaSwipeCard from '@/components/IdeaSwipeCard.vue'
import ActionBar from '@/components/ActionBar.vue'
import DateSelector from '@/components/DateSelector.vue'
import QuotaGate from '@/components/QuotaGate.vue'
import { useDrawer } from '@/composables/useDrawer'
import {
  fetchDates,
  fetchDigest,
  addKbPaper,
  dismissPaper,
  fetchIdeaDigest,
  createIdeaFeedback,
} from '@shared/api'
import type { PaperSummary } from '@shared/types/paper'
import type { IdeaCandidate } from '@shared/types/idea'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '@shared/stores/auth'
import { useEngagement } from '@shared/composables/useEngagement'

defineOptions({ name: 'RecommendView' })

const router = useRouter()
const route = useRoute()
const engagement = useEngagement()
const drawer = useDrawer()

type Mode = 'paper' | 'idea'
const activeMode = ref<Mode>('paper')

// Paper state
const dates = ref<string[]>([])
const selectedDate = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)
const error = ref('')
const totalAvailable = ref(0)
const quotaLimit = ref<number | null>(null)
const responseTier = ref<string>('anonymous')
const currentIndex = ref(0)
const history = ref<number[]>([])

const currentPaper = computed(() => papers.value[currentIndex.value] ?? null)
const allSwiped = computed(() => papers.value.length > 0 && currentIndex.value >= papers.value.length)
const isQuotaExceeded = computed(() => {
  if (loading.value) return false
  const limit = quotaLimit.value
  const count = papers.value.length
  if (limit === null || count === 0) return false
  return currentIndex.value >= count && count >= limit
})
const isActuallyLimited = computed(() => {
  if (quotaLimit.value === null) return false
  return totalAvailable.value > papers.value.length
})
const quotaMessage = computed(() => {
  const tier = responseTier.value
  const limit = quotaLimit.value
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') return `已达 Pro 上限（${limit ?? 15} 篇）`
  if (tier === 'anonymous') return `未登录限 ${limit ?? 3} 篇，登录后查看更多`
  return `已达上限（${limit ?? 3} 篇），升级 Pro 查看更多`
})

// Idea state
const ideaCandidates = ref<IdeaCandidate[]>([])
const ideaLoading = ref(false)
const ideaError = ref('')
const ideaTotalAvailable = ref(0)
const ideaQuotaLimit = ref<number | null>(null)
const ideaIndex = ref(0)
const ideaHistory = ref<number[]>([])

const currentIdea = computed(() => ideaCandidates.value[ideaIndex.value] ?? null)
const allIdeasSwiped = computed(() => ideaCandidates.value.length > 0 && ideaIndex.value >= ideaCandidates.value.length)
const isIdeaQuotaExceeded = computed(() => {
  if (ideaLoading.value) return false
  const limit = ideaQuotaLimit.value
  const count = ideaCandidates.value.length
  if (limit === null || count === 0) return false
  return ideaIndex.value >= count && count >= limit
})
const isIdeaActuallyLimited = computed(() => {
  if (ideaQuotaLimit.value === null) return false
  return ideaTotalAvailable.value > ideaCandidates.value.length
})

// Current card counter
const counterText = computed(() => {
  if (activeMode.value === 'paper') {
    if (!currentPaper.value || papers.value.length === 0) return ''
    return `${currentIndex.value + 1} / ${papers.value.length}`
  } else {
    if (!currentIdea.value || ideaCandidates.value.length === 0) return ''
    return `${ideaIndex.value + 1} / ${ideaCandidates.value.length}`
  }
})

// Init
onMounted(async () => {
  await ensureAuthInitialized()
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) selectedDate.value = dates.value[0]
  } catch {
    error.value = '获取日期列表失败'
  }
})

async function loadDigest(date: string) {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchDigest(date)
    papers.value = Array.isArray(res.papers) ? res.papers : []
    totalAvailable.value = res.total_available ?? papers.value.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (isAuthenticated.value ? currentTier.value : 'anonymous')
    currentIndex.value = 0
    history.value = []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    papers.value = []
  } finally {
    loading.value = false
  }
}

async function loadIdeaDigest(date: string) {
  if (!isAuthenticated.value) return
  ideaLoading.value = true
  ideaError.value = ''
  try {
    const res = await fetchIdeaDigest(date)
    ideaCandidates.value = Array.isArray(res.candidates) ? res.candidates : []
    ideaTotalAvailable.value = res.total_available ?? ideaCandidates.value.length
    ideaQuotaLimit.value = res.quota_limit ?? null
    ideaIndex.value = 0
    ideaHistory.value = []
  } catch (e: any) {
    ideaError.value = e?.message || '加载失败'
    ideaCandidates.value = []
  } finally {
    ideaLoading.value = false
  }
}

watch(selectedDate, (date) => {
  if (date) {
    loadDigest(date)
    if (activeMode.value === 'idea') loadIdeaDigest(date)
  }
})

watch(isAuthenticated, () => {
  if (selectedDate.value) {
    loadDigest(selectedDate.value)
    if (activeMode.value === 'idea') loadIdeaDigest(selectedDate.value)
  }
})

watch(activeMode, (mode) => {
  if (mode === 'idea' && selectedDate.value && ideaCandidates.value.length === 0 && !ideaLoading.value) {
    loadIdeaDigest(selectedDate.value)
  }
})

// Paper actions
function handleSwipeLeft() {
  const paper = currentPaper.value
  history.value.push(currentIndex.value)
  currentIndex.value++
  if (paper && isAuthenticated.value) {
    dismissPaper(paper.paper_id).catch(() => {})
  }
}

function handleSwipeRight() {
  const paper = currentPaper.value
  if (!paper) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  history.value.push(currentIndex.value)
  currentIndex.value++
  addKbPaper(paper.paper_id, paper).catch(() => {})
  engagement.record('collect', 'recommend-swipe', paper.paper_id)
}

function handleSwipeUp() {
  const paper = currentPaper.value
  if (!paper) return
  engagement.record('view', 'recommend-detail', paper.paper_id)
  router.push(`/paper/${paper.paper_id}`)
}

function skip() { handleSwipeLeft() }
function like() { handleSwipeRight() }
function undo() {
  if (history.value.length === 0) return
  currentIndex.value = history.value.pop()!
}
function openDetail() {
  if (currentPaper.value) {
    engagement.record('view', 'recommend-detail', currentPaper.value.paper_id)
    router.push(`/paper/${currentPaper.value.paper_id}`)
  }
}
function askAI() {
  if (currentPaper.value) {
    router.push({ name: 'chat', query: { paperId: currentPaper.value.paper_id, title: currentPaper.value.short_title } })
  }
}
function resetCards() { currentIndex.value = 0; history.value = [] }

// Idea actions
function handleIdeaSwipeLeft() { skipIdea() }
function handleIdeaSwipeRight() { collectIdea() }
function handleIdeaSwipeUp() { openIdeaDetail() }

function skipIdea() {
  const idea = currentIdea.value
  ideaHistory.value.push(ideaIndex.value)
  ideaIndex.value++
  if (idea && isAuthenticated.value) {
    createIdeaFeedback({ candidate_id: idea.id, action: 'skip' }).catch(() => {})
  }
}

function collectIdea() {
  const idea = currentIdea.value
  if (!idea) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  ideaHistory.value.push(ideaIndex.value)
  ideaIndex.value++
  createIdeaFeedback({ candidate_id: idea.id, action: 'collect' }).catch(() => {})
  engagement.record('collect', 'idea-recommend', String(idea.id))
}

function openIdeaDetail() {
  if (currentIdea.value) {
    engagement.record('view', 'idea-recommend-open', String(currentIdea.value.id))
    router.push(`/idea/candidates/${currentIdea.value.id}`)
  }
}

function undoIdea() {
  if (ideaHistory.value.length === 0) return
  ideaIndex.value = ideaHistory.value.pop()!
}

function resetIdeas() { ideaIndex.value = 0; ideaHistory.value = [] }

function goLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath } })
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-hidden">
    <!-- Compact header: menu | mode pills | date | counter -->
    <div
      class="shrink-0 flex items-center gap-2 px-3 glass-header"
      style="padding-top: max(10px, env(safe-area-inset-top, 10px)); padding-bottom: 6px; min-height: 46px;"
    >
      <!-- Hamburger menu -->
      <button
        type="button"
        class="recommend-menu-btn"
        aria-label="打开菜单"
        @click="drawer.open()"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="3" y1="12" x2="21" y2="12"/>
          <line x1="3" y1="6" x2="21" y2="6"/>
          <line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <!-- Mode toggle pills -->
      <div class="flex items-center bg-bg-elevated rounded-full border border-border gap-0 shrink-0" style="padding: 2px;">
        <button
          type="button"
          class="mode-pill"
          :class="activeMode === 'paper' ? 'active' : 'inactive'"
          @click="activeMode = 'paper'"
        >论文</button>
        <button
          type="button"
          class="mode-pill"
          :class="activeMode === 'idea' ? 'active' : 'inactive'"
          @click="activeMode = 'idea'"
        >灵感</button>
      </div>

      <!-- Date selector -->
      <div class="flex-1 flex items-center justify-center min-w-0">
        <DateSelector
          v-if="dates.length > 0"
          :dates="dates"
          :model-value="selectedDate"
          @update:model-value="selectedDate = $event"
        />
      </div>

      <!-- Counter badge -->
      <div
        v-if="counterText"
        class="shrink-0 px-2 py-0.5 rounded-full bg-bg-elevated border border-border/60"
      >
        <span class="text-[10px] text-text-muted tabular-nums font-medium">{{ counterText }}</span>
      </div>
    </div>

    <!-- ===== PAPER MODE ===== -->
    <template v-if="activeMode === 'paper'">
      <!-- Card area -->
      <div class="flex-1 relative overflow-hidden min-h-0">
        <!-- Loading skeleton -->
        <div v-if="loading" class="absolute inset-0 mx-4 my-2">
          <div class="w-full h-full rounded-2xl bg-bg-card border border-border animate-pulse flex flex-col p-6 gap-4">
            <div class="flex justify-between items-center">
              <div class="h-7 w-32 rounded-full bg-bg-elevated" />
              <div class="h-11 w-11 rounded-full bg-bg-elevated" />
            </div>
            <div class="h-8 w-full rounded-xl bg-bg-elevated" />
            <div class="h-5 w-3/4 rounded-lg bg-bg-elevated" />
            <div class="h-16 w-full rounded-xl bg-bg-elevated" />
            <div class="flex-1" />
            <div class="h-4 w-24 mx-auto rounded bg-bg-elevated" />
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8">
          <div class="w-14 h-14 rounded-full bg-tinder-pink/10 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-pink">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <p class="text-[15px] text-text-primary font-medium text-center">{{ error }}</p>
          <button type="button" class="btn-primary max-w-[160px]" @click="loadDigest(selectedDate)">重试</button>
        </div>

        <!-- Quota exceeded -->
        <QuotaGate
          v-else-if="isQuotaExceeded && isActuallyLimited && quotaMessage"
          :message="quotaMessage"
          :show-login-cta="!isAuthenticated"
          @login="goLogin"
        />

        <!-- All swiped -->
        <div v-else-if="allSwiped" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="w-20 h-20 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-tinder-green">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div>
            <h2 class="text-lg font-bold text-text-primary">今日全部浏览完</h2>
            <p class="text-sm text-text-muted mt-1">共 {{ papers.length }} 篇，明天再来</p>
          </div>
          <button type="button" class="btn-ghost max-w-[180px]" @click="resetCards">重新浏览</button>
        </div>

        <!-- Current card — full-bleed, no side margins -->
        <div v-else-if="currentPaper" class="absolute inset-0">
          <SwipeCard
            :key="currentPaper.paper_id"
            :paper="currentPaper"
            @swipe-left="handleSwipeLeft"
            @swipe-right="handleSwipeRight"
            @swipe-up="handleSwipeUp"
            @ask-ai="askAI"
          />
        </div>

        <!-- No data -->
        <div v-else-if="!loading && selectedDate" class="absolute inset-0 flex items-center justify-center">
          <p class="text-sm text-text-muted">该日期暂无论文</p>
        </div>

        <!-- Action bar: overlaid at bottom with generous gradient fade -->
        <div
          v-if="currentPaper && !loading"
          class="absolute bottom-0 left-0 right-0 z-20 pointer-events-none"
          style="background: linear-gradient(to top, var(--color-bg-card) 40%, transparent 100%); padding-bottom: max(8px, env(safe-area-inset-bottom, 8px));"
        >
          <div class="pointer-events-auto">
            <ActionBar
              mode="paper"
              :can-undo="history.length > 0"
              @undo="undo"
              @skip="skip"
              @like="like"
              @detail="openDetail"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- ===== IDEA MODE ===== -->
    <template v-else-if="activeMode === 'idea'">
      <!-- Card area -->
      <div class="flex-1 relative overflow-hidden min-h-0">
        <!-- Not logged in -->
        <div v-if="!isAuthenticated" class="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
          <div class="w-20 h-20 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-tinder-purple">
              <circle cx="12" cy="8" r="4"/><path d="M6 20v-2a6 6 0 0 1 12 0v2"/>
            </svg>
          </div>
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-1">登录查看灵感推荐</h2>
            <p class="text-sm text-text-muted leading-relaxed">基于你的研究方向，每日推荐新灵感</p>
          </div>
          <button type="button" class="btn-primary max-w-[220px]" @click="goLogin">立即登录</button>
        </div>

        <!-- Loading skeleton -->
        <div v-else-if="ideaLoading" class="absolute inset-0 mx-4 my-2">
          <div class="w-full h-full rounded-2xl bg-bg-card border border-border animate-pulse flex flex-col p-6 gap-4">
            <div class="flex justify-between items-center">
              <div class="h-7 w-20 rounded-full bg-bg-elevated" />
              <div class="h-11 w-11 rounded-full bg-bg-elevated" />
            </div>
            <div class="h-8 w-full rounded-xl bg-bg-elevated" />
            <div class="h-5 w-3/4 rounded-lg bg-bg-elevated" />
            <div class="h-20 w-full rounded-xl bg-bg-elevated" />
            <div class="flex-1" />
            <div class="h-4 w-24 mx-auto rounded bg-bg-elevated" />
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="ideaError" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8">
          <div class="w-14 h-14 rounded-full bg-tinder-pink/10 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-pink">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <p class="text-[15px] text-text-primary font-medium text-center">{{ ideaError }}</p>
          <button type="button" class="btn-primary max-w-[160px]" @click="loadIdeaDigest(selectedDate)">重试</button>
        </div>

        <!-- Quota exceeded -->
        <QuotaGate
          v-else-if="isIdeaQuotaExceeded && isIdeaActuallyLimited"
          title="灵感查看受限"
          message="升级 Pro 账号可查看更多每日灵感推荐"
          :show-login-cta="false"
        />

        <!-- All swiped -->
        <div v-else-if="allIdeasSwiped" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="w-20 h-20 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-tinder-green">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div>
            <h2 class="text-lg font-bold text-text-primary">今日灵感全部浏览</h2>
            <p class="text-sm text-text-muted mt-1">共 {{ ideaCandidates.length }} 个，明天继续</p>
          </div>
          <button type="button" class="btn-ghost max-w-[180px]" @click="resetIdeas">重新浏览</button>
        </div>

        <!-- Idea card — full-bleed, no side margins -->
        <div v-else-if="currentIdea" class="absolute inset-0">
          <IdeaSwipeCard
            :key="currentIdea.id"
            :candidate="currentIdea"
            @swipe-left="handleIdeaSwipeLeft"
            @swipe-right="handleIdeaSwipeRight"
            @swipe-up="handleIdeaSwipeUp"
          />
        </div>

        <!-- No data -->
        <div v-else-if="!ideaLoading && selectedDate" class="absolute inset-0 flex items-center justify-center">
          <p class="text-sm text-text-muted">该日期暂无灵感推荐</p>
        </div>

        <!-- Action bar: overlaid at bottom with generous gradient fade -->
        <div
          v-if="isAuthenticated && currentIdea && !ideaLoading"
          class="absolute bottom-0 left-0 right-0 z-20 pointer-events-none"
          style="background: linear-gradient(to top, var(--color-bg-card) 40%, transparent 100%); padding-bottom: max(8px, env(safe-area-inset-bottom, 8px));"
        >
          <div class="pointer-events-auto">
            <ActionBar
              mode="idea"
              :can-undo="ideaHistory.length > 0"
              @undo="undoIdea"
              @skip="skipIdea"
              @like="collectIdea"
              @detail="openIdeaDetail"
            />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.recommend-menu-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
  transition: color 0.12s ease, background 0.12s ease;
}
.recommend-menu-btn:active {
  background: var(--color-bg-elevated);
  opacity: 0.8;
}
</style>
