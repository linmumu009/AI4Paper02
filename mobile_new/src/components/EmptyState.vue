<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-4 px-8 py-16 text-center">
    <!-- Illustration-style icon -->
    <div class="w-16 h-16 rounded-2xl bg-bg-elevated border border-border flex items-center justify-center">
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-text-muted">
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>
        <path d="M9 12h6M12 9v6"/>
      </svg>
    </div>
    <div>
      <h3 class="text-base font-semibold text-text-primary mb-1">{{ title }}</h3>
      <p v-if="description" class="text-sm text-text-muted leading-relaxed">{{ description }}</p>
    </div>
    <slot />
  </div>
</template>
