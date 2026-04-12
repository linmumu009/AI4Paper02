<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => route.meta?.tab as string | undefined)

const tabs = [
  { key: 'recommend', path: '/recommend', label: '推荐' },
  { key: 'idea',      path: '/idea',      label: '灵感' },
  { key: 'knowledge', path: '/knowledge', label: '知识库' },
  { key: 'profile',   path: '/profile',   label: '我的' },
]
</script>

<template>
  <nav
    class="shrink-0 flex items-stretch border-t border-border glass-header"
    style="padding-bottom: max(8px, env(safe-area-inset-bottom, 8px));"
  >
    <!-- 推荐 -->
    <button
      type="button"
      class="tab-item"
      :class="{ active: activeTab === 'recommend' }"
      aria-label="推荐"
      @click="router.push('/recommend')"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
        <polyline points="9 22 9 12 15 12 15 22"/>
      </svg>
      <span>推荐</span>
    </button>

    <!-- 灵感 -->
    <button
      type="button"
      class="tab-item"
      :class="{ active: activeTab === 'idea' }"
      aria-label="灵感"
      @click="router.push('/idea')"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18h6"/>
        <path d="M10 22h4"/>
        <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1 4.5-3 6l-1 3H9l-1-3C6 13.5 5 11.5 5 9a7 7 0 0 1 7-7z"/>
      </svg>
      <span>灵感</span>
    </button>

    <!-- 知识库 -->
    <button
      type="button"
      class="tab-item"
      :class="{ active: activeTab === 'knowledge' }"
      aria-label="知识库"
      @click="router.push('/knowledge')"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      </svg>
      <span>知识库</span>
    </button>

    <!-- 我的 -->
    <button
      type="button"
      class="tab-item"
      :class="{ active: activeTab === 'profile' }"
      aria-label="我的"
      @click="router.push('/profile')"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
      </svg>
      <span>我的</span>
    </button>
  </nav>
</template>

<style scoped>
.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-height: 48px;
  padding: 7px 4px 6px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.01em;
  -webkit-tap-highlight-color: transparent;
  transition: color 0.15s ease;
}
.tab-item:active {
  opacity: 0.75;
}
.tab-item.active {
  color: var(--color-tinder-pink);
}
</style>
