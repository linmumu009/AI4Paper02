<script setup lang="ts">
import { watch, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    title?: string
    height?: string
  }>(),
  { height: 'auto' },
)

const emit = defineEmits<{
  (e: 'close'): void
}>()

watch(
  () => props.visible,
  (v) => {
    if (v) {
      document.body.style.overflow = 'hidden'
    } else {
      nextTick(() => {
        document.body.style.overflow = ''
      })
    }
  },
  { immediate: true },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet-fade">
      <div
        v-if="props.visible"
        class="fixed inset-0 z-50 flex flex-col justify-end"
        @click.self="emit('close')"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/60" @click="emit('close')" />

        <!-- Sheet -->
        <Transition name="sheet-slide">
          <div
            v-if="props.visible"
            class="relative rounded-t-2xl bg-bg-card border-t border-border flex flex-col"
            :style="props.height !== 'auto' ? `height: ${props.height}` : ''"
            style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px)); max-height: 90dvh;"
          >
            <!-- Handle -->
            <div class="flex justify-center pt-3 pb-1 shrink-0">
              <div class="w-10 h-1 rounded-full bg-border-light" />
            </div>

            <!-- Title -->
            <div v-if="props.title" class="px-5 pb-3 shrink-0">
              <h3 class="text-[15px] font-semibold text-text-primary">{{ props.title }}</h3>
            </div>

            <!-- Content -->
            <div class="flex-1 overflow-y-auto overscroll-contain">
              <slot />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet-fade-enter-active,
.sheet-fade-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-fade-enter-from,
.sheet-fade-leave-to {
  opacity: 0;
}
.sheet-slide-enter-active,
.sheet-slide-leave-active {
  transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1);
}
.sheet-slide-enter-from,
.sheet-slide-leave-to {
  transform: translateY(100%);
}
</style>
