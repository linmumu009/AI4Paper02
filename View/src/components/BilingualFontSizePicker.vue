<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useBilingualTheme } from '../composables/useBilingualTheme'

const { theme, setFontSize } = useBilingualTheme()

const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const popoverRef = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
}

function onClickOutside(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node
  if (triggerRef.value?.contains(target) || popoverRef.value?.contains(target)) return
  open.value = false
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onClickOutside))

function onFontSizeInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  setFontSize(val)
}

const sizeLabel = computed(() => `${theme.value.fontSize}px`)
</script>

<template>
  <div class="font-picker-wrapper">
    <!-- 触发按钮 -->
    <button
      ref="triggerRef"
      class="font-picker-trigger"
      :class="{ active: open }"
      title="调整双语字号"
      @click="toggle"
    >
      <span class="font-trigger-label">A</span>
    </button>

    <!-- Popover -->
    <Transition name="font-picker-pop">
      <div v-if="open" ref="popoverRef" class="font-picker-popover">
        <div class="font-picker-header">
          <span class="font-picker-label">字号</span>
          <span class="font-size-badge">{{ sizeLabel }}</span>
        </div>
        <div class="font-picker-slider-row">
          <span class="font-slider-hint">小</span>
          <input
            type="range"
            class="font-picker-slider"
            min="12"
            max="20"
            step="1"
            :value="theme.fontSize"
            @input="onFontSizeInput"
          />
          <span class="font-slider-hint">大</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.font-picker-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.font-picker-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  padding: 0;
}
.font-picker-trigger:hover,
.font-picker-trigger.active {
  background: var(--color-bg-hover);
  border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}

.font-trigger-label {
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
  font-family: serif;
}

/* ── Popover ── */
.font-picker-popover {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 200;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 12px 14px;
  width: 180px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
}

.font-picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.font-picker-label {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.font-size-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: hsl(var(--bilingual-hue), var(--bilingual-saturation), 45%);
  background: hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, 0.12);
  border: 1px solid hsla(var(--bilingual-hue), var(--bilingual-saturation), 50%, 0.25);
  border-radius: 4px;
  padding: 0.1em 0.45em;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
}

/* ── Slider ── */
.font-picker-slider-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.font-slider-hint {
  font-size: 0.65rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.font-picker-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--color-border-light);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.font-picker-slider::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: hsl(var(--bilingual-hue), var(--bilingual-saturation), 55%);
  border: 2px solid var(--color-bg-elevated);
  cursor: pointer;
  transition: background 0.15s;
}
.font-picker-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: hsl(var(--bilingual-hue), var(--bilingual-saturation), 55%);
  border: 2px solid var(--color-bg-elevated);
  cursor: pointer;
}

/* ── Transition ── */
.font-picker-pop-enter-active,
.font-picker-pop-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.font-picker-pop-enter-from,
.font-picker-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}
</style>
