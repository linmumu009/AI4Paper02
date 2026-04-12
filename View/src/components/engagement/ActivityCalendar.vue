<script setup lang="ts">
/**
 * ActivityCalendar — GitHub-style contribution heatmap for research activity.
 * Adds week-day labels and month separators vs the old plain grid.
 */
import { computed } from 'vue'
import type { ActivityCalendarDay } from '../../api'

const props = defineProps<{
  days: ActivityCalendarDay[]
  today: string
}>()

// Build a grid: weeks as columns, days (Mon-Sun) as rows
// We display Mon-Sun (1-7) vertically
interface CalCell {
  day_key: string
  completed: boolean
  partial: boolean
  tasks_done: number
  isToday: boolean
  isEmpty: boolean  // padding cell
}

interface WeekCol {
  cells: CalCell[]
  /** First day_key in this week column (for month label logic) */
  firstKey: string
  monthLabel: string | null
}

const grid = computed<WeekCol[]>(() => {
  if (!props.days.length) return []

  // Pad so first cell aligns to Monday
  const first = new Date(props.days[0].day_key + 'T00:00:00')
  const dow = (first.getDay() + 6) % 7  // 0=Mon … 6=Sun
  const paddedDays: (ActivityCalendarDay | null)[] = [
    ...Array(dow).fill(null),
    ...props.days,
  ]

  // Fill weeks
  const weeks: WeekCol[] = []
  for (let i = 0; i < paddedDays.length; i += 7) {
    const slice = paddedDays.slice(i, i + 7)
    while (slice.length < 7) slice.push(null)

    const cells: CalCell[] = slice.map(d => d
      ? {
          day_key: d.day_key,
          completed: d.completed,
          partial: d.partial,
          tasks_done: d.tasks_done,
          isToday: d.day_key === props.today,
          isEmpty: false,
        }
      : { day_key: '', completed: false, partial: false, tasks_done: 0, isToday: false, isEmpty: true }
    )

    // Month label: show when the first non-empty cell changes month
    let monthLabel: string | null = null
    const firstReal = cells.find(c => !c.isEmpty)
    if (firstReal) {
      const d = new Date(firstReal.day_key + 'T00:00:00')
      const prevWeek = weeks[weeks.length - 1]
      const prevFirstReal = prevWeek?.cells.find(c => !c.isEmpty)
      if (!prevFirstReal || new Date(prevFirstReal.day_key + 'T00:00:00').getMonth() !== d.getMonth()) {
        monthLabel = d.toLocaleDateString('zh-CN', { month: 'short' })
      }
    }

    weeks.push({ cells, firstKey: cells.find(c => !c.isEmpty)?.day_key ?? '', monthLabel })
  }

  return weeks
})

const completedCount = computed(() => props.days.filter(d => d.completed).length)

function cellClass(cell: CalCell): string {
  if (cell.isEmpty) return 'bg-transparent'
  if (cell.isToday) return cell.completed
    ? 'bg-tinder-gold ring-2 ring-tinder-gold/50'
    : cell.partial
      ? 'bg-tinder-gold/30 ring-2 ring-tinder-blue/40'
      : 'bg-bg-elevated ring-2 ring-tinder-blue/40'
  if (cell.completed) return 'bg-tinder-gold/80 hover:bg-tinder-gold'
  if (cell.partial) return 'bg-tinder-gold/25 hover:bg-tinder-gold/35'
  return 'bg-bg-elevated hover:bg-bg-hover border border-border/40'
}

function cellTitle(cell: CalCell): string {
  if (cell.isEmpty) return ''
  const d = new Date(cell.day_key + 'T00:00:00')
  const label = d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  if (cell.completed) return `${label} · 全部完成`
  if (cell.partial) return `${label} · 完成 ${cell.tasks_done}/3`
  return `${label} · 未记录`
}

const DOW_LABELS = ['一', '三', '五']  // Mon, Wed, Fri positions (0,2,4 → indices)
const DOW_SHOW = [0, 2, 4]
</script>

<template>
  <div>
    <!-- Month labels row -->
    <div class="flex gap-1 mb-0.5 pl-6">
      <div
        v-for="week in grid"
        :key="week.firstKey"
        class="w-3.5 text-[9px] text-text-muted text-center shrink-0"
      >{{ week.monthLabel ?? '' }}</div>
    </div>

    <div class="flex gap-1">
      <!-- Day-of-week labels on left -->
      <div class="flex flex-col gap-1 mr-0.5 shrink-0 justify-around" style="padding-top: 0px;">
        <div
          v-for="i in 7"
          :key="i"
          class="h-3.5 text-[9px] text-text-muted flex items-center"
        >{{ DOW_SHOW.includes(i - 1) ? DOW_LABELS[DOW_SHOW.indexOf(i - 1)] : '' }}</div>
      </div>

      <!-- Week columns -->
      <div class="flex gap-1">
        <div
          v-for="week in grid"
          :key="week.firstKey"
          class="flex flex-col gap-1"
        >
          <div
            v-for="(cell, di) in week.cells"
            :key="`${week.firstKey}-${di}`"
            :title="cellTitle(cell)"
            class="w-3.5 h-3.5 rounded-sm transition-colors cursor-default"
            :class="cellClass(cell)"
          />
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="flex items-center justify-between mt-2">
      <div class="flex items-center gap-3 text-[9px] text-text-muted">
        <span class="flex items-center gap-1">
          <span class="inline-block w-3 h-3 rounded-sm bg-tinder-gold/80"></span>完成
        </span>
        <span class="flex items-center gap-1">
          <span class="inline-block w-3 h-3 rounded-sm bg-tinder-gold/25"></span>部分
        </span>
        <span class="flex items-center gap-1">
          <span class="inline-block w-3 h-3 rounded-sm bg-bg-elevated border border-border/40"></span>未记录
        </span>
      </div>
      <p class="text-[10px] text-text-muted">{{ completedCount }} / {{ days.length }} 天完成</p>
    </div>
  </div>
</template>
