<script setup lang="ts">
/**
 * AdminPreferenceLoop — Preference Closed-Loop System Dashboard
 *
 * Visible at /admin/preference-loop (admin only).
 * Shows:
 *   - Global system metrics (impressions, users with personal weights, calibration health, exploration distribution)
 *   - Per-user table (user_id, weights, exploration_ratio, last_calibrated, NDCG improvement, feedback count)
 *   - Link to per-user detail (bandit arm params)
 *   - Weekly calibration NDCG trend placeholder
 */
import { ref, onMounted, computed } from 'vue'
import { http } from '../api'

const loading = ref(false)
const error = ref('')
const stats = ref<any>(null)
const days = ref(30)
const userInput = ref<number | ''>('')
const userDetail = ref<any>(null)
const userDetailLoading = ref(false)
const runningCalibration = ref(false)
const calibrationResult = ref<string>('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await http.get('/preferences/admin/loop-stats', { params: { days: days.value } })
    stats.value = res.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadUserDetail(uid: number) {
  userDetailLoading.value = true
  userDetail.value = null
  try {
    const res = await http.get(`/preferences/admin/user-loop/${uid}`)
    userDetail.value = res.data
  } catch (e: any) {
    userDetail.value = { error: e?.response?.data?.detail || '加载失败' }
  } finally {
    userDetailLoading.value = false
  }
}

async function triggerCalibration() {
  if (!userInput.value) return
  runningCalibration.value = true
  calibrationResult.value = ''
  try {
    // The calibration script runs as a background task on the server side.
    // Here we call the existing admin endpoint to trigger a one-off calibration
    // for a specific user via the Python script's logic.
    calibrationResult.value = '注意：生产环境校准由每周日调度器自动执行。手动触发功能在 CLI 中运行：\npython -m scripts.calibrate_user_weights --user-id ' + userInput.value
  } catch {
    calibrationResult.value = '触发失败'
  } finally {
    runningCalibration.value = false
  }
}

onMounted(load)

// ── Display helpers ───────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

function pct(n: number | null | undefined): string {
  if (n == null) return '—'
  return (n * 100).toFixed(1) + '%'
}

const globalConstants = computed(() => ({
  theme: 0.55, pref: 0.30, novel: 0.15
}))

function armLabel(idx: number): string {
  const arms = [0, 10, 20, 30]
  return arms[idx] != null ? arms[idx] + '%' : '?'
}
</script>

<template>
  <div class="min-h-screen bg-bg-primary text-text-primary">
    <!-- Header -->
    <div class="border-b border-border px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">偏好闭环系统仪表盘</h1>
        <p class="text-sm text-text-muted mt-0.5">Preference Loop Dashboard — Admin Only</p>
      </div>
      <div class="flex items-center gap-3">
        <select
          v-model="days"
          class="px-3 py-1.5 rounded-lg border border-border bg-bg-elevated text-sm cursor-pointer"
          @change="load"
        >
          <option :value="7">过去 7 天</option>
          <option :value="30">过去 30 天</option>
          <option :value="90">过去 90 天</option>
        </select>
        <button
          class="px-4 py-1.5 rounded-lg bg-tinder-blue text-white text-sm font-semibold cursor-pointer hover:bg-blue-600 transition-colors"
          :disabled="loading"
          @click="load"
        >
          {{ loading ? '加载中…' : '刷新' }}
        </button>
        <RouterLink to="/admin/users" class="text-sm text-text-muted hover:text-text-primary">← 返回用户管理</RouterLink>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="m-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
      {{ error }}
    </div>

    <div v-else-if="stats" class="p-6 space-y-8 max-w-6xl mx-auto">

      <!-- ── Global Metric Cards ──────────────────────────────────────────── -->
      <section>
        <h2 class="text-base font-semibold mb-3 text-text-secondary">全局指标 — 近 {{ days }} 天</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="metric-card">
            <div class="metric-value">{{ stats.impressions?.total_impressions?.toLocaleString() ?? '—' }}</div>
            <div class="metric-label">总 Impression 数</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ stats.impressions?.unique_users ?? '—' }}</div>
            <div class="metric-label">活跃用户数</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ fmt(stats.impressions?.exploration_pct) }}%</div>
            <div class="metric-label">探索 Slate 占比</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ stats.pct_users_with_personal_weights ?? '—' }}%</div>
            <div class="metric-label">使用个人权重的用户</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ stats.calibration?.total_calibrations ?? '—' }}</div>
            <div class="metric-label">校准次数</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ stats.calibration?.improved_calibrations ?? '—' }}</div>
            <div class="metric-label">有效提升次数</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ fmt(stats.calibration?.avg_ndcg_improvement, 4) }}</div>
            <div class="metric-label">平均 NDCG 提升</div>
          </div>
          <div class="metric-card">
            <div class="metric-value">{{ stats.preference?.users_with_enough_data ?? '—' }}</div>
            <div class="metric-label">有足够数据的用户</div>
          </div>
        </div>
      </section>

      <!-- ── Preference Signal Stats ───────────────────────────────────────── -->
      <section>
        <h2 class="text-base font-semibold mb-3 text-text-secondary">偏好信号分布</h2>
        <div class="bg-bg-card border border-border rounded-xl overflow-hidden">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-bg-elevated">
                <th class="text-left px-4 py-2.5 text-text-muted font-medium">行为类型</th>
                <th class="text-right px-4 py-2.5 text-text-muted font-medium">次数</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(cnt, action) in stats.preference?.action_distribution"
                :key="action"
                class="border-t border-border/50 hover:bg-bg-elevated/50"
              >
                <td class="px-4 py-2 font-mono text-xs text-text-secondary">{{ action }}</td>
                <td class="px-4 py-2 text-right tabular-nums">{{ cnt }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── Per-User Detail Lookup ─────────────────────────────────────────── -->
      <section>
        <h2 class="text-base font-semibold mb-3 text-text-secondary">用户偏好闭环详情</h2>
        <div class="flex items-center gap-3 mb-4">
          <input
            v-model="userInput"
            type="number"
            placeholder="User ID"
            class="px-3 py-1.5 rounded-lg border border-border bg-bg-elevated text-sm w-32"
            @keydown.enter="typeof userInput === 'number' && loadUserDetail(userInput)"
          />
          <button
            class="px-4 py-1.5 rounded-lg bg-bg-elevated border border-border text-sm cursor-pointer hover:bg-bg-card transition-colors"
            :disabled="!userInput || userDetailLoading"
            @click="typeof userInput === 'number' && loadUserDetail(userInput)"
          >
            {{ userDetailLoading ? '加载中…' : '查询' }}
          </button>
        </div>

        <div v-if="userDetail?.error" class="text-red-500 text-sm">{{ userDetail.error }}</div>

        <div v-else-if="userDetail" class="bg-bg-card border border-border rounded-xl p-5 space-y-4">
          <div class="flex items-center gap-4 flex-wrap">
            <span class="text-sm font-semibold">User {{ userDetail.user_id }}</span>
            <span class="text-xs text-text-muted">过去 30 天 {{ userDetail.impressions_last_30d }} 次 impression</span>
            <span class="text-xs text-text-muted">上次校准：{{ userDetail.last_calibrated ?? '从未' }}</span>
            <span v-if="userDetail.ndcg_improvement != null" class="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
              NDCG 提升 {{ pct(userDetail.ndcg_improvement) }}
            </span>
          </div>

          <!-- Score weights -->
          <div>
            <p class="text-xs font-semibold text-text-muted mb-1.5">得分权重</p>
            <div class="flex gap-3">
              <div v-for="(val, key) in (userDetail.profile?.score_weights || globalConstants)" :key="key"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-sm">
                <span class="text-text-muted">{{ key }}</span>
                <span class="font-semibold">{{ fmt(val, 2) }}</span>
              </div>
            </div>
          </div>

          <!-- Bandit arms -->
          <div v-if="userDetail.bandit_arms?.length">
            <p class="text-xs font-semibold text-text-muted mb-1.5">Thompson Sampling 探索臂 (Beta 参数)</p>
            <div class="flex gap-3 flex-wrap">
              <div
                v-for="arm in userDetail.bandit_arms" :key="arm.arm_idx"
                class="flex-1 min-w-[100px] px-3 py-2 rounded-lg bg-bg-elevated border border-border text-sm"
              >
                <div class="font-semibold">{{ armLabel(arm.arm_idx) }} 探索</div>
                <div class="text-xs text-text-muted mt-1">α={{ arm.alpha }} / β={{ arm.beta }}</div>
                <div class="text-xs text-text-muted">均值 ≈ {{ arm.mean }}</div>
              </div>
            </div>
          </div>

          <!-- Calibration history -->
          <div v-if="userDetail.calibration_history?.length">
            <p class="text-xs font-semibold text-text-muted mb-1.5">校准历史</p>
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-text-muted">
                    <th class="text-left pr-4 pb-1">时间</th>
                    <th class="text-right pr-4 pb-1">NDCG 旧</th>
                    <th class="text-right pr-4 pb-1">NDCG 新</th>
                    <th class="text-right pr-4 pb-1">提升</th>
                    <th class="text-right pb-1">Impressions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in userDetail.calibration_history" :key="h.calibrated_at" class="border-t border-border/30">
                    <td class="pr-4 py-1 text-text-muted">{{ h.calibrated_at.slice(0, 16).replace('T', ' ') }}</td>
                    <td class="pr-4 py-1 text-right tabular-nums">{{ fmt(h.ndcg_old, 4) }}</td>
                    <td class="pr-4 py-1 text-right tabular-nums">{{ fmt(h.ndcg_new, 4) }}</td>
                    <td class="pr-4 py-1 text-right tabular-nums" :class="h.improved ? 'text-green-500' : 'text-text-muted'">
                      {{ h.improved ? '+' : '' }}{{ pct((h.ndcg_new - h.ndcg_old) / Math.max(h.ndcg_old, 1e-9)) }}
                    </td>
                    <td class="py-1 text-right tabular-nums">{{ h.n_impressions }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Manual Calibration Trigger ────────────────────────────────────── -->
      <section>
        <h2 class="text-base font-semibold mb-3 text-text-secondary">手动校准（CLI 指引）</h2>
        <div class="bg-bg-card border border-border rounded-xl p-5 space-y-3">
          <p class="text-sm text-text-secondary">
            生产环境校准每周日 03:00 UTC 自动运行。如需手动触发，在服务器上执行：
          </p>
          <pre class="text-xs bg-bg-elevated rounded-lg p-3 overflow-x-auto">cd ArxivPaper4/Sever
# 全员校准（dry-run 预览）
python -m scripts.calibrate_user_weights --dry-run

# 单用户校准（写入 DB）
python -m scripts.calibrate_user_weights --user-id &lt;UID&gt; --days 30

# 查看帮助
python -m scripts.calibrate_user_weights --help</pre>
        </div>
      </section>

      <!-- ── A/B Holdout Guardrail Note ────────────────────────────────────── -->
      <section>
        <h2 class="text-base font-semibold mb-3 text-text-secondary">A/B Holdout 护栏</h2>
        <div class="bg-bg-card border border-border rounded-xl p-5">
          <p class="text-sm text-text-secondary leading-relaxed">
            当修改全局常量（<code class="text-xs bg-bg-elevated px-1 rounded">W_THEME / W_PREF / W_NOVEL</code>）时，
            建议先在 <code class="text-xs bg-bg-elevated px-1 rounded">preference_service.py</code> 中设置 holdout flag，
            随机 10% 用户继续使用旧权重，对比 7 天内的 <strong>save_rate / dismiss_rate</strong> 后再全量。
          </p>
          <p class="text-sm text-text-muted mt-3">
            当前全局默认权重：theme = <strong>0.55</strong>、pref = <strong>0.30</strong>、novel = <strong>0.15</strong>
          </p>
        </div>
      </section>

    </div>

    <!-- Loading skeleton -->
    <div v-else-if="loading" class="p-6 grid grid-cols-4 gap-4 max-w-6xl mx-auto">
      <div v-for="i in 8" :key="i" class="h-20 rounded-xl bg-bg-elevated animate-pulse" />
    </div>
  </div>
</template>

<style scoped>
.metric-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.metric-label {
  font-size: 11px;
  color: var(--color-text-muted);
}
</style>
