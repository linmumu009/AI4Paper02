<script setup lang="ts">
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'

defineOptions({ name: 'AdminDashboardView' })

const router = useRouter()

const items = [
  { label: '用户管理', desc: '查看用户、调整等级、权限管理', icon: 'users', color: 'tinder-blue', route: '/admin/users' },
  { label: '数据统计', desc: '概览、用户活跃、趋势图', icon: 'bar-chart', color: 'tinder-green', route: '/admin/analytics' },
  { label: '数据追踪', desc: 'Pipeline 数据流转漏斗', icon: 'funnel', color: 'tinder-purple', route: '/admin/data-tracking' },
  { label: '兑换码管理', desc: '发放、查询、禁用订阅码', icon: 'key', color: 'tinder-gold', route: '/admin/redeem-keys' },
  { label: 'LLM 配置库', desc: '系统级 LLM 配置 CRUD', icon: 'cpu', color: 'tinder-blue', route: '/admin/llm-configs' },
  { label: '提示词配置库', desc: '系统级 Prompt 配置 CRUD', icon: 'edit', color: 'tinder-pink', route: '/admin/prompt-configs' },
  { label: '论文推荐配置', desc: '推荐模块参数配置', icon: 'settings', color: 'tinder-green', route: '/admin/recommend-config' },
  { label: '灵感生成配置', desc: 'Idea Generation 参数配置', icon: 'lightbulb', color: 'tinder-gold', route: '/admin/idea-system-config' },
]
</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-y-auto">
    <PageHeader title="管理后台" @back="router.back()" />

    <div class="px-4 pt-4 pb-8 space-y-3">
      <div
        v-for="item in items"
        :key="item.route"
        class="flex items-center gap-4 px-4 py-4 rounded-2xl border border-border bg-bg-card active:bg-bg-hover cursor-pointer transition-colors"
        @click="router.push(item.route)"
      >
        <div
          class="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0"
          :class="`bg-${item.color}/10`"
        >
          <!-- Icon variants -->
          <svg v-if="item.icon === 'users'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <svg v-else-if="item.icon === 'bar-chart'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          <svg v-else-if="item.icon === 'funnel'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          <svg v-else-if="item.icon === 'key'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
          </svg>
          <svg v-else-if="item.icon === 'cpu'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
          </svg>
          <svg v-else-if="item.icon === 'edit'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="`text-${item.color}`">
            <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-[14px] font-semibold text-text-primary">{{ item.label }}</p>
          <p class="text-[12px] text-text-muted mt-0.5 truncate">{{ item.desc }}</p>
        </div>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </div>
    </div>
  </div>
</template>
