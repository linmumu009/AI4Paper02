<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    autofocus?: boolean
  }>(),
  { placeholder: '搜索' },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'clear'): void
}>()
</script>

<template>
  <div class="relative flex items-center">
    <svg
      class="absolute left-3 text-text-muted pointer-events-none shrink-0"
      width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
    <input
      :value="props.modelValue"
      :placeholder="props.placeholder"
      :autofocus="props.autofocus"
      type="search"
      class="w-full pl-9 pr-9 py-2.5 rounded-xl bg-bg-elevated border border-border text-text-primary text-[14px] outline-none focus:border-tinder-pink transition-colors placeholder:text-text-muted"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <button
      v-if="props.modelValue"
      type="button"
      class="absolute right-3 text-text-muted p-0.5"
      @click="emit('update:modelValue', ''); emit('clear')"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  </div>
</template>
