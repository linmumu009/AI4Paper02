<script setup lang="ts">
import { ref } from 'vue'
import IdeaLabView from './IdeaLabView.vue'
import AtomBrowser from './AtomBrowser.vue'
import ExemplarView from './ExemplarView.vue'

type Tool = 'idea' | 'atoms' | 'exemplars'

const activeTool = ref<Tool>('idea')

const tools: { key: Tool; icon: string; label: string }[] = [
  { key: 'idea', icon: '🧪', label: '灵感工作台' },
  { key: 'atoms', icon: '🔬', label: '原子库' },
  { key: 'exemplars', icon: '⭐', label: '范例库' },
]
</script>

<template>
  <div class="h-full flex overflow-hidden">
    <!-- Workbench sidebar: fluid width via CSS var, icon-only below ~100px -->
    <aside class="workbench-aside shrink-0 bg-bg-sidebar border-r border-border flex flex-col overflow-hidden">
      <div class="shrink-0 px-2 py-3 border-b border-border">
        <h2 class="text-sm font-bold text-text-primary flex items-center justify-center gap-2 overflow-hidden">
          <span class="shrink-0">⚙️</span>
          <span class="workbench-label truncate">工作台</span>
        </h2>
      </div>
      <nav class="flex-1 p-1.5 space-y-0.5 overflow-y-auto">
        <button
          v-for="tool in tools"
          :key="tool.key"
          class="w-full flex items-center gap-2.5 px-2 py-2.5 rounded-lg text-sm transition-colors cursor-pointer text-left border-none"
          :class="activeTool === tool.key
            ? 'bg-bg-elevated text-text-primary font-semibold'
            : 'bg-transparent text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
          :title="tool.label"
          @click="activeTool = tool.key"
        >
          <span class="text-base shrink-0">{{ tool.icon }}</span>
          <span class="workbench-label truncate">{{ tool.label }}</span>
        </button>
      </nav>
    </aside>

    <!-- Tool content -->
    <div class="flex-1 min-w-0 overflow-hidden">
      <IdeaLabView v-if="activeTool === 'idea'" />
      <AtomBrowser v-else-if="activeTool === 'atoms'" :embedded="true" />
      <ExemplarView v-else-if="activeTool === 'exemplars'" :embedded="true" />
    </div>
  </div>
</template>

<style scoped>
.workbench-aside {
  width: var(--workbench-sidebar-w);
}
/* When the sidebar shrinks below ~6rem, hide text labels and center icons */
@container (max-width: 5.5rem) {
  .workbench-label { display: none; }
}
/* Fallback for browsers without container queries: hide labels below 100px */
@media (max-width: 900px) {
  .workbench-label { display: none; }
}
</style>
