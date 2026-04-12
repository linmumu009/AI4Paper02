<script setup lang="ts">
defineProps<{
  title?: string
}>()
</script>

<!--
  Compact header for primary tab pages (推荐/灵感/知识库/我的).
  Height is ~40px vs PageHeader's 56px+, recovering ~16-30px of vertical space.
  No back button needed (TabBar handles navigation).
  safe-area-inset-top is applied via padding.
-->
<template>
  <div
    class="shrink-0 flex items-center justify-between px-4 z-10"
    style="padding-top: max(10px, env(safe-area-inset-top, 10px)); padding-bottom: 6px; min-height: 40px;"
  >
    <!-- Title (left-aligned, smaller) -->
    <h1 class="text-[17px] font-bold text-text-primary leading-none">
      <slot name="title">{{ title }}</slot>
    </h1>

    <!-- Action buttons (right) -->
    <div class="flex items-center gap-0.5">
      <slot name="right" />
    </div>
  </div>
</template>
