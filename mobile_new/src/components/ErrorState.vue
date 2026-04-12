<script setup lang="ts">
defineProps<{
  message: string
}>()

const emit = defineEmits<{
  (e: 'retry'): void
}>()
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-5 px-8 py-16 text-center">
    <div class="w-14 h-14 rounded-full bg-tinder-pink/10 flex items-center justify-center">
      <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-pink">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
    </div>
    <div>
      <p class="text-[15px] font-medium text-text-primary mb-1">出错了</p>
      <p class="text-sm text-text-muted leading-relaxed">{{ message }}</p>
    </div>
    <button type="button" class="btn-primary max-w-[160px]" @click="emit('retry')">
      重新加载
    </button>
  </div>
</template>
