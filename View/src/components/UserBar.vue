<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { currentUser, currentTier, isAuthenticated, logout } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const showUserMenu = ref(false)
const userBarRef = ref<HTMLElement | null>(null)

// Avatar: derive a deterministic color from the username
const AVATAR_COLORS = [
  '#7c3aed', '#2563eb', '#059669', '#d97706', '#dc2626',
  '#db2777', '#0891b2', '#65a30d', '#9333ea', '#ea580c',
]

function strHash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0
  }
  return h
}

const avatarColor = computed(() => {
  const name = currentUser.value?.username || ''
  return AVATAR_COLORS[strHash(name) % AVATAR_COLORS.length]
})

const initial = computed(() => {
  const name = currentUser.value?.username || ''
  return name.charAt(0).toUpperCase() || '?'
})

function toggleUserMenu() {
  showUserMenu.value = !showUserMenu.value
}

function closeUserMenu() {
  showUserMenu.value = false
}

function handleClickOutside(e: MouseEvent) {
  if (userBarRef.value && !userBarRef.value.contains(e.target as Node)) {
    closeUserMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})

function goCommunity() {
  closeUserMenu()
  router.push('/community')
}

function goUserProfile() {
  closeUserMenu()
  router.push('/profile')
}

function goUserAdvancedSettings() {
  closeUserMenu()
  router.push('/advanced-settings')
}

function goTutorial() {
  closeUserMenu()
  router.push('/tutorial')
}

async function doUserLogout() {
  closeUserMenu()
  await logout()
  if (
    route.name === 'note-editor' ||
    route.name === 'profile' ||
    route.name === 'advanced-settings'
  ) {
    await router.replace('/')
  }
}

function goLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath } })
}
</script>

<template>
  <div ref="userBarRef" class="relative border-t border-border shrink-0">
    <!-- Authenticated: user bar button -->
    <template v-if="isAuthenticated">
      <button
        class="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-bg-hover transition-colors cursor-pointer bg-transparent border-none text-left"
        @click.stop="toggleUserMenu"
      >
        <!-- Colored initial avatar -->
        <div
          class="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0 select-none"
          :style="{ backgroundColor: avatarColor }"
        >
          {{ initial }}
        </div>
        <!-- Username -->
        <span class="flex-1 min-w-0 text-xs font-medium text-text-secondary truncate">
          {{ currentUser?.username }}
        </span>
        <!-- Tier badge -->
        <span
          v-if="currentTier === 'free'"
          class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold border border-border text-text-muted select-none"
        >普通</span>
        <span
          v-else-if="currentTier === 'pro'"
          class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold text-white select-none"
          style="background: linear-gradient(135deg, #f59e0b, #f97316);"
        >PRO</span>
        <span
          v-else-if="currentTier === 'pro_plus'"
          class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold text-white select-none"
          style="background: linear-gradient(135deg, #fd267a, #a855f7);"
        >PRO+</span>
        <!-- Chevron -->
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3 h-3 text-text-muted shrink-0 transition-transform duration-200"
          :class="showUserMenu ? 'rotate-180' : ''"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="18 15 12 9 6 15" />
        </svg>
      </button>

      <!-- Dropdown menu (expands upward) -->
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 translate-y-1"
      >
        <div
          v-if="showUserMenu"
          class="absolute bottom-full left-0 right-0 mb-1 mx-2 py-1 bg-bg-card border border-border rounded-lg shadow-xl z-50"
        >
          <button
            class="w-full px-4 py-2 text-left text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            @click="goCommunity"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            社区
          </button>
          <button
            class="w-full px-4 py-2 text-left text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            @click="goUserProfile"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
            个人中心
          </button>
          <button
            class="w-full px-4 py-2 text-left text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            @click="goUserAdvancedSettings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            高级设置
          </button>
          <button
            class="w-full px-4 py-2 text-left text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            @click="goTutorial"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
            使用教程
          </button>
          <div class="mx-3 my-1 border-t border-border"></div>
          <button
            class="w-full px-4 py-2 text-left text-xs text-text-muted hover:bg-bg-hover hover:text-tinder-pink transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            @click="doUserLogout"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            退出登录
          </button>
        </div>
      </Transition>
    </template>

    <!-- Not authenticated: login button -->
    <template v-else>
      <button
        class="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors cursor-pointer bg-transparent border-none"
        @click="goLogin"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><polyline points="10 17 15 12 10 7" /><line x1="15" y1="12" x2="3" y2="12" />
        </svg>
        登录
      </button>
    </template>
  </div>
</template>
