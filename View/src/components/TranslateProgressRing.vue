<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 0–100 */
    percent: number
    size?: number
  }>(),
  { size: 20 },
)

const p = computed(() => Math.max(0, Math.min(100, Math.round(props.percent))))

const cx = computed(() => props.size / 2)
const cy = computed(() => props.size / 2)
const r = computed(() => (props.size - 4) / 2)
const c = computed(() => 2 * Math.PI * r.value)
const dashOffset = computed(() => c.value * (1 - p.value / 100))
const gTransform = computed(() => `rotate(-90 ${cx.value} ${cy.value})`)
</script>

<template>
  <svg
    class="shrink-0 text-amber-500"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    aria-hidden="true"
  >
    <g :transform="gTransform">
      <circle
        :cx="cx"
        :cy="cy"
        :r="r"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        class="opacity-20"
      />
      <circle
        :cx="cx"
        :cy="cy"
        :r="r"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        :stroke-dasharray="c"
        :stroke-dashoffset="dashOffset"
      />
    </g>
    <text
      :x="cx"
      :y="cy + 1"
      text-anchor="middle"
      dominant-baseline="middle"
      class="fill-text-secondary"
      :style="{ fontSize: `${Math.max(6, size * 0.28)}px`, fontWeight: 600 }"
    >{{ p }}</text>
  </svg>
</template>
