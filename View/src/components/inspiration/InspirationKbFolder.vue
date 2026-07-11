<script setup lang="ts">
import { ref } from 'vue'
import type { KbFolder, KbPaper } from '../../types/paper'
import InspirationPaperRow from './InspirationPaperRow.vue'
// Self-reference for recursion
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import InspirationKbFolder from './InspirationKbFolder.vue'

const props = defineProps<{
  folder: KbFolder
  depth: number
  generatingPaperIds: Set<string>
}>()

const emit = defineEmits<{
  openDetail: [id: string, title: string]
  generate: [id: string, title: string]
}>()

const expanded = ref(true)

function paperTitle(p: KbPaper): string {
  return (p.paper_data as any)?.short_title
    || (p.paper_data as any)?.['📖标题']
    || p.paper_id
}

function paperSubtitle(p: KbPaper): string {
  return (p.paper_data as any)?.institution || ''
}
</script>

<template>
  <div>
    <!-- Folder header row (matches SidebarFolder.vue style) -->
    <div
      class="flex items-center gap-2.5 py-2 rounded-lg cursor-pointer transition-colors group hover:bg-bg-hover"
      :style="{ paddingLeft: `${8 + depth * 14}px`, paddingRight: '8px' }"
      @click.stop="expanded = !expanded"
    >
      <!-- Expand toggle -->
      <button
        class="w-5 h-5 flex items-center justify-center bg-transparent border-none cursor-pointer shrink-0 p-0"
        @click.stop="expanded = !expanded"
      >
        <svg
          class="w-3 h-3 text-text-muted transition-transform duration-150"
          :class="expanded ? 'rotate-90' : ''"
          viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <!-- Folder icon -->
      <svg
        class="shrink-0 text-text-secondary transition-colors"
        style="width:20px;height:20px;"
        viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
      >
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
      <!-- Name + count -->
      <div class="flex-1 min-w-0 flex flex-col justify-center">
        <span class="text-sm font-medium text-text-primary truncate">{{ folder.name }}</span>
        <span v-if="folder.papers?.length" class="text-[11px] text-text-muted truncate mt-0.5">
          {{ folder.papers.length }} 篇
        </span>
      </div>
    </div>

    <!-- Expanded content -->
    <template v-if="expanded">
      <!-- Child folders (recursive) -->
      <InspirationKbFolder
        v-for="child in folder.children"
        :key="child.id"
        :folder="child"
        :depth="depth + 1"
        :generating-paper-ids="generatingPaperIds"
        @open-detail="(id, title) => emit('openDetail', id, title)"
        @generate="(id, title) => emit('generate', id, title)"
      />
      <!-- Papers in this folder -->
      <InspirationPaperRow
        v-for="paper in folder.papers"
        :key="paper.paper_id"
        :paper-id="paper.paper_id"
        :title="paperTitle(paper)"
        :subtitle="paperSubtitle(paper)"
        :depth="depth + 1"
        :generating-paper-ids="generatingPaperIds"
        @open-detail="emit('openDetail', paper.paper_id, paperTitle(paper))"
        @generate="emit('generate', paper.paper_id, paperTitle(paper))"
      />
    </template>
  </div>
</template>
