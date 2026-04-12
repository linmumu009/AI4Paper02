<template>
  <Teleport to="body">
    <div
      aria-live="polite"
      aria-atomic="false"
      class="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none"
    >
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="pointer-events-auto flex items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-lg max-w-xs"
          :class="typeClass(toast.type)"
          role="alert"
        >
          <span class="shrink-0 mt-0.5 text-base leading-none" aria-hidden="true">{{ typeIcon(toast.type) }}</span>
          <span class="flex-1">{{ toast.text }}</span>
          <button
            class="shrink-0 ml-1 opacity-70 hover:opacity-100 transition-opacity"
            :aria-label="'关闭通知: ' + toast.text"
            @click="dismiss(toast.id)"
          >✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToast, type ToastType } from '../composables/useToast'

const { toasts, dismiss } = useToast()

function typeClass(type: ToastType) {
  switch (type) {
    case 'error':   return 'bg-red-600 text-white'
    case 'warning': return 'bg-yellow-500 text-white'
    case 'success': return 'bg-green-600 text-white'
    default:        return 'bg-gray-700 text-white'
  }
}

function typeIcon(type: ToastType) {
  switch (type) {
    case 'error':   return '✕'
    case 'warning': return '⚠'
    case 'success': return '✓'
    default:        return 'ℹ'
  }
}
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
