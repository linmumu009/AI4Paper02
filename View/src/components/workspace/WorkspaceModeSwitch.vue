<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { ResearchWorkspaceMode } from '../../composables/useResearchWorkspace'

const props = withDefaults(defineProps<{
  modelValue: ResearchWorkspaceMode
  modes?: readonly ResearchWorkspaceMode[]
  ariaLabel?: string
}>(), {
  modes: () => ['card', 'list', 'immersive'],
  ariaLabel: '论文浏览模式',
})

const emit = defineEmits<{
  'update:modelValue': [mode: ResearchWorkspaceMode]
}>()

const buttons = ref<HTMLButtonElement[]>([])

const labels: Record<ResearchWorkspaceMode, string> = {
  card: '卡片',
  list: '列表',
  immersive: '沉浸',
}

function selectMode(mode: ResearchWorkspaceMode) {
  if (mode !== props.modelValue) emit('update:modelValue', mode)
}

function handleArrowKey(event: KeyboardEvent, index: number) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  let nextIndex = index
  if (event.key === 'ArrowLeft') nextIndex = (index - 1 + props.modes.length) % props.modes.length
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % props.modes.length
  if (event.key === 'Home') nextIndex = 0
  if (event.key === 'End') nextIndex = props.modes.length - 1
  const mode = props.modes[nextIndex]
  if (!mode) return
  selectMode(mode)
  void nextTick(() => buttons.value[nextIndex]?.focus())
}

function setButtonRef(element: unknown, index: number) {
  if (element instanceof HTMLButtonElement) buttons.value[index] = element
}
</script>

<template>
  <div
    class="workspace-mode-switch"
    role="radiogroup"
    :aria-label="ariaLabel"
  >
    <button
      v-for="(mode, index) in modes"
      :key="mode"
      :ref="element => setButtonRef(element, index)"
      type="button"
      role="radio"
      class="workspace-mode-switch__button"
      :class="{ 'workspace-mode-switch__button--active': modelValue === mode }"
      :aria-checked="modelValue === mode"
      :tabindex="modelValue === mode ? 0 : -1"
      :title="`${labels[mode]}模式`"
      @click="selectMode(mode)"
      @keydown="handleArrowKey($event, index)"
    >
      {{ labels[mode] }}
    </button>
  </div>
</template>

<style scoped>
.workspace-mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-bg-elevated) 88%, transparent);
}

.workspace-mode-switch__button {
  min-width: 48px;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  transition: color 150ms ease, background-color 150ms ease, box-shadow 150ms ease;
}

.workspace-mode-switch__button:hover {
  color: var(--color-text-primary);
}

.workspace-mode-switch__button:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--color-tinder-pink) 70%, white);
  outline-offset: 2px;
}

.workspace-mode-switch__button--active {
  background: var(--color-bg-card);
  color: var(--color-tinder-pink);
  box-shadow: 0 1px 4px color-mix(in srgb, #000 18%, transparent);
}

@media (max-width: 1199px) {
  .workspace-mode-switch__button {
    min-width: 42px;
    padding-inline: 9px;
  }
}

@media (max-width: 639px) {
  .workspace-mode-switch {
    padding: 2px;
  }

  .workspace-mode-switch__button {
    min-width: 38px;
    height: 26px;
    padding-inline: 7px;
    font-size: 10px;
  }
}
</style>
