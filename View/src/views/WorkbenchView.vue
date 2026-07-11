<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import IdeaLabView from './IdeaLabView.vue'
import AtomBrowser from './AtomBrowser.vue'
import ExemplarView from './ExemplarView.vue'
import MemoryClustersView from './MemoryClustersView.vue'
import EvalReplayView from './EvalReplayView.vue'
import IdeaDetailPanel from '../components/idea/IdeaDetailPanel.vue'

const route = useRoute()
const router = useRouter()

type Tool = 'idea' | 'atoms' | 'exemplars' | 'clusters' | 'eval'

const activeTool = ref<Tool>('idea')

// candidate_id from query: when present, show IdeaDetailView overlay instead of normal tool
const activeCandidateId = computed(() => {
  const v = route.query.candidate_id
  return v ? Number(v) : null
})

// Sync active tool from route query (e.g. ?tab=atoms)
function syncTabFromRoute() {
  const tab = route.query.tab as string
  if (tab === 'atoms' || tab === 'exemplars' || tab === 'clusters' || tab === 'idea' || tab === 'eval') {
    activeTool.value = tab
  }
}
onMounted(syncTabFromRoute)
watch(() => route.query.tab, syncTabFromRoute)

// initialPaperId for AtomBrowser when navigated from ResearchMemoryPanel
const initialAtomPaperId = computed(() => (route.query.paper_id as string) || '')

const tools: { key: Tool; icon: string; label: string }[] = [
  { key: 'idea', icon: '🧪', label: '灵感工作台' },
  { key: 'atoms', icon: '🔬', label: '研究原子库' },
  { key: 'clusters', icon: '🗺️', label: '研究图谱' },
  { key: 'exemplars', icon: '⭐', label: '范例库' },
  { key: 'eval', icon: '📊', label: '评估基准' },
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
      <!-- candidate_id query: show detail panel with proper streaming plan generation -->
      <IdeaDetailPanel
        v-if="activeCandidateId"
        :candidate-id="activeCandidateId"
        @close="router.replace('/workbench')"
        @open-paper="(pid) => router.push(`/papers/${pid}`)"
      />
      <template v-else>
        <IdeaLabView v-if="activeTool === 'idea'" />
        <AtomBrowser
          v-else-if="activeTool === 'atoms'"
          :embedded="true"
          :initial-paper-id="initialAtomPaperId"
        />
        <MemoryClustersView v-else-if="activeTool === 'clusters'" :embedded="true" />
        <ExemplarView v-else-if="activeTool === 'exemplars'" :embedded="true" />
        <EvalReplayView v-else-if="activeTool === 'eval'" />
      </template>
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
