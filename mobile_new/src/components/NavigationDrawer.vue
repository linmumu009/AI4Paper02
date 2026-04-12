<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDrawer } from '@/composables/useDrawer'
import { isAuthenticated, currentUser, isAdmin } from '@shared/stores/auth'

const route = useRoute()
const router = useRouter()
const drawer = useDrawer()

function navigate(path: string) {
  drawer.close()
  router.push(path)
}

const currentPath = computed(() => route.path)

function isActive(path: string): boolean {
  if (path === '/recommend') return currentPath.value === '/recommend' || currentPath.value === '/'
  return currentPath.value.startsWith(path)
}

const userInitial = computed(() => {
  const name = currentUser.value?.nickname || currentUser.value?.username || ''
  return name.charAt(0).toUpperCase() || '?'
})

const userName = computed(() =>
  currentUser.value?.nickname || currentUser.value?.username || '未登录'
)

const tierLabel = computed(() => {
  const tier = currentUser.value?.tier
  if (tier === 'pro_plus') return 'Pro+'
  if (tier === 'pro') return 'Pro'
  if (isAuthenticated.value) return 'Free'
  return ''
})

const tierColor = computed(() => {
  const tier = currentUser.value?.tier
  if (tier === 'pro_plus') return 'text-tinder-purple'
  if (tier === 'pro') return 'text-tinder-gold'
  return 'text-text-muted'
})
</script>

<template>
  <!-- Backdrop -->
  <Transition name="drawer-backdrop">
    <div
      v-if="drawer.isOpen.value"
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]"
      @click="drawer.close()"
    />
  </Transition>

  <!-- Drawer panel -->
  <Transition name="drawer-slide">
    <nav
      v-if="drawer.isOpen.value"
      class="fixed inset-y-0 left-0 z-50 w-72 flex flex-col bg-bg-sidebar border-r border-border overflow-y-auto"
      style="padding-top: max(16px, env(safe-area-inset-top, 16px)); padding-bottom: max(24px, env(safe-area-inset-bottom, 24px));"
    >
      <!-- User section -->
      <div class="px-4 pb-5 mb-1">
        <div v-if="isAuthenticated" class="flex items-center gap-3">
          <div
            class="w-11 h-11 rounded-full flex items-center justify-center text-base font-bold text-white shrink-0"
            style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
          >
            {{ userInitial }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-text-primary truncate">{{ userName }}</p>
            <p v-if="tierLabel" class="text-[11px] font-medium" :class="tierColor">{{ tierLabel }}</p>
          </div>
          <!-- Close button -->
          <button
            type="button"
            class="drawer-close-btn"
            aria-label="关闭菜单"
            @click="drawer.close()"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <div v-else class="flex items-center justify-between gap-3">
          <div
            class="w-11 h-11 rounded-full flex items-center justify-center shrink-0 bg-bg-elevated border border-border"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <button
            type="button"
            class="flex-1 py-2 rounded-xl text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
            @click="navigate('/login')"
          >登录 / 注册</button>
          <button
            type="button"
            class="drawer-close-btn"
            aria-label="关闭菜单"
            @click="drawer.close()"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="drawer-divider" />

      <!-- Primary nav -->
      <div class="px-2 py-2">
        <button type="button" class="drawer-item" :class="{ active: isActive('/recommend') }" @click="navigate('/recommend')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <span>推荐</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/knowledge') }" @click="navigate('/knowledge')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
          <span>知识库</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/compare-library') }" @click="navigate('/compare-library')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-blue);">
            <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
          <span>对比库</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/research-library') }" @click="navigate('/research-library')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-purple);">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <span>研究库</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/idea') && !currentPath.startsWith('/idea/lab') && !currentPath.startsWith('/idea/atoms') && !currentPath.startsWith('/idea/eval') }" @click="navigate('/idea')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 1 7 7c0 2.5-1 4.5-3 6l-1 3H9l-1-3C6 13.5 5 11.5 5 9a7 7 0 0 1 7-7z"/>
          </svg>
          <span>灵感管理</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/my-papers') }" @click="navigate('/my-papers')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          <span>我的论文</span>
        </button>
      </div>

      <div class="drawer-divider" />

      <!-- Tools -->
      <div class="px-2 py-2">
        <p class="drawer-section-label">工具</p>
        <button type="button" class="drawer-item" :class="{ active: isActive('/chat') }" @click="navigate('/chat')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-purple);">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span>AI 对话</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/research') }" @click="navigate('/research')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-purple);">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <span>深度研究</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/compare') }" @click="navigate('/compare')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-blue);">
            <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
          <span>论文对比</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/idea/lab') }" @click="navigate('/idea/lab')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-pink);">
            <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>
          </svg>
          <span>灵感实验室</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/idea/atoms') }" @click="navigate('/idea/atoms')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-gold);">
            <circle cx="12" cy="12" r="1"/><path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5z"/><path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5z"/>
          </svg>
          <span>原子库</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/knowledge/auto-classify') }" @click="navigate('/knowledge/auto-classify')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-green);">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
          </svg>
          <span>自动分类</span>
        </button>
      </div>

      <div class="drawer-divider" />

      <!-- Community & info -->
      <div class="px-2 py-2">
        <p class="drawer-section-label">社区</p>
        <button type="button" class="drawer-item" :class="{ active: isActive('/community') }" @click="navigate('/community')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          <span>社区</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/announcements') }" @click="navigate('/announcements')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M22 17H2a3 3 0 0 0 3-3V9a7 7 0 0 1 14 0v5a3 3 0 0 0 3 3zm-8.27 4a2 2 0 0 1-3.46 0"/>
          </svg>
          <span>公告</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/tutorial') }" @click="navigate('/tutorial')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span>使用教程</span>
        </button>
      </div>

      <div class="drawer-divider" />

      <!-- Account -->
      <div class="px-2 py-2">
        <p class="drawer-section-label">账号</p>
        <button type="button" class="drawer-item" :class="{ active: isActive('/profile') }" @click="navigate('/profile')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
          </svg>
          <span>个人中心</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/subscription') }" @click="navigate('/subscription')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-gold);">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          <span>订阅管理</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/achievements') }" @click="navigate('/achievements')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-pink);">
            <circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>
          </svg>
          <span>成就</span>
        </button>
        <button type="button" class="drawer-item" :class="{ active: isActive('/settings') }" @click="navigate('/settings')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>高级设置</span>
        </button>
      </div>

      <!-- Admin section (visible to admin/superadmin only) -->
      <template v-if="isAdmin">
        <div class="drawer-divider" />
        <div class="px-2 py-2">
          <p class="drawer-section-label" style="color: var(--color-tinder-pink);">管理员</p>
          <button type="button" class="drawer-item" :class="{ active: isActive('/admin') }" @click="navigate('/admin')">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drawer-icon" style="color: var(--color-tinder-pink);">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span>管理控制台</span>
          </button>
        </div>
      </template>
    </nav>
  </Transition>
</template>

<style scoped>
.drawer-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-align: left;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.12s ease, color 0.12s ease;
}
.drawer-item:active {
  opacity: 0.75;
}
.drawer-item.active {
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-gradient-start) 12%, transparent);
}
.drawer-item.active .drawer-icon {
  color: var(--color-gradient-start);
}
.drawer-icon {
  flex-shrink: 0;
  color: var(--color-text-muted);
  transition: color 0.12s ease;
}
.drawer-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 16px;
}
.drawer-section-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 14px 6px;
  margin: 0;
}
.drawer-close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: none;
  background: var(--color-bg-elevated);
  color: var(--color-text-muted);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
  transition: color 0.12s ease;
}
.drawer-close-btn:active {
  opacity: 0.7;
}

/* Transitions */
.drawer-backdrop-enter-active,
.drawer-backdrop-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(-100%);
}
</style>
