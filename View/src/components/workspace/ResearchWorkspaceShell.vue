<script setup lang="ts">
import type { ResearchWorkspaceMode } from '../../composables/useResearchWorkspace'

withDefaults(defineProps<{
  mode: ResearchWorkspaceMode
  showToolbar?: boolean
  ariaLabel?: string
}>(), {
  showToolbar: true,
  ariaLabel: '论文研究工作区',
})
</script>

<template>
  <section
    class="research-workspace-shell"
    :data-workspace-mode="mode"
    :aria-label="ariaLabel"
  >
    <header v-if="showToolbar" class="research-workspace-shell__toolbar">
      <slot name="toolbar" />
    </header>

    <div class="research-workspace-shell__content">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.research-workspace-shell {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg);
}

.research-workspace-shell__toolbar {
  position: relative;
  z-index: 8;
  display: flex;
  min-height: var(--workspace-toolbar-h, 50px);
  flex: 0 0 auto;
  align-items: center;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 72%, transparent);
  background: color-mix(in srgb, var(--color-bg) 94%, var(--color-bg-card));
}

.research-workspace-shell__content {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.research-workspace-shell[data-workspace-mode='list'] .research-workspace-shell__content,
.research-workspace-shell[data-workspace-mode='immersive'] .research-workspace-shell__content {
  align-items: stretch;
}

@media (max-width: 767px) {
  .research-workspace-shell__toolbar {
    min-height: auto;
  }
}
</style>
