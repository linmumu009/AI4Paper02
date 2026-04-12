<script setup lang="ts">
withDefaults(
  defineProps<{
    icon?: string
    label?: string
    disabled?: boolean
  }>(),
  {},
)

const emit = defineEmits<{
  (e: 'click'): void
}>()
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    class="fixed z-40 right-5 bottom-6 w-14 h-14 rounded-full flex items-center justify-center shadow-lg transition-transform active:scale-90 disabled:opacity-50"
    style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
    :aria-label="label"
    @click="emit('click')"
  >
    <slot>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
    </slot>
  </button>
</template>
