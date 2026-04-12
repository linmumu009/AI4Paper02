<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import Navbar from './components/Navbar.vue'
import GlobalChatDrawer from './components/GlobalChatDrawer.vue'
import FloatingActions from './components/FloatingActions.vue'
import EngagementToast from './components/EngagementToast.vue'
import AppToast from './components/AppToast.vue'
import AppErrorBoundary from './components/AppErrorBoundary.vue'
import { useRouter, useRoute } from 'vue-router'
import { trackSessionDuration, flushAnalytics } from './composables/useAnalytics'
import { useGlobalChat } from './composables/useGlobalChat'
import { useEngagement } from './composables/useEngagement'
import { useEntitlements } from './composables/useEntitlements'
import { isAuthenticated } from './stores/auth'

const router = useRouter()
const route = useRoute()
const { isOpen, chatDrawerWidthPx, messageSentSignal, researchRequest, compareRequest } = useGlobalChat()
const mainChatOffset = computed(() =>
  isOpen.value ? `${chatDrawerWidthPx.value}px` : '0px',
)
const engagement = useEngagement()
const { refreshEntitlements } = useEntitlements()

// Session duration tracking
const sessionStart = Date.now()
let sessionTimer: ReturnType<typeof setInterval> | null = null

function handleAuthRequired() {
  if (route.path === '/login' || route.path === '/register') return
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

  // Report session duration every 5 minutes
  sessionTimer = setInterval(() => {
    const duration = (Date.now() - sessionStart) / 1000
    trackSessionDuration(duration)
  }, 5 * 60 * 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('auth-required', handleAuthRequired)
  if (sessionTimer) clearInterval(sessionTimer)
  // Final session duration report
  const duration = (Date.now() - sessionStart) / 1000
  trackSessionDuration(duration)
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
