<script setup lang="ts">
export type RoundStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'
export type RoundColor = 'accent' | 'blue' | 'purple'

const props = defineProps<{
  roundLabel: string
  title: string
  status: RoundStatus
  color: RoundColor
  collapsed: boolean
  statusDetail?: string
}>()

const emit = defineEmits<{
  toggleCollapse: []
}>()
</script>

<template>
  <div
    class="rounded-2xl overflow-hidden transition-all duration-400"
    :class="[
      status === 'running'
        ? 'border border-border/50 shadow-[0_0_28px_-6px_rgba(255,68,88,0.12)]'
        : status === 'error'
          ? 'border border-red-400/20'
          : 'border border-border/40',
    ]"
  >
    <!-- Header -->
    <button
      class="w-full flex items-center justify-between px-5 py-4 hover:bg-bg-elevated/30 transition-colors text-left"
      @click="emit('toggleCollapse')"
    >
      <div class="flex items-center gap-3 min-w-0">
        <!-- Round badge: neutral, only accent when running -->
        <span
          class="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded font-mono tracking-wider border transition-colors duration-300"
          :class="status === 'running'
            ? 'bg-accent-primary/10 text-accent-primary border-accent-primary/20'
            : status === 'done'
              ? 'bg-transparent text-text-muted/60 border-border/40'
              : status === 'error'
                ? 'bg-red-400/8 text-red-400/70 border-red-400/20'
                : 'bg-transparent text-text-muted/40 border-border/30'"
        >{{ roundLabel }}</span>

        <span class="text-sm font-medium text-text-secondary truncate">{{ title }}</span>
      </div>

      <div class="flex items-center gap-2.5 shrink-0 ml-2">
        <!-- Status indicator -->
        <template v-if="status === 'running'">
          <span class="flex items-center gap-1.5 text-xs text-accent-primary/80">
            <span class="inline-block w-1 h-1 rounded-full bg-accent-primary animate-pulse"></span>
            {{ statusDetail || '进行中' }}
          </span>
        </template>
        <template v-else-if="status === 'done'">
          <span class="flex items-center gap-1 text-xs text-text-muted/60">
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="m20 6-11 11-5-5"/>
            </svg>
            <span v-if="statusDetail">{{ statusDetail }}</span>
            <span v-else>完成</span>
          </span>
        </template>
        <template v-else-if="status === 'error'">
          <span class="text-xs text-red-400/70">错误</span>
        </template>
        <template v-else-if="status === 'cancelled'">
          <span class="text-xs text-text-muted/40">已中止</span>
        </template>

        <!-- Collapse chevron -->
        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          class="text-text-muted/30 transition-transform duration-200"
          :class="collapsed ? '' : 'rotate-180'">
          <path d="m18 15-6-6-6 6"/>
        </svg>
      </div>
    </button>

    <!-- Collapsible body with smooth height transition -->
    <Transition name="round-body">
      <div v-if="!collapsed" class="overflow-hidden">
        <div class="px-6 pt-1 pb-6 border-t border-border/20">
          <slot />
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.round-body-enter-active,
.round-body-leave-active {
  transition: max-height 0.35s ease, opacity 0.25s ease;
  max-height: 2000px;
}
.round-body-enter-from,
.round-body-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
