<script setup lang="ts">
import { computed } from 'vue'
import type { ResearchRadarResponse } from '@shared/api/radar'
import type { TasklineItem } from './DailyResearchTaskline.vue'

defineOptions({ name: 'TodayMissionBar' })

const props = defineProps<{
  items: TasklineItem[]
  radar: ResearchRadarResponse | null
  radarLoading: boolean
  isAuthenticated: boolean
}>()

const emit = defineEmits<{
  action: [id: string]
}>()

// ── Item splitting ──────────────────────────────────────────────────
const progressItem = computed(() => props.items.find(i => i.isProgress) ?? null)
const actionItems  = computed(() => props.items.filter(i => !i.isProgress))

// ── Priority rules for primary task ────────────────────────────────
// User goal: show ONE clear "next action", not a wall of equal chips.
// Priority: urgent/overdue first, then high-value KB actions, then fallback browse.
const PRIMARY_ORDER = [
  'open_review',        // spaced-review cards overdue — highest urgency
  'open_missed',        // missed papers surfaced by rec engine
  'open_unread',        // collected but unread KB papers
  'open_research',      // enough KB papers to launch deep research
  'continue_browse',    // still papers left today — fallback
  'open_reactivation',  // actionable follow-up questions from recap — higher value than summary
  'open_recap',         // weekly recap summary — low urgency, optional
]

const primaryTask = computed<TasklineItem | null>(() => {
  for (const id of PRIMARY_ORDER) {
    const found = actionItems.value.find(i => i.id === id && i.status !== 'done')
    if (found) return found
  }
  // Fallback: first item with an action that isn't done
  return actionItems.value.find(i => i.action && i.status !== 'done') ?? null
})

const secondaryItems = computed(() =>
  actionItems.value.filter(i => i !== primaryTask.value),
)

// ── Radar summary (right side) — compact, read-only context ────────
// Only the values that are unique to the radar and not covered by taskline chips.
const papersLabel = computed(() => {
  const p = props.radar?.papers
  if (!p || p.total_available === 0) return null
  const quota = p.quota_limit
  return (quota !== null && p.total_available > quota)
    ? `${quota} 篇`
    : `${p.total_available} 篇`
})

const papersFallback = computed(() =>
  props.radar?.papers?.is_fallback ? props.radar.papers.effective_date : null,
)

const ideasCount = computed(() => props.radar?.ideas?.visible_count ?? 0)
const ideasSub   = computed(() => {
  const i = props.radar?.ideas
  return (i?.is_fallback && i.effective_date) ? i.effective_date : null
})

const showRadarSummary = computed(() =>
  props.isAuthenticated && !props.radarLoading && props.radar != null &&
  (papersLabel.value != null || ideasCount.value > 0),
)

// ── Click handler ───────────────────────────────────────────────────
function handleClick(item: TasklineItem) {
  if (item.action) emit('action', item.action)
}
</script>

<template>
  <!-- Only rendered on lg+ screens (same as old DailyResearchTaskline) -->
  <div class="mission-bar hidden lg:flex items-center shrink-0">

    <!-- Progress dots + streak -->
    <div
      v-if="progressItem"
      class="flex items-center gap-1.5 px-4 py-1.5 shrink-0"
    >
      <span class="text-[10px] font-medium text-text-muted leading-none select-none">今日</span>
      <div class="flex items-center gap-1">
        <span
          v-for="t in progressItem.progressTasks"
          :key="t.key"
          class="mission-dot"
          :class="t.done ? 'mission-dot--done' : 'mission-dot--pending'"
          :title="t.label"
        />
      </div>
      <span
        v-if="progressItem.streakDays && progressItem.streakDays > 0"
        class="text-[10px] text-text-muted leading-none ml-0.5 select-none"
      >{{ progressItem.streakDays }}天</span>
    </div>

    <!-- Divider -->
    <span v-if="progressItem" class="mission-divider" aria-hidden="true" />

    <!-- ── Primary action ───────────────────────────────────────────── -->
    <component
      :is="primaryTask?.action ? 'button' : 'div'"
      v-if="primaryTask"
      class="primary-chip"
      :class="[
        primaryTask.urgent                    && 'primary-chip--urgent',
        !primaryTask.urgent && primaryTask.action && primaryTask.status !== 'done' && 'primary-chip--active',
        primaryTask.status === 'done'         && 'primary-chip--done',
        primaryTask.action                    && 'primary-chip--btn',
      ]"
      :type="primaryTask.action ? 'button' : undefined"
      @click="handleClick(primaryTask)"
    >
      <!-- Urgency indicator -->
      <span v-if="primaryTask.urgent && primaryTask.status !== 'done'" class="primary-chip__urgency-dot" />

      <!-- Done checkmark -->
      <svg
        v-if="primaryTask.status === 'done'"
        class="primary-chip__icon primary-chip__icon--done"
        viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <polyline points="3 8 6.5 12 13 4" />
      </svg>

      <span
        class="primary-chip__label"
        :class="primaryTask.status === 'done' && 'line-through opacity-60'"
      >{{ primaryTask.label }}</span>

      <span
        v-if="primaryTask.count != null && primaryTask.status !== 'done'"
        class="primary-chip__badge"
      >{{ primaryTask.count }}</span>
      <span
        v-else-if="primaryTask.sub && primaryTask.status !== 'done'"
        class="primary-chip__sub"
      >{{ primaryTask.sub }}</span>

      <!-- Right arrow for clickable non-done items -->
      <svg
        v-if="primaryTask.action && primaryTask.status !== 'done'"
        class="primary-chip__arrow"
        viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <path d="M6 4l4 4-4 4" />
      </svg>
    </component>

    <!-- ── Secondary actions ─────────────────────────────────────────── -->
    <div v-if="secondaryItems.length" class="flex items-center gap-1 px-1.5 overflow-x-auto scrollbar-none">
      <component
        :is="item.action && item.status !== 'done' ? 'button' : 'div'"
        v-for="item in secondaryItems"
        :key="item.id"
        class="secondary-chip"
        :class="[
          item.status === 'done'                            && 'secondary-chip--done',
          item.urgent && item.status !== 'done'             && 'secondary-chip--urgent',
          item.action && item.status !== 'done'             && 'secondary-chip--btn',
        ]"
        :type="item.action && item.status !== 'done' ? 'button' : undefined"
        @click="handleClick(item)"
      >
        <span
          class="secondary-chip__label"
          :class="item.status === 'done' && 'line-through opacity-50'"
        >{{ item.label }}</span>
        <span
          v-if="item.count != null && item.status !== 'done'"
          class="secondary-chip__count"
        >{{ item.count }}</span>
        <span
          v-else-if="item.sub && item.status !== 'done'"
          class="secondary-chip__sub"
        >{{ item.sub }}</span>
      </component>
    </div>

    <!-- Spacer -->
    <div class="flex-1 min-w-0" />

    <!-- ── Radar summary (right side, folded into compact text) ──────── -->
    <!-- Only shows papers count and ideas — items already covered by taskline chips
         (missed, review, recap) are intentionally omitted here to avoid duplication. -->
    <div v-if="showRadarSummary" class="flex items-center gap-2 px-4 shrink-0">
      <!-- Today's paper count — context only, not clickable -->
      <span v-if="papersLabel" class="radar-summary-stat">
        <svg class="radar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        {{ papersLabel }}
        <span v-if="papersFallback" class="radar-summary-stat__fallback"> · {{ papersFallback }}</span>
      </span>

      <!-- Ideas count — links to workbench -->
      <button
        v-if="ideasCount > 0"
        type="button"
        class="radar-summary-btn"
        :title="ideasSub ? `今日灵感，来自 ${ideasSub}` : '前往灵感工作台'"
        @click="emit('action', 'open_ideas')"
      >
        <svg class="radar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/>
          <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/>
          <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>
          <line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>
          <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/>
          <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>
        </svg>
        {{ ideasCount }} 灵感
      </button>
    </div>

    <!-- Radar loading skeleton (right side) -->
    <div
      v-else-if="radarLoading && isAuthenticated"
      class="flex items-center gap-1.5 px-4 ml-auto shrink-0"
    >
      <div class="skeleton-chip" />
      <div class="skeleton-chip" />
    </div>

  </div>
</template>

<style scoped>
/* ── Container ─────────────────────────────────────────────────────── */
.mission-bar {
  background: color-mix(in srgb, var(--color-bg-card) 40%, transparent);
  min-height: 36px;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 40%, transparent);
  overflow-x: hidden;
}

/* ── Progress dots ─────────────────────────────────────────────────── */
.mission-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.mission-dot--done    { background: var(--color-tinder-green, #21bf73); }
.mission-dot--pending { background: color-mix(in srgb, var(--color-border) 80%, transparent); }

/* ── Divider ───────────────────────────────────────────────────────── */
.mission-divider {
  width: 1px;
  height: 14px;
  background: color-mix(in srgb, var(--color-border) 50%, transparent);
  flex-shrink: 0;
  margin: 0 4px;
}

/* ── Primary chip ──────────────────────────────────────────────────── */
.primary-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px 3px 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent);
  background: color-mix(in srgb, var(--color-bg-elevated) 55%, transparent);
  white-space: nowrap;
  flex-shrink: 0;
  font: inherit;
  cursor: default;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, opacity 0.15s;
  margin-left: 2px;
  margin-right: 4px;
}
.primary-chip--btn {
  cursor: pointer;
}
.primary-chip--btn:hover {
  background: color-mix(in srgb, var(--color-bg-elevated) 90%, transparent);
  border-color: color-mix(in srgb, var(--color-border) 85%, transparent);
}
.primary-chip--active {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-tinder-blue, #4b9eff) 55%, transparent);
}
.primary-chip--urgent {
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-tinder-pink, #fd267a) 60%, transparent);
  border-color: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 35%, transparent);
}
.primary-chip--done {
  opacity: 0.4;
  border-color: transparent;
  background: transparent;
  cursor: default;
}

.primary-chip__urgency-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-tinder-pink, #fd267a);
  flex-shrink: 0;
}
.primary-chip__icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
}
.primary-chip__icon--done { color: var(--color-tinder-green, #21bf73); }

.primary-chip__label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
}
.primary-chip__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  background: color-mix(in srgb, var(--color-tinder-blue, #4b9eff) 15%, transparent);
  color: var(--color-tinder-blue, #4b9eff);
  border: 1px solid color-mix(in srgb, var(--color-tinder-blue, #4b9eff) 30%, transparent);
}
.primary-chip--urgent .primary-chip__badge {
  background: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 15%, transparent);
  color: var(--color-tinder-pink, #fd267a);
  border-color: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 30%, transparent);
}
.primary-chip__sub {
  font-size: 10px;
  color: var(--color-text-muted);
  line-height: 1.3;
}
.primary-chip__arrow {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  opacity: 0.65;
}

/* ── Secondary chips ───────────────────────────────────────────────── */
.secondary-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--color-border) 38%, transparent);
  background: transparent;
  white-space: nowrap;
  flex-shrink: 0;
  font: inherit;
  cursor: default;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, opacity 0.15s;
}
.secondary-chip--btn {
  cursor: pointer;
}
.secondary-chip--btn:hover {
  background: color-mix(in srgb, var(--color-bg-elevated) 55%, transparent);
  border-color: color-mix(in srgb, var(--color-border) 65%, transparent);
}
.secondary-chip--done {
  opacity: 0.38;
  border-color: transparent;
}
.secondary-chip--urgent {
  border-color: color-mix(in srgb, var(--color-tinder-pink, #fd267a) 35%, transparent);
}

.secondary-chip__label {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--color-text-secondary);
  line-height: 1.3;
}
.secondary-chip__count {
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-muted);
  line-height: 1.3;
}
.secondary-chip__sub {
  font-size: 10px;
  color: var(--color-text-muted);
  line-height: 1.3;
}

/* ── Radar summary ─────────────────────────────────────────────────── */
.radar-summary-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--color-text-muted);
  white-space: nowrap;
  opacity: 0.75;
}
.radar-summary-stat__fallback {
  opacity: 0.65;
}
.radar-icon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  opacity: 0.55;
}
.radar-summary-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 5px;
  border: 1px solid color-mix(in srgb, var(--color-border) 38%, transparent);
  background: transparent;
  font: inherit;
  font-size: 10px;
  color: var(--color-text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.radar-summary-btn:hover {
  background: color-mix(in srgb, var(--color-bg-elevated) 55%, transparent);
  color: var(--color-text-secondary);
}

/* ── Loading skeleton ──────────────────────────────────────────────── */
.skeleton-chip {
  width: 52px;
  height: 20px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-bg-elevated) 50%, transparent);
  animation: skeleton-pulse 2.5s ease-in-out infinite;
}
@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.45; }
  50%       { opacity: 0.2; }
}
</style>
