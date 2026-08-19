<script setup lang="ts">
import type { SummaryDensity } from '../types/paper'

const props = withDefaults(defineProps<{
  modelValue: SummaryDensity
  detailedAvailable?: boolean
  loading?: boolean
  compact?: boolean
}>(), {
  detailedAvailable: true,
  loading: false,
  compact: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: SummaryDensity]
}>()

function select(value: SummaryDensity) {
  if (value === 'detailed' && (!props.detailedAvailable || props.loading)) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="summary-density" :class="{ 'summary-density--compact': compact }">
    <span v-if="!compact" class="summary-density__label">阅读版本</span>
    <div class="summary-density__options" role="group" aria-label="选择摘要阅读版本">
      <button
        type="button"
        class="summary-density__button"
        :class="{ 'summary-density__button--active': modelValue === 'concise' }"
        :aria-pressed="modelValue === 'concise'"
        title="信息更短，适合快速浏览和分享"
        @click.stop="select('concise')"
      >
        精简版
      </button>
      <button
        type="button"
        class="summary-density__button"
        :class="{ 'summary-density__button--active': modelValue === 'detailed' }"
        :disabled="!detailedAvailable || loading"
        :aria-pressed="modelValue === 'detailed'"
        :aria-busy="loading"
        :title="detailedAvailable ? '保留更多研究细节，适合精读' : '这篇论文暂时只有精简版'"
        @click.stop="select('detailed')"
      >
        <span v-if="loading" class="summary-density__spinner" aria-hidden="true"></span>
        详细版
      </button>
    </div>
  </div>
</template>

<style scoped>
.summary-density {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.summary-density__label {
  color: var(--color-text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.summary-density__options {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-bg-elevated);
}

.summary-density__button {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 0;
  border-radius: 999px;
  padding: 4px 11px;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  transition: background-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.summary-density__button:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.summary-density__button--active {
  background: var(--color-bg-card);
  color: var(--color-tinder-blue, var(--color-text-primary));
  box-shadow: 0 1px 4px rgb(0 0 0 / 12%);
}

.summary-density__button:focus-visible {
  outline: 2px solid var(--color-tinder-blue, currentColor);
  outline-offset: 1px;
}

.summary-density__button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.summary-density__spinner {
  width: 9px;
  height: 9px;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: summary-density-spin 700ms linear infinite;
}

.summary-density--compact .summary-density__button {
  min-height: 26px;
  padding: 4px 9px;
  font-size: 10px;
}

@keyframes summary-density-spin {
  to { transform: rotate(360deg); }
}
</style>
