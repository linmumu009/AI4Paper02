<script setup lang="ts">
import { useEntitlements } from '../../composables/useEntitlements'

const { gateAllowed } = useEntitlements()

interface GateItem {
  key: 'general_chat' | 'note_file_upload' | 'batch_export' | 'llm_preset' | 'prompt_preset'
  label: string
  icon: string
}

const GATES: GateItem[] = [
  { key: 'general_chat',     label: '通用 AI 助手',  icon: '🤖' },
  { key: 'note_file_upload', label: '笔记附件上传',   icon: '📎' },
  { key: 'batch_export',     label: '批量导出',       icon: '📦' },
  { key: 'llm_preset',       label: '自定义模型预设', icon: '⚙️' },
  { key: 'prompt_preset',    label: '提示词预设',     icon: '📝' },
]
</script>

<template>
  <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
    <div
      v-for="gate in GATES"
      :key="gate.key"
      class="flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors"
      :class="gateAllowed(gate.key)
        ? 'bg-tinder-green/8 border border-tinder-green/20'
        : 'bg-bg-elevated border border-border opacity-50'"
    >
      <span class="text-sm shrink-0">{{ gate.icon }}</span>
      <div class="min-w-0 flex-1">
        <p class="text-[11px] font-medium truncate" :class="gateAllowed(gate.key) ? 'text-text-primary' : 'text-text-muted'">
          {{ gate.label }}
        </p>
      </div>
      <svg
        v-if="gateAllowed(gate.key)"
        xmlns="http://www.w3.org/2000/svg"
        class="w-3 h-3 text-tinder-green shrink-0"
        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <polyline points="20 6 9 17 4 12"/>
      </svg>
      <svg
        v-else
        xmlns="http://www.w3.org/2000/svg"
        class="w-3 h-3 text-text-muted shrink-0"
        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    </div>
  </div>
</template>
