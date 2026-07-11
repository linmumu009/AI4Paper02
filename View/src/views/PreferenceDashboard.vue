<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchPreferenceProfile,
  rebuildPreferenceProfile,
  fetchSuppressions,
  fetchCalibrationStatus,
  nudgePaper,
  categoryNudge,
  type PreferenceProfileSummary,
  type CategoryDetail,
  type CalibrationStatus,
  type SuppressedPaper,
} from '../api/index'
import EmbeddedPaperDetailPanel from '../components/EmbeddedPaperDetailPanel.vue'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), {
  embedded: false,
})

const router = useRouter()

// Inline paper detail (embedded mode only)
const selectedPaperId = ref<string | null>(null)

const loading = ref(true)
const error = ref('')
const rebuilding = ref(false)
const rebuildMsg = ref('')
const profile = ref<PreferenceProfileSummary | null>(null)
const calibration = ref<CalibrationStatus | null>(null)
const suppressions = ref<SuppressedPaper[]>([])

// ── Category calibration state ───────────────────────────────────────────────
const nudgingCategory = ref<string | null>(null)
const categoryToasts = ref<Record<string, string>>({})

const suppressionDate = computed(() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [profileRes, calRes] = await Promise.allSettled([
      fetchPreferenceProfile(),
      fetchCalibrationStatus(),
    ])
    if (profileRes.status === 'fulfilled') profile.value = profileRes.value
    if (calRes.status === 'fulfilled') calibration.value = calRes.value

    if (profile.value?.has_enough_data) {
      try {
        const res = await fetchSuppressions(suppressionDate.value, 5)
        suppressions.value = res.suppressions
      } catch {
        suppressions.value = []
      }
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function handleRebuild() {
  rebuilding.value = true
  rebuildMsg.value = ''
  try {
    await rebuildPreferenceProfile()
    rebuildMsg.value = '偏好已重新计算'
    await loadAll()
  } catch (e: any) {
    rebuildMsg.value = e?.response?.data?.detail || '重新计算失败'
  } finally {
    rebuilding.value = false
    setTimeout(() => { rebuildMsg.value = '' }, 3000)
  }
}

async function handleNudgeMore(paper: SuppressedPaper) {
  try {
    await nudgePaper({
      paper_id: paper.paper_id,
      direction: 'more',
      categories: paper.categories,
      institution_tier: paper.institution_tier,
    })
    suppressions.value = suppressions.value.filter(p => p.paper_id !== paper.paper_id)
  } catch {
    // fail silently — nudge is non-critical
  }
}

async function handleCategoryNudge(category: string, direction: 'more' | 'less' | 'reset') {
  nudgingCategory.value = category
  try {
    await categoryNudge(category, direction)
    const toastMap: Record<string, string> = {
      more: `已增加「${category}」方向推荐，下一轮日报生效`,
      less: `已减少「${category}」方向推荐，下一轮日报生效`,
      reset: `已重置「${category}」方向的显式偏好信号`,
    }
    categoryToasts.value = { ...categoryToasts.value, [category]: toastMap[direction] }
    setTimeout(() => {
      const next = { ...categoryToasts.value }
      delete next[category]
      categoryToasts.value = next
    }, 3000)
    // Refresh profile so the panel reflects the updated signal
    const updated = await fetchPreferenceProfile()
    if (updated) profile.value = updated
  } catch {
    // fail silently — calibration nudge is non-critical
  } finally {
    nudgingCategory.value = null
  }
}

function fmtPct(n: number): string {
  return `${Math.round(n * 100)}%`
}

const maxCatWeight = computed(() => {
  if (!profile.value?.top_categories?.length) return 1
  return Math.max(...profile.value.top_categories.map(c => c.weight))
})

const explorationLabel = computed(() => {
  const r = profile.value?.exploration_ratio
  if (r == null) return null
  if (r <= 0.1) return '几乎不探索新领域'
  if (r <= 0.2) return '以精准匹配为主，少量探索'
  if (r <= 0.35) return '精准匹配与探索均衡'
  return '积极探索新领域'
})

function weightLabel(key: string): string {
  const map: Record<string, string> = { theme: '主题质量', pref: '个人偏好', novel: '新颖探索' }
  return map[key] ?? key
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(loadAll)
</script>

<template>
  <!-- Embedded inline paper detail -->
  <EmbeddedPaperDetailPanel
    v-if="props.embedded && selectedPaperId"
    :paper-id="selectedPaperId"
    back-label="返回研究偏好"
    class="h-full"
    @back="selectedPaperId = null"
  />

  <div
    v-else
    class="text-text-primary"
    :class="props.embedded ? 'min-h-0 bg-transparent' : 'min-h-screen bg-bg-primary'"
  >
    <!-- Header (full page only) -->
    <div
      v-if="!props.embedded"
      class="border-b border-border px-6 py-4 flex items-center justify-between"
    >
      <div>
        <h1 class="text-xl font-bold">研究偏好</h1>
        <p class="text-sm text-text-muted mt-0.5">系统学到了什么、正在推荐什么、压低了什么，以及如何纠偏</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="px-4 py-1.5 rounded-lg bg-bg-elevated border border-border text-sm cursor-pointer hover:bg-bg-card transition-colors"
          :disabled="loading"
          @click="loadAll"
        >
          {{ loading ? '加载中…' : '刷新' }}
        </button>
        <RouterLink to="/" class="text-sm text-text-muted hover:text-text-primary">← 返回首页</RouterLink>
      </div>
    </div>

    <!-- Embedded: title + toolbar -->
    <div
      v-else
      class="max-w-5xl mx-auto px-4 sm:px-8 pt-6 pb-2 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
    >
      <div>
        <h2 class="text-lg font-bold text-text-primary">研究偏好</h2>
        <p class="text-xs text-text-muted mt-1">系统学到了什么、正在推荐什么、压低了什么，以及如何纠偏</p>
      </div>
      <button
        type="button"
        class="self-start sm:self-auto px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-sm cursor-pointer hover:bg-bg-card transition-colors shrink-0"
        :disabled="loading"
        @click="loadAll"
      >
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <!-- Loading -->
    <div
      v-if="loading"
      class="flex items-center justify-center text-text-muted text-sm"
      :class="props.embedded ? 'py-12' : 'py-24'"
    >
      加载偏好数据…
    </div>

    <!-- Error -->
    <div
      v-else-if="error"
      class="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-center justify-between"
      :class="props.embedded ? 'mx-4 sm:mx-8 my-2' : 'm-6'"
    >
      <span>{{ error }}</span>
      <button type="button" class="ml-4 underline text-sm cursor-pointer shrink-0" @click="loadAll">重试</button>
    </div>

    <!-- Content -->
    <div
      v-else
      class="space-y-6 max-w-5xl mx-auto"
      :class="props.embedded ? 'px-4 sm:px-8 pb-8 pt-2' : 'p-6'"
    >

      <!-- ── 状态卡 ──────────────────────────────────────── -->
      <section class="grid md:grid-cols-2 gap-4">

        <!-- Left: learning status -->
        <div class="pref-card">
          <h2 class="pref-card-title">偏好学习状态</h2>

          <div v-if="!profile?.has_enough_data" class="space-y-3">
            <div class="flex items-start gap-3">
              <div class="w-9 h-9 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center shrink-0 mt-0.5">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-blue-600 dark:text-blue-400">
                  <circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/>
                </svg>
              </div>
              <div>
                <p class="text-sm font-semibold text-text-primary">正在建立偏好档案</p>
                <p class="text-sm text-text-muted mt-0.5">
                  再 <span class="font-semibold text-blue-500">{{ profile?.min_feedback_needed ?? '…' }}</span> 次操作后启用个人推荐
                </p>
              </div>
            </div>
            <p class="text-xs text-text-muted leading-relaxed">
              收藏论文、开启深度研究、点"多看/少看此类"都会加快学习速度。目前已有 <strong>{{ profile?.total_feedback_count ?? 0 }}</strong> 条信号。
            </p>
          </div>

          <div v-else class="space-y-2.5">
            <div class="pref-row">
              <span class="text-sm text-text-secondary">行为信号数</span>
              <span class="text-sm font-semibold">{{ profile.total_feedback_count }}</span>
            </div>
            <div class="pref-row">
              <span class="text-sm text-text-secondary">画像更新时间</span>
              <span class="text-xs font-mono text-text-muted">{{ fmtDate(profile.built_at) }}</span>
            </div>
            <div class="pref-row">
              <span class="text-sm text-text-secondary">个性化权重</span>
              <span
                class="text-xs font-semibold px-2 py-0.5 rounded-full"
                :class="calibration?.has_personal_weights
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-bg-elevated text-text-muted'"
              >
                {{ calibration?.has_personal_weights ? '已启用' : '使用系统默认' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Right: calibration -->
        <div class="pref-card">
          <h2 class="pref-card-title">自动校准状态</h2>
          <div v-if="calibration" class="space-y-2.5">
            <div class="pref-row">
              <span class="text-sm text-text-secondary">上次校准</span>
              <span class="text-xs font-mono text-text-muted">{{ calibration.last_calibrated ? fmtDate(calibration.last_calibrated) : '尚未校准' }}</span>
            </div>
            <div v-if="calibration.ndcg_improvement != null" class="pref-row">
              <span class="text-sm text-text-secondary">推荐准确度改善</span>
              <span
                class="text-sm font-semibold"
                :class="calibration.ndcg_improvement > 0 ? 'text-green-600 dark:text-green-400' : 'text-text-muted'"
              >
                {{ calibration.ndcg_improvement > 0 ? '+' : '' }}{{ (calibration.ndcg_improvement * 100).toFixed(1) }}%
              </span>
            </div>
            <div v-if="calibration.n_impressions_last != null" class="pref-row">
              <span class="text-sm text-text-secondary">参考曝光数</span>
              <span class="text-xs font-mono text-text-muted">{{ calibration.n_impressions_last }}</span>
            </div>
            <div v-if="calibration.n_saves_last != null" class="pref-row">
              <span class="text-sm text-text-secondary">参考收藏数</span>
              <span class="text-xs font-mono text-text-muted">{{ calibration.n_saves_last }}</span>
            </div>
          </div>
          <p v-else class="text-sm text-text-muted">校准数据加载失败。</p>
          <p class="mt-3 text-xs text-text-muted leading-relaxed">
            系统每周根据收藏行为自动校准推荐权重，无需手动操作。
          </p>
        </div>
      </section>

      <!-- ── 偏好方向 + 关键词 ────────────────────────── -->
      <section v-if="profile?.has_enough_data" class="grid md:grid-cols-2 gap-4">

        <!-- Categories -->
        <div class="pref-card">
          <h2 class="pref-card-title">偏好研究方向</h2>
          <div v-if="profile.top_categories?.length" class="space-y-3">
            <div v-for="cat in profile.top_categories" :key="cat.category" class="space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-sm text-text-primary font-medium truncate max-w-[80%]">{{ cat.category }}</span>
                <span class="text-xs text-text-muted font-mono">{{ fmtPct(cat.weight) }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-bg-elevated overflow-hidden">
                <div
                  class="h-full rounded-full bg-blue-500 transition-all duration-500"
                  :style="{ width: `${(cat.weight / maxCatWeight) * 100}%` }"
                />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-text-muted">暂无分类偏好数据。</p>
        </div>

        <!-- Keywords + negative -->
        <div class="space-y-4">
          <div class="pref-card">
            <h2 class="pref-card-title">关键词雷达</h2>
            <div v-if="profile.top_keywords?.length" class="flex flex-wrap gap-2">
              <span
                v-for="kw in profile.top_keywords"
                :key="kw.keyword"
                class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
              >
                {{ kw.keyword }}
              </span>
            </div>
            <p v-else class="text-sm text-text-muted">暂无关键词数据。</p>
          </div>

          <div class="pref-card">
            <h2 class="pref-card-title">少看方向</h2>
            <div v-if="profile.negative_categories?.length" class="flex flex-wrap gap-2">
              <span
                v-for="cat in profile.negative_categories"
                :key="cat"
                class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
              >
                {{ cat }}
              </span>
            </div>
            <p v-else class="text-xs text-text-muted leading-relaxed">
              当你点"少看此类"后，屏蔽的方向会出现在这里。
            </p>
          </div>
        </div>
      </section>

      <!-- ── 偏好校准建议 ────────────────────────────── -->
      <section v-if="profile?.has_enough_data && (profile.positive_category_details?.length || profile.negative_category_details?.length)" class="pref-card">
        <h2 class="pref-card-title">偏好校准</h2>
        <p class="text-xs text-text-muted mb-4 leading-relaxed">
          以下是系统目前学到的你的研究方向偏好。你可以直接调整，修正会在下一轮日报中生效。
        </p>

        <!-- Positive categories -->
        <div v-if="profile.positive_category_details?.length" class="mb-5">
          <p class="text-xs font-semibold text-text-secondary mb-1">系统正在加权推荐</p>
          <p class="text-[11px] text-text-muted mb-2 leading-snug">以下方向在当前日报中出现频率更高，可一键调低或重置。</p>
          <div class="space-y-2">
            <div
              v-for="cat in profile.positive_category_details"
              :key="cat.category"
              class="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-bg-elevated border border-border"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-sm font-medium text-text-primary truncate">{{ cat.category }}</span>
                <span class="text-[10px] text-text-muted shrink-0">{{ cat.signal_count }} 次信号</span>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <span
                  v-if="categoryToasts[cat.category]"
                  class="text-[11px] text-green-600 dark:text-green-400 font-medium whitespace-nowrap"
                >
                  ✓ 已更新
                </span>
                <template v-else>
                  <button
                    class="calib-btn calib-btn--more"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'more')"
                  >
                    继续多看
                  </button>
                  <button
                    class="calib-btn calib-btn--less"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'less')"
                  >
                    少一点
                  </button>
                  <button
                    class="calib-btn calib-btn--reset"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'reset')"
                    title="清除此方向的显式纠偏信号"
                  >
                    重置
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Negative categories -->
        <div v-if="profile.negative_category_details?.length">
          <p class="text-xs font-semibold text-text-secondary mb-1">系统正在压低</p>
          <p class="text-[11px] text-text-muted mb-2 leading-snug">这些方向的论文推荐优先级已降低。点「恢复推荐」可撤销压低，或点「重置」清除信号。</p>
          <div class="space-y-2">
            <div
              v-for="cat in profile.negative_category_details"
              :key="cat.category"
              class="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-red-50/60 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-sm font-medium text-red-700 dark:text-red-400 truncate">{{ cat.category }}</span>
                <span class="text-[10px] text-text-muted shrink-0">{{ cat.signal_count }} 次信号</span>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <span
                  v-if="categoryToasts[cat.category]"
                  class="text-[11px] text-green-600 dark:text-green-400 font-medium whitespace-nowrap"
                >
                  ✓ 已更新
                </span>
                <template v-else>
                  <button
                    class="calib-btn calib-btn--more"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'more')"
                  >
                    恢复推荐
                  </button>
                  <button
                    class="calib-btn calib-btn--less"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'less')"
                  >
                    继续少看
                  </button>
                  <button
                    class="calib-btn calib-btn--reset"
                    :disabled="nudgingCategory === cat.category"
                    @click="handleCategoryNudge(cat.category, 'reset')"
                    title="清除此方向的显式纠偏信号"
                  >
                    重置
                  </button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 推荐引擎设置 ────────────────────────────── -->
      <section v-if="calibration" class="pref-card">
        <h2 class="pref-card-title">推荐引擎当前设置</h2>
        <div class="flex flex-wrap gap-4">
          <!-- Score weights -->
          <div class="flex-1 min-w-48">
            <p class="text-xs text-text-muted mb-2">评分权重</p>
            <div class="flex gap-3">
              <div
                v-for="(val, key) in calibration.score_weights"
                :key="key"
                class="flex flex-col items-center py-2 px-3 rounded-xl bg-bg-elevated border border-border min-w-16"
              >
                <span class="text-base font-bold text-text-primary">{{ fmtPct(val) }}</span>
                <span class="text-[10px] text-text-muted mt-0.5">{{ weightLabel(key as string) }}</span>
              </div>
            </div>
          </div>
          <!-- Exploration ratio -->
          <div v-if="profile?.exploration_ratio != null" class="flex-1 min-w-48">
            <p class="text-xs text-text-muted mb-2">探索比例</p>
            <div class="flex items-center gap-3">
              <span class="text-2xl font-bold text-purple-600 dark:text-purple-400">{{ fmtPct(profile.exploration_ratio) }}</span>
              <div>
                <span class="text-xs text-text-muted block">{{ explorationLabel }}</span>
                <span class="text-[10px] text-text-muted/70 mt-0.5 block leading-snug">
                  比例偏低说明系统优先精准匹配，可能过度推荐已熟悉方向；<br>比例偏高表示会引入更多新领域，但相关性略低。
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 可能错过的论文 ─────────────────────────── -->
      <section v-if="profile?.has_enough_data" class="pref-card">
        <h2 class="pref-card-title">可能错过的论文</h2>
        <p class="text-xs text-text-muted mb-4">以下论文因不完全符合你的偏好被过滤，但综合质量较高。</p>

        <div v-if="suppressions.length === 0" class="text-sm text-text-muted py-2">
          今日暂无被过滤的高质量论文。
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="paper in suppressions"
            :key="paper.paper_id"
            class="flex items-start justify-between gap-4 p-3 rounded-xl bg-bg-elevated border border-border"
          >
            <div class="flex-1 min-w-0">
              <a
                class="text-sm font-semibold text-text-primary hover:text-blue-500 transition-colors cursor-pointer line-clamp-2 leading-snug"
                @click="props.embedded ? (selectedPaperId = paper.paper_id) : router.push(`/papers/${paper.paper_id}`)"
              >
                {{ paper.short_title }}
              </a>
              <p class="text-xs text-text-muted mt-0.5 truncate">{{ paper['📖标题'] }}</p>
              <p class="text-xs text-text-muted mt-0.5">{{ paper.institution }}</p>
              <p v-if="paper.suppression_summary" class="text-xs text-text-muted mt-1.5 leading-relaxed">
                {{ paper.suppression_summary }}
              </p>
            </div>
            <button
              class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors cursor-pointer"
              @click="handleNudgeMore(paper)"
            >
              其实想看
            </button>
          </div>
        </div>
      </section>

      <!-- ── 操作区 ──────────────────────────────────── -->
      <section class="flex items-center gap-4">
        <button
          class="px-6 py-2.5 rounded-xl font-semibold text-sm text-white cursor-pointer transition-opacity disabled:opacity-60"
          style="background: linear-gradient(135deg, #fd267a, #ff6036);"
          :disabled="rebuilding"
          @click="handleRebuild"
        >
          {{ rebuilding ? '计算中…' : '重新计算我的偏好' }}
        </button>
        <p v-if="rebuildMsg" class="text-sm" :class="rebuildMsg.includes('失败') ? 'text-red-500' : 'text-green-600'">
          {{ rebuildMsg }}
        </p>
        <p v-else class="text-xs text-text-muted">
          系统在每次操作后会自动更新画像，手动重算会立即刷新。
        </p>
      </section>

    </div>
  </div>
</template>

<style scoped>
.pref-card {
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 20px;
}
.pref-card-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ── Calibration nudge buttons ── */
.calib-btn {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  border: 1px solid transparent;
  white-space: nowrap;
}
.calib-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.calib-btn--more {
  background: var(--color-bg-elevated);
  border-color: var(--color-border);
  color: var(--color-text-primary);
}
.calib-btn--more:not(:disabled):hover {
  background: #dbeafe;
  border-color: #93c5fd;
  color: #1d4ed8;
}
.calib-btn--less {
  background: var(--color-bg-elevated);
  border-color: var(--color-border);
  color: var(--color-text-primary);
}
.calib-btn--less:not(:disabled):hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #b91c1c;
}
.calib-btn--reset {
  background: transparent;
  border-color: var(--color-border-light, var(--color-border));
  color: var(--color-text-muted);
}
.calib-btn--reset:not(:disabled):hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
}
</style>
