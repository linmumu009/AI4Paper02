<script setup lang="ts">
import { useRouter } from 'vue-router'
import UserBar from './UserBar.vue'
import { isAuthenticated } from '../stores/auth'

const props = defineProps<{
  currentCategory: string
  currentSort: string
  showSidebar: boolean
}>()

const emit = defineEmits<{
  'update:currentCategory': [value: string]
  'update:currentSort': [value: string]
  'toggleSidebar': []
  'openCreateDialog': []
}>()

const router = useRouter()

const categories = [
  { value: '', label: '全部', icon: '🗂️' },
  { value: 'question', label: '提问', icon: '❓' },
  { value: 'discussion', label: '讨论', icon: '💬' },
  { value: 'sharing', label: '分享', icon: '📢' },
  { value: 'help', label: '求助', icon: '🆘' },
]
</script>

<template>
  <aside class="w-[80vw] max-w-[320px] lg:w-[clamp(200px,18vw,256px)] h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 relative">
    <!-- Header -->
    <div class="px-4 pt-5 pb-4 border-b border-border">
      <div class="flex items-center justify-between mb-3">
        <div
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold text-white shrink-0 tracking-wide"
          style="background: linear-gradient(135deg, #fd267a, #ff6036);"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          社区
        </div>
        <!-- Collapse button -->
        <button
          class="w-9 h-9 flex items-center justify-center rounded-lg text-text-muted/60 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
          title="收起侧边栏"
          @click="emit('toggleSidebar')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/>
          </svg>
        </button>
      </div>

      <!-- New post button -->
      <button
        v-if="isAuthenticated"
        class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-sm font-semibold bg-brand-gradient text-white hover:opacity-90 transition-opacity"
        @click="emit('openCreateDialog')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        发帖
      </button>
      <button
        v-else
        class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-full text-sm font-semibold bg-brand-gradient text-white hover:opacity-90 transition-opacity"
        @click="router.push('/login')"
      >
        登录后发帖
      </button>
    </div>

    <!-- Category nav -->
    <div class="flex-1 overflow-y-auto py-3">
      <div class="px-3 mb-1">
        <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wider px-2 mb-1.5">分类</p>
        <div class="space-y-0.5">
          <button
            v-for="cat in categories"
            :key="cat.value"
            class="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer"
            :class="currentCategory === cat.value
              ? 'bg-gradient-to-r from-[#fd267a]/15 to-[#ff6036]/10 text-[#fd267a] border border-[#fd267a]/20'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary border border-transparent'"
            @click="emit('update:currentCategory', cat.value)"
          >
            <span class="text-base leading-none">{{ cat.icon }}</span>
            <span>{{ cat.label }}</span>
            <div
              v-if="currentCategory === cat.value"
              class="ml-auto w-1.5 h-1.5 rounded-full bg-[#fd267a]"
            />
          </button>
        </div>
      </div>

      <div class="px-3 mt-4">
        <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wider px-2 mb-1.5">排序</p>
        <div class="space-y-0.5">
          <button
            class="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer"
            :class="currentSort === 'latest'
              ? 'bg-gradient-to-r from-[#fd267a]/15 to-[#ff6036]/10 text-[#fd267a] border border-[#fd267a]/20'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary border border-transparent'"
            @click="emit('update:currentSort', 'latest')"
          >
            <span class="text-base leading-none">🕐</span>
            <span>最新</span>
            <div v-if="currentSort === 'latest'" class="ml-auto w-1.5 h-1.5 rounded-full bg-[#fd267a]" />
          </button>
          <button
            class="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-all cursor-pointer"
            :class="currentSort === 'hot'
              ? 'bg-gradient-to-r from-[#fd267a]/15 to-[#ff6036]/10 text-[#fd267a] border border-[#fd267a]/20'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary border border-transparent'"
            @click="emit('update:currentSort', 'hot')"
          >
            <span class="text-base leading-none">🔥</span>
            <span>最热</span>
            <div v-if="currentSort === 'hot'" class="ml-auto w-1.5 h-1.5 rounded-full bg-[#fd267a]" />
          </button>
        </div>
      </div>
    </div>

    <!-- User bar -->
    <div class="shrink-0 border-t border-border">
      <UserBar />
    </div>
  </aside>
</template>
