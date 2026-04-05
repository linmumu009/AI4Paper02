<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import Navbar from './components/Navbar.vue'
import GlobalChatDrawer from './components/GlobalChatDrawer.vue'
import FloatingActions from './components/FloatingActions.vue'
import { useRouter, useRoute } from 'vue-router'
import { trackSessionDuration, flushAnalytics } from './composables/useAnalytics'
import { useGlobalChat } from './composables/useGlobalChat'

const router = useRouter()
const route = useRoute()
const { isOpen, chatDrawerWidthPx } = useGlobalChat()
const mainChatOffset = computed(() =>
  isOpen.value ? `${chatDrawerWidthPx.value}px` : '0px',
)

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
      <router-view />
      <GlobalChatDrawer />
      <FloatingActions />
    </main>
  </div>
</template>
