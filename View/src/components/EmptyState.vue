<script setup lang="ts">
defineProps<{
  /** Emoji or short text icon displayed large */
  icon?: string
  title: string
  description?: string
}>()
</script>

<!--
  Generic empty/completed state block.
  Usage:
    <EmptyState icon="🎉" title="全部浏览完" description="明天更新新论文">
      <button @click="reset">重新浏览</button>
    </EmptyState>
-->
<template>
  <div class="flex flex-col items-center gap-4 text-center px-8 max-w-sm">
    <span v-if="icon" class="text-5xl mb-1 select-none">{{ icon }}</span>
    <h2 class="text-xl font-bold text-text-primary">{{ title }}</h2>
    <p v-if="description" class="text-sm text-text-muted leading-relaxed">{{ description }}</p>
    <!-- action area -->
    <div v-if="$slots.default" class="flex items-center gap-3 mt-1 flex-wrap justify-center">
      <slot />
    </div>
  </div>
</template>
