<script setup lang="ts">
import { useDrawer } from '@/composables/useDrawer'

defineProps<{
  title?: string
}>()

const drawer = useDrawer()
</script>

<!--
  Compact header for primary tab pages.
  Replaces TabPageHeader — adds a hamburger button to open the NavigationDrawer.
  Height ~40px. safe-area-inset-top applied via padding.
-->
<template>
  <div
    class="shrink-0 flex items-center gap-2 px-3 z-10 glass-header"
    style="padding-top: max(10px, env(safe-area-inset-top, 10px)); padding-bottom: 6px; min-height: 40px;"
  >
    <!-- Hamburger -->
    <button
      type="button"
      class="page-header-menu-btn"
      aria-label="打开菜单"
      @click="drawer.open()"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Title slot -->
    <h1 class="text-[16px] font-bold text-text-primary leading-none flex-1 min-w-0 truncate">
      <slot name="title">{{ title }}</slot>
    </h1>

    <!-- Right slot for action buttons -->
    <div class="flex items-center gap-0.5">
      <slot name="right" />
    </div>
  </div>
</template>

<style scoped>
.page-header-menu-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
  transition: color 0.12s ease, background 0.12s ease;
}
.page-header-menu-btn:active {
  background: var(--color-bg-elevated);
  opacity: 0.8;
}
</style>
