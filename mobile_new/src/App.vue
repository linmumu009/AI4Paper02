<script setup lang="ts">
import { watch, onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NavigationDrawer from './components/NavigationDrawer.vue'
import EngagementToast from './components/EngagementToast.vue'
import TabBar from './components/TabBar.vue'
import { isAuthenticated } from '@shared/stores/auth'
import { useEngagement } from '@shared/composables/useEngagement'
import { useEntitlements } from '@shared/composables/useEntitlements'
import { trackSessionDuration, flushAnalytics } from '@shared/composables/useAnalytics'

const route = useRoute()
const router = useRouter()
const engagement = useEngagement()
const { refreshEntitlements } = useEntitlements()

// Show the bottom TabBar only on the four primary tab routes
const TAB_ROUTES = new Set(['recommend', 'idea', 'knowledge', 'profile'])
const showTabBar = computed(() => TAB_ROUTES.has(route.name as string))

// Directional transition based on route depth
const ROUTE_DEPTH: Record<string, number> = {
  recommend: 0,
  idea: 0,
  knowledge: 0,
  profile: 0,
  tutorial: 1,
}
const transitionName = ref('slide-forward')

router.afterEach((to, from) => {
  const toDepth = ROUTE_DEPTH[to.name as string] ?? 1
  const fromDepth = ROUTE_DEPTH[from.name as string] ?? 1
  if (toDepth === fromDepth && toDepth === 0) {
    transitionName.value = 'fade'
  } else if (toDepth >= fromDepth) {
    transitionName.value = 'slide-forward'
  } else {
    transitionName.value = 'slide-back'
  }
})

function handleAuthRequired() {
  if (route.path === '/login' || route.path === '/register') return
  router.push({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

watch(isAuthenticated, (authed) => {
  if (authed) {
    engagement.loadStatus()
    refreshEntitlements()
  }
})

const sessionStart = Date.now()
let sessionTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  window.addEventListener('auth-required', handleAuthRequired)
  sessionTimer = setInterval(() => {
    const duration = (Date.now() - sessionStart) / 1000
    trackSessionDuration(duration)
  }, 5 * 60 * 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('auth-required', handleAuthRequired)
  if (sessionTimer) clearInterval(sessionTimer)
  trackSessionDuration((Date.now() - sessionStart) / 1000)
  flushAnalytics()
})

</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Global navigation drawer (rendered once, above everything) -->
    <NavigationDrawer />

    <main class="flex-1 overflow-hidden relative min-h-0">
      <router-view v-slot="{ Component }">
        <Transition :name="transitionName">
          <keep-alive :include="['RecommendView', 'KnowledgeView', 'ProfileView']">
            <component :is="Component" :key="route.fullPath" />
          </keep-alive>
        </Transition>
      </router-view>
    </main>
    <!-- Bottom tab bar: shown only on primary tab routes for fast switching -->
    <TabBar v-if="showTabBar" />
    <EngagementToast />
  </div>
</template>
