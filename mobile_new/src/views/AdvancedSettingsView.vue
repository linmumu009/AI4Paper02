<script setup lang="ts">
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { isAuthenticated } from '@shared/stores/auth'

defineOptions({ name: 'AdvancedSettingsView' })

const router = useRouter()

const presetItems = [
  {
    key: 'llm-presets',
    label: '模型预设',
    desc: '自定义 LLM 模型与 API 配置',
    icon: 'cpu',
    color: 'text-tinder-blue',
    route: '/settings/llm-presets',
  },
  {
    key: 'prompt-presets',
    label: '提示词预设',
    desc: '自定义 Prompt 模板库',
    icon: 'edit',
    color: 'text-tinder-purple',
    route: '/settings/prompt-presets',
  },
]

const featureItems = [
  {
    key: 'compare',
    label: '对比分析配置',
    desc: '自定义论文对比的模型与提示词',
    color: 'text-tinder-blue',
    route: '/settings/feature/compare',
  },
  {
    key: 'inspiration',
    label: '灵感涌现配置',
    desc: '自定义灵感生成的模型与参数',
    color: 'text-tinder-green',
    route: '/settings/feature/inspiration',
  },
  {
    key: 'idea_generate',
    label: '灵感生成多阶段配置',
    desc: '7 个阶段的模型与提示词配置',
    color: 'text-tinder-gold',
    route: '/settings/feature/idea_generate',
  },
  {
    key: 'paper_recommend',
    label: '论文推荐参数',
    desc: '推荐流水线的模型、提示词与字数参数',
    color: 'text-tinder-pink',
    route: '/settings/feature/paper_recommend',
  },
]
</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-y-auto">
    <PageHeader title="高级设置" @back="router.back()" />

    <div v-if="!isAuthenticated" class="flex-1 flex flex-col items-center justify-center px-8 pb-16 gap-4">
      <p class="text-[14px] text-text-muted text-center">请先登录后访问高级设置</p>
      <button type="button" class="btn-primary max-w-xs" @click="router.push('/login')">登录</button>
    </div>

    <div v-else class="pb-8">
      <!-- Preset management -->
      <div class="mx-4 mt-4 mb-1">
        <p class="text-[11px] font-semibold uppercase tracking-wider text-text-muted px-1 mb-2">预设管理</p>
        <div class="rounded-2xl overflow-hidden border border-border bg-bg-card divide-y divide-border">
          <button
            v-for="item in presetItems"
            :key="item.key"
            type="button"
            class="settings-row"
            @click="router.push(item.route)"
          >
            <div class="w-9 h-9 rounded-xl bg-bg-elevated border border-border flex items-center justify-center shrink-0">
              <!-- CPU icon for LLM -->
              <svg v-if="item.icon === 'cpu'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="item.color">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
                <line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" />
                <line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" />
                <line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" />
                <line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" />
              </svg>
              <!-- Edit icon for prompt -->
              <svg v-else-if="item.icon === 'edit'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :class="item.color">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </div>
            <div class="flex-1 min-w-0 text-left">
              <p class="text-[14px] font-medium text-text-primary">{{ item.label }}</p>
              <p class="text-[12px] text-text-muted mt-0.5 truncate">{{ item.desc }}</p>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Feature configuration -->
      <div class="mx-4 mt-5 mb-1">
        <p class="text-[11px] font-semibold uppercase tracking-wider text-text-muted px-1 mb-2">功能配置</p>
        <div class="rounded-2xl overflow-hidden border border-border bg-bg-card divide-y divide-border">
          <button
            v-for="item in featureItems"
            :key="item.key"
            type="button"
            class="settings-row"
            @click="router.push(item.route)"
          >
            <div class="w-2.5 h-2.5 rounded-full shrink-0" :class="item.color.replace('text-', 'bg-')" />
            <div class="flex-1 min-w-0 text-left">
              <p class="text-[14px] font-medium text-text-primary">{{ item.label }}</p>
              <p class="text-[12px] text-text-muted mt-0.5 truncate">{{ item.desc }}</p>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  width: 100%;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.1s ease;
}
.settings-row:active { background: var(--color-bg-hover); }
</style>
