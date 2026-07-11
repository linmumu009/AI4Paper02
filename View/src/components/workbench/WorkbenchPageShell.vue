<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{
  /** Emoji or character shown before the title */
  icon?: string
  title: string
  /** Short one-line description rendered below the title row */
  description?: string
  /** Compact header padding style (used by IdeaLabView) */
  compact?: boolean
  /** When set, renders a back button that navigates to this path */
  backTo?: string
}>(), {
  compact: false,
})

const router = useRouter()
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header bar -->
    <div
      class="shrink-0 border-b border-border bg-bg"
      :class="props.compact ? 'px-4 sm:px-5 pt-3.5 pb-3' : 'px-4 sm:px-6 pt-4 sm:pt-6 pb-4'"
    >
      <!-- Title row -->
      <div
        class="flex items-center gap-3"
        :class="(props.description || $slots.subtitle || $slots.filters) ? (props.compact ? 'mb-2.5' : 'mb-3') : ''"
      >
        <button
          v-if="props.backTo"
          class="wb-back-btn"
          @click="router.push(props.backTo)"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
          返回
        </button>
        <h1
          class="flex items-center gap-2 font-bold text-text-primary flex-1 min-w-0"
          :class="props.compact ? 'text-base' : 'text-xl'"
        >
          <span
            v-if="props.icon"
            class="shrink-0"
            :class="props.compact ? 'text-base' : 'text-2xl'"
          >{{ props.icon }}</span>
          <span>{{ props.title }}</span>
          <slot name="title-extra" />
        </h1>
        <slot name="header-right" />
      </div>

      <!-- Optional description text -->
      <p v-if="props.description" class="text-xs text-text-muted leading-relaxed mb-2">
        {{ props.description }}
      </p>

      <!-- Optional stats / subtitle content -->
      <slot name="subtitle" />

      <!-- Optional filters row (tabs, search, etc.) -->
      <slot name="filters" />
    </div>

    <!-- Page content (each view provides its own layout) -->
    <slot />
  </div>
</template>
