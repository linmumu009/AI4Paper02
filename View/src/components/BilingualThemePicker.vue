<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useBilingualTheme, BILINGUAL_PRESETS, type BilingualPreset } from '../composables/useBilingualTheme'

const { theme, setPreset, setIntensity, isActivePreset } = useBilingualTheme()

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

function presetSwatchStyle(preset: BilingualPreset) {
  return {
    background: `hsl(${preset.hue}, ${preset.saturation}%, 55%)`,
  }
}

function onIntensityInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  setIntensity(val)
}

</script>

<template>
  <div class="bilingual-picker-wrapper">
    <!-- 触发按钮 -->
    <button
      ref="triggerRef"
      class="picker-trigger"
      :class="{ active: open }"
      title="自定义双语配色"
      @click="toggle"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="4" cy="4" r="2.5" fill="hsl(195,70%,55%)"/>
        <circle cx="12" cy="4" r="2.5" fill="hsl(150,60%,50%)"/>
        <circle cx="4" cy="12" r="2.5" fill="hsl(270,60%,60%)"/>
        <circle cx="12" cy="12" r="2.5" fill="hsl(30,80%,55%)"/>
      </svg>
    </button>

    <!-- Popover -->
    <Transition name="picker-pop">
      <div v-if="open" ref="popoverRef" class="picker-popover">
        <div class="picker-label">配色</div>
        <div class="picker-swatches">
          <button
            v-for="preset in BILINGUAL_PRESETS"
            :key="preset.name"
            class="swatch"
            :class="{ selected: isActivePreset(preset) }"
            :title="preset.name"
            :style="presetSwatchStyle(preset)"
            @click="setPreset(preset)"
          />
        </div>

        <div class="picker-label picker-label--mt">浓度</div>
        <div class="picker-slider-row">
          <span class="slider-hint">淡</span>
          <input
            type="range"
            class="picker-slider"
            min="2"
            max="15"
            step="1"
            :value="theme.intensity"
            @input="onIntensityInput"
          />
          <span class="slider-hint">浓</span>
        </div>

      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bilingual-picker-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.picker-trigger {
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
.picker-trigger:hover,
.picker-trigger.active {
  background: var(--color-bg-hover);
  border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}

/* ── Popover ── */
.picker-popover {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 200;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 12px 14px;
  width: 196px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.18);
}

.picker-label {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.picker-label--mt {
  margin-top: 12px;
}

/* ── Swatches ── */
.picker-swatches {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.swatch {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  transition: transform 0.12s, border-color 0.12s;
  padding: 0;
  outline: none;
}
.swatch:hover {
  transform: scale(1.15);
}
.swatch.selected {
  border-color: var(--color-text-primary);
  transform: scale(1.1);
}

/* ── Slider ── */
.picker-slider-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.slider-hint {
  font-size: 0.65rem;
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.picker-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--color-border-light);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.picker-slider::-webkit-slider-thumb {
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
.picker-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: hsl(var(--bilingual-hue), var(--bilingual-saturation), 55%);
  border: 2px solid var(--color-bg-elevated);
  cursor: pointer;
}

/* ── Transition ── */
.picker-pop-enter-active,
.picker-pop-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.picker-pop-enter-from,
.picker-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}
</style>
