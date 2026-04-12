<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { KbMenuItem } from '../types/paper'

const props = defineProps<{
  items: KbMenuItem[]
  x: number
  y: number
}>()

const emit = defineEmits<{
  select: [key: string]
  close: []
}>()

const menuRef = ref<HTMLDivElement | null>(null)

function onClickOutside(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    emit('close')
  }
}

onMounted(() => {
  nextTick(() => {
    document.addEventListener('mousedown', onClickOutside, true)
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onClickOutside, true)
})

function handleSelect(key: string) {
  emit('select', key)
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuRef"
      class="fixed z-[9999] min-w-[140px] max-w-[180px] py-1 bg-bg-elevated border border-border rounded-lg shadow-xl"
      :style="{ left: `${x}px`, top: `${y}px` }"
    >
      <button
        v-for="item in items"
        :key="item.key"
        class="w-full text-left px-3 py-2 text-xs bg-transparent border-none transition-colors flex items-center gap-2"
        :class="item.disabled
          ? 'text-text-muted/40 cursor-not-allowed'
          : item.danger
            ? 'text-tinder-pink hover:bg-tinder-pink/10 cursor-pointer'
            : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer'"
        :disabled="item.disabled"
        @click="item.disabled ? undefined : handleSelect(item.key)"
      >
        <!-- research icon -->
        <svg
          v-if="item.icon === 'research'"
          class="w-3.5 h-3.5 shrink-0 opacity-60"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          <path d="M11 8v3"/><path d="M8 11h6"/>
        </svg>
        <!-- compare icon -->
        <svg
          v-else-if="item.icon === 'compare'"
          class="w-3.5 h-3.5 shrink-0 opacity-60"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22V12"/><path d="m21 3-7 7-4-4-7 7"/>
        </svg>
        <span class="truncate">{{ item.label }}</span>
      </button>
    </div>
  </Teleport>
</template>
