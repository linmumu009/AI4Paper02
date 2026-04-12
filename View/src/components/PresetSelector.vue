<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

interface PresetOption {
  id: number
  name: string
  model?: string         // LLM presets carry this field
  prompt_content?: string // Prompt presets carry this field
}

interface NoneOption {
  label: string          // e.g. "手动配置" / "自定义" / "使用默认（继承）"
}

const props = withDefaults(defineProps<{
  presets: PresetOption[]
  modelValue: number | string | null
  /** text shown in trigger when nothing selected (no noneOption) */
  placeholder?: string
  /** if set, renders a "none/clear" option at the top of the dropdown */
  noneOption?: NoneOption | null
  /** hex accent color used for selected state */
  accentColor?: string
  /** whether to show the model name as subtitle in each dropdown row */
  showModelHint?: boolean
  /** callback when user clicks "+ 创建预设" */
  onGoToCreate?: (() => void) | null
  /** dropdown direction */
  dropDirection?: 'down' | 'up'
}>(), {
  placeholder: '未选择，使用系统默认',
  noneOption: null,
  accentColor: '#6366f1',
  showModelHint: false,
  onGoToCreate: null,
  dropDirection: 'down',
})

const emit = defineEmits<{
  'update:modelValue': [val: number | string | null]
}>()

const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)
const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

// ─── Dropdown fixed position (Teleport to body) ─────────────────────────────

interface DropPos {
  top: number
  left: number
  minWidth: number
}

const dropPos = ref<DropPos>({ top: 0, left: 0, minWidth: 0 })

function calcPosition() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const dropH = dropdownRef.value?.offsetHeight ?? 280 // estimated fallback
  const spaceBelow = window.innerHeight - rect.bottom
  const spaceAbove = rect.top

  const forceUp = props.dropDirection === 'up'
  const goUp = forceUp || (spaceBelow < dropH + 8 && spaceAbove > spaceBelow)

  dropPos.value = {
    top: goUp ? rect.top - dropH - 4 + window.scrollY : rect.bottom + 4 + window.scrollY,
    left: rect.left + window.scrollX,
    minWidth: rect.width,
  }
}

const showSearch = computed(() => props.presets.length >= 5)

const filteredPresets = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return props.presets
  return props.presets.filter(p =>
    p.name.toLowerCase().includes(q) ||
    (p.model || '').toLowerCase().includes(q)
  )
})

async function toggleOpen() {
  if (open.value) {
    open.value = false
    searchQuery.value = ''
    return
  }
  open.value = true
  await nextTick()
  calcPosition()
  if (showSearch.value) {
    await nextTick()
    searchInputRef.value?.focus()
  }
}

// ─── Derived ───────────────────────────────────────────────────────────────

const selectedPreset = computed(() =>
  props.modelValue != null && props.modelValue !== ''
    ? props.presets.find(p => String(p.id) === String(props.modelValue)) ?? null
    : null
)

const isNoneSelected = computed(() =>
  props.modelValue == null || props.modelValue === ''
)

/** Text displayed on the trigger button */
const triggerLabel = computed(() => {
  if (selectedPreset.value) return selectedPreset.value.name
  if (isNoneSelected.value && props.noneOption) return props.noneOption.label
  return props.placeholder
})

/** Subtitle displayed in the trigger when a LLM preset is selected */
const triggerSubtitle = computed(() => {
  if (props.showModelHint && selectedPreset.value?.model)
    return selectedPreset.value.model
  return null
})

const hasSelection = computed(() => selectedPreset.value !== null)

// ─── Style helpers ─────────────────────────────────────────────────────────

const accentHex = computed(() => props.accentColor)

function gradientStyle(active: boolean) {
  if (!active) return {}
  return { background: `linear-gradient(135deg, ${accentHex.value}cc, ${accentHex.value})` }
}

// ─── Interactions ──────────────────────────────────────────────────────────

function select(id: number | string | null) {
  emit('update:modelValue', id)
  open.value = false
  searchQuery.value = ''
}

function clear() {
  emit('update:modelValue', null)
}

function handleOutsideClick(e: MouseEvent) {
  if (
    triggerRef.value && !triggerRef.value.contains(e.target as Node) &&
    dropdownRef.value && !dropdownRef.value.contains(e.target as Node)
  ) {
    open.value = false
  }
}

function handleScroll() {
  if (open.value) calcPosition()
}

onMounted(() => {
  document.addEventListener('mousedown', handleOutsideClick)
  window.addEventListener('scroll', handleScroll, true)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', handleOutsideClick)
  window.removeEventListener('scroll', handleScroll, true)
})
</script>

<template>
  <div class="preset-selector inline-flex items-center gap-1.5 min-w-0">
    <!-- Trigger button -->
    <button
      ref="triggerRef"
      type="button"
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all duration-150 min-w-0 max-w-[220px]"
      :class="hasSelection
        ? 'border-transparent text-white shadow-sm'
        : 'border-border text-text-secondary hover:border-text-muted bg-bg-elevated/60'"
      :style="hasSelection ? gradientStyle(true) : {}"
      @click="toggleOpen"
    >
      <!-- icon: model chip or prompt chip -->
      <svg class="w-3 h-3 shrink-0 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path v-if="showModelHint" d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>
        <path v-else d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline v-if="!showModelHint" points="14 2 14 8 20 8"/>
      </svg>

      <span class="flex flex-col items-start min-w-0">
        <span class="truncate leading-tight" :class="!hasSelection && !noneOption ? 'opacity-50 italic' : ''">
          {{ triggerLabel }}
        </span>
        <span v-if="triggerSubtitle" class="text-[10px] font-mono opacity-70 truncate leading-tight">
          {{ triggerSubtitle }}
        </span>
      </span>

      <!-- Chevron -->
      <svg
        class="w-3 h-3 shrink-0 opacity-60 transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
        viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
      >
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>

    <!-- Clear button (shown when a real preset is selected) -->
    <button
      v-if="hasSelection"
      type="button"
      class="w-5 h-5 flex items-center justify-center rounded-full border border-border/60 text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors text-[10px] shrink-0"
      title="清除选择"
      @click.stop="clear"
    >✕</button>

    <!-- Dropdown panel — teleported to body to escape overflow:hidden ancestors -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 scale-95 -translate-y-1"
        enter-to-class="opacity-100 scale-100 translate-y-0"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 scale-100 translate-y-0"
        leave-to-class="opacity-0 scale-95 -translate-y-1"
      >
        <div
          v-if="open"
          ref="dropdownRef"
          class="fixed z-[9999] w-64 bg-bg-card border border-border rounded-xl shadow-xl overflow-hidden"
          :style="{
            top: dropPos.top + 'px',
            left: dropPos.left + 'px',
            minWidth: dropPos.minWidth + 'px',
          }"
        >
          <!-- Header -->
          <div class="px-3 pt-2.5 pb-1.5 border-b border-border/50">
            <p class="text-[11px] font-semibold text-text-secondary uppercase tracking-wide">
              {{ showModelHint ? '选择模型预设' : '选择提示词预设' }}
            </p>
          </div>

          <!-- Search box — shown only when presets >= 5 -->
          <div v-if="showSearch" class="px-2 py-1.5 border-b border-border/40">
            <div class="relative">
              <svg class="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-muted/60 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                type="text"
                placeholder="搜索..."
                class="w-full pl-6 pr-2 py-1 text-xs bg-bg-elevated border border-border/60 rounded-md text-text-primary placeholder-text-muted/60 focus:outline-none focus:border-text-muted/40 transition-colors"
                @click.stop
                @keydown.escape="open = false; searchQuery = ''"
              />
            </div>
          </div>

          <div class="max-h-52 overflow-y-auto">
            <!-- None / default option (hidden when searching) -->
            <button
              v-if="noneOption && !searchQuery"
              type="button"
              class="w-full px-3 py-2 text-left text-xs flex items-center justify-between gap-2 transition-colors"
              :class="isNoneSelected
                ? 'bg-bg-elevated text-text-primary font-medium'
                : 'text-text-muted hover:bg-bg-hover'"
              @click="select(null)"
            >
              <span class="italic">{{ noneOption.label }}</span>
              <svg v-if="isNoneSelected" class="w-3 h-3 shrink-0" :style="{ color: accentHex }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </button>

            <!-- No presets state -->
            <div v-if="presets.length === 0" class="px-3 py-3">
              <p class="text-xs text-text-muted mb-2">暂无预设</p>
              <button
                v-if="onGoToCreate"
                type="button"
                class="text-xs font-medium transition-colors hover:opacity-80"
                :style="{ color: accentHex }"
                @click="onGoToCreate?.(); open = false"
              >+ 创建预设 →</button>
            </div>

            <!-- No search results -->
            <div v-else-if="filteredPresets.length === 0" class="px-3 py-4 text-center">
              <p class="text-xs text-text-muted">无匹配「{{ searchQuery }}」的预设</p>
              <button
                type="button"
                class="mt-1.5 text-[11px] transition-colors hover:opacity-80"
                :style="{ color: accentHex }"
                @click="searchQuery = ''"
              >清除搜索</button>
            </div>

            <!-- Preset options -->
            <button
              v-for="preset in filteredPresets"
              :key="preset.id"
              type="button"
              class="w-full px-3 py-2 text-left text-xs flex items-center justify-between gap-2 transition-colors"
              :class="String(modelValue) === String(preset.id)
                ? 'bg-bg-elevated text-text-primary'
                : 'text-text-secondary hover:bg-bg-hover'"
              @click="select(preset.id)"
            >
              <span class="flex flex-col min-w-0">
                <span class="font-medium truncate">{{ preset.name }}</span>
                <span v-if="showModelHint && preset.model" class="text-[10px] font-mono text-text-muted truncate opacity-80">
                  {{ preset.model }}
                </span>
              </span>
              <svg
                v-if="String(modelValue) === String(preset.id)"
                class="w-3 h-3 shrink-0"
                :style="{ color: accentHex }"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
              >
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </button>
          </div>

          <!-- Footer: go to create (when presets exist but user wants more) -->
          <div v-if="presets.length > 0 && onGoToCreate" class="border-t border-border/50 px-3 py-2">
            <button
              type="button"
              class="text-xs transition-colors hover:opacity-80"
              :style="{ color: accentHex }"
              @click="onGoToCreate?.(); open = false"
            >管理预设 →</button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
