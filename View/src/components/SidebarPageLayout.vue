<script setup lang="ts">
withDefaults(defineProps<{
  showSidebar: boolean
  openButtonTitle?: string
}>(), {
  openButtonTitle: '展开知识库',
})

defineEmits<{ 'update:showSidebar': [value: boolean] }>()
</script>

<!--
  Shared page scaffold for pages that have a collapsible left sidebar.
  Handles: outer container, mobile overlay backdrop, open-sidebar button, main-content wrapper.

  The caller provides:
    - #sidebar slot: your Sidebar component or guest aside with its own Transition wrapper
    - default slot: the main page content

  The caller is responsible for the sidebar's own Transition (sidebar-slide animation),
  as it contains view-specific component refs and event bindings.
-->
<template>
  <div class="h-full flex relative">

    <!-- Mobile overlay backdrop (click to close) -->
    <Transition name="spg-fade">
      <div
        v-if="showSidebar"
        class="fixed inset-0 z-20 bg-black/60 lg:hidden"
        @click="$emit('update:showSidebar', false)"
      />
    </Transition>

    <!-- Sidebar area (caller provides content + its own slide Transition) -->
    <slot name="sidebar" />

    <!-- Open sidebar button — visible when sidebar is collapsed -->
    <Transition name="spg-fade">
      <button
        v-if="!showSidebar"
        class="fixed top-[calc(var(--navbar-h)+2.5rem)] left-0 z-10 flex items-center justify-center w-[54px] h-[54px] bg-bg-card border border-border border-l-0 rounded-r-lg shadow-sm text-text-muted/60 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
        :title="openButtonTitle"
        @click="$emit('update:showSidebar', true)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="27" height="27" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>
        </svg>
      </button>
    </Transition>

    <!-- Main content area -->
    <div class="flex-1 flex flex-col relative overflow-hidden min-w-0">
      <slot />
    </div>

  </div>
</template>

<style>
/* Fade for the overlay and open-button (non-scoped so Transition can find the classes) */
.spg-fade-enter-active,
.spg-fade-leave-active {
  transition: opacity 0.2s ease;
}
.spg-fade-enter-from,
.spg-fade-leave-to {
  opacity: 0;
}
</style>
