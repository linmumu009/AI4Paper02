<script setup lang="ts">
/** 论文灵感 Tab 中单篇论文的行渲染（通用，适用于「我的论文」和「知识库论文」子 Tab）。 */
const props = defineProps<{
  paperId: string
  title: string
  subtitle: string
  depth: number
  generatingPaperIds: Set<string>
}>()

const emit = defineEmits<{
  openDetail: []
  generate: []
}>()

function avatarColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash)
  return `hsl(${Math.abs(hash % 360)}, 60%, 35%)`
}
</script>

<template>
  <div
    class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-bg-hover transition-colors"
    :style="{ paddingLeft: `${8 + depth * 14}px` }"
  >
    <div
      class="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold ring-1 ring-white/20"
      :style="{ background: avatarColor(paperId) }"
    >{{ (title || '?').slice(0, 2) }}</div>

    <div
      class="flex-1 min-w-0 cursor-pointer"
      title="查看灵感详情"
      @click="emit('openDetail')"
    >
      <div class="text-xs font-medium text-text-primary truncate">{{ title }}</div>
      <div v-if="subtitle" class="text-[10px] text-text-muted truncate">{{ subtitle }}</div>
    </div>

    <button
      class="shrink-0 flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border-none cursor-pointer transition-all font-medium"
      :class="generatingPaperIds.has(paperId)
        ? 'text-amber-600 bg-amber-500/10 cursor-not-allowed'
        : 'text-white bg-brand-gradient hover:opacity-90'"
      :disabled="generatingPaperIds.has(paperId)"
      title="基于此论文生成灵感候选"
      @click.stop="emit('generate')"
    >
      <span v-if="generatingPaperIds.has(paperId)" class="animate-spin">⟳</span>
      <svg v-else class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18h6M10 22h4M12 2a7 7 0 0 1 7 7c0 2.7-1.5 5-3.5 6.3V17a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1v-1.7C6.5 14 5 11.7 5 9a7 7 0 0 1 7-7z"/>
      </svg>
      <span>{{ generatingPaperIds.has(paperId) ? '生成中' : '灵感涌现' }}</span>
    </button>
  </div>
</template>
