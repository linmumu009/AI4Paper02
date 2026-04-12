<script setup lang="ts">
defineProps<{
  message?: string
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 py-16 px-6">
    <div class="relative w-12 h-12">
      <svg class="w-12 h-12 text-tinder-pink animate-spin" viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="3" stroke-dasharray="100 28" stroke-linecap="round" opacity="0.3"/>
        <circle cx="24" cy="24" r="20" stroke="url(#spin-grad)" stroke-width="3" stroke-dasharray="36 92" stroke-linecap="round"/>
        <defs>
          <linearGradient id="spin-grad" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stop-color="#fd267a"/>
            <stop offset="100%" stop-color="#ff6036"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
    <p v-if="message" class="text-sm text-text-muted text-center">{{ message }}</p>
  </div>
</template>
