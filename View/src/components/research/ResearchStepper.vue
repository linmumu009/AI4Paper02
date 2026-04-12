<script setup lang="ts">
export type StepStatus = 'pending' | 'running' | 'done' | 'error' | 'cancelled'

export interface StepDef {
  id: string
  label: string
  sublabel?: string
  color: 'accent' | 'blue' | 'purple'
}

const props = defineProps<{
  steps: StepDef[]
  statuses: StepStatus[]
}>()

const emit = defineEmits<{
  stepClick: [index: number]
}>()

const colorMap: Record<string, { ring: string; badge: string; text: string; dot: string; line: string }> = {
  accent: {
    ring: 'ring-accent-primary',
    badge: 'bg-accent-primary/15 text-accent-primary border-accent-primary/30',
    text: 'text-accent-primary',
    dot: 'bg-accent-primary',
    line: 'bg-accent-primary',
  },
  blue: {
    ring: 'ring-blue-400',
    badge: 'bg-blue-400/15 text-blue-400 border-blue-400/30',
    text: 'text-blue-400',
    dot: 'bg-blue-400',
    line: 'bg-blue-400',
  },
  purple: {
    ring: 'ring-purple-400',
    badge: 'bg-purple-400/15 text-purple-400 border-purple-400/30',
    text: 'text-purple-400',
    dot: 'bg-purple-400',
    line: 'bg-purple-400',
  },
}

function isDone(i: number) { return props.statuses[i] === 'done' }
function isRunning(i: number) { return props.statuses[i] === 'running' }
function isError(i: number) { return props.statuses[i] === 'error' }
function isCancelled(i: number) { return props.statuses[i] === 'cancelled' }
function isPending(i: number) { return props.statuses[i] === 'pending' }
function isActive(i: number) { return isRunning(i) || isDone(i) || isError(i) || isCancelled(i) }

function linePercent(i: number): number {
  // Line between step i and step i+1: fill based on the *next* step's state
  const nextStatus = props.statuses[i + 1]
  if (!nextStatus || nextStatus === 'pending') return 0
  return 100
}

function handleClick(i: number) {
  if (isActive(i)) emit('stepClick', i)
}
</script>

<template>
  <div class="flex items-center justify-between px-4 py-4">
    <template v-for="(step, i) in steps" :key="step.id">
      <!-- Step node -->
      <button
        class="flex flex-col items-center gap-1.5 relative z-10 transition-opacity"
        :class="[
          isPending(i) && !isRunning(i) ? 'opacity-30 cursor-default' : 'cursor-pointer',
        ]"
        :disabled="isPending(i) && !isRunning(i)"
        @click="handleClick(i)"
      >
        <!-- Circle indicator -->
        <div
          class="relative flex items-center justify-center w-8 h-8 rounded-full border transition-all duration-500"
          :class="[
            isDone(i) ? 'border-border bg-bg-elevated' :
            isError(i) ? 'border-red-400/40 bg-red-400/5' :
            isCancelled(i) ? 'border-border/40 bg-transparent' :
            isRunning(i) ? 'ring-2 ring-accent-primary/30 ring-offset-0 border-accent-primary/60 bg-bg-elevated research-pulse' :
            'border-border/50 bg-transparent'
          ]"
        >
          <!-- Done: checkmark (subtle) -->
          <svg v-if="isDone(i)" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
            class="text-text-muted">
            <path d="m20 6-11 11-5-5"/>
          </svg>
          <!-- Error: X -->
          <svg v-else-if="isError(i)" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
            class="text-red-400/70">
            <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
          </svg>
          <!-- Cancelled: dash -->
          <svg v-else-if="isCancelled(i)" xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
            class="text-text-muted/50">
            <path d="M5 12h14"/>
          </svg>
          <!-- Running: spinner -->
          <svg v-else-if="isRunning(i)" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            class="animate-spin text-accent-primary">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          <!-- Pending: number -->
          <span v-else class="text-[11px] font-medium text-text-muted/40">{{ i + 1 }}</span>
        </div>

        <!-- Label -->
        <div class="text-center">
          <div
            class="text-[10px] font-medium leading-tight tracking-wide"
            :class="[
              isDone(i) ? 'text-text-muted' :
              isError(i) ? 'text-red-400/70' :
              isCancelled(i) ? 'text-text-muted/40' :
              isRunning(i) ? 'text-accent-primary' :
              'text-text-muted/40'
            ]"
          >{{ step.label }}</div>
          <div v-if="step.sublabel" class="text-[9px] text-text-muted/30 mt-0.5 leading-tight font-mono">{{ step.sublabel }}</div>
        </div>
      </button>

      <!-- Connector line (between steps) -->
      <div
        v-if="i < steps.length - 1"
        class="flex-1 mx-3 h-px bg-border/40 relative overflow-hidden"
        style="min-width: 24px"
      >
        <div
          class="absolute inset-y-0 left-0 transition-all duration-700 ease-in-out"
          :class="[
            isRunning(i + 1) ? 'bg-accent-primary/40 research-line-shimmer' :
            isDone(i + 1) || isError(i + 1) || isCancelled(i + 1) ? 'bg-border' : ''
          ]"
          :style="{ width: linePercent(i) + '%' }"
        />
      </div>
    </template>
  </div>
</template>
