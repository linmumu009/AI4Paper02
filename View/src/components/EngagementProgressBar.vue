<script setup lang="ts">
/**
 * EngagementProgressBar — Navbar-mounted engagement widget.
 * Now composes EngagementPill (trigger) + EngagementPanel (dropdown).
 * All logic delegated to the sub-components and useEngagement composable.
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useEngagement } from '../composables/useEngagement'
import EngagementPill from './engagement/EngagementPill.vue'
import EngagementPanel from './engagement/EngagementPanel.vue'

const {
  status, loading, loadError, loadStatus,
  taskItems, allDone,
  hasNewRewards, markRewardsRead,
} = useEngagement()

const showPanel = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const streakCurrent = computed(() => status.value?.streak?.current ?? 0)

const activeRewardCount = computed(() =>
  (status.value?.rewards ?? []).filter(r => r.status === 'active').length
)

function togglePanel() {
  showPanel.value = !showPanel.value
  if (showPanel.value && hasNewRewards.value) {
    markRewardsRead()
  }
}

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    showPanel.value = false
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))
</script>

<template>
  <div ref="rootRef" class="relative">
    <!-- Pill trigger -->
    <EngagementPill
      :task-items="taskItems"
      :streak-current="streakCurrent"
      :all-done="allDone"
      :has-new-rewards="hasNewRewards"
      :active-reward-count="activeRewardCount"
      :loading="loading"
      :load-error="loadError"
      :is-open="showPanel"
      @toggle="loadError ? loadStatus(true) : togglePanel()"
    />

    <!-- Dropdown panel -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 scale-95 -translate-y-1"
      enter-to-class="opacity-100 scale-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 scale-100 translate-y-0"
      leave-to-class="opacity-0 scale-95 -translate-y-1"
    >
      <div
        v-if="showPanel"
        class="absolute top-full left-1/2 -translate-x-1/2 mt-2 z-30"
      >
        <EngagementPanel :task-items="taskItems" />
      </div>
    </Transition>
  </div>
</template>
