<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  modelValue: string       // YYYY-MM-DD
  availableDates: string[] // only these are selectable
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// Parse the current selection to seed the initial view month
function parseYM(dateStr: string): { year: number; month: number } {
  if (dateStr && /^\d{4}-\d{2}/.test(dateStr)) {
    const [y, m] = dateStr.split('-')
    return { year: Number(y), month: Number(m) }
  }
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1 }
}

const { year: initYear, month: initMonth } = parseYM(props.modelValue)
const viewYear = ref(initYear)
const viewMonth = ref(initMonth) // 1-12

// Keep viewYear/viewMonth synced if parent changes modelValue externally
watch(() => props.modelValue, (val) => {
  const { year, month } = parseYM(val)
  viewYear.value = year
  viewMonth.value = month
})

// O(1) lookup set
const availableSet = computed(() => new Set(props.availableDates))

// Set of months that have at least one available date (for nav limiting)
const availableMonths = computed(() => {
  const s = new Set<string>()
  for (const d of props.availableDates) {
    s.add(d.slice(0, 7)) // YYYY-MM
  }
  return s
})

const monthLabel = computed(() => {
  const d = new Date(viewYear.value, viewMonth.value - 1, 1)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' })
})

const today = new Date().toISOString().slice(0, 10)

// Calendar grid cells: null = padding, string = YYYY-MM-DD
const calendarCells = computed(() => {
  const year = viewYear.value
  const month = viewMonth.value
  const firstDay = new Date(year, month - 1, 1)
  // Monday-first: 0=Mon … 6=Sun
  let startOffset = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(year, month, 0).getDate()

  const cells: (string | null)[] = []
  for (let i = 0; i < startOffset; i++) cells.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    const mm = String(month).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    cells.push(`${year}-${mm}-${dd}`)
  }
  // Pad to complete the last row
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
})

function prevMonth() {
  if (viewMonth.value === 1) {
    viewMonth.value = 12
    viewYear.value -= 1
  } else {
    viewMonth.value -= 1
  }
}

function nextMonth() {
  if (viewMonth.value === 12) {
    viewMonth.value = 1
    viewYear.value += 1
  } else {
    viewMonth.value += 1
  }
}

const currentYM = computed(() => `${viewYear.value}-${String(viewMonth.value).padStart(2, '0')}`)
const hasPrev = computed(() => {
  // Allow going back if any available month is before the current view
  for (const ym of availableMonths.value) {
    if (ym < currentYM.value) return true
  }
  return false
})
const hasNext = computed(() => {
  for (const ym of availableMonths.value) {
    if (ym > currentYM.value) return true
  }
  return false
})

function selectDate(date: string | null) {
  if (!date) return
  if (!availableSet.value.has(date)) return
  emit('update:modelValue', date)
}

const weekdays = ['一', '二', '三', '四', '五', '六', '日']
</script>

<template>
  <div class="select-none p-3">
    <!-- Month navigation header -->
    <div class="flex items-center justify-between mb-2 px-0.5">
      <button
        class="w-7 h-7 flex items-center justify-center rounded-lg transition-colors border-none bg-transparent"
        :class="hasPrev
          ? 'text-text-secondary hover:text-text-primary hover:bg-bg-hover cursor-pointer'
          : 'text-text-muted/20 cursor-default'"
        :disabled="!hasPrev"
        @click="hasPrev && prevMonth()"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>

      <span class="text-sm font-semibold text-text-primary tracking-tight">{{ monthLabel }}</span>

      <button
        class="w-7 h-7 flex items-center justify-center rounded-lg transition-colors border-none bg-transparent"
        :class="hasNext
          ? 'text-text-secondary hover:text-text-primary hover:bg-bg-hover cursor-pointer'
          : 'text-text-muted/20 cursor-default'"
        :disabled="!hasNext"
        @click="hasNext && nextMonth()"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
    </div>

    <!-- Weekday headers -->
    <div class="grid grid-cols-7 mb-1">
      <div
        v-for="wd in weekdays"
        :key="wd"
        class="text-center text-[10px] font-medium text-text-muted/50 py-1"
      >
        {{ wd }}
      </div>
    </div>

    <!-- Day grid -->
    <div class="grid grid-cols-7 gap-y-0.5">
      <div
        v-for="(cell, idx) in calendarCells"
        :key="idx"
        class="flex items-center justify-center"
      >
        <!-- Empty padding cell -->
        <div v-if="!cell" class="w-8 h-8" />

        <!-- Date cell -->
        <button
          v-else
          class="relative w-8 h-8 flex flex-col items-center justify-center rounded-lg text-[13px] font-medium transition-colors border-none"
          :class="[
            cell === modelValue
              ? 'bg-tinder-pink text-white shadow-sm cursor-pointer'
              : availableSet.has(cell)
                ? cell === today
                  ? 'text-tinder-pink hover:bg-tinder-pink/10 cursor-pointer bg-transparent'
                  : 'text-text-primary hover:bg-bg-hover cursor-pointer bg-transparent'
                : 'text-text-muted/25 cursor-default bg-transparent'
          ]"
          :disabled="!availableSet.has(cell)"
          @click="selectDate(cell)"
        >
          <span class="leading-none">{{ Number(cell.slice(8)) }}</span>
          <!-- Dot indicator for available dates (when not selected) -->
          <span
            v-if="availableSet.has(cell) && cell !== modelValue"
            class="absolute bottom-1 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full"
            :class="cell === today ? 'bg-tinder-pink' : 'bg-text-muted/40'"
          />
        </button>
      </div>
    </div>

    <!-- Quick legend -->
    <div class="flex items-center gap-3 mt-2.5 pt-2 border-t border-border/50 px-0.5">
      <div class="flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-text-muted/40 shrink-0" />
        <span class="text-[10px] text-text-muted/50">有数据</span>
      </div>
      <div class="flex items-center gap-1">
        <span class="w-4 h-4 rounded-md bg-tinder-pink shrink-0" />
        <span class="text-[10px] text-text-muted/50">已选中</span>
      </div>
    </div>
  </div>
</template>
