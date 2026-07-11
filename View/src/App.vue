<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import Navbar from './components/Navbar.vue'
import GlobalChatDrawer from './components/GlobalChatDrawer.vue'
import FloatingActions from './components/FloatingActions.vue'
import EngagementToast from './components/EngagementToast.vue'
import AppToast from './components/AppToast.vue'
import AppErrorBoundary from './components/AppErrorBoundary.vue'
import GlobalSearchPalette from './components/GlobalSearchPalette.vue'
import { useRouter, useRoute } from 'vue-router'
import {
  trackSessionDuration,
  flushAnalytics,
  flushAnalyticsForPageHide,
} from './composables/useAnalytics'
import { useGlobalChat } from './composables/useGlobalChat'
import { useEngagement } from './composables/useEngagement'
import { useEntitlements } from './composables/useEntitlements'
import { invalidateAuthSession, isAuthenticated } from './stores/auth'
import { routeLoading, routeLoadError } from './router'

const router = useRouter()
const route = useRoute()
const { isOpen, chatDrawerWidthPx, messageSentSignal, researchRequest, compareRequest } = useGlobalChat()
const mainChatOffset = computed(() =>
  isOpen.value ? `${chatDrawerWidthPx.value}px` : '0px',
)
const engagement = useEngagement()
const { refreshEntitlements } = useEntitlements()

// Session duration tracking. Periodic events are cumulative snapshots sharing
// one ID; the backend keeps the maximum snapshot instead of summing duplicates.
const analyticsSessionId = globalThis.crypto?.randomUUID?.()
  ?? `session-${Date.now()}-${Math.random().toString(36).slice(2)}`
let accumulatedSessionSeconds = 0
let sessionActiveSince: number | null = document.visibilityState === 'visible' ? Date.now() : null
let sessionTimer: ReturnType<typeof setInterval> | null = null

function reportSessionSnapshot(pause = false) {
  const now = Date.now()
  if (sessionActiveSince !== null) {
    accumulatedSessionSeconds += (now - sessionActiveSince) / 1000
    sessionActiveSince = pause ? null : now
  }
  if (accumulatedSessionSeconds > 0) {
    trackSessionDuration(accumulatedSessionSeconds, analyticsSessionId)
  }
}

function handleVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    reportSessionSnapshot(true)
    flushAnalyticsForPageHide()
  } else if (sessionActiveSince === null) {
    sessionActiveSince = Date.now()
  }
}

function handlePageHide() {
  reportSessionSnapshot(true)
  flushAnalyticsForPageHide()
}

function handleAuthRequired() {
  const hadAuthenticatedSession = isAuthenticated.value
  invalidateAuthSession()
  if (!hadAuthenticatedSession || route.path === '/login' || route.path === '/register') return
  router.push({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

function reloadCurrentPage() {
  window.location.reload()
}

// Load engagement status and entitlements whenever the user becomes authenticated.
watch(isAuthenticated, (authed) => {
  if (authed) {
    engagement.loadStatus()
    refreshEntitlements()
  }
})

// Global analyze signal — ensures routes without their own watcher (Tutorial, Community,
// PaperDetail for research/compare, etc.) still credit the daily "analyze" task.
// Per-page record() calls in DailyDigest/PaperList are idempotent on the backend,
// so duplicate calls for the same action on the same day are safe.
watch(messageSentSignal, () => {
  if (isAuthenticated.value) engagement.record('analyze', 'global-chat')
})

watch(researchRequest, (req) => {
  if (req && isAuthenticated.value) engagement.record('analyze', 'global-research')
})

watch(compareRequest, (req) => {
  if (req && isAuthenticated.value) engagement.record('analyze', 'global-compare')
})

onMounted(() => {
  window.addEventListener('auth-required', handleAuthRequired)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('pagehide', handlePageHide)

  // Report session duration every 5 minutes
  sessionTimer = setInterval(() => {
    reportSessionSnapshot()
  }, 5 * 60 * 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('auth-required', handleAuthRequired)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('pagehide', handlePageHide)
  if (sessionTimer) clearInterval(sessionTimer)
  reportSessionSnapshot(true)
  flushAnalytics()
})
</script>

<template>
  <div class="h-screen flex flex-col bg-bg">
    <!-- Top nav bar -->
    <Navbar />
    <!-- Main content -->
    <main
      class="flex-1 overflow-hidden relative transition-[margin] duration-200 ease-out"
      :style="{ marginRight: mainChatOffset }"
    >
      <AppErrorBoundary>
        <router-view />
      </AppErrorBoundary>
      <Transition
        enter-active-class="transition-opacity duration-150"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-100"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="routeLoading || routeLoadError"
          class="absolute inset-0 z-40 flex items-center justify-center bg-bg/95 px-5 backdrop-blur-sm"
          :aria-live="routeLoadError ? 'assertive' : 'polite'"
          :role="routeLoadError ? 'alert' : 'status'"
        >
          <div v-if="routeLoadError" class="max-w-md rounded-2xl border border-tinder-pink/25 bg-bg-card p-6 text-center shadow-xl">
            <div class="mb-3 text-2xl" aria-hidden="true">⚠️</div>
            <h1 class="text-lg font-semibold text-text-primary">页面加载失败</h1>
            <p class="mt-2 text-sm leading-6 text-text-secondary">网络可能暂时中断，或页面资源已经更新。请重新加载后继续。</p>
            <button
              type="button"
              class="mt-5 rounded-full bg-brand-gradient px-5 py-2 text-sm font-semibold text-white"
              @click="reloadCurrentPage"
            >
              重新加载
            </button>
          </div>
          <div v-else class="w-full max-w-3xl" aria-label="页面加载中">
            <div class="mx-auto mb-5 h-9 w-44 animate-pulse rounded-xl bg-bg-elevated" />
            <div class="space-y-3 rounded-3xl border border-border bg-bg-card p-6 shadow-xl">
              <div class="h-5 w-2/3 animate-pulse rounded bg-bg-elevated" />
              <div class="h-3 w-full animate-pulse rounded bg-bg-elevated/80" />
              <div class="h-3 w-5/6 animate-pulse rounded bg-bg-elevated/80" />
              <div class="grid grid-cols-1 gap-3 pt-3 sm:grid-cols-2">
                <div class="h-24 animate-pulse rounded-2xl bg-bg-elevated/70" />
                <div class="h-24 animate-pulse rounded-2xl bg-bg-elevated/70" />
              </div>
            </div>
            <p class="mt-4 text-center text-xs text-text-muted">正在加载研究工作区…</p>
          </div>
        </div>
      </Transition>
      <GlobalChatDrawer />
      <FloatingActions />
      <EngagementToast />
      <AppToast />
      <GlobalSearchPalette />
    </main>
  </div>
</template>
