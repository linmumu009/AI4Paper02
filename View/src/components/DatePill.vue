<script setup lang="ts">
defineProps<{
  date: string
}>()
</script>

<template>
  <div class="flex items-center justify-between gap-2 px-3 py-2 bg-bg-elevated border border-border rounded-xl">
    <div class="flex items-center gap-2 min-w-0">
      <svg class="w-3.5 h-3.5 shrink-0 text-text-muted/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <span class="text-sm font-medium text-text-primary truncate">{{ date || '—' }}</span>
    </div>
    <slot />
  </div>
</template>
