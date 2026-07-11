<script setup lang="ts">
/**
 * WhyNotDrawer — "可能错过的论文" 组件
 *
 * 两种使用模式：
 *   - 默认（self-contained）：渲染自己的折叠 pill 和展开面板，适合嵌入页面固定位置。
 *   - embedded=true：只渲染内容面板（无 pill toggle），由父组件通过 modal 控制显示，
 *     挂载时自动加载数据，支持 @close 事件。
 */
import { ref, computed, watch, onMounted } from 'vue'
import { fetchSuppressions, nudgePaper, type SuppressedPaper } from '../api/index'

const props = defineProps<{
  date: string
  isAuthenticated: boolean
  /** When true: renders content-only (no toggle pill), auto-loads on mount, emits 'close'. */
  embedded?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

// ── State ───────────────────────────────────────────────────────────────────

const isOpen = ref(false)
const loading = ref(false)
const suppressions = ref<SuppressedPaper[]>([])
const nudgedIds = ref<Set<string>>(new Set())
const error = ref('')

// ── Load suppressions on open ────────────────────────────────────────────────

async function load() {
  if (!props.isAuthenticated || !props.date) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchSuppressions(props.date, 5)
    suppressions.value = res.suppressions
  } catch {
    error.value = '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function toggle() {
  isOpen.value = !isOpen.value
  if (isOpen.value && suppressions.value.length === 0) {
    load()
  }
}

// Reload when date changes and drawer is open (or embedded mode)
watch(() => props.date, () => {
  suppressions.value = []
  nudgedIds.value = new Set()
  if (isOpen.value || props.embedded) load()
})

// Auto-load in embedded mode
onMounted(() => {
  if (props.embedded) load()
})

// ── Nudge ────────────────────────────────────────────────────────────────────

async function pullIn(paper: SuppressedPaper) {
  try {
    await nudgePaper({
      paper_id: paper.paper_id,
      direction: 'more',
      categories: paper.categories || [],
      institution_tier: paper.institution_tier || 4,
    })
    nudgedIds.value = new Set([...nudgedIds.value, paper.paper_id])
  } catch {
    // fail silently — nudge is non-critical
  }
}

// ── Display helpers ──────────────────────────────────────────────────────────

const count = computed(() => suppressions.value.length)

function tierLabel(tier?: number): string {
  switch (tier) {
    case 1: return 'T1'
    case 2: return 'T2'
    case 3: return 'T3'
    default: return 'T4'
  }
}

function tierClass(tier?: number): string {
  switch (tier) {
    case 1: return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
    case 2: return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
    case 3: return 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300'
    default: return 'bg-zinc-100 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300'
  }
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'text-green-600 dark:text-green-400'
  if (score >= 0.4) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-zinc-400'
}
</script>

<template>
  <div v-if="isAuthenticated" class="why-not-wrapper">

    <!-- ── Self-contained mode: toggle pill ── -->
    <template v-if="!embedded">
      <button
        class="why-not-toggle"
        :class="{ 'why-not-toggle--open': isOpen }"
        @click="toggle"
      >
        <span class="why-not-icon">🔍</span>
        <span class="why-not-label">
          可能错过的论文
          <span v-if="count > 0" class="why-not-count">{{ count }}</span>
        </span>
        <svg
          class="why-not-chevron"
          :class="{ 'rotate-180': isOpen }"
          width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
    </template>

    <!-- ── Content panel (shown when open in self-contained mode, or always in embedded mode) ── -->
    <Transition name="drawer-slide">
      <div v-if="embedded || isOpen" class="why-not-panel" :class="{ 'why-not-panel--embedded': embedded }">

        <!-- Embedded header with close button -->
        <div v-if="embedded" class="why-not-embedded-header">
          <span class="text-[13px] font-semibold text-text-primary">可能错过的论文</span>
          <button class="why-not-close-btn" @click="emit('close')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="why-not-empty">
          <span class="text-text-muted text-sm">加载中…</span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="why-not-empty">
          <span class="text-red-500 text-sm">{{ error }}</span>
        </div>

        <!-- Empty -->
        <div v-else-if="count === 0" class="why-not-empty">
          <span class="text-text-muted text-sm">暂时没有可补看的论文，或偏好数据还在积累中。</span>
        </div>

        <!-- Paper list -->
        <div v-else class="why-not-list">
          <p class="why-not-desc">
            这些论文主题相关度不错，但当前偏好模型给分较低。点"想看更多类似"会帮助推荐变准。
          </p>
          <div
            v-for="paper in suppressions"
            :key="paper.paper_id"
            class="why-not-card"
            :class="{ 'why-not-card--nudged': nudgedIds.has(paper.paper_id) }"
          >
            <!-- Header row -->
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <p class="text-sm font-semibold text-text-primary leading-snug line-clamp-2">
                  {{ paper.short_title || paper['📖标题'] }}
                </p>
                <p class="text-xs text-text-muted mt-0.5 truncate">
                  {{ paper['📖标题'] && paper.short_title ? paper['📖标题'] : '' }}
                </p>
              </div>
              <!-- Scores -->
              <div class="flex items-center gap-2 shrink-0 mt-0.5">
                <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded" :class="tierClass(paper.institution_tier)">
                  {{ tierLabel(paper.institution_tier) }}
                </span>
                <span class="text-[11px] font-bold tabular-nums" :class="scoreColor(paper.relevance_score)">
                  {{ (paper.relevance_score * 100).toFixed(0) }}
                </span>
              </div>
            </div>

            <!-- Institution -->
            <p v-if="paper.institution" class="text-xs text-text-muted mt-1 truncate">
              🏛 {{ paper.institution }}
            </p>

            <!-- Suppression reason -->
            <div class="why-not-reason">
              <span class="text-[11px] text-text-muted leading-relaxed">
                {{ paper.suppression_summary }}
              </span>
            </div>

            <!-- Contributions (top 2) -->
            <div v-if="paper.contributions?.length" class="flex flex-wrap gap-1 mt-1.5">
              <span
                v-for="c in paper.contributions.slice(0, 2)"
                :key="c.key"
                class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] leading-tight"
                :class="c.delta < 0
                  ? 'bg-red-50 text-red-600 dark:bg-red-900/25 dark:text-red-400'
                  : 'bg-green-50 text-green-600 dark:bg-green-900/25 dark:text-green-400'"
                :title="c.label"
              >
                {{ c.delta < 0 ? '↓' : '↑' }} {{ c.key }}
              </span>
            </div>

            <!-- Nudge button -->
            <div class="flex justify-end mt-2">
              <button
                v-if="!nudgedIds.has(paper.paper_id)"
                class="why-not-pullin-btn"
                @click="pullIn(paper)"
              >
                想看更多类似 →
              </button>
              <span v-else class="text-[11px] text-tinder-blue font-medium">
                ✓ 已加入偏好
              </span>
            </div>
          </div>
        </div>

      </div>
    </Transition>
  </div>
</template>

<style scoped>
.why-not-wrapper {
  width: 100%;
  max-width: var(--card-max-w, 420px);
  margin: 0 auto;
}

.why-not-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 14px;
  border-radius: 10px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-light);
  color: var(--color-text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  text-align: left;
}

.why-not-toggle:hover,
.why-not-toggle--open {
  background: var(--color-bg-card);
  border-color: var(--color-border);
  color: var(--color-text-secondary);
}

.why-not-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.why-not-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 5px;
}

.why-not-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--color-text-muted);
  color: var(--color-bg-primary);
  font-size: 9px;
  font-weight: 700;
}

.why-not-chevron {
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

/* Panel */
.why-not-panel {
  margin-top: 6px;
  border-radius: 12px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
}

.why-not-empty {
  padding: 16px;
  text-align: center;
}

.why-not-desc {
  font-size: 11px;
  color: var(--color-text-muted);
  padding: 10px 14px 6px;
  line-height: 1.5;
}

.why-not-list {
  padding-bottom: 8px;
}

.why-not-card {
  padding: 12px 14px;
  border-top: 1px solid var(--color-border-light);
  transition: background 0.15s;
}

.why-not-card:first-child {
  border-top: none;
}

.why-not-card--nudged {
  background: color-mix(in srgb, var(--color-bg-card) 90%, var(--tinder-blue, #0078ff) 10%);
}

.why-not-reason {
  margin-top: 5px;
  padding: 5px 8px;
  border-radius: 6px;
  background: var(--color-bg-elevated);
  border-left: 2px solid var(--color-border);
}

.why-not-pullin-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.why-not-pullin-btn:hover {
  background: var(--color-bg-elevated);
  border-color: var(--tinder-blue, #0078ff);
  color: var(--tinder-blue, #0078ff);
}

/* Transition */
.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Embedded mode: no rounded top corners, no extra wrapper margin */
.why-not-panel--embedded {
  margin-top: 0;
  border-radius: 0;
  border: none;
  max-height: 70dvh;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.why-not-embedded-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--color-border-light);
}

.why-not-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.why-not-close-btn:hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}
</style>
