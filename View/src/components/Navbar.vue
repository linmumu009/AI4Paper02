<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'
import { isDark, toggleTheme } from '../stores/theme'
import { API_ORIGIN, fetchUnreadAnnouncementCount, markAllAnnouncementsRead, fetchAnnouncements } from '../api'
import type { Announcement } from '../types/paper'
import { useEngagement } from '../composables/useEngagement'
import EngagementProgressBar from './EngagementProgressBar.vue'

// 在 Tauri 桌面端（API_ORIGIN 有值）时隐藏下载安装包按钮
const isDesktop = !!API_ORIGIN

const route = useRoute()
const router = useRouter()

// ── 桌面端自动更新 ────────────────────────────────────────────────────────────
const _tauriInvoke: ((cmd: string, args?: Record<string, unknown>) => Promise<any>) | null =
  (window as any).__TAURI_INTERNALS__?.invoke ?? null

type UpdateState = 'idle' | 'checking' | 'available' | 'none' | 'installing' | 'error'
const updateState = ref<UpdateState>('idle')
const updateVersion = ref('')
const updateBody = ref('')

async function checkForUpdate() {
  if (!_tauriInvoke || updateState.value === 'checking' || updateState.value === 'installing') return
  updateState.value = 'checking'
  try {
    const info = await _tauriInvoke('check_update')
    if (info.available) {
      updateState.value = 'available'
      updateVersion.value = info.version || ''
      updateBody.value = info.body || ''
    } else {
      updateState.value = 'none'
      setTimeout(() => { updateState.value = 'idle' }, 3000)
    }
  } catch {
    updateState.value = 'error'
    setTimeout(() => { updateState.value = 'idle' }, 3000)
  }
}

async function installUpdate() {
  if (!_tauriInvoke) return
  updateState.value = 'installing'
  try {
    await _tauriInvoke('install_update')
  } catch {
    updateState.value = 'error'
    setTimeout(() => { updateState.value = 'idle' }, 3000)
  }
}

const navItems = [
  {
    to: '/',
    label: '发现',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12z"/></svg>`,
  },
  {
    to: '/inspiration',
    label: '灵感',
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>`,
  },
]

// ---------------------------------------------------------------------------
// Announcement bell + popover
// ---------------------------------------------------------------------------
const unreadCount = ref(0)
const showAnnouncementPopover = ref(false)
const recentAnnouncements = ref<Announcement[]>([])
const announcementsLoading = ref(false)
const announcementPopoverRef = ref<HTMLElement | null>(null)

const unreadLabel = computed(() => (unreadCount.value > 99 ? '99+' : String(unreadCount.value)))

async function refreshUnreadCount() {
  if (!isAuthenticated.value) return
  try {
    const res = await fetchUnreadAnnouncementCount()
    unreadCount.value = res.count
  } catch {
    // silently ignore polling errors
  }
}

async function openAnnouncementPopover() {
  if (showAnnouncementPopover.value) {
    showAnnouncementPopover.value = false
    return
  }
  showAnnouncementPopover.value = true
  announcementsLoading.value = true
  try {
    const res = await fetchAnnouncements({ limit: 5 })
    recentAnnouncements.value = res.announcements
    if (unreadCount.value > 0) {
      await markAllAnnouncementsRead()
      unreadCount.value = 0
    }
  } catch {
    // ignore
  } finally {
    announcementsLoading.value = false
  }
}

function closeAnnouncementPopover() {
  showAnnouncementPopover.value = false
}

function goAllAnnouncements() {
  closeAnnouncementPopover()
  router.push('/profile?tab=announcements')
}

function goToAnnouncement(id: number) {
  closeAnnouncementPopover()
  router.push(`/announcements/${id}`)
}

function announcementTagLabel(tag: string): string {
  const map: Record<string, string> = {
    important: '重要', general: '一般', update: '更新', maintenance: '维护',
  }
  return map[tag] || tag
}

function announcementTagClass(tag: string): string {
  const map: Record<string, string> = {
    important: 'bg-red-500/15 text-red-400 border-red-500/20',
    general: 'bg-gray-500/15 text-text-muted border-gray-500/20',
    update: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    maintenance: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  }
  return map[tag] || 'bg-gray-500/15 text-text-muted border-gray-500/20'
}

function formatAnnouncementDate(ts: string): string {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return ts
  }
}

function handleClickOutsideAnnouncement(e: MouseEvent) {
  if (announcementPopoverRef.value && !announcementPopoverRef.value.contains(e.target as Node)) {
    closeAnnouncementPopover()
  }
}

let _pollTimer: ReturnType<typeof setInterval> | null = null

function _handleVisibilityChange() {
  if (document.visibilityState === 'visible') {
    refreshUnreadCount()
  }
}

// P7 + C3: Engagement — badge display and global progress bar
const engagement = useEngagement()
const highestBadge = computed(() => engagement.highestBadge.value)
const engTaskItems = computed(() => engagement.taskItems.value)
const engAllDone = computed(() => engagement.allDone.value)
const engHasNew = computed(() => engagement.hasNewRewards.value)
const engAllDoneVal = computed(() => engagement.allDone.value)
const engTasksDone = computed(() => {
  const p = engagement.status.value?.progress
  return p ? `${p.progress_count}/${p.target_count}` : '0/3'
})

onMounted(async () => {
  await ensureAuthInitialized()
  await refreshUnreadCount()
  // Reduce polling interval when tab is hidden using the Page Visibility API
  _pollTimer = setInterval(() => {
    if (document.visibilityState === 'visible') refreshUnreadCount()
  }, 90_000)
  document.addEventListener('visibilitychange', _handleVisibilityChange)
  document.addEventListener('click', handleClickOutsideAnnouncement)
})

onBeforeUnmount(() => {
  if (_pollTimer) clearInterval(_pollTimer)
  document.removeEventListener('visibilitychange', _handleVisibilityChange)
  document.removeEventListener('click', handleClickOutsideAnnouncement)
})
</script>

<template>
  <nav class="h-12 sm:h-14 flex items-center justify-between px-3 sm:px-5 bg-bg-sidebar border-b border-border">
    <!-- Logo -->
    <router-link to="/" class="flex items-center gap-1.5 no-underline shrink-0">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"
           class="w-7 h-7 sm:w-8 sm:h-8 flex-shrink-0" aria-hidden="true">
        <defs>
          <linearGradient id="nav-fg" x1="256" y1="273" x2="256" y2="88" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stop-color="#fd267a"/>
            <stop offset="100%" stop-color="#ff6036"/>
          </linearGradient>
          <linearGradient id="nav-ig" x1="256" y1="268" x2="256" y2="133" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stop-color="#ff8c00" stop-opacity="0.9"/>
            <stop offset="100%" stop-color="#ffe066" stop-opacity="0.55"/>
          </linearGradient>
        </defs>
        <path d="M148,260 L320,260 L364,304 L364,426 L148,426 Z"
              fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.25)" stroke-width="4"/>
        <path d="M320,260 L364,260 L364,304 Z"
              fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" stroke-width="3"/>
        <rect x="172" y="320" width="114" height="10" rx="5" fill="rgba(255,255,255,0.20)"/>
        <rect x="172" y="346" width="152" height="10" rx="5" fill="rgba(255,255,255,0.14)"/>
        <rect x="172" y="372" width="96"  height="10" rx="5" fill="rgba(255,255,255,0.11)"/>
        <path d="M170,273 C150,243 145,206 158,170 C166,146 182,133 192,146
                 C200,156 197,174 206,168 C214,161 212,140 221,123
                 C230,105 246,96 256,88 C266,96 282,105 291,123
                 C300,140 298,161 306,168 C315,174 312,156 320,146
                 C330,133 346,146 354,170 C367,206 362,243 342,273 Z"
              fill="url(#nav-fg)"/>
        <path d="M210,268 C198,244 195,214 206,188 C213,170 227,162 233,174
                 C237,183 234,197 241,193 C248,188 245,170 253,154
                 C256,145 256,136 256,133 C256,136 256,145 259,154
                 C267,170 264,188 271,193 C278,197 275,183 279,174
                 C285,162 299,170 306,188 C317,214 314,244 302,268 Z"
              fill="url(#nav-ig)" opacity="0.65"/>
      </svg>
      <span class="text-lg sm:text-xl gradient-text font-bold tracking-tight">AI4Papers</span>
    </router-link>

    <!-- Center nav icons -->
    <div class="flex items-center gap-1 sm:gap-2">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :title="item.label"
        class="relative flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-xl no-underline transition-all duration-200 group"
        :class="(item.to === '/' ? route.path === '/' : route.path.startsWith(item.to))
          ? 'text-tinder-pink'
          : 'text-text-muted hover:text-text-secondary'"
      >
        <span
          class="w-[18px] h-[18px] sm:w-5 sm:h-5 flex items-center justify-center transition-all duration-200"
          v-html="item.svg"
        />
        <span class="text-[10px] font-medium leading-none tracking-wide hidden sm:block">{{ item.label }}</span>
        <!-- Active indicator dot -->
        <span
          v-if="item.to === '/' ? route.path === '/' : route.path.startsWith(item.to)"
          class="absolute bottom-0 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-tinder-pink"
        />
      </router-link>
    </div>

    <!-- Right auth area -->
    <div class="flex items-center justify-end gap-2 shrink-0">
      <!-- Tutorial entry -->
      <router-link
        to="/tutorial"
        title="使用教程"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 no-underline"
        :class="route.path === '/tutorial'
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
      </router-link>

      <!-- Download installer button (web-only; hidden in Tauri desktop) -->
      <a
        v-if="!isDesktop"
        href="/api/download/latest-installer"
        download
        title="下载客户端安装包"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 no-underline text-text-muted hover:text-text-secondary hover:bg-bg-hover"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </a>

      <!-- Workbench entry button -->
      <router-link
        to="/workbench"
        title="工作台"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 no-underline"
        :class="route.path.startsWith('/workbench') || route.path.startsWith('/idea')
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/>
        </svg>
      </router-link>

      <!-- 检查更新按钮（桌面端专属） -->
      <button
        v-if="isDesktop"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 cursor-pointer bg-transparent border-none"
        :class="updateState === 'available'
          ? 'text-tinder-green animate-pulse'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
        :title="updateState === 'available'
          ? `发现新版本 ${updateVersion}，点击安装`
          : updateState === 'checking' ? '检查中…'
          : updateState === 'installing' ? '安装中…'
          : updateState === 'none' ? '已是最新版本'
          : updateState === 'error' ? '检查失败'
          : '检查更新'"
        :disabled="updateState === 'checking' || updateState === 'installing'"
        @click="updateState === 'available' ? installUpdate() : checkForUpdate()"
      >
        <!-- 有更新：向下箭头（安装）-->
        <svg v-if="updateState === 'available'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        <!-- 检查中 / 安装中：旋转圆圈 -->
        <svg v-else-if="updateState === 'checking' || updateState === 'installing'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px] animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        <!-- 默认：刷新图标 -->
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>

      <!-- Mobile engagement icon (xs only — shows daily progress + new indicator) -->
      <router-link
        v-if="isAuthenticated && engagement.status.value"
        to="/profile?tab=achievements"
        title="研究激励进度"
        class="sm:hidden relative w-8 h-8 flex items-center justify-center rounded-full no-underline transition-all duration-200 hover:bg-bg-hover"
        :class="engAllDoneVal ? 'text-tinder-gold' : 'text-text-muted'"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="8 21 12 17 16 21"/><line x1="12" y1="17" x2="12" y2="11"/><path d="M7 4H2v3a5 5 0 0 0 5 5h0"/><path d="M17 4h5v3a5 5 0 0 1-5 5h0"/><rect x="7" y="2" width="10" height="9" rx="1"/>
        </svg>
        <!-- Progress fraction badge -->
        <span
          class="absolute -bottom-0.5 -right-0.5 min-w-[15px] h-[13px] px-0.5 flex items-center justify-center rounded-full text-[8px] font-bold leading-none select-none"
          :class="engAllDoneVal ? 'bg-tinder-gold text-white' : 'bg-bg-elevated text-text-muted border border-border'"
        >{{ engTasksDone }}</span>
        <!-- NEW reward dot -->
        <span
          v-if="engHasNew"
          class="absolute top-0 right-0 w-2 h-2 rounded-full bg-[#f59e0b]"
        />
      </router-link>

      <!-- C3: Global engagement progress bar (authenticated only, desktop) -->
      <div v-if="isAuthenticated && engagement.status.value" class="hidden sm:block">
        <EngagementProgressBar
          :task-items="engTaskItems"
          :streak="engagement.status.value?.streak"
          :all-done="engAllDone"
        />
      </div>

      <!-- P7: Highest honorary badge (authenticated, earned badge only; hidden when progress bar is visible since bar is more informative) -->
      <router-link
        v-if="isAuthenticated && highestBadge && !engagement.status.value"
        to="/profile?tab=achievements"
        :title="highestBadge.name"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full no-underline transition-all duration-200 hover:bg-bg-hover"
      >
        <span class="text-base leading-none select-none">{{ highestBadge.emoji }}</span>
      </router-link>

      <!-- Announcement bell (authenticated only) -->
      <div v-if="isAuthenticated" ref="announcementPopoverRef" class="relative">
        <button
          class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 cursor-pointer bg-transparent border-none relative"
          :class="showAnnouncementPopover
            ? 'text-tinder-pink bg-bg-elevated'
            : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
          title="公告"
          @click.stop="openAnnouncementPopover"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <!-- Unread badge -->
          <span
            v-if="unreadCount > 0"
            class="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold leading-none select-none"
          >{{ unreadLabel }}</span>
        </button>

        <!-- Announcement popover -->
        <Transition
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="opacity-0 scale-95 -translate-y-1"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition duration-100 ease-in"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-95 -translate-y-1"
        >
          <div
            v-if="showAnnouncementPopover"
            class="absolute right-0 top-full mt-2 w-80 bg-bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden"
            @click.stop
          >
            <!-- Popover header -->
            <div class="px-4 py-3 border-b border-border flex items-center justify-between">
              <span class="text-sm font-semibold text-text-primary flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                </svg>
                公告
              </span>
            </div>

            <!-- Loading -->
            <div v-if="announcementsLoading" class="flex items-center justify-center py-8">
              <svg class="w-5 h-5 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
              </svg>
            </div>

            <!-- Empty -->
            <div v-else-if="recentAnnouncements.length === 0" class="py-8 text-center text-sm text-text-muted">
              暂无公告
            </div>

            <!-- List -->
            <div v-else class="divide-y divide-border/60">
              <div
                v-for="item in recentAnnouncements"
                :key="item.id"
                class="px-4 py-3 flex items-start gap-2.5 hover:bg-bg-hover transition-colors cursor-pointer"
                @click="goToAnnouncement(item.id)"
              >
                <!-- Unread dot -->
                <span
                  v-if="!item.is_read"
                  class="mt-1.5 w-1.5 h-1.5 rounded-full bg-tinder-pink shrink-0"
                />
                <span v-else class="mt-1.5 w-1.5 h-1.5 shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="text-xs font-semibold text-text-primary truncate">{{ item.title }}</span>
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium shrink-0"
                      :class="announcementTagClass(item.tag)"
                    >{{ announcementTagLabel(item.tag) }}</span>
                  </div>
                  <p class="text-[11px] text-text-muted mt-0.5">{{ formatAnnouncementDate(item.created_at) }}</p>
                </div>
              </div>
            </div>

            <!-- Footer link -->
            <div class="px-4 py-2.5 border-t border-border">
              <button
                class="w-full text-xs text-text-muted hover:text-tinder-pink transition-colors text-center bg-transparent border-none cursor-pointer py-0.5"
                @click="goAllAnnouncements"
              >查看全部公告 →</button>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Login / Register buttons (unauthenticated only) -->
      <template v-if="!isAuthenticated">
        <router-link
          :to="{ path: '/login', query: { redirect: route.fullPath } }"
          class="hidden sm:flex items-center px-3 py-1.5 rounded-lg text-xs font-medium text-text-secondary border border-border hover:border-tinder-pink/50 hover:text-text-primary transition-colors no-underline"
        >登录</router-link>
        <router-link
          :to="{ path: '/register', query: { redirect: route.fullPath } }"
          class="flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold text-white border-none bg-brand-gradient hover:opacity-90 transition-opacity no-underline"
        >注册</router-link>
      </template>

      <!-- Theme toggle -->
      <button
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover transition-all duration-200 cursor-pointer bg-transparent border-none"
        :title="isDark ? '切换到日间模式' : '切换到夜间模式'"
        @click="toggleTheme"
      >
        <!-- Sun icon (shown in dark mode → click to go light) -->
        <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px] transition-transform duration-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
        <!-- Moon icon (shown in light mode → click to go dark) -->
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px] transition-transform duration-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

    </div>
  </nav>
</template>
