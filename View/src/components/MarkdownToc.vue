<script setup lang="ts">
import { ref, computed } from 'vue'

export interface TocHeading {
  id: string
  text: string
  level: number
}

const props = defineProps<{
  headings: TocHeading[]
  activeId: string
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const search = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.headings
  return props.headings.filter((h) => h.text.toLowerCase().includes(q))
})

function indentClass(level: number): string {
  if (level <= 1) return 'pl-2'
  if (level === 2) return 'pl-5'
  if (level === 3) return 'pl-8'
  return 'pl-10'
}

function textSizeClass(level: number): string {
  if (level <= 1) return 'text-[14px] font-semibold'
  if (level === 2) return 'text-[13px] font-medium'
  return 'text-[12px]'
}

function inactiveClass(level: number): string {
  if (level <= 1) return 'text-text-primary hover:bg-bg-hover'
  if (level === 2) return 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
  return 'text-text-muted hover:text-text-primary hover:bg-bg-hover'
}

function dotClass(level: number): string {
  if (level <= 1) return 'w-1.5 h-1.5'
  if (level === 2) return 'w-1 h-1'
  return 'w-[3px] h-[3px]'
}
</script>

<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Search -->
    <div class="shrink-0 px-2 py-2 border-b border-border">
      <div class="relative">
        <svg
          class="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-muted pointer-events-none"
          viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          v-model="search"
          type="text"
          placeholder="搜索标题…"
          class="w-full pl-6 pr-2 py-1 text-[12px] bg-bg-elevated border border-border rounded-md text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
        />
      </div>
    </div>

    <!-- Heading list -->
    <nav class="flex-1 overflow-y-auto py-1">
      <div v-if="filtered.length === 0" class="px-3 py-4 text-[11px] text-text-muted text-center">
        无匹配标题
      </div>
      <button
        v-for="h in filtered"
        :key="h.id"
        class="w-full text-left pr-2 py-1 flex items-start gap-1.5 transition-colors bg-transparent border-none cursor-pointer group"
        :class="[
          indentClass(h.level),
          activeId === h.id
            ? 'text-tinder-pink bg-tinder-pink/8'
            : inactiveClass(h.level),
        ]"
        @click="emit('select', h.id)"
      >
        <span
          class="mt-[3px] shrink-0 rounded-full transition-colors"
          :class="[
            dotClass(h.level),
            activeId === h.id ? 'bg-tinder-pink' : 'bg-border group-hover:bg-text-muted',
          ]"
        />
        <span class="leading-snug break-words min-w-0" :class="textSizeClass(h.level)">
          {{ h.text }}
        </span>
      </button>
    </nav>
  </div>
</template>
