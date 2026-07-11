<script setup lang="ts">
defineOptions({ name: 'DailyResearchTaskline' })

export interface TasklineProgressTask {
  key: string
  label: string
  done: boolean
}

export interface TasklineItem {
  id: string
  label: string
  sub?: string
  /** done = green check; active = needs attention (has count); idle = info-only */
  status: 'done' | 'active' | 'idle'
  action?: string
  count?: number
  urgent?: boolean
  /** Special progress item: renders inline task dots instead of a count badge */
  isProgress?: boolean
  progressTasks?: TasklineProgressTask[]
  streakDays?: number
}

const props = defineProps<{
  items: TasklineItem[]
}>()

const emit = defineEmits<{
  action: [id: string]
}>()

function handleClick(item: TasklineItem) {
  if (item.action) emit('action', item.action)
}
</script>

<template>
  <!-- Only rendered on lg+ screens via parent v-if; hide on <lg via CSS just in case -->
  <div class="taskline hidden lg:flex items-center gap-1.5 px-4 py-1.5 border-b border-border/40 overflow-x-auto scrollbar-none shrink-0">

    <template v-for="item in items" :key="item.id">

      <!-- Progress item — non-clickable, shows task dots + streak -->
      <div
        v-if="item.isProgress"
        class="taskline-chip taskline-chip--info flex items-center gap-2"
      >
        <span class="taskline-chip__label">今日进度</span>
        <div class="flex items-center gap-1">
          <span
            v-for="t in item.progressTasks"
            :key="t.key"
            class="taskline-dot"
            :class="t.done ? 'taskline-dot--done' : 'taskline-dot--pending'"
            :title="t.label"
          />
        </div>
        <span
          v-if="item.streakDays && item.streakDays > 0"
          class="taskline-chip__sub ml-0.5"
        >{{ item.streakDays }}天连续</span>
      </div>

      <!-- Divider after progress item -->
      <span v-if="item.isProgress" class="taskline-divider" aria-hidden="true" />

      <!-- Action / info item -->
      <component
        :is="item.action ? 'button' : 'div'"
        v-else
        class="taskline-chip"
        :class="[
          item.status === 'done'   && 'taskline-chip--done',
          item.status === 'active' && (item.urgent ? 'taskline-chip--urgent' : 'taskline-chip--active'),
          item.status === 'idle'   && 'taskline-chip--idle',
          item.action              && 'taskline-chip--btn',
        ]"
        :type="item.action ? 'button' : undefined"
        @click="handleClick(item)"
      >
        <!-- Done checkmark -->
        <svg
          v-if="item.status === 'done'"
          class="taskline-chip__icon taskline-chip__icon--done"
          viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="3 8 6.5 12 13 4" />
        </svg>

        <span class="taskline-chip__label" :class="item.status === 'done' && 'line-through opacity-60'">
          {{ item.label }}
        </span>

        <span
          v-if="item.count != null && item.status !== 'done'"
          class="taskline-chip__badge"
        >{{ item.count }}</span>

        <span
          v-else-if="item.sub && item.status !== 'done'"
          class="taskline-chip__sub"
        >{{ item.sub }}</span>

        <!-- Arrow for clickable items that are active -->
        <svg
          v-if="item.action && item.status !== 'done'"
          class="taskline-chip__arrow"
          viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <path d="M6 4l4 4-4 4" />
        </svg>
      </component>

    </template>

  </div>
</template>

<style scoped>
/* ── Container ─────────────────────────────────────────────────────────── */
.taskline {
  background: color-mix(in srgb, var(--color-bg-card) 40%, transparent);
  min-height: 34px;
  scrollbar-width: none;
}
.taskline::-webkit-scrollbar { display: none; }

/* ── Divider ───────────────────────────────────────────────────────────── */
.taskline-divider {
  width: 1px;
  height: 16px;
  background: color-mix(in srgb, var(--color-border) 60%, transparent);
  flex-shrink: 0;
}

/* ── Task dots (progress item) ─────────────────────────────────────────── */
.taskline-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.taskline-dot--done    { background: var(--color-tinder-green, #21bf73); }
.taskline-dot--pending { background: color-mix(in srgb, var(--color-border) 80%, transparent); }

/* ── Base chip ─────────────────────────────────────────────────────────── */
.taskline-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px 2px 7px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-border) 50%, transparent);
  background: transparent;
  white-space: nowrap;
  flex-shrink: 0;
  font: inherit;
  cursor: default;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, opacity 0.15s;
}

/* Clickable */
.taskline-chip--btn {
  cursor: pointer;
}
.taskline-chip--btn:hover {
  background: color-mix(in srgb, var(--color-bg-elevated) 70%, transparent);
  border-color: color-mix(in srgb, var(--color-border) 80%, transparent);
}

/* Info (progress chip) */
.taskline-chip--info {
  border-color: transparent;
  background: transparent;
  padding-left: 0;
}

/* Active: needs attention */
.taskline-chip--active {
  border-color: color-mix(in srgb, var(--color-border) 70%, transparent);
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-tinder-blue, #4b9eff) 50%, transparent);
}

/* Urgent: missed / review due */
.taskline-chip--urgent {
  border-color: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 40%, transparent);
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-tinder-pink, #fd267a) 50%, transparent);
}

/* Done: muted */
.taskline-chip--done {
  opacity: 0.5;
  border-color: color-mix(in srgb, var(--color-border) 35%, transparent);
}

/* Idle: info, not urgent */
.taskline-chip--idle {
  border-color: color-mix(in srgb, var(--color-border) 40%, transparent);
  opacity: 0.75;
}

/* ── Chip internals ────────────────────────────────────────────────────── */
.taskline-chip__label {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary);
  line-height: 1.3;
}

.taskline-chip__sub {
  font-size: 10px;
  color: var(--color-text-muted);
  line-height: 1.3;
}

.taskline-chip__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  background: color-mix(in srgb, var(--color-bg-elevated) 90%, transparent);
  color: var(--color-text-secondary);
  border: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent);
}

.taskline-chip--urgent .taskline-chip__badge {
  background: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 15%, transparent);
  color: var(--color-tinder-pink, #fd267a);
  border-color: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 30%, transparent);
}

.taskline-chip__icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
}
.taskline-chip__icon--done {
  color: var(--color-tinder-green, #21bf73);
}

.taskline-chip__arrow {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  opacity: 0.6;
}
</style>
