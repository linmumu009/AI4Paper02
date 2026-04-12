<script setup lang="ts">
withDefaults(defineProps<{
  /** Spinner size: sm=h-4/w-4, md=h-6/w-6, lg=h-8/w-8 (default: lg) */
  size?: 'sm' | 'md' | 'lg'
  /** Tailwind text-color class override (default: text-tinder-pink) */
  color?: string
  /** Optional label shown below the spinner */
  text?: string
}>(), {
  size: 'lg',
  color: 'text-tinder-pink',
})
</script>

<template>
  <div class="flex flex-col items-center gap-3">
    <svg
      class="animate-spin"
      :class="[
        size === 'sm' ? 'h-4 w-4' : size === 'md' ? 'h-6 w-6' : 'h-8 w-8',
        color,
      ]"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
    <span v-if="text || $slots.default" class="text-text-muted text-sm">
      <slot>{{ text }}</slot>
    </span>
  </div>
</template>
