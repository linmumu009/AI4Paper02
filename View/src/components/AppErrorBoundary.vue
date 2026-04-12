<template>
  <slot v-if="!hasError" />
  <div
    v-else
    class="flex flex-col items-center justify-center h-full min-h-[200px] p-8 text-center gap-4"
    role="alert"
    aria-live="assertive"
  >
    <div class="text-5xl" aria-hidden="true">⚠️</div>
    <h2 class="text-xl font-bold text-text-primary">页面遇到了一个问题</h2>
    <p class="text-sm text-text-muted max-w-md leading-relaxed">
      {{ message || '发生了意外错误。这已被记录，我们会尽快修复。' }}
    </p>
    <button
      class="px-4 py-2 rounded-lg bg-tinder-pink text-white text-sm font-medium hover:opacity-90 transition-opacity border-none cursor-pointer"
      @click="reset"
    >
      重新加载
    </button>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, h } from 'vue'

/**
 * AppErrorBoundary — catches unhandled Vue render errors in its subtree.
 *
 * Usage:
 *   <AppErrorBoundary>
 *     <SomeComplexView />
 *   </AppErrorBoundary>
 *
 * This is a class-based component because Vue 3's errorCaptured lifecycle
 * hook requires defineComponent options API for proper boundary semantics.
 */
export default defineComponent({
  name: 'AppErrorBoundary',

  props: {
    message: {
      type: String,
      default: '',
    },
  },

  emits: ['error'],

  setup(props, { emit }) {
    const hasError = ref(false)
    const capturedError = ref<unknown>(null)

    function reset() {
      hasError.value = false
      capturedError.value = null
    }

    return { hasError, capturedError, reset }
  },

  errorCaptured(err, instance, info) {
    this.hasError = true
    this.capturedError = err
    this.$emit('error', { error: err, info })
    console.error('[AppErrorBoundary] Caught render error:', err, info)
    // Return false to stop propagation
    return false
  },
})
</script>
