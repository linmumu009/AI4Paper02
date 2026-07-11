<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import Navbar from './components/Navbar.vue'
import GlobalChatDrawer from './components/GlobalChatDrawer.vue'
import FloatingActions from './components/FloatingActions.vue'
import EngagementToast from './components/EngagementToast.vue'
import AppToast from './components/AppToast.vue'
import AppErrorBoundary from './components/AppErrorBoundary.vue'
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
      <GlobalChatDrawer />
      <FloatingActions />
      <EngagementToast />
      <AppToast />
    </main>
  </div>
</template>
