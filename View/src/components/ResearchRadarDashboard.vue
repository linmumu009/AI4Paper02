<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ResearchRadarResponse, RadarRecapStatus } from '@shared/api/radar'

defineOptions({ name: 'ResearchRadarDashboard' })

const props = defineProps<{
  radar: ResearchRadarResponse | null
  loading: boolean
  isAuthenticated: boolean
}>()

const emit = defineEmits<{
  (e: 'open-missed'): void
  (e: 'open-ideas'): void
  (e: 'open-recap'): void
}>()

const collapsed = ref(false)

// ── Derived values ─────────────────────────────────────────────────────────

const papersLabel = computed(() => {
  const p = props.radar?.papers
  if (!p) return '—'
  if (p.total_available === 0) return '暂无'
  const quota = p.quota_limit
  if (quota !== null && p.total_available > quota) return `${quota} 篇`
  return `${p.total_available} 篇`
})

const papersSub = computed(() => {
  const p = props.radar?.papers
  if (!p) return '今日推荐'
  return p.is_fallback ? `来自 ${p.effective_date}` : '今日推荐'
})

const hasPapers = computed(() => (props.radar?.papers?.total_available ?? 0) > 0)

const missedCount = computed(() => props.radar?.missed?.count ?? 0)

const reviewCount = computed(() => props.radar?.review?.count ?? 0)

const recapStatus = computed<RadarRecapStatus>(() => props.radar?.recap?.status ?? 'none')
const recapPaperCount = computed(() => props.radar?.recap?.paper_count ?? 0)
const recapLabel = computed(() => {
  switch (recapStatus.value) {
    case 'ok': return `${recapPaperCount.value} 篇`
    case 'generating': return '生成中'
    case 'error': return '失败'
    case 'no_llm_config': return '未配置'
    case 'insufficient_papers': return `${recapPaperCount.value} 篇`
    default: return '暂无'
  }
})
// Active = recap exists; still clickable in other states so user can see why / trigger generation
const recapActive = computed(() => recapStatus.value === 'ok')

const ideasVisibleCount = computed(() => props.radar?.ideas?.visible_count ?? 0)
const ideasTotalCount = computed(() => props.radar?.ideas?.total_available ?? 0)
const ideasSub = computed(() => {
  const i = props.radar?.ideas
  if (!i) return '今日灵感'
  return i.is_fallback ? `来自 ${i.effective_date}` : '今日灵感'
})
</script>

<template>
  <div class="radar-dashboard shrink-0" :class="{ 'radar-dashboard--collapsed': collapsed }">
    <div class="radar-dashboard-inner">
      <!-- Label -->
      <span class="radar-label">研究雷达</span>

      <!-- Chips -->
      <div v-if="loading" class="radar-chips">
        <div v-for="i in 3" :key="i" class="radar-chip radar-chip--skeleton" />
      </div>

      <div v-else-if="radar && !collapsed" class="radar-chips">
        <!-- Papers chip (always shown) -->
        <div
          class="radar-chip"
          :class="hasPapers ? 'radar-chip--active' : 'radar-chip--muted'"
          title="今日推荐论文"
        >
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
          <span class="radar-chip-value">{{ papersLabel }}</span>
          <span class="radar-chip-sub">{{ papersSub }}</span>
        </div>

        <!-- Missed chip (authenticated, any count) -->
        <button
          v-if="isAuthenticated"
          type="button"
          class="radar-chip"
          :class="missedCount > 0 ? 'radar-chip--active radar-chip--clickable' : 'radar-chip--muted radar-chip--clickable'"
          title="可能错过的论文（点击查看）"
          @click="emit('open-missed')"
        >
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span class="radar-chip-value">{{ missedCount > 0 ? `${missedCount} 篇` : '暂无' }}</span>
          <span class="radar-chip-sub">可能错过</span>
        </button>

        <!-- Review chip (authenticated, info-only on desktop — handled via mobile swipe) -->
        <div
          v-if="isAuthenticated && reviewCount > 0"
          class="radar-chip"
          :class="reviewCount > 0 ? 'radar-chip--active' : 'radar-chip--muted'"
          title="到期复习卡片（可在移动端处理）"
        >
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
          <span class="radar-chip-value">{{ reviewCount > 0 ? `${reviewCount} 篇` : '暂无' }}</span>
          <span class="radar-chip-sub">到期复习</span>
        </div>

        <!-- Recap chip (authenticated — always clickable; page shows status & can trigger generation) -->
        <button
          v-if="isAuthenticated"
          type="button"
          class="radar-chip radar-chip--clickable"
          :class="recapActive ? 'radar-chip--active' : 'radar-chip--muted'"
          :title="recapStatus === 'ok' ? '查看本周研究回顾' : '前往本周回顾'"
          @click="emit('open-recap')"
        >
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span class="radar-chip-value">{{ recapLabel }}</span>
          <span class="radar-chip-sub">本周回顾</span>
        </button>

        <!-- Ideas chip (authenticated) -->
        <button
          v-if="isAuthenticated"
          type="button"
          class="radar-chip radar-chip--clickable"
          :class="ideasVisibleCount > 0 ? 'radar-chip--active' : 'radar-chip--muted'"
          title="前往灵感工作台"
          @click="emit('open-ideas')"
        >
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/>
            <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>
            <line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>
            <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>
          </svg>
          <span class="radar-chip-value">
            {{ ideasVisibleCount > 0 ? `${ideasVisibleCount} 个` : '暂无' }}
          </span>
          <span class="radar-chip-sub">{{ ideasSub }}</span>
        </button>

        <!-- Unauthenticated CTA -->
        <div v-if="!isAuthenticated" class="radar-chip radar-chip--muted radar-chip--auth-hint">
          <svg class="radar-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4"/><path d="M6 20v-2a6 6 0 0 1 12 0v2"/>
          </svg>
          <span class="radar-chip-value">登录</span>
          <span class="radar-chip-sub">查看个性化</span>
        </div>
      </div>

      <!-- Right: collapse toggle -->
      <button
        type="button"
        class="radar-collapse-btn"
        :title="collapsed ? '展开研究雷达' : '收起研究雷达'"
        @click="collapsed = !collapsed"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline v-if="collapsed" points="6 9 12 15 18 9" />
          <polyline v-else points="18 15 12 9 6 15" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* ── Container ─────────────────────────────────────────────────────────── */
.radar-dashboard {
  /* Hairline separator, no filled background block that looks like a nav bar */
  box-shadow: inset 0 -1px 0 color-mix(in srgb, var(--color-border) 60%, transparent);
  background: transparent;
}

.radar-dashboard-inner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 16px;
  min-height: 36px;
}

/* ── Label ─────────────────────────────────────────────────────────────── */
.radar-label {
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-muted);
  white-space: nowrap;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  flex-shrink: 0;
  opacity: 0.7;
}

/* ── Chips scroll area ─────────────────────────────────────────────────── */
.radar-chips {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.radar-chips::-webkit-scrollbar {
  display: none;
}

/* ── Base chip ─────────────────────────────────────────────────────────── */
.radar-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  /* Smaller padding → less visual bulk */
  padding: 2px 8px 2px 6px;
  border-radius: 8px;
  /* Flat by default: no fill, faint border */
  border: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  background: transparent;
  white-space: nowrap;
  flex-shrink: 0;
  font: inherit;
  cursor: default;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}

/* Muted state: use lighter text/border colors, NOT whole-chip opacity */
.radar-chip--muted {
  border-color: color-mix(in srgb, var(--color-border) 35%, transparent);
}

/* Active state: slightly stronger border, left accent line */
.radar-chip--active {
  border-color: color-mix(in srgb, var(--color-border) 80%, transparent);
  box-shadow: inset 2px 0 0 color-mix(in srgb, var(--color-text-secondary) 35%, transparent);
}

/* Clickable */
.radar-chip--clickable {
  cursor: pointer;
}

.radar-chip--clickable:hover {
  background: color-mix(in srgb, var(--color-bg-elevated) 70%, transparent);
  border-color: var(--color-border);
}

.radar-chip--clickable:focus-visible {
  outline: 2px solid var(--color-border);
  outline-offset: 1px;
}

/* ── Skeleton ──────────────────────────────────────────────────────────── */
.radar-chip--skeleton {
  width: 72px;
  height: 22px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-bg-elevated) 50%, transparent);
  border: 1px solid transparent;
  /* Slower, very faint pulse — don't compete with paper card loading */
  animation: radar-pulse 2.5s ease-in-out infinite;
}

@keyframes radar-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 0.2; }
}

/* ── Chip internals ────────────────────────────────────────────────────── */
.radar-chip-icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
  /* Always subdued; only the text carries meaning */
  color: var(--color-text-muted);
  opacity: 0.65;
}

.radar-chip-value {
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  /* muted chip: lighter text */
  color: var(--color-text-secondary);
}

.radar-chip--muted .radar-chip-value {
  color: var(--color-text-muted);
  font-weight: 500;
}

.radar-chip-sub {
  font-size: 10px;
  color: var(--color-text-muted);
  line-height: 1;
  opacity: 0.8;
}

.radar-chip--auth-hint {
  border-style: dashed;
}

/* ── Collapse button ───────────────────────────────────────────────────── */
.radar-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: none;
  background: transparent;
  /* Very faint by default; hover reveals it */
  color: var(--color-text-muted);
  opacity: 0.4;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 0.15s, background 0.15s;
}

.radar-collapse-btn:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--color-bg-elevated) 60%, transparent);
}

.radar-collapse-btn:focus-visible {
  opacity: 1;
  outline: 2px solid var(--color-border);
  outline-offset: 1px;
}

/* ── Collapsed state ───────────────────────────────────────────────────── */
.radar-dashboard--collapsed .radar-dashboard-inner {
  min-height: 28px;
  padding-top: 3px;
  padding-bottom: 3px;
}
</style>
