<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import {
  fetchAdminUsers,
  fetchAdminUserDetail,
  updateAdminUserTier,
  updateAdminUserRole,
  issueAdminRedeemKeys,
  fetchAdminRedeemKeys,
  disableAdminRedeemKey,
  runPipeline,
  getPipelineRunStatus,
  stopPipeline,
  getScheduleConfig,
  updateScheduleConfig,
  getScheduleHistory,
  type ScheduleHistoryRecord,
  getSystemConfig,
  updateSystemConfig,
  fetchLlmConfigs,
  createLlmConfig,
  updateLlmConfig,
  deleteLlmConfig,
  applyLlmConfig,
  fetchPromptConfigs,
  createPromptConfig,
  updatePromptConfig,
  deletePromptConfig,
  applyPromptConfig,
  batchApplyConfigs,
  adminResetUserPassword,
  adminForceLogout,
  adminDisableUser,
  adminEnableUser,
  adminDeleteUser,
  fetchAdminFeatureDefaults,
  saveAdminFeatureDefault,
  resetAdminFeatureDefault,
  type AdminFeatureDefaultEntry,
  fetchAdminCustomConfigs,
  type CustomConfigAuditResponse,
  type AuditUserRecord,
  fetchPipelineStepConfig,
  savePipelineStepConfig,
  resetPipelineStepConfig,
  fetchOpenRouterKeyPool,
  saveOpenRouterKeyPool,
  fetchOpenRouterFreeModels,
  type OpenRouterKeyPoolStatus,
  type OpenRouterFreeModel,
} from '../api'
import type {
  AuthUser,
  UserTier,
  UserRole,
  PipelineRunStatus,
  ScheduleConfig,
  SystemConfigGroup,
  LlmConfig,
  PromptConfig,
  AdminRedeemKeyRecord,
  AdminUserDetailResponse,
  SubscriptionHistoryRecord,
  PipelineStepDefinition,
} from '../types/paper'
import { isSuperAdmin, currentUser } from '../stores/auth'
import { usePollingTask } from '../composables/usePollingTask'

const AdminAnalytics = defineAsyncComponent(() => import('../components/AdminAnalytics.vue'))
const PipelineConsole = defineAsyncComponent(() => import('../components/PipelineConsole.vue'))
const AdminDataTrackingPanel = defineAsyncComponent(() => import('../components/admin/AdminDataTrackingPanel.vue'))
const AdminPdfCleanupPanel = defineAsyncComponent(() => import('../components/admin/AdminPdfCleanupPanel.vue'))
const AdminPreferenceAnalyticsPanel = defineAsyncComponent(() => import('../components/admin/AdminPreferenceAnalyticsPanel.vue'))
const AdminAnnouncementsPanel = defineAsyncComponent(() => import('../components/admin/AdminAnnouncementsPanel.vue'))

// ---------------------------------------------------------------------------
// Sidebar menu state
// ---------------------------------------------------------------------------
const activeTab = ref<'users' | 'subscription-keys' | 'roles' | 'pipeline' | 'console' | 'schedule' | 'data-tracking' | 'step-config' | 'paper-recommend-config' | 'idea-generate-config' | 'feature-defaults-config' | 'llm-config' | 'prompt-config' | 'announcements' | 'analytics' | 'preference-analytics' | 'user-custom-configs' | 'pdf-cleanup'>('users')
const showAdminSidebar = ref(false)

const menuItems = computed(() => {
  const items: { key: typeof activeTab.value; icon: string; label: string; desc: string; group?: string }[] = [
    { key: 'analytics', icon: '📊', label: '数据统计', desc: '平台数据分析与用户洞察', group: '概览' },
    { key: 'preference-analytics', icon: '🧭', label: '偏好推荐分析', desc: '用户偏好信号覆盖率与行为分布', group: '概览' },
    // Note: Preference Loop Dashboard is a separate page at /admin/preference-loop
    { key: 'users', icon: '👥', label: '用户等级', desc: '管理用户访问等级', group: '用户' },
    { key: 'subscription-keys', icon: '🎟️', label: '会员兑换码', desc: '批量发放并管理兑换码', group: '用户' },
  ]
  if (isSuperAdmin.value) {
    items.push({ key: 'roles', icon: '🛡️', label: '权限管理', desc: '管理用户角色权限', group: '用户' })
  }
  items.push(
    { key: 'announcements', icon: '📢', label: '公告管理', desc: '发布和管理平台公告通知', group: '运营' },
    { key: 'pipeline', icon: '🚀', label: '脚本执行', desc: '手动运行 Pipeline', group: '运维' },
    { key: 'console', icon: '🖥️', label: '运行控制台', desc: '可观测 Run / Step / 产物 / 重跑', group: '运维' },
    { key: 'schedule', icon: '🕐', label: '定时调度', desc: '自动定时执行配置', group: '运维' },
    { key: 'data-tracking', icon: '📈', label: '数据追踪', desc: 'Pipeline 每步数据量变化追踪', group: '运维' },
    { key: 'step-config', icon: '⚙️', label: '步骤控制', desc: '控制 Pipeline 中哪些步骤启用或禁用', group: '运维' },
    { key: 'pdf-cleanup', icon: '🗑️', label: 'PDF 清理', desc: 'N天未收藏的推荐PDF缓存清理', group: '运维' },
    { key: 'paper-recommend-config', icon: '⭐', label: '论文推荐配置', desc: '论文推荐功能模型与提示词配置', group: '系统配置' },
    { key: 'idea-generate-config', icon: '💡', label: '灵感生成配置', desc: '灵感生成功能模型与提示词配置', group: '系统配置' },
    { key: 'feature-defaults-config', icon: '🎛️', label: 'AI功能默认配置', desc: '问答/对比/深度研究等功能的默认参数', group: '系统配置' },
    { key: 'llm-config', icon: '🤖', label: '模型配置库', desc: '管理大模型配置', group: '配置库' },
    { key: 'prompt-config', icon: '📝', label: '提示词库', desc: '管理提示词配置', group: '配置库' },
    { key: 'user-custom-configs', icon: '🔍', label: '用户配置审计', desc: '查看各用户独立模型/提示词配置情况', group: '配置库' },
  )
  return items
})

// Compute groups for sidebar rendering
const menuGroups = computed(() => {
  const groups: { name: string; items: typeof menuItems.value }[] = []
  const seen = new Set<string>()
  for (const item of menuItems.value) {
    const g = item.group || ''
    if (!seen.has(g)) {
      seen.add(g)
      groups.push({ name: g, items: [] })
    }
    groups.find((x) => x.name === g)!.items.push(item)
  }
  return groups
})

// ---------------------------------------------------------------------------
// User Management
// ---------------------------------------------------------------------------
const users = ref<AuthUser[]>([])
const loading = ref(false)
const error = ref('')
const savingUserId = ref<number | null>(null)

const tierOptions: { label: string; value: UserTier }[] = [
  { label: '普通', value: 'free' },
  { label: 'Pro', value: 'pro' },
  { label: 'Pro+', value: 'pro_plus' },
]

const roleOptions: { label: string; value: UserRole }[] = [
  { label: '普通用户', value: 'user' },
  { label: '管理员', value: 'admin' },
  { label: '超级管理员', value: 'superadmin' },
]

function tierLabel(tier: UserTier) {
  if (tier === 'pro') return 'Pro'
  if (tier === 'pro_plus') return 'Pro+'
  return '普通'
}

function roleLabel(role: UserRole) {
  if (role === 'superadmin') return '超级管理员'
  if (role === 'admin') return '管理员'
  return '普通用户'
}

function roleBadgeClass(role: UserRole) {
  if (role === 'superadmin') return 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
  if (role === 'admin') return 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
  return 'bg-bg-elevated text-text-secondary'
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchAdminUsers()
    users.value = res.users
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载用户列表失败'
  } finally {
    loading.value = false
  }
}

async function onTierChange(user: AuthUser, event: Event) {
  const tier = (event.target as HTMLSelectElement).value as UserTier
  if (tier === user.tier) return
  savingUserId.value = user.id
  try {
    const res = await updateAdminUserTier(user.id, tier)
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx >= 0) users.value[idx] = res.user
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '更新失败')
  } finally {
    savingUserId.value = null
  }
}

async function onRoleChange(user: AuthUser, event: Event) {
  const role = (event.target as HTMLSelectElement).value as UserRole
  if (role === user.role) return
  if (!confirm(`确定将用户「${user.username}」的角色修改为「${roleLabel(role)}」吗？`)) {
    ;(event.target as HTMLSelectElement).value = user.role
    return
  }
  savingUserId.value = user.id
  try {
    const res = await updateAdminUserRole(user.id, role)
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx >= 0) users.value[idx] = res.user
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '更新失败')
    ;(event.target as HTMLSelectElement).value = user.role
  } finally {
    savingUserId.value = null
  }
}

// ---------------------------------------------------------------------------
// Subscription key management
// ---------------------------------------------------------------------------
const redeemPlanTier = ref<'pro' | 'pro_plus'>('pro')
const redeemDurationDays = ref(30)
const redeemKeyCount = ref(10)
const redeemValidDays = ref<number | null>(90)
const redeemMaxUses = ref(1)
const redeemNote = ref('')
const issuingRedeemKeys = ref(false)
const issueRedeemError = ref('')
const issuedBatchId = ref('')
const issuedCodes = ref<string[]>([])
const copyIssuedCodesMsg = ref('')

const redeemKeysLoading = ref(false)
const redeemKeysError = ref('')
const redeemKeys = ref<AdminRedeemKeyRecord[]>([])
const redeemKeysBatchFilter = ref('')

function redeemKeyStatusText(status: string): string {
  if (status === 'consumed') return '已用尽'
  if (status === 'disabled') return '已禁用'
  return '可用'
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

async function copyIssuedCodes() {
  if (issuedCodes.value.length === 0) return
  const text = issuedCodes.value.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    copyIssuedCodesMsg.value = '已复制'
    setTimeout(() => { copyIssuedCodesMsg.value = '' }, 1800)
  } catch {
    copyIssuedCodesMsg.value = '复制失败，请手动复制'
    setTimeout(() => { copyIssuedCodesMsg.value = '' }, 1800)
  }
}

async function loadRedeemKeys() {
  redeemKeysLoading.value = true
  redeemKeysError.value = ''
  try {
    const res = await fetchAdminRedeemKeys({
      batch_id: redeemKeysBatchFilter.value.trim() || undefined,
      limit: 200,
    })
    redeemKeys.value = res.keys || []
  } catch (e: any) {
    redeemKeysError.value = e?.response?.data?.detail || '加载兑换码列表失败'
  } finally {
    redeemKeysLoading.value = false
  }
}

async function handleIssueRedeemKeys() {
  issueRedeemError.value = ''
  issuedBatchId.value = ''
  issuedCodes.value = []
  copyIssuedCodesMsg.value = ''
  issuingRedeemKeys.value = true
  try {
    const res = await issueAdminRedeemKeys({
      plan_tier: redeemPlanTier.value,
      duration_days: redeemDurationDays.value,
      key_count: redeemKeyCount.value,
      valid_days: redeemValidDays.value,
      max_uses: redeemMaxUses.value,
      note: redeemNote.value.trim() || '',
    })
    issuedBatchId.value = res.batch_id
    issuedCodes.value = res.codes || []
    await loadRedeemKeys()
  } catch (e: any) {
    issueRedeemError.value = e?.response?.data?.detail || '发码失败'
  } finally {
    issuingRedeemKeys.value = false
  }
}

async function handleDisableRedeemKey(key: AdminRedeemKeyRecord) {
  if (key.status !== 'active') return
  if (!window.confirm(`确定禁用兑换码 #${key.id} 吗？`)) return
  try {
    await disableAdminRedeemKey(key.id)
    await loadRedeemKeys()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '禁用失败')
  }
}

// ---------------------------------------------------------------------------
// Pipeline Execution
// ---------------------------------------------------------------------------
const pipelineStatus = ref<PipelineRunStatus | null>(null)
const pipelineLoading = ref(false)
const pipelineError = ref('')
// Track the current run_id so the UI always shows the right run after a refresh
const trackedRunId = ref<string | null>(null)

// Run form
const runDate = ref(new Date().toISOString().slice(0, 10))
const runPipelineName = ref('default')
const runSllm = ref<number | null>(null)
const runZo = ref('F')
const runForce = ref(false)
const runMultiUser = ref(true)
const runMaxConcurrentUsers = ref(3)
// Arxiv 检索参数
const runDays = ref<number | null>(null)
const runCategories = ref('')
const runQuery = ref('')
const runMaxPapers = ref<number | null>(null)
const showAdvancedParams = ref(false)
const isRunning = computed(() => pipelineStatus.value?.running === true)

// Schedule
const schedule = ref<ScheduleConfig>({
  enabled: false,
  hour: 6,
  minute: 0,
  pipeline: 'daily',
  sllm: null,
  zo: 'F',
  user_id: null,
  multi_user: true,
  max_concurrent_user_pipelines: 3,
})
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)
const scheduleCustomUserCount = ref<number | null>(null)

// Schedule execution history
const scheduleHistory = ref<ScheduleHistoryRecord[]>([])
const scheduleHistoryLoading = ref(false)

async function loadScheduleHistory() {
  scheduleHistoryLoading.value = true
  try {
    scheduleHistory.value = await getScheduleHistory(50)
  } catch {
    // silently ignore
  } finally {
    scheduleHistoryLoading.value = false
  }
}

const logsContainer = ref<HTMLElement | null>(null)

async function loadPipelineStatus() {
  try {
    const status = await getPipelineRunStatus()
    pipelineStatus.value = status
    // Track which run we are watching so we can highlight a new run
    if (status.run_id) {
      trackedRunId.value = status.run_id
    }
  } catch (e: any) {
    // silently ignore polling errors
  }
}

async function loadSchedule() {
  scheduleLoading.value = true
  try {
    const cfg = await getScheduleConfig()
    schedule.value = {
      ...schedule.value,
      ...cfg,
      multi_user: cfg.multi_user !== undefined ? cfg.multi_user : true,
      max_concurrent_user_pipelines: cfg.max_concurrent_user_pipelines ?? 3,
    }
    // Load custom user count for display
    try {
      const usersRes = await fetch('/api/admin/users/custom-config-count', {
        credentials: 'include',
      })
      if (usersRes.ok) {
        const data = await usersRes.json()
        scheduleCustomUserCount.value = data.count ?? null
      }
    } catch (_) {
      // ignore; count is cosmetic
    }
    // Load history in parallel (non-blocking)
    loadScheduleHistory()
  } catch (e: any) {
    // use defaults
  } finally {
    scheduleLoading.value = false
  }
}

async function handleRunPipeline() {
  pipelineError.value = ''
  pipelineLoading.value = true
  try {
    if (runMultiUser.value) {
      // 多用户编排模式：shared + per_user（含所有自定义配置用户）
      await runPipeline({
        date: runDate.value,
        sllm: runSllm.value,
        zo: runZo.value,
        force: runForce.value,
        multi_user: true,
        max_concurrent_user_pipelines: runMaxConcurrentUsers.value,
        days: runDays.value ?? null,
        categories: runCategories.value.trim() || null,
        extra_query: runQuery.value.trim() || null,
        max_papers: runMaxPapers.value ?? null,
      })
    } else {
      await runPipeline({
        pipeline: runPipelineName.value,
        date: runDate.value,
        sllm: runSllm.value,
        zo: runZo.value,
        force: runForce.value,
        days: runDays.value || null,
        categories: runCategories.value.trim() || null,
        extra_query: runQuery.value.trim() || null,
        max_papers: runMaxPapers.value ?? null,
      })
    }
    startPolling()
    await loadPipelineStatus()
  } catch (e: any) {
    pipelineError.value = e?.response?.data?.detail || '启动失败'
  } finally {
    pipelineLoading.value = false
  }
}

async function handleStopPipeline() {
  if (!confirm('确定要终止正在运行的 Pipeline 吗？')) return
  try {
    await stopPipeline()
    await loadPipelineStatus()
  } catch (e: any) {
    pipelineError.value = e?.response?.data?.detail || '终止失败'
  }
}

async function handleSaveSchedule() {
  scheduleSaving.value = true
  try {
    const res = await updateScheduleConfig({
      enabled: schedule.value.enabled,
      hour: schedule.value.hour,
      minute: schedule.value.minute,
      pipeline: schedule.value.pipeline,
      sllm: schedule.value.sllm,
      zo: schedule.value.zo,
      user_id: schedule.value.user_id ?? null,
      multi_user: schedule.value.multi_user ?? true,
      max_concurrent_user_pipelines: schedule.value.max_concurrent_user_pipelines ?? 3,
    })
    schedule.value = res.schedule
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

const { start: startPolling } = usePollingTask(async () => {
  await loadPipelineStatus()
  if (logsContainer.value) {
    logsContainer.value.scrollTop = logsContainer.value.scrollHeight
  }
  return pipelineStatus.value?.running === true
}, { intervalMs: 2000 })

const formattedStartedAt = computed(() => {
  if (!pipelineStatus.value?.started_at) return '-'
  try {
    return new Date(pipelineStatus.value.started_at).toLocaleString('zh-CN')
  } catch {
    return pipelineStatus.value.started_at
  }
})

const formattedFinishedAt = computed(() => {
  if (!pipelineStatus.value?.finished_at) return '-'
  try {
    return new Date(pipelineStatus.value.finished_at).toLocaleString('zh-CN')
  } catch {
    return pipelineStatus.value.finished_at
  }
})

const statusLabel = computed(() => {
  if (!pipelineStatus.value) return '未知'
  if (pipelineStatus.value.running) return '运行中'
  if (pipelineStatus.value.exit_code === 0) return '已完成'
  if (pipelineStatus.value.exit_code !== null) return '异常退出'
  return '空闲'
})

const statusColor = computed(() => {
  if (!pipelineStatus.value) return 'text-text-muted'
  if (pipelineStatus.value.running) return 'text-blue-400'
  if (pipelineStatus.value.exit_code === 0) return 'text-green-400'
  if (pipelineStatus.value.exit_code !== null) return 'text-red-400'
  return 'text-text-muted'
})

// ---------------------------------------------------------------------------
// System Config Management
// ---------------------------------------------------------------------------
const configGroups = ref<SystemConfigGroup[]>([])
const configLoading = ref(false)
const configError = ref('')
const configValues = ref<Record<string, any>>({})

async function loadSystemConfig() {
  configLoading.value = true
  configError.value = ''
  try {
    const res = await getSystemConfig()
    configGroups.value = res.groups
    // 初始化配置值
    const values: Record<string, any> = {}
    for (const group of res.groups) {
      for (const item of group.items) {
        values[item.key] = item.value
      }
    }
    configValues.value = values
  } catch (e: any) {
    configError.value = e?.response?.data?.detail || '加载配置失败'
  } finally {
    configLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// System Config: Preset-based UI state & helpers
// ---------------------------------------------------------------------------

// Module-based config structure: each module groups its LLM + prompts together
// ── 论文推荐 功能模块 ──────────────────────────────────────────────
const recommendConfigModules = [
  {
    key: 'theme_select',
    label: '主题相关性评分',
    icon: '🎯',
    desc: '对论文进行主题相关性评分，筛选相关论文',
    llmPrefix: 'theme_select' as string | null,
    prompts: [
      { variable: 'theme_select_system_prompt', label: '评分提示词' },
    ],
  },
  {
    key: 'org',
    label: '机构判别',
    icon: '🏛️',
    desc: '提取论文作者机构信息',
    llmPrefix: 'org' as string | null,
    prompts: [
      { variable: 'pdf_info_system_prompt', label: '机构判别提示词' },
    ],
  },
  {
    key: 'summary',
    label: '摘要生成',
    icon: '📄',
    desc: '生成论文中文摘要笔记',
    llmPrefix: 'summary' as string | null,
    prompts: [
      { variable: 'system_prompt', label: '摘要生成提示词' },
    ],
  },
  {
    key: 'summary_limit',
    label: '摘要精简',
    icon: '✂️',
    desc: '压缩摘要各部分至字数上限（按需触发）',
    llmPrefix: 'summary_limit' as string | null,
    prompts: [
      { variable: 'summary_limit_prompt_card', label: '八字段整卡终稿精简提示词' },
      { variable: 'summary_limit_prompt_intro', label: '文章简介精简提示词' },
      { variable: 'summary_limit_prompt_method', label: '重点思路精简提示词' },
      { variable: 'summary_limit_prompt_findings', label: '分析总结精简提示词' },
      { variable: 'summary_limit_prompt_opinion', label: '个人观点精简提示词' },
      { variable: 'summary_limit_prompt_structure_check', label: '结构校验提示词' },
      { variable: 'summary_limit_prompt_structure_rewrite', label: '结构重排提示词' },
      { variable: 'summary_limit_prompt_headline', label: '首行压缩提示词' },
    ],
  },
  {
    key: 'summary_batch',
    label: '批量摘要',
    icon: '📦',
    desc: '批量处理论文摘要生成任务',
    llmPrefix: 'summary_batch' as string | null,
    prompts: [
      { variable: 'summary_batch_system_prompt', label: '批量摘要提示词' },
    ],
  },
  {
    key: 'paper_assets',
    label: '论文结构化抽取',
    icon: '🔬',
    desc: '提取论文结构化数据',
    llmPrefix: null,
    prompts: [
      { variable: 'paper_assets_system_prompt', label: '结构化抽取提示词' },
    ],
  },
]

// ── 灵感生成 功能模块 ──────────────────────────────────────────────
const ideaConfigModules = [
  {
    key: 'idea_ingest',
    label: '原子抽取 (idea_ingest)',
    icon: '⚗️',
    desc: '从论文全文抽取结构化灵感原子',
    llmPrefix: 'idea_ingest' as string | null,
    prompts: [
      { variable: 'idea_ingest_system_prompt', label: '原子抽取提示词' },
    ],
  },
  {
    key: 'idea_question',
    label: '研究问题生成 (idea_question)',
    icon: '❓',
    desc: '从局限性原子挖掘有价值的研究问题',
    llmPrefix: 'idea_question' as string | null,
    prompts: [
      { variable: 'idea_question_system_prompt', label: '研究问题生成提示词' },
    ],
  },
  {
    key: 'idea_candidate',
    label: '灵感候选生成 (idea_candidate)',
    icon: '💡',
    desc: '基于研究问题与原子生成多策略灵感候选',
    llmPrefix: 'idea_candidate' as string | null,
    prompts: [
      { variable: 'idea_candidate_system_prompt', label: '灵感候选生成提示词' },
    ],
  },
  {
    key: 'idea_review',
    label: '灵感评审 (idea_review)',
    icon: '🔍',
    desc: '多视角评委对灵感候选进行评审打分',
    llmPrefix: 'idea_review' as string | null,
    prompts: [
      { variable: 'idea_review_system_prompt', label: '灵感评审提示词' },
    ],
  },
  {
    key: 'idea_revise',
    label: '灵感修订 (idea_revise)',
    icon: '✏️',
    desc: '根据评审反馈自动修订灵感候选',
    llmPrefix: 'idea_revise' as string | null,
    prompts: [
      { variable: 'idea_revise_system_prompt', label: '灵感修订提示词' },
    ],
  },
  {
    key: 'idea_plan',
    label: '实验计划生成 (idea_plan)',
    icon: '📋',
    desc: '为通过评审的灵感生成可执行实验计划',
    llmPrefix: 'idea_plan' as string | null,
    prompts: [
      { variable: 'idea_plan_system_prompt', label: '实验计划生成提示词' },
    ],
  },
  {
    key: 'idea_eval',
    label: '评测回放 (idea_eval)',
    icon: '🔁',
    desc: '对问题集重新生成灵感用于历史版本对比',
    llmPrefix: 'idea_eval' as string | null,
    prompts: [
      { variable: 'idea_eval_system_prompt', label: '评测回放提示词' },
    ],
  },
]

// 合并供 detect 函数使用
const configModules = [...recommendConfigModules, ...ideaConfigModules]

// Per-prefix selected LLM config IDs
const selectedLlmConfigIds = ref<Record<string, number | null>>({
  theme_select: null,
  org: null,
  summary: null,
  summary_limit: null,
  summary_batch: null,
  idea_ingest: null,
  idea_question: null,
  idea_candidate: null,
  idea_review: null,
  idea_revise: null,
  idea_plan: null,
  idea_eval: null,
})

// Per-variable selected prompt config IDs
const selectedPromptConfigIds = ref<Record<string, number | null>>({
  theme_select_system_prompt: null,
  system_prompt: null,
  summary_limit_prompt_card: null,
  summary_limit_prompt_intro: null,
  summary_limit_prompt_method: null,
  summary_limit_prompt_findings: null,
  summary_limit_prompt_opinion: null,
  summary_limit_prompt_structure_check: null,
  summary_limit_prompt_structure_rewrite: null,
  summary_limit_prompt_headline: null,
  summary_batch_system_prompt: null,
  pdf_info_system_prompt: null,
  paper_assets_system_prompt: null,
  idea_ingest_system_prompt: null,
  idea_question_system_prompt: null,
  idea_candidate_system_prompt: null,
  idea_review_system_prompt: null,
  idea_revise_system_prompt: null,
  idea_plan_system_prompt: null,
  idea_eval_system_prompt: null,
})

// Word limit values (editable)
const wordLimitValues = ref<Record<string, number>>({
  summary_limit_section_limit_intro: 170,
  summary_limit_section_limit_method: 270,
  summary_limit_section_limit_findings: 270,
  summary_limit_section_limit_opinion: 150,
  summary_limit_headline_limit: 18,
})

const wordLimitDefaults: Record<string, number> = {
  summary_limit_section_limit_intro: 170,
  summary_limit_section_limit_method: 270,
  summary_limit_section_limit_findings: 270,
  summary_limit_section_limit_opinion: 150,
  summary_limit_headline_limit: 18,
}

const wordLimitLabels: Record<string, string> = {
  summary_limit_section_limit_intro: '文章简介',
  summary_limit_section_limit_method: '重点思路',
  summary_limit_section_limit_findings: '分析总结',
  summary_limit_section_limit_opinion: '个人观点',
  summary_limit_headline_limit: '首行字数',
}

// Mapping: prefix → config.py model/base_url key names
const prefixModelKey: Record<string, string> = {
  theme_select: 'theme_select_model',
  org: 'org_model',
  summary: 'summary_model',
  summary_limit: 'summary_limit_model',
  summary_batch: 'summary_batch_model',
  idea_ingest:     'idea_ingest_model',
  idea_question:   'idea_question_model',
  idea_candidate:  'idea_candidate_model',
  idea_review:     'idea_review_model',
  idea_revise:     'idea_revise_model',
  idea_plan:       'idea_plan_model',
  idea_eval:       'idea_eval_model',
}
const prefixBaseUrlKey: Record<string, string> = {
  theme_select: 'theme_select_base_url',
  org: 'org_base_url',
  summary: 'summary_base_url',
  summary_limit: 'summary_limit_base_url',
  summary_batch: 'summary_batch_base_url',
  idea_ingest:     'idea_ingest_base_url',
  idea_question:   'idea_question_base_url',
  idea_candidate:  'idea_candidate_base_url',
  idea_review:     'idea_review_base_url',
  idea_revise:     'idea_revise_base_url',
  idea_plan:       'idea_plan_base_url',
  idea_eval:       'idea_eval_base_url',
}

const applyingModelPrefix = ref<string | null>(null)
const applyingPromptVariable = ref<string | null>(null)
const savingWordLimits = ref(false)
const sysConfigSuccessMsg = ref('')

// ---------------------------------------------------------------------------
// Batch save state: track original selections to detect dirty items
// ---------------------------------------------------------------------------

// Snapshot of LLM/prompt selection at the time the page was last loaded/saved
const originalLlmConfigIds = ref<Record<string, number | null>>({})
const originalPromptConfigIds = ref<Record<string, number | null>>({})

// Global quick-fill: one LLM or prompt applied to all modules at once
const quickFillLlmId = ref<number | null>(null)
const quickFillPromptId = ref<number | null>(null)

// Batch saving state
const batchSaving = ref(false)
const batchSaveScope = ref<'recommend' | 'idea' | null>(null)

// How many items changed (per scope)
const recommendDirtyCount = computed(() => {
  let count = 0
  for (const mod of recommendConfigModules) {
    if (mod.llmPrefix) {
      if (selectedLlmConfigIds.value[mod.llmPrefix] !== originalLlmConfigIds.value[mod.llmPrefix]) count++
    }
    for (const p of mod.prompts) {
      if (selectedPromptConfigIds.value[p.variable] !== originalPromptConfigIds.value[p.variable]) count++
    }
  }
  return count
})

const ideaDirtyCount = computed(() => {
  let count = 0
  for (const mod of ideaConfigModules) {
    if (mod.llmPrefix) {
      if (selectedLlmConfigIds.value[mod.llmPrefix] !== originalLlmConfigIds.value[mod.llmPrefix]) count++
    }
    for (const p of mod.prompts) {
      if (selectedPromptConfigIds.value[p.variable] !== originalPromptConfigIds.value[p.variable]) count++
    }
  }
  return count
})

function snapshotSelections() {
  originalLlmConfigIds.value = { ...selectedLlmConfigIds.value }
  originalPromptConfigIds.value = { ...selectedPromptConfigIds.value }
}

function applyQuickFillLlm(scope: 'recommend' | 'idea') {
  if (!quickFillLlmId.value) return
  const modules = scope === 'recommend' ? recommendConfigModules : ideaConfigModules
  for (const mod of modules) {
    if (mod.llmPrefix) {
      selectedLlmConfigIds.value[mod.llmPrefix] = quickFillLlmId.value
    }
  }
}

function applyQuickFillPrompt(scope: 'recommend' | 'idea') {
  if (!quickFillPromptId.value) return
  const modules = scope === 'recommend' ? recommendConfigModules : ideaConfigModules
  for (const mod of modules) {
    for (const p of mod.prompts) {
      selectedPromptConfigIds.value[p.variable] = quickFillPromptId.value
    }
  }
}

async function handleBatchSave(scope: 'recommend' | 'idea') {
  const modules = scope === 'recommend' ? recommendConfigModules : ideaConfigModules
  const llmApplies: { config_id: number; prefix: string }[] = []
  const promptApplies: { config_id: number; variable: string }[] = []

  for (const mod of modules) {
    if (mod.llmPrefix) {
      const id = selectedLlmConfigIds.value[mod.llmPrefix]
      const origId = originalLlmConfigIds.value[mod.llmPrefix]
      if (id && id !== origId) {
        llmApplies.push({ config_id: id, prefix: mod.llmPrefix })
      }
    }
    for (const p of mod.prompts) {
      const id = selectedPromptConfigIds.value[p.variable]
      const origId = originalPromptConfigIds.value[p.variable]
      if (id && id !== origId) {
        promptApplies.push({ config_id: id, variable: p.variable })
      }
    }
  }

  if (llmApplies.length === 0 && promptApplies.length === 0) {
    sysConfigSuccessMsg.value = '没有需要保存的更改'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
    return
  }

  batchSaving.value = true
  batchSaveScope.value = scope
  try {
    const res = await batchApplyConfigs(llmApplies, promptApplies)
    await loadSystemConfig()
    detectLlmSelections()
    detectPromptSelections()
    snapshotSelections()
    const errMsg = res.errors?.length ? `（${res.errors.length} 项有误）` : ''
    sysConfigSuccessMsg.value = `✓ 已保存 ${res.applied_count} 项配置${errMsg}`
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 3000)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    batchSaving.value = false
    batchSaveScope.value = null
  }
}

function detectLlmSelections() {
  for (const mod of configModules) {
    if (!mod.llmPrefix) continue
    const currentModel = configValues.value[prefixModelKey[mod.llmPrefix]]
    const currentUrl = configValues.value[prefixBaseUrlKey[mod.llmPrefix]]
    if (!currentModel && !currentUrl) {
      selectedLlmConfigIds.value[mod.llmPrefix] = null
      continue
    }
    const match = llmConfigs.value.find(c => c.model === currentModel && c.base_url === currentUrl)
    selectedLlmConfigIds.value[mod.llmPrefix] = match?.id ?? null
  }
}

function detectPromptSelections() {
  for (const mod of configModules) {
    for (const prompt of mod.prompts) {
      const currentPrompt = configValues.value[prompt.variable]
      if (!currentPrompt) {
        selectedPromptConfigIds.value[prompt.variable] = null
        continue
      }
      const match = promptConfigs.value.find(c => c.prompt_content === currentPrompt)
      selectedPromptConfigIds.value[prompt.variable] = match?.id ?? null
    }
  }
}

function initWordLimits() {
  for (const key of Object.keys(wordLimitDefaults)) {
    if (key in configValues.value && configValues.value[key] !== undefined) {
      wordLimitValues.value[key] = Number(configValues.value[key]) || wordLimitDefaults[key]
    }
  }
}

// MinerU Token
const mineruTokenValue = ref('')
const mineruTokenVisible = ref(false)
const savingMineruToken = ref(false)

function initMineruToken() {
  mineruTokenValue.value = String(configValues.value['minerU_Token'] || '')
}

async function handleSaveMineruToken() {
  savingMineruToken.value = true
  try {
    await updateSystemConfig({ minerU_Token: mineruTokenValue.value })
    await loadSystemConfig()
    initMineruToken()
    sysConfigSuccessMsg.value = 'MinerU Token 已保存'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    savingMineruToken.value = false
  }
}

// arXiv 检索分类
const ARXIV_COMMON_CATEGORIES = [
  { code: 'cs.CL', label: '计算语言学' },
  { code: 'cs.LG', label: '机器学习' },
  { code: 'cs.AI', label: '人工智能' },
  { code: 'stat.ML', label: '统计机器学习' },
  { code: 'cs.CV', label: '计算机视觉' },
  { code: 'cs.IR', label: '信息检索' },
  { code: 'cs.RO', label: '机器人学' },
  { code: 'cs.NE', label: '神经/进化计算' },
  { code: 'cs.SE', label: '软件工程' },
  { code: 'cs.CR', label: '密码学与安全' },
  { code: 'cs.DC', label: '分布式计算' },
  { code: 'cs.DS', label: '数据结构与算法' },
  { code: 'cs.GT', label: '博弈论' },
  { code: 'eess.SP', label: '信号处理' },
  { code: 'math.OC', label: '优化与控制' },
  { code: 'q-bio.BM', label: '生物分子' },
  { code: 'physics.comp-ph', label: '计算物理' },
  { code: 'q-fin.ST', label: '统计金融' },
]
const adminSearchCategories = ref<string[]>([])
const adminCategoryCustomInput = ref('')
const savingAdminCategories = ref(false)

function initAdminSearchCategories() {
  const raw = configValues.value['SEARCH_CATEGORIES']
  if (Array.isArray(raw)) {
    adminSearchCategories.value = [...raw]
  } else if (typeof raw === 'string' && raw) {
    adminSearchCategories.value = raw.split(',').map((s: string) => s.trim()).filter(Boolean)
  } else {
    adminSearchCategories.value = ['cs.CL', 'cs.LG', 'cs.AI', 'stat.ML']
  }
}

function toggleAdminCategory(code: string) {
  const idx = adminSearchCategories.value.indexOf(code)
  if (idx >= 0) {
    if (adminSearchCategories.value.length > 1) {
      adminSearchCategories.value.splice(idx, 1)
    }
  } else {
    adminSearchCategories.value.push(code)
  }
}

function addAdminCustomCategory() {
  const code = adminCategoryCustomInput.value.trim()
  if (code && !adminSearchCategories.value.includes(code)) {
    adminSearchCategories.value.push(code)
  }
  adminCategoryCustomInput.value = ''
}

function removeAdminCategory(code: string) {
  if (adminSearchCategories.value.length > 1) {
    adminSearchCategories.value = adminSearchCategories.value.filter(c => c !== code)
  }
}

async function handleSaveAdminCategories() {
  savingAdminCategories.value = true
  try {
    await updateSystemConfig({ SEARCH_CATEGORIES: adminSearchCategories.value })
    await loadSystemConfig()
    initAdminSearchCategories()
    sysConfigSuccessMsg.value = '检索分类已保存'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    savingAdminCategories.value = false
  }
}

async function handleApplyLlmConfig(prefix: string) {
  const configId = selectedLlmConfigIds.value[prefix]
  if (!configId) return
  applyingModelPrefix.value = prefix
  try {
    await applyLlmConfig(configId, prefix)
    await loadSystemConfig()
    detectLlmSelections()
    sysConfigSuccessMsg.value = '模型配置已应用'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用失败')
  } finally {
    applyingModelPrefix.value = null
  }
}

async function handleApplyPromptConfig(variable: string) {
  const configId = selectedPromptConfigIds.value[variable]
  if (!configId) return
  applyingPromptVariable.value = variable
  try {
    await applyPromptConfig(configId, variable)
    await loadSystemConfig()
    detectPromptSelections()
    sysConfigSuccessMsg.value = '提示词配置已应用'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用失败')
  } finally {
    applyingPromptVariable.value = null
  }
}

async function handleSaveWordLimits() {
  savingWordLimits.value = true
  try {
    await updateSystemConfig({ ...wordLimitValues.value })
    await loadSystemConfig()
    initWordLimits()
    sysConfigSuccessMsg.value = '字数上限已保存'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    savingWordLimits.value = false
  }
}

// ---------------------------------------------------------------------------
// Feature Defaults Config (AI 功能默认配置)
// ---------------------------------------------------------------------------

interface FeatureDefaultsMeta {
  feature: string
  label: string
  icon: string
  desc: string
  editableFields: string[]
  promptFields: { key: string; label: string }[]
  specialFields?: { key: string; label: string; type: 'select' | 'number'; options?: { value: any; label: string }[] }[]
}

const FEATURE_DEFAULTS_META: FeatureDefaultsMeta[] = [
  {
    feature: 'paper_chat',
    label: 'AI 问答',
    icon: '💬',
    desc: '论文单篇问答功能的默认参数',
    editableFields: ['temperature', 'max_tokens', 'input_hard_limit', 'input_safety_margin'],
    promptFields: [{ key: 'system_prompt', label: '系统提示词' }],
    specialFields: [
      { key: 'data_source', label: '数据来源', type: 'select', options: [{ value: 'summary', label: 'summary（AI摘要）' }, { value: 'fulltext', label: 'fulltext（全文）' }] },
      { key: 'context_strategy', label: '上下文策略', type: 'select', options: [{ value: 'recent_k', label: 'recent_k（最近K轮）' }, { value: 'summary', label: 'summary（摘要压缩）' }, { value: 'full', label: 'full（全部）' }] },
      { key: 'context_k', label: '上下文轮数 (K)', type: 'number' },
    ],
  },
  {
    feature: 'compare',
    label: '对比分析',
    icon: '🔬',
    desc: '多篇论文横向对比分析功能的默认参数',
    editableFields: ['temperature', 'max_tokens', 'input_hard_limit', 'input_safety_margin'],
    promptFields: [{ key: 'system_prompt', label: '系统提示词' }],
    specialFields: [
      { key: 'data_source', label: '数据来源', type: 'select', options: [{ value: 'summary', label: 'summary（AI摘要）' }, { value: 'fulltext', label: 'fulltext（全文）' }] },
    ],
  },
  {
    feature: 'my_papers',
    label: '我的论文解析',
    icon: '📚',
    desc: '用户上传/导入论文解析、摘要生成与摘要精简的默认参数',
    editableFields: [
      'temperature',
      'max_tokens',
      'input_hard_limit',
      'input_safety_margin',
      'section_limit_intro',
      'section_limit_method',
      'section_limit_findings',
      'section_limit_opinion',
      'headline_limit',
    ],
    promptFields: [
      { key: 'system_prompt', label: '摘要生成提示词' },
      { key: 'summary_limit_prompt_intro', label: '文章简介精简提示词' },
      { key: 'summary_limit_prompt_method', label: '重点思路精简提示词' },
      { key: 'summary_limit_prompt_findings', label: '分析总结精简提示词' },
      { key: 'summary_limit_prompt_opinion', label: '个人观点精简提示词' },
    ],
  },
  {
    feature: 'inspiration',
    label: '灵感涌现',
    icon: '✨',
    desc: '灵感涌现对比分析功能的默认参数',
    editableFields: ['temperature', 'max_tokens', 'input_hard_limit', 'input_safety_margin'],
    promptFields: [{ key: 'system_prompt', label: '系统提示词' }],
  },
  {
    feature: 'deep_research',
    label: '深度研究',
    icon: '🔭',
    desc: '多轮深度研究功能的默认参数与各轮次提示词',
    editableFields: ['temperature', 'max_tokens', 'input_hard_limit', 'input_safety_margin'],
    promptFields: [
      { key: 'round1_system_prompt', label: 'Round 1 提示词（相关性排序）' },
      { key: 'round2_system_prompt', label: 'Round 2 提示词（摘要分析）' },
      { key: 'round3_system_prompt', label: 'Round 3 提示词（全文深读）' },
    ],
  },
]

const featureDefaultsData = ref<AdminFeatureDefaultEntry[]>([])
const featureDefaultsLoading = ref(false)
const featureDefaultsError = ref('')
const featureDefaultsSaving = ref<string | null>(null) // feature being saved
const featureDefaultsResetting = ref<string | null>(null) // feature being reset
const featureDefaultsSuccessMsg = ref('')

// Local editable copies: { [feature]: { [key]: value } }
const featureDefaultsEdits = ref<Record<string, Record<string, any>>>({})
// Snapshot of last-saved values for dirty detection
const featureDefaultsSnapshot = ref<Record<string, Record<string, any>>>({})
// Textarea expand state: { [feature+key]: boolean }
const featurePromptExpanded = ref<Record<string, boolean>>({})

function _featurePromptKey(feature: string, key: string) {
  return `${feature}__${key}`
}

function isFeatureDefaultsDirty(feature: string): boolean {
  const edits = featureDefaultsEdits.value[feature] || {}
  const snapshot = featureDefaultsSnapshot.value[feature] || {}
  return JSON.stringify(edits) !== JSON.stringify(snapshot)
}

const featureDefaultsDirtyCount = computed(() =>
  FEATURE_DEFAULTS_META.filter(m => isFeatureDefaultsDirty(m.feature)).length
)

async function loadFeatureDefaults() {
  featureDefaultsLoading.value = true
  featureDefaultsError.value = ''
  try {
    const res = await fetchAdminFeatureDefaults()
    featureDefaultsData.value = res.features
    // Initialize local edits from effective_defaults + admin_overrides (for extra fields like admin_llm_config_id)
    for (const entry of res.features) {
      const init = {
        ...entry.effective_defaults,
        admin_llm_config_id: entry.admin_overrides?.admin_llm_config_id ?? null,
      }
      featureDefaultsEdits.value[entry.feature] = init
      featureDefaultsSnapshot.value[entry.feature] = { ...init }
    }
  } catch (e: any) {
    featureDefaultsError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    featureDefaultsLoading.value = false
  }
}

async function handleSaveFeatureDefaults(feature: string) {
  featureDefaultsSaving.value = feature
  featureDefaultsSuccessMsg.value = ''
  try {
    const meta = FEATURE_DEFAULTS_META.find(m => m.feature === feature)
    if (!meta) return
    const edits = featureDefaultsEdits.value[feature] || {}
    // Build overrides: only fields that differ from hardcoded defaults
    const entry = featureDefaultsData.value.find(e => e.feature === feature)
    const hardcoded = entry?.hardcoded_defaults || {}
    const overrides: Record<string, any> = {}
    const allKeys = [
      'admin_llm_config_id',
      ...meta.editableFields,
      ...meta.promptFields.map(p => p.key),
      ...(meta.specialFields || []).map(s => s.key),
    ]
    for (const key of allKeys) {
      if (key in edits) {
        overrides[key] = edits[key]
      }
    }
    const res = await saveAdminFeatureDefault(feature, overrides)
    // Update local snapshot and data (admin_llm_config_id lives in overrides, not effective_defaults)
    const newState = {
      ...res.effective_defaults,
      admin_llm_config_id: overrides.admin_llm_config_id ?? null,
    }
    featureDefaultsSnapshot.value[feature] = { ...newState }
    featureDefaultsEdits.value[feature] = { ...newState }
    const idx = featureDefaultsData.value.findIndex(e => e.feature === feature)
    if (idx !== -1) {
      featureDefaultsData.value[idx] = {
        ...featureDefaultsData.value[idx],
        effective_defaults: res.effective_defaults,
        admin_overrides: overrides,
        has_admin_overrides: true,
      }
    }
    featureDefaultsSuccessMsg.value = '已保存'
    setTimeout(() => { featureDefaultsSuccessMsg.value = '' }, 3000)
  } catch (e: any) {
    alert('保存失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    featureDefaultsSaving.value = null
  }
}

async function handleResetFeatureDefaults(feature: string) {
  if (!confirm(`确定要将「${FEATURE_DEFAULTS_META.find(m => m.feature === feature)?.label || feature}」的默认配置恢复为内置默认值吗？`)) return
  featureDefaultsResetting.value = feature
  try {
    await resetAdminFeatureDefault(feature)
    // Reload to get fresh hardcoded values
    await loadFeatureDefaults()
    featureDefaultsSuccessMsg.value = '已恢复默认'
    setTimeout(() => { featureDefaultsSuccessMsg.value = '' }, 3000)
  } catch (e: any) {
    alert('重置失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    featureDefaultsResetting.value = null
  }
}

// Watch activeTab to load config when switching to config tabs
watch(activeTab, async (newTab) => {
  if (newTab === 'subscription-keys' && redeemKeys.value.length === 0) {
    loadRedeemKeys()
  } else if (newTab === 'paper-recommend-config' || newTab === 'idea-generate-config') {
    const promises: Promise<void>[] = []
    if (configGroups.value.length === 0) promises.push(loadSystemConfig())
    if (llmConfigs.value.length === 0) promises.push(loadLlmConfigs())
    if (promptConfigs.value.length === 0) promises.push(loadPromptConfigs())
    if (promises.length > 0) await Promise.all(promises)
    detectLlmSelections()
    detectPromptSelections()
    snapshotSelections()
    initWordLimits()
    initMineruToken()
    initAdminSearchCategories()
  } else if (newTab === 'feature-defaults-config') {
    const promises: Promise<void>[] = []
    if (featureDefaultsData.value.length === 0) promises.push(loadFeatureDefaults())
    if (llmConfigs.value.length === 0) promises.push(loadLlmConfigs())
    if (promises.length > 0) await Promise.all(promises)
  } else if (newTab === 'llm-config') {
    if (llmConfigs.value.length === 0) loadLlmConfigs()
    if (!keyPoolStatus.value) loadKeyPool()
  } else if (newTab === 'prompt-config' && promptConfigs.value.length === 0) {
    loadPromptConfigs()
  } else if (newTab === 'user-custom-configs' && !customConfigsData.value) {
    loadCustomConfigs()
  }
})

// ---------------------------------------------------------------------------
// LLM Config Management
// ---------------------------------------------------------------------------
const llmConfigs = ref<LlmConfig[]>([])
const llmConfigLoading = ref(false)
const llmConfigError = ref('')
const llmConfigEditing = ref<LlmConfig | null>(null)
const llmConfigForm = ref<Partial<LlmConfig>>({})
const llmConfigSaving = ref(false)
const llmConfigApplying = ref<number | null>(null)

const usagePrefixOptions = [
  { value: 'theme_select', label: '主题评分 (theme_select)' },
  { value: 'org', label: '机构判别 (org)' },
  { value: 'summary', label: '摘要生成 (summary)' },
  { value: 'summary_limit', label: '摘要精简 (summary_limit)' },
  { value: 'summary_batch', label: '批量摘要 (summary_batch)' },
  { value: 'idea_generate',   label: '灵感生成·全局兜底 (idea_generate)' },
  { value: 'idea_ingest',    label: '灵感·原子抽取 (idea_ingest)' },
  { value: 'idea_question',  label: '灵感·研究问题生成 (idea_question)' },
  { value: 'idea_candidate', label: '灵感·候选生成 (idea_candidate)' },
  { value: 'idea_review',    label: '灵感·评审 (idea_review)' },
  { value: 'idea_revise',    label: '灵感·修订 (idea_revise)' },
  { value: 'idea_plan',      label: '灵感·实验计划 (idea_plan)' },
  { value: 'idea_eval',      label: '灵感·评测回放 (idea_eval)' },
]

async function loadLlmConfigs() {
  llmConfigLoading.value = true
  llmConfigError.value = ''
  try {
    const res = await fetchLlmConfigs()
    llmConfigs.value = res.configs
  } catch (e: any) {
    llmConfigError.value = e?.response?.data?.detail || '加载模型配置列表失败'
  } finally {
    llmConfigLoading.value = false
  }
}

function startEditLlmConfig(config?: LlmConfig) {
  if (config) {
    llmConfigEditing.value = config
    llmConfigForm.value = { ...config }
  } else {
    llmConfigEditing.value = null
    llmConfigForm.value = {
      name: '',
      remark: '',
      base_url: '',
      api_key: '',
      model: '',
      max_tokens: undefined,
      temperature: undefined,
      concurrency: undefined,
      input_hard_limit: undefined,
      input_safety_margin: undefined,
      enable_thinking: false,
      use_openrouter_free_pool: false,
      endpoint: undefined,
      completion_window: undefined,
      out_root: undefined,
      jsonl_root: undefined,
    }
  }
}

async function saveLlmConfig() {
  const usePool = !!llmConfigForm.value.use_openrouter_free_pool
  if (!llmConfigForm.value.name || !llmConfigForm.value.model) {
    window.alert('请填写必填字段：名称、model')
    return
  }
  if (!usePool && (!llmConfigForm.value.base_url || !llmConfigForm.value.api_key)) {
    window.alert('未启用 OpenRouter Key 池时，请填写 base_url 和 api_key')
    return
  }
  llmConfigSaving.value = true
  llmConfigError.value = ''
  try {
    if (llmConfigEditing.value?.id) {
      await updateLlmConfig(llmConfigEditing.value.id, llmConfigForm.value)
    } else {
      await createLlmConfig(llmConfigForm.value as Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>)
    }
    await loadLlmConfigs()
    llmConfigEditing.value = null
    llmConfigForm.value = {}
  } catch (e: any) {
    llmConfigError.value = e?.response?.data?.detail || '保存配置失败'
    window.alert(llmConfigError.value)
  } finally {
    llmConfigSaving.value = false
  }
}

async function deleteLlmConfigHandler(id: number) {
  if (!window.confirm('确定要删除此配置吗？')) return
  try {
    await deleteLlmConfig(id)
    await loadLlmConfigs()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '删除配置失败')
  }
}

async function applyLlmConfigHandler(id: number, usagePrefix: string) {
  llmConfigApplying.value = id
  try {
    await applyLlmConfig(id, usagePrefix)
    window.alert(`配置已成功应用到 ${usagePrefix} 前缀`)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用配置失败')
  } finally {
    llmConfigApplying.value = null
  }
}

// ---------------------------------------------------------------------------
// OpenRouter Key Pool Management
// ---------------------------------------------------------------------------
const keyPoolStatus = ref<OpenRouterKeyPoolStatus | null>(null)
const keyPoolLoading = ref(false)
const keyPoolSaving = ref(false)
const keyPoolError = ref('')
const keyPoolKeysText = ref('')
const keyPoolDailyLimit = ref(50)
const keyPoolExpanded = ref(false)

const freeModels = ref<OpenRouterFreeModel[]>([])
const freeModelsLoading = ref(false)
const freeModelsExpanded = ref(false)

async function loadKeyPool() {
  keyPoolLoading.value = true
  keyPoolError.value = ''
  try {
    const res = await fetchOpenRouterKeyPool()
    keyPoolStatus.value = res
    keyPoolDailyLimit.value = res.daily_limit
  } catch (e: any) {
    keyPoolError.value = e?.response?.data?.detail || '加载 Key 池状态失败'
  } finally {
    keyPoolLoading.value = false
  }
}

async function saveKeyPool() {
  keyPoolSaving.value = true
  keyPoolError.value = ''
  try {
    const res = await saveOpenRouterKeyPool(keyPoolKeysText.value, keyPoolDailyLimit.value)
    keyPoolStatus.value = res
    keyPoolKeysText.value = ''
    window.alert(`已保存 ${res.total_keys} 个 Key，每日限额 ${res.daily_limit} 次`)
  } catch (e: any) {
    keyPoolError.value = e?.response?.data?.detail || '保存 Key 池失败'
    window.alert(keyPoolError.value)
  } finally {
    keyPoolSaving.value = false
  }
}

async function loadFreeModels() {
  freeModelsLoading.value = true
  try {
    const res = await fetchOpenRouterFreeModels()
    freeModels.value = res.models
    freeModelsExpanded.value = true
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '获取免费模型列表失败')
  } finally {
    freeModelsLoading.value = false
  }
}

function pickFreeModel(model: OpenRouterFreeModel) {
  llmConfigForm.value.model = model.id
  if (!llmConfigForm.value.base_url) {
    llmConfigForm.value.base_url = 'https://openrouter.ai/api/v1'
  }
  freeModelsExpanded.value = false
}

// ---------------------------------------------------------------------------
// Prompt Config Management
// ---------------------------------------------------------------------------
const promptConfigs = ref<PromptConfig[]>([])
const promptConfigLoading = ref(false)
const promptConfigError = ref('')
const promptConfigEditing = ref<PromptConfig | null>(null)
const promptConfigForm = ref<Partial<PromptConfig>>({})
const promptConfigSaving = ref(false)
const promptConfigApplying = ref<number | null>(null)

const promptVariableOptions = [
  { value: 'theme_select_system_prompt', label: '主题评分提示词 (theme_select_system_prompt)' },
  { value: 'system_prompt', label: '摘要生成提示词 (system_prompt)' },
  { value: 'summary_limit_prompt_card', label: '摘要精简-八字段整卡终稿 (summary_limit_prompt_card)' },
  { value: 'summary_limit_prompt_intro', label: '摘要精简-文章简介 (summary_limit_prompt_intro)' },
  { value: 'summary_limit_prompt_method', label: '摘要精简-重点思路 (summary_limit_prompt_method)' },
  { value: 'summary_limit_prompt_findings', label: '摘要精简-分析总结 (summary_limit_prompt_findings)' },
  { value: 'summary_limit_prompt_opinion', label: '摘要精简-个人观点 (summary_limit_prompt_opinion)' },
  { value: 'summary_limit_prompt_structure_check', label: '摘要结构校验 (summary_limit_prompt_structure_check)' },
  { value: 'summary_limit_prompt_structure_rewrite', label: '摘要结构重排 (summary_limit_prompt_structure_rewrite)' },
  { value: 'summary_limit_prompt_headline', label: '摘要首行压缩 (summary_limit_prompt_headline)' },
  { value: 'summary_batch_system_prompt', label: '批量摘要提示词 (summary_batch_system_prompt)' },
  { value: 'pdf_info_system_prompt', label: '机构判别提示词 (pdf_info_system_prompt)' },
  { value: 'paper_assets_system_prompt', label: '论文结构化抽取 (paper_assets_system_prompt)' },
]

async function loadPromptConfigs() {
  promptConfigLoading.value = true
  promptConfigError.value = ''
  try {
    const res = await fetchPromptConfigs()
    promptConfigs.value = res.configs
  } catch (e: any) {
    promptConfigError.value = e?.response?.data?.detail || '加载提示词配置列表失败'
  } finally {
    promptConfigLoading.value = false
  }
}

function startEditPromptConfig(config?: PromptConfig) {
  if (config) {
    promptConfigEditing.value = config
    promptConfigForm.value = { ...config }
  } else {
    promptConfigEditing.value = null
    promptConfigForm.value = {
      name: '',
      remark: '',
      prompt_content: '',
    }
  }
}

async function savePromptConfig() {
  if (!promptConfigForm.value.name || !promptConfigForm.value.prompt_content) {
    window.alert('请填写必填字段：名称、prompt_content')
    return
  }
  promptConfigSaving.value = true
  promptConfigError.value = ''
  try {
    if (promptConfigEditing.value?.id) {
      await updatePromptConfig(promptConfigEditing.value.id, promptConfigForm.value)
    } else {
      await createPromptConfig(promptConfigForm.value as Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>)
    }
    await loadPromptConfigs()
    promptConfigEditing.value = null
    promptConfigForm.value = {}
  } catch (e: any) {
    promptConfigError.value = e?.response?.data?.detail || '保存配置失败'
    window.alert(promptConfigError.value)
  } finally {
    promptConfigSaving.value = false
  }
}

async function deletePromptConfigHandler(id: number) {
  if (!window.confirm('确定要删除此配置吗？')) return
  try {
    await deletePromptConfig(id)
    await loadPromptConfigs()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '删除配置失败')
  }
}

async function applyPromptConfigHandler(id: number, variableName: string) {
  promptConfigApplying.value = id
  try {
    await applyPromptConfig(id, variableName)
    window.alert(`配置已成功应用到变量 ${variableName}`)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用配置失败')
  } finally {
    promptConfigApplying.value = null
  }
}

// ---------------------------------------------------------------------------
// User Custom Config Audit
// ---------------------------------------------------------------------------
const customConfigsData = ref<CustomConfigAuditResponse | null>(null)
const customConfigsLoading = ref(false)
const customConfigsError = ref('')
const customConfigsExpandedUsers = ref<Set<number>>(new Set())

async function loadCustomConfigs() {
  customConfigsLoading.value = true
  customConfigsError.value = ''
  try {
    customConfigsData.value = await fetchAdminCustomConfigs()
  } catch (e: any) {
    customConfigsError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    customConfigsLoading.value = false
  }
}

function toggleCustomConfigUser(uid: number) {
  const s = new Set(customConfigsExpandedUsers.value)
  if (s.has(uid)) s.delete(uid)
  else s.add(uid)
  customConfigsExpandedUsers.value = s
}

function featureLabel(f: string): string {
  const map: Record<string, string> = {
    compare: '对比分析',
    inspiration: '灵感涌现',
    paper_chat: '论文问答',
    deep_research: '深度研究',
    translate: '翻译',
    idea_generate: '灵感生成',
    paper_recommend: '论文推荐',
    auto_classify: '自动分类',
  }
  return map[f] || f
}

// ---------------------------------------------------------------------------
// User Detail Modal
// ---------------------------------------------------------------------------
const userDetailVisible = ref(false)
const userDetailLoading = ref(false)
const userDetailError = ref('')
const userDetail = ref<AdminUserDetailResponse | null>(null)

async function openUserDetail(user: AuthUser) {
  userDetailVisible.value = true
  userDetailLoading.value = true
  userDetailError.value = ''
  userDetail.value = null
  try {
    userDetail.value = await fetchAdminUserDetail(user.id)
  } catch (e: any) {
    userDetailError.value = e?.response?.data?.detail || '加载用户详情失败'
  } finally {
    userDetailLoading.value = false
  }
}

function closeUserDetail() {
  userDetailVisible.value = false
  userDetail.value = null
  userDetailError.value = ''
  showResetPwdForm.value = false
  showDeleteConfirm.value = false
  resetPwdValue.value = ''
  deleteConfirmInput.value = ''
  clearActionFeedback()
}

function handleUserDetailKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeUserDetail()
}

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    admin: '管理员调整',
    redeem: '兑换码',
    expiry: '到期自动降级',
    register: '注册赠送',
    manual: '手动',
  }
  return map[source] ?? source
}

// ---------------------------------------------------------------------------
// User Detail – Admin Actions
// ---------------------------------------------------------------------------
const actionBusy = ref(false)
const actionMsg = ref('')
const actionError = ref('')
const showResetPwdForm = ref(false)
const resetPwdValue = ref('')
const showDeleteConfirm = ref(false)
const deleteConfirmInput = ref('')

function clearActionFeedback() {
  actionMsg.value = ''
  actionError.value = ''
}

async function handleAdminResetPassword() {
  if (!userDetail.value) return
  clearActionFeedback()
  actionBusy.value = true
  try {
    await adminResetUserPassword(userDetail.value.user.id, resetPwdValue.value)
    showResetPwdForm.value = false
    resetPwdValue.value = ''
    actionMsg.value = '密码已重置'
  } catch (e: any) {
    actionError.value = e?.response?.data?.detail || '重置失败'
  } finally {
    actionBusy.value = false
  }
}

async function handleAdminForceLogout() {
  if (!userDetail.value) return
  if (!confirm(`确定要强制下线用户「${userDetail.value.user.username}」的所有会话吗？`)) return
  clearActionFeedback()
  actionBusy.value = true
  try {
    const res = await adminForceLogout(userDetail.value.user.id)
    actionMsg.value = `已清除 ${res.sessions_deleted} 个会话`
    userDetail.value.active_sessions = 0
  } catch (e: any) {
    actionError.value = e?.response?.data?.detail || '操作失败'
  } finally {
    actionBusy.value = false
  }
}

async function handleAdminDisable() {
  if (!userDetail.value) return
  if (!confirm(`确定要禁用用户「${userDetail.value.user.username}」的账号吗？禁用后该用户将无法登录。`)) return
  clearActionFeedback()
  actionBusy.value = true
  try {
    const res = await adminDisableUser(userDetail.value.user.id)
    userDetail.value.user = res.user
    actionMsg.value = '账号已禁用'
  } catch (e: any) {
    actionError.value = e?.response?.data?.detail || '操作失败'
  } finally {
    actionBusy.value = false
  }
}

async function handleAdminEnable() {
  if (!userDetail.value) return
  if (!confirm(`确定要启用用户「${userDetail.value.user.username}」的账号吗？`)) return
  clearActionFeedback()
  actionBusy.value = true
  try {
    const res = await adminEnableUser(userDetail.value.user.id)
    userDetail.value.user = res.user
    actionMsg.value = '账号已启用'
  } catch (e: any) {
    actionError.value = e?.response?.data?.detail || '操作失败'
  } finally {
    actionBusy.value = false
  }
}

function openDeleteConfirm() {
  deleteConfirmInput.value = ''
  showDeleteConfirm.value = true
  clearActionFeedback()
}

async function handleAdminDelete() {
  if (!userDetail.value) return
  if (deleteConfirmInput.value !== userDetail.value.user.username) {
    actionError.value = '输入的用户名不匹配，请重新输入'
    return
  }
  clearActionFeedback()
  actionBusy.value = true
  try {
    await adminDeleteUser(userDetail.value.user.id)
    // 从列表中移除
    users.value = users.value.filter((u) => u.id !== userDetail.value!.user.id)
    closeUserDetail()
  } catch (e: any) {
    actionError.value = e?.response?.data?.detail || '删除失败'
  } finally {
    actionBusy.value = false
  }
}

// ---------------------------------------------------------------------------
// Step Config
// ---------------------------------------------------------------------------

const stepDefs = ref<PipelineStepDefinition[]>([])
const stepConfig = ref<Record<string, boolean>>({})
const stepConfigLoading = ref(false)
const stepConfigSaving = ref(false)
const stepConfigError = ref('')
const stepConfigSuccess = ref('')

const defMap = computed(() => Object.fromEntries(stepDefs.value.map(d => [d.key, d])))

const stepsByGroup = computed(() => {
  const groups = new Map<string, PipelineStepDefinition[]>()
  for (const def of stepDefs.value) {
    if (!groups.has(def.group)) groups.set(def.group, [])
    groups.get(def.group)!.push(def)
  }
  return [...groups.entries()]
})

function enabledCountInGroup(steps: PipelineStepDefinition[]) {
  return steps.filter(s => stepConfig.value[s.key] !== false).length
}

function costClass(level: string) {
  if (level === 'high') return 'bg-red-500/15 text-red-400'
  if (level === 'medium') return 'bg-amber-500/15 text-amber-400'
  return 'bg-green-500/15 text-green-400'
}

function costLabel(level: string) {
  if (level === 'high') return '高消耗'
  if (level === 'medium') return '中消耗'
  return '低消耗'
}

function disableCascade(key: string) {
  stepConfig.value = { ...stepConfig.value, [key]: false }
  for (const def of stepDefs.value) {
    if (def.requires.includes(key) && def.can_disable && stepConfig.value[def.key] !== false) {
      disableCascade(def.key)
    }
  }
}

function enableCascade(key: string) {
  stepConfig.value = { ...stepConfig.value, [key]: true }
  const def = defMap.value[key]
  if (!def) return
  for (const req of def.requires) {
    if (stepConfig.value[req] === false) {
      enableCascade(req)
    }
  }
}

function toggleStep(key: string) {
  if (stepConfig.value[key] === false) {
    enableCascade(key)
  } else {
    disableCascade(key)
  }
  stepConfigSuccess.value = ''
  stepConfigError.value = ''
}

async function loadStepConfig() {
  if (stepConfigLoading.value) return
  stepConfigLoading.value = true
  stepConfigError.value = ''
  try {
    const res = await fetchPipelineStepConfig()
    stepDefs.value = res.definitions
    stepConfig.value = res.config
  } catch (e: any) {
    stepConfigError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    stepConfigLoading.value = false
  }
}

async function saveStepConfig() {
  stepConfigSaving.value = true
  stepConfigError.value = ''
  stepConfigSuccess.value = ''
  try {
    await savePipelineStepConfig(stepConfig.value)
    stepConfigSuccess.value = '配置已保存，下次 Pipeline 运行时生效'
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail?.errors) {
      stepConfigError.value = detail.errors.join('；')
    } else {
      stepConfigError.value = detail || e?.message || '保存失败'
    }
  } finally {
    stepConfigSaving.value = false
  }
}

async function doResetStepConfig() {
  if (!confirm('确认将步骤配置恢复为默认值？')) return
  stepConfigError.value = ''
  stepConfigSuccess.value = ''
  try {
    await resetPipelineStepConfig()
    await loadStepConfig()
    stepConfigSuccess.value = '已恢复默认配置'
  } catch (e: any) {
    stepConfigError.value = e?.response?.data?.detail || e?.message || '重置失败'
  }
}

function applyTokenSavingConfig() {
  const ideaSteps = ['idea_ingest', 'idea_combine', 'idea_review', 'idea_compound']
  stepConfig.value = { ...stepConfig.value }
  for (const key of ideaSteps) {
    if (key in stepConfig.value) {
      stepConfig.value[key] = false
    }
  }
  stepConfigSuccess.value = ''
  stepConfigError.value = ''
}

onMounted(async () => {
  loadUsers()
  await loadPipelineStatus()
  await loadSchedule()
  if (pipelineStatus.value?.running) {
    startPolling()
  }
})

// load announcements when tab switches
watch(activeTab, (tab) => {
  if (tab === 'step-config' && stepDefs.value.length === 0) loadStepConfig()
})

</script>

<template>
  <div class="h-full flex overflow-hidden relative">

    <!-- Mobile sidebar overlay backdrop -->
    <div
      v-if="showAdminSidebar"
      class="fixed inset-0 z-20 bg-black/60 md:hidden"
      @click="showAdminSidebar = false"
    />

    <!-- Mobile admin nav toggle button -->
    <button
      v-if="!showAdminSidebar"
      class="absolute top-2 left-2 z-10 md:hidden w-8 h-8 flex items-center justify-center rounded-full bg-bg-card border border-border text-text-secondary hover:bg-bg-hover transition-colors"
      title="后台管理导航"
      @click="showAdminSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>

    <!-- ============================== -->
    <!-- Sidebar -->
    <!-- ============================== -->
    <aside
      :class="[
        'z-30 lg:z-auto settings-sidebar h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300',
        showAdminSidebar
          ? 'fixed lg:relative inset-y-0 left-0 translate-x-0'
          : 'fixed lg:relative inset-y-0 left-0 -translate-x-full lg:translate-x-0'
      ]"
    >
      <!-- Mobile close button (hidden once sidebar is persistent at lg) -->
      <button
        class="lg:hidden absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary border-none cursor-pointer"
        @click="showAdminSidebar = false"
      >✕</button>
      <!-- Sidebar header -->
      <div class="px-4 pt-5 pb-3 border-b border-border">
        <h2 class="text-base font-bold text-text-primary tracking-tight">⚙ 后台管理</h2>
        <p class="text-[11px] text-text-muted mt-0.5">系统管理与运维</p>
      </div>

      <!-- Menu items (grouped) -->
      <nav class="flex-1 overflow-y-auto p-2">
        <div v-for="group in menuGroups" :key="group.name" class="mb-2">
          <div v-if="group.name" class="px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted/60">
            {{ group.name }}
          </div>
          <div class="space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.key"
              class="w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left bg-transparent border-none cursor-pointer transition-all duration-150"
              :class="activeTab === item.key
                ? 'bg-bg-elevated shadow-sm'
                : 'hover:bg-bg-hover'"
              @click="activeTab = item.key; showAdminSidebar = false"
            >
              <span class="text-lg leading-none mt-0.5 shrink-0">{{ item.icon }}</span>
              <div class="min-w-0">
                <div
                  class="text-sm font-medium truncate"
                  :class="activeTab === item.key ? 'text-text-primary' : 'text-text-secondary'"
                >{{ item.label }}</div>
                <div class="text-[11px] text-text-muted truncate mt-0.5">{{ item.desc }}</div>
              </div>
              <!-- Active indicator -->
              <div
                v-if="activeTab === item.key"
                class="ml-auto mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0"
              ></div>
            </button>
          </div>
        </div>
      </nav>

      <!-- Sidebar footer: pipeline status badge -->
      <div class="px-3 py-3 border-t border-border">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :class="isRunning ? 'bg-blue-400 animate-pulse' : 'bg-gray-500'"
          ></span>
          <span class="truncate">Pipeline: {{ isRunning ? '运行中' : '空闲' }}</span>
        </div>
        <div v-if="schedule.enabled" class="text-[10px] text-text-muted mt-1 pl-4">
          定时 {{ String(schedule.hour).padStart(2, '0') }}:{{ String(schedule.minute).padStart(2, '0') }} 自动执行
        </div>
      </div>
    </aside>

    <!-- ============================== -->
    <!-- Main content area -->
    <!-- ============================== -->
    <div class="flex-1 flex flex-col overflow-hidden min-w-0">

      <!-- ============================================================= -->
      <!-- Page: Analytics Dashboard (数据统计分析)                     -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'analytics'" class="flex-1 flex flex-col p-3 sm:p-6 overflow-auto">
        <div class="mb-4 shrink-0">
          <h1 class="text-lg font-bold text-text-primary">📊 数据统计分析</h1>
          <p class="text-xs text-text-muted mt-0.5">平台数据分析、用户洞察与内容热度</p>
        </div>
        <AdminAnalytics />
      </div>

      <!-- ============================================================= -->
      <!-- Page: Preference Analytics (偏好推荐分析)                   -->
      <!-- ============================================================= -->
      <AdminPreferenceAnalyticsPanel v-if="activeTab === 'preference-analytics'" />

      <!-- ============================================================= -->
      <!-- Page: Announcement Management (公告管理)                     -->
      <!-- ============================================================= -->
      <AdminAnnouncementsPanel v-if="activeTab === 'announcements'" />

      <!-- ============================================================= -->
      <!-- Page: User Tier Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'users'" class="flex-1 flex flex-col p-3 sm:p-6 overflow-hidden">
        <div class="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">👥 用户等级</h1>
            <p class="text-xs text-text-muted mt-0.5">管理用户的访问等级（Free / Pro / Pro+）</p>
          </div>
          <button
            class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="loadUsers"
          >
            🔄 刷新
          </button>
        </div>

        <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400">{{ error }}</div>

        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">用户名</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">当前等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">到期时间</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">调整等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">最后登录</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in users"
                :key="u.id"
                class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors cursor-pointer"
                @click.stop="openUserDetail(u)"
              >
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ u.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">
                  {{ u.username }}
                  <span
                    v-if="currentUser?.id === u.id"
                    class="ml-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full"
                  >我</span>
                  <span
                    v-if="u.is_disabled"
                    class="ml-1 text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full border border-red-500/30"
                  >已禁用</span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="px-2 py-0.5 rounded-full text-xs"
                    :class="roleBadgeClass(u.role)"
                  >
                    {{ roleLabel(u.role) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-text-secondary">{{ tierLabel(u.tier) }}</td>
                <td class="px-4 py-3 text-text-muted text-xs">
                  {{ u.tier_expires_at ? formatDateTime(u.tier_expires_at) : (u.tier === 'free' ? '-' : '长期') }}
                </td>
                <td class="px-4 py-3" @click.stop>
                  <select
                    :value="u.tier"
                    :disabled="savingUserId === u.id"
                    class="px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 cursor-pointer disabled:opacity-60 transition-all"
                    @change="onTierChange(u, $event)"
                  >
                    <option v-for="opt in tierOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                </td>
                <td class="px-4 py-3 text-text-muted text-xs">
                  {{ u.last_login_at ? new Date(u.last_login_at).toLocaleString('zh-CN') : '从未' }}
                </td>
              </tr>
              <tr v-if="users.length === 0">
                <td colspan="7" class="px-4 py-10 text-center text-text-muted">暂无用户</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Subscription Redeem Keys -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'subscription-keys'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🎟️ 会员兑换码</h1>
          <p class="text-xs text-text-muted mt-0.5">用于发放 Pro / Pro+ 时长权益，不影响管理员角色体系</p>
        </div>

        <div class="rounded-xl bg-bg-card border border-border p-5">
          <h2 class="text-sm font-semibold text-text-primary mb-3">批量发码</h2>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs text-text-muted mb-1">套餐</label>
              <select v-model="redeemPlanTier" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm">
                <option value="pro">Pro</option>
                <option value="pro_plus">Pro+</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">时长（天）</label>
              <input v-model.number="redeemDurationDays" type="number" min="1" max="3650" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">数量</label>
              <input v-model.number="redeemKeyCount" type="number" min="1" max="500" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">有效期（天，可空）</label>
              <input v-model.number="redeemValidDays" type="number" min="1" max="3650" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">单码可用次数</label>
              <input v-model.number="redeemMaxUses" type="number" min="1" max="20" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div class="md:col-span-1">
              <label class="block text-xs text-text-muted mb-1">备注</label>
              <input v-model="redeemNote" type="text" maxlength="256" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" placeholder="例如：3月活动批次" />
            </div>
          </div>
          <div class="mt-4 flex items-center gap-3">
            <button
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-60 cursor-pointer"
              :disabled="issuingRedeemKeys"
              @click="handleIssueRedeemKeys"
            >
              {{ issuingRedeemKeys ? '生成中...' : '生成兑换码' }}
            </button>
            <span v-if="issueRedeemError" class="text-xs text-red-400">{{ issueRedeemError }}</span>
            <span v-else-if="issuedBatchId" class="text-xs text-green-400">已生成批次：{{ issuedBatchId }}</span>
          </div>
          <div v-if="issuedCodes.length > 0" class="mt-4">
            <div class="mb-2 flex items-center justify-between gap-2">
              <p class="text-xs text-text-muted">请立即复制并保存（明文仅本次返回）</p>
              <div class="flex items-center gap-2">
                <button
                  class="px-2.5 py-1 rounded border border-border text-xs text-text-secondary hover:bg-bg-hover cursor-pointer"
                  @click="copyIssuedCodes"
                >
                  复制全部
                </button>
                <span v-if="copyIssuedCodesMsg" class="text-xs text-green-400">{{ copyIssuedCodesMsg }}</span>
              </div>
            </div>
            <textarea
              :value="issuedCodes.join('\n')"
              readonly
              class="w-full min-h-[140px] px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs font-mono"
            />
          </div>
        </div>

        <div class="rounded-xl bg-bg-card border border-border p-5 flex-1 min-h-[260px] overflow-auto">
          <div class="flex items-center gap-2 mb-3">
            <input
              v-model="redeemKeysBatchFilter"
              type="text"
              placeholder="按批次号过滤"
              class="px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm"
            />
            <button class="px-3 py-2 rounded-lg border border-border text-sm text-text-secondary hover:bg-bg-hover cursor-pointer" @click="loadRedeemKeys">查询</button>
          </div>
          <div v-if="redeemKeysLoading" class="text-sm text-text-muted">加载中...</div>
          <div v-else-if="redeemKeysError" class="text-sm text-red-400">{{ redeemKeysError }}</div>
          <table v-else class="w-full text-sm">
            <thead>
              <tr class="border-b border-border text-text-muted">
                <th class="text-left py-2">ID</th>
                <th class="text-left py-2">批次</th>
                <th class="text-left py-2">套餐</th>
                <th class="text-left py-2">时长</th>
                <th class="text-left py-2">使用</th>
                <th class="text-left py-2">状态</th>
                <th class="text-left py-2">到期</th>
                <th class="text-left py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in redeemKeys" :key="k.id" class="border-b border-border/50">
                <td class="py-2 text-text-muted font-mono text-xs">{{ k.id }}</td>
                <td class="py-2 text-text-secondary font-mono text-xs">{{ k.batch_id }}</td>
                <td class="py-2 text-text-primary">{{ tierLabel(k.plan_tier) }}</td>
                <td class="py-2 text-text-secondary">{{ k.duration_days }} 天</td>
                <td class="py-2 text-text-secondary">{{ k.used_count }} / {{ k.max_uses }}</td>
                <td class="py-2">
                  <span
                    class="px-2 py-0.5 rounded-full text-xs"
                    :class="k.status === 'active' ? 'bg-green-500/15 text-green-400' : k.status === 'consumed' ? 'bg-blue-500/15 text-blue-300' : 'bg-red-500/15 text-red-300'"
                  >{{ redeemKeyStatusText(k.status) }}</span>
                </td>
                <td class="py-2 text-text-muted text-xs">{{ k.expire_at ? formatDateTime(k.expire_at) : '长期有效' }}</td>
                <td class="py-2">
                  <button
                    v-if="k.status === 'active'"
                    class="px-2 py-1 rounded border border-red-500/30 text-red-300 text-xs hover:bg-red-500/10 cursor-pointer"
                    @click="handleDisableRedeemKey(k)"
                  >禁用</button>
                  <span v-else class="text-text-muted text-xs">—</span>
                </td>
              </tr>
              <tr v-if="redeemKeys.length === 0">
                <td colspan="8" class="py-8 text-center text-text-muted">暂无兑换码记录</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Role / Permission Management (superadmin only) -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'roles'" class="flex-1 flex flex-col p-3 sm:p-6 overflow-hidden">
        <div class="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">🛡️ 权限管理</h1>
            <p class="text-xs text-text-muted mt-0.5">设置用户角色：普通用户 / 管理员 / 超级管理员</p>
          </div>
          <button
            class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="loadUsers"
          >
            🔄 刷新
          </button>
        </div>

        <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400">{{ error }}</div>

        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <!-- Info banner -->
          <div class="px-4 py-3 bg-amber-500/5 border-b border-amber-500/20 flex items-center gap-2">
            <span class="text-amber-400 text-sm">⚠️</span>
            <span class="text-xs text-amber-400/80">仅超级管理员可修改角色权限，请谨慎操作</span>
          </div>
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">用户名</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">当前角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">修改角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">注册时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in users"
                :key="u.id"
                class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors cursor-pointer"
                @click.stop="openUserDetail(u)"
              >
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ u.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">
                  {{ u.username }}
                  <span
                    v-if="currentUser?.id === u.id"
                    class="ml-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full"
                  >我</span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="px-2 py-0.5 rounded-full text-xs"
                    :class="roleBadgeClass(u.role)"
                  >
                    {{ roleLabel(u.role) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-text-secondary text-xs">{{ tierLabel(u.tier) }}</td>
                <td class="px-4 py-3" @click.stop>
                  <select
                    v-if="currentUser?.id !== u.id"
                    :value="u.role"
                    :disabled="savingUserId === u.id"
                    class="px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-amber-500/50 cursor-pointer disabled:opacity-60 transition-all"
                    @change="onRoleChange(u, $event)"
                  >
                    <option v-for="opt in roleOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                  <span v-else class="text-xs text-text-muted italic">— 无法修改自己</span>
                </td>
                <td class="px-4 py-3 text-text-muted text-xs">
                  {{ u.created_at ? new Date(u.created_at).toLocaleString('zh-CN') : '-' }}
                </td>
              </tr>
              <tr v-if="users.length === 0">
                <td colspan="6" class="px-4 py-10 text-center text-text-muted">暂无用户</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Role description cards -->
        <div class="grid grid-cols-3 gap-3 mt-4 shrink-0">
          <div class="rounded-xl bg-bg-card border border-border p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-bg-elevated text-text-secondary">普通用户</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">仅可浏览论文、使用知识库等基础功能</p>
          </div>
          <div class="rounded-xl bg-bg-card border border-blue-500/20 p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30">管理员</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">可管理用户等级、执行脚本、配置定时调度</p>
          </div>
          <div class="rounded-xl bg-bg-card border border-amber-500/20 p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30">超级管理员</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">拥有所有管理权限，可修改任意用户角色</p>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Pipeline Execution -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'pipeline'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🚀 脚本执行</h1>
          <p class="text-xs text-text-muted mt-0.5">手动触发 Pipeline 运行，查看实时日志</p>
        </div>

        <!-- Run Controls -->
        <div class="rounded-xl bg-bg-card border border-border p-5">
          <h2 class="text-sm font-semibold text-text-primary mb-3">执行参数</h2>

          <!-- 多用户模式开关 -->
          <div class="flex items-center gap-3 mb-3 p-3 rounded-lg bg-bg-elevated border border-border">
            <label class="flex items-center gap-2 cursor-pointer select-none">
              <input
                v-model="runMultiUser"
                type="checkbox"
                class="w-4 h-4 rounded border-border text-blue-500 focus:ring-blue-500/30 bg-bg-card cursor-pointer"
              />
              <span class="text-sm font-medium text-text-primary">多用户编排模式</span>
            </label>
            <span class="text-xs text-text-muted">
              {{ runMultiUser ? '✅ shared 阶段 + 为所有自定义配置用户执行 per_user 阶段（与定时调度相同，结果写入数据库，前台可见）' : '⚠️ 旧模式 / 调试用：单用户执行指定 Pipeline（结果仍写入数据库，但不并行运行各用户分支）' }}
            </span>
            <div v-if="runMultiUser" class="ml-auto flex items-center gap-1.5 shrink-0">
              <span class="text-xs text-text-muted">最大并发用户数</span>
              <input
                v-model.number="runMaxConcurrentUsers"
                type="number"
                min="1"
                max="20"
                class="w-14 px-2 py-1 rounded bg-bg-card border border-border text-text-primary text-xs text-center focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
          </div>

          <!-- 基础参数 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div>
              <label class="block text-xs text-text-muted mb-1">运行日期</label>
              <input
                v-model="runDate"
                type="date"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Pipeline
                <span v-if="runMultiUser" class="ml-1 text-[10px] text-blue-400">（多用户模式下固定为 shared+per_user）</span>
              </label>
              <select
                v-model="runPipelineName"
                :disabled="runMultiUser"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <option value="default">default (全流程)</option>
                <option value="daily">daily (每日流程)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">摘要模型 (SLLM)</label>
              <select
                v-model="runSllm"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option :value="null">默认</option>
                <option :value="1">1 - Qwen</option>
                <option :value="2">2 - Claude (GPTGod)</option>
                <option :value="3">3 - Claude (VectorEngine)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Zotero 推送</label>
              <select
                v-model="runZo"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="F">关闭</option>
                <option value="T">开启</option>
              </select>
            </div>
          </div>

          <!-- Arxiv 检索参数折叠区 -->
          <div class="mb-4">
            <button
              type="button"
              class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors mb-2"
              @click="showAdvancedParams = !showAdvancedParams"
            >
              <span class="transition-transform duration-200" :class="showAdvancedParams ? 'rotate-90' : ''">▶</span>
              <span>Arxiv 检索参数</span>
              <span
                v-if="runDays || runCategories || runQuery || runMaxPapers"
                class="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400"
              >已自定义</span>
            </button>

            <div v-if="showAdvancedParams" class="grid grid-cols-2 md:grid-cols-4 gap-3 pl-0">
              <div>
                <label class="block text-xs text-text-muted mb-1">
                  时间窗口 (天)
                  <span class="ml-1 text-[10px] text-text-muted/60">--days，默认 1</span>
                </label>
                <input
                  v-model.number="runDays"
                  type="number"
                  min="1"
                  max="30"
                  placeholder="1"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div>
                <label class="block text-xs text-text-muted mb-1">
                  最大论文数
                  <span class="ml-1 text-[10px] text-text-muted/60">--max-papers，默认 500（多用户 shared 阶段同样生效）</span>
                </label>
                <input
                  v-model.number="runMaxPapers"
                  type="number"
                  min="1"
                  max="5000"
                  placeholder="500"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs text-text-muted mb-1">
                  检索分类
                  <span class="ml-1 text-[10px] text-text-muted/60">--categories，逗号分隔，如 cs.AI,cs.LG</span>
                </label>
                <input
                  v-model="runCategories"
                  type="text"
                  placeholder="cs.CL,cs.LG,cs.AI,stat.ML"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div class="md:col-span-4">
                <label class="block text-xs text-text-muted mb-1">
                  附加关键词
                  <span class="ml-1 text-[10px] text-text-muted/60">--query，支持自然语言或 arXiv 高级表达式（ti:/abs:/AND/OR...）</span>
                </label>
                <input
                  v-model="runQuery"
                  type="text"
                  placeholder='例：reinforcement learning 或 ti:"large language model" AND abs:reasoning'
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
            </div>
          </div>

          <div class="flex items-center gap-3 flex-wrap">
            <button
              :disabled="isRunning || pipelineLoading"
              class="px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="isRunning
                ? 'bg-gray-600 text-gray-300'
                : runForce
                  ? 'bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-600/20'
                  : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/20'"
              @click="handleRunPipeline"
            >
              {{ pipelineLoading ? '启动中...' : isRunning ? '运行中...' : runForce ? '▶ 强制执行' : '▶ 开始执行' }}
            </button>
            <label class="flex items-center gap-1.5 cursor-pointer select-none group">
              <input
                v-model="runForce"
                type="checkbox"
                class="w-4 h-4 rounded border-border text-orange-500 focus:ring-orange-500/30 bg-bg-elevated cursor-pointer"
              />
              <span class="text-xs text-text-secondary group-hover:text-text-primary transition-colors">强制重新执行</span>
              <span class="text-[10px] text-text-muted/60" title="忽略幂等检查，删除已有输出并重新执行全部步骤">(?)</span>
            </label>
            <button
              v-if="isRunning"
              class="px-5 py-2 rounded-lg bg-red-600/20 text-red-400 border border-red-500/30 text-sm font-medium hover:bg-red-600/30 transition-all duration-200"
              @click="handleStopPipeline"
            >
              ■ 终止
            </button>
            <button
              v-if="!isRunning && pipelineStatus"
              class="px-3 py-2 rounded-lg border border-border text-xs text-text-secondary bg-transparent hover:bg-bg-hover transition-colors"
              @click="loadPipelineStatus"
            >
              🔄 刷新状态
            </button>
            <span v-if="pipelineError" class="text-red-400 text-sm">{{ pipelineError }}</span>
          </div>
        </div>

        <!-- Status Panel -->
        <div class="rounded-xl bg-bg-card border border-border p-5">
          <h2 class="text-sm font-semibold text-text-primary mb-3">📊 运行状态</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">状态</div>
              <div class="text-sm font-semibold flex items-center gap-2" :class="statusColor">
                <span
                  v-if="isRunning"
                  class="inline-block w-2 h-2 bg-blue-400 rounded-full animate-pulse"
                ></span>
                {{ statusLabel }}
              </div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">当前步骤</div>
              <div class="text-sm text-text-primary truncate">{{ pipelineStatus?.current_step || '-' }}</div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">开始时间</div>
              <div class="text-sm text-text-primary">{{ formattedStartedAt }}</div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">完成时间</div>
              <div class="text-sm text-text-primary">{{ formattedFinishedAt }}</div>
            </div>
          </div>

          <!-- Logs -->
          <div class="mt-3">
            <div class="flex items-center justify-between mb-2">
              <div class="text-xs text-text-muted">运行日志</div>
              <div v-if="trackedRunId" class="text-[10px] text-text-muted/60 font-mono">
                run: {{ trackedRunId }}
              </div>
            </div>
            <div
              ref="logsContainer"
              class="h-64 overflow-auto rounded-lg bg-[#0d1117] border border-border p-3 font-mono text-xs leading-5 text-green-400/90"
            >
              <div v-if="!pipelineStatus?.logs?.length" class="text-text-muted italic">暂无日志...</div>
              <div v-for="(line, i) in pipelineStatus?.logs" :key="i" class="whitespace-pre-wrap break-all">
                <span v-if="line.includes('[ERROR]')" class="text-red-400">{{ line }}</span>
                <span v-else-if="line.includes('SKIP')" class="text-yellow-500/80">{{ line }}</span>
                <span v-else-if="line.includes('RUN step')" class="text-cyan-400">{{ line }}</span>
                <span v-else-if="line.includes('START pipeline')" class="text-blue-400 font-bold">{{ line }}</span>
                <span v-else>{{ line }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Pipeline Console (Observability) -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'console'" class="flex-1 flex flex-col p-3 sm:p-6 overflow-hidden gap-3">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🖥️ 运行控制台</h1>
          <p class="text-xs text-text-muted mt-0.5">可观测每次 Pipeline 运行的 Step 状态、产物、事件流，以及单步重跑</p>
        </div>
        <PipelineConsole class="flex-1 min-h-0" />
      </div>

      <!-- ============================================================= -->
      <!-- Page: Schedule Config -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'schedule'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🕐 定时调度</h1>
          <p class="text-xs text-text-muted mt-0.5">配置每日自动执行 Pipeline 的时间和参数</p>
        </div>

        <div class="rounded-xl bg-bg-card border border-border p-5">
          <!-- Toggle -->
          <div class="flex items-center gap-3 mb-5">
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="schedule.enabled"
                type="checkbox"
                class="sr-only peer"
              />
              <div class="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
            <span class="text-sm font-medium" :class="schedule.enabled ? 'text-blue-400' : 'text-text-muted'">
              {{ schedule.enabled ? '已启用自动定时执行' : '自动定时执行已关闭' }}
            </span>
          </div>

          <!-- Config grid -->
          <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
            <div>
              <label class="block text-xs text-text-muted mb-1">执行时间 (时)</label>
              <input
                v-model.number="schedule.hour"
                type="number"
                min="0"
                max="23"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">执行时间 (分)</label>
              <input
                v-model.number="schedule.minute"
                type="number"
                min="0"
                max="59"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Pipeline</label>
              <select
                v-model="schedule.pipeline"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="default">default</option>
                <option value="daily">daily</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">摘要模型</label>
              <select
                v-model="schedule.sllm"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option :value="null">默认</option>
                <option :value="1">1 - Qwen</option>
                <option :value="2">2 - Claude (GPTGod)</option>
                <option :value="3">3 - Claude (VectorEngine)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Zotero</label>
              <select
                v-model="schedule.zo"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="F">关闭</option>
                <option value="T">开启</option>
              </select>
            </div>
            <!-- Multi-user settings -->
            <div class="col-span-2">
              <label class="block text-xs text-text-muted mb-2 font-medium">多用户并行模式</label>
              <div class="flex items-center gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" v-model="schedule.multi_user"
                    class="w-4 h-4 rounded border-border bg-bg-elevated text-blue-500 focus:ring-blue-500/50" />
                  <span class="text-xs text-text-primary">启用多用户并行管线</span>
                </label>
                <span class="text-xs text-text-muted">（推荐：自动为所有有个性化配置的用户各生成一份个性化结果）</span>
              </div>
            </div>
            <div v-if="schedule.multi_user">
              <label class="block text-xs text-text-muted mb-1">最大并发用户数</label>
              <input
                v-model.number="schedule.max_concurrent_user_pipelines"
                type="number"
                min="1"
                max="20"
                placeholder="3"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div v-if="schedule.multi_user">
              <label class="block text-xs text-text-muted mb-1">有个性化配置的用户数</label>
              <div class="px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-secondary text-sm">
                {{ scheduleCustomUserCount != null ? scheduleCustomUserCount + ' 个用户' : '加载中...' }}
              </div>
            </div>
          </div>

          <!-- Summary & Save -->
          <div class="flex items-center gap-3 flex-wrap pt-3 border-t border-border">
            <button
              :disabled="scheduleSaving"
              class="px-5 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium shadow-lg shadow-green-600/20 transition-all duration-200 disabled:opacity-50"
              @click="handleSaveSchedule"
            >
              {{ scheduleSaving ? '保存中...' : '💾 保存配置' }}
            </button>
            <span v-if="schedule.enabled" class="text-xs text-text-muted">
              每天 {{ String(schedule.hour).padStart(2, '0') }}:{{ String(schedule.minute).padStart(2, '0') }} 自动执行
              <template v-if="schedule.last_run_date">
                · 上次运行: {{ schedule.last_run_date }}
              </template>
            </span>
            <!-- 调度线程状态 -->
            <span
              v-if="schedule.enabled && schedule.scheduler_alive !== undefined"
              class="ml-auto flex items-center gap-1.5 text-xs"
              :class="schedule.scheduler_alive ? 'text-green-400' : 'text-red-400'"
            >
              <span
                class="inline-block w-2 h-2 rounded-full"
                :class="schedule.scheduler_alive ? 'bg-green-400 animate-pulse' : 'bg-red-400'"
              ></span>
              {{ schedule.scheduler_alive ? '调度线程运行中' : '调度线程已停止（刷新页面可自动重启）' }}
            </span>
          </div>
        </div>

        <!-- Info card -->
        <div class="rounded-xl bg-blue-500/5 border border-blue-500/20 p-4">
          <h3 class="text-sm font-medium text-blue-400 mb-2">💡 说明</h3>
          <ul class="text-xs text-text-muted space-y-1.5 list-none p-0 m-0">
            <li>• 定时调度会在每天设定时间自动执行一次 Pipeline</li>
            <li>• 自动执行期间仍可手动点击「脚本执行」运行，但不会同时执行两个</li>
            <li>• 调度配置会持久化保存，服务重启后自动恢复</li>
            <li>• 如果当天的 Pipeline 输出已存在，对应步骤会自动跳过</li>
            <li class="text-green-400">• <strong>多用户并行模式</strong>（推荐）：调度时自动发现所有有个性化配置的用户，为每人单独运行一遍 per_user 管线，结果存储到 DB，按用户展示个性化内容</li>
            <li class="text-text-muted">• 共享阶段（arxiv抓取 / PDF下载 / MinerU解析）只运行一次，所有用户共享，避免重复调用</li>
          </ul>
        </div>

        <!-- Execution History -->
        <div class="rounded-xl bg-bg-card border border-border p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text-primary">📋 执行日志</h3>
            <button
              class="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border text-xs text-text-muted bg-transparent hover:bg-bg-hover transition-colors cursor-pointer"
              :disabled="scheduleHistoryLoading"
              @click="loadScheduleHistory()"
            >
              <span v-if="scheduleHistoryLoading" class="inline-block w-3 h-3 border border-text-muted border-t-transparent rounded-full animate-spin"></span>
              <span v-else>🔄</span>
              刷新
            </button>
          </div>

          <!-- Loading state -->
          <div v-if="scheduleHistoryLoading && scheduleHistory.length === 0" class="flex items-center justify-center py-8 text-text-muted text-xs gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中…
          </div>

          <!-- Empty state -->
          <div v-else-if="scheduleHistory.length === 0" class="text-center py-8 text-text-muted text-xs">
            暂无执行记录，执行完成后将在此显示
          </div>

          <!-- Table -->
          <div v-else class="overflow-x-auto">
            <table class="w-full text-xs border-collapse">
              <thead>
                <tr class="border-b border-border text-text-muted">
                  <th class="text-left py-2 pr-3 font-medium whitespace-nowrap">执行时间</th>
                  <th class="text-left py-2 pr-3 font-medium whitespace-nowrap">触发方式</th>
                  <th class="text-center py-2 pr-3 font-medium whitespace-nowrap">执行配置数</th>
                  <th class="text-center py-2 pr-3 font-medium whitespace-nowrap">状态</th>
                  <th class="text-right py-2 font-medium whitespace-nowrap">耗时</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="rec in scheduleHistory"
                  :key="rec.run_id"
                  class="border-b border-border/50 hover:bg-bg-elevated/40 transition-colors"
                >
                  <!-- 执行时间 -->
                  <td class="py-2 pr-3 whitespace-nowrap text-text-secondary font-mono">
                    {{ rec.started_at ? rec.started_at.replace('T', ' ').replace(/\.\d+Z$/, '').replace('Z', '') : rec.date_str }}
                  </td>
                  <!-- 触发方式 -->
                  <td class="py-2 pr-3 whitespace-nowrap">
                    <span
                      class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
                      :class="rec.trigger === 'scheduled' ? 'bg-blue-500/10 text-blue-400' : 'bg-purple-500/10 text-purple-400'"
                    >
                      {{ rec.trigger === 'scheduled' ? '⏰ 定时' : '▶ 手动' }}
                    </span>
                  </td>
                  <!-- 执行配置数 -->
                  <td class="py-2 pr-3 text-center whitespace-nowrap text-text-secondary">
                    {{ rec.user_count }}
                  </td>
                  <!-- 状态 -->
                  <td class="py-2 pr-3 text-center whitespace-nowrap">
                    <span
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
                      :class="rec.success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'"
                    >
                      <span class="inline-block w-1.5 h-1.5 rounded-full" :class="rec.success ? 'bg-green-400' : 'bg-red-400'"></span>
                      {{ rec.success ? '成功' : `失败 (${rec.exit_code ?? '?'})` }}
                    </span>
                  </td>
                  <!-- 耗时 -->
                  <td class="py-2 text-right whitespace-nowrap text-text-muted font-mono">
                    <template v-if="rec.started_at && rec.finished_at">
                      {{ Math.round((new Date(rec.finished_at).getTime() - new Date(rec.started_at).getTime()) / 1000 / 60) }} 分钟
                    </template>
                    <template v-else>—</template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: 数据追踪 (Pipeline Data Tracking)                       -->
      <!-- ============================================================= -->
      <AdminDataTrackingPanel v-if="activeTab === 'data-tracking'" />

      <!-- ============================================================= -->
      <!-- Page: 步骤控制 (Pipeline Step Config)                        -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'step-config'" class="flex-1 overflow-auto p-3 sm:p-6 pb-24">
        <div class="max-w-3xl mx-auto space-y-5">

          <!-- Header -->
          <div class="flex flex-wrap items-start justify-between gap-3 shrink-0">
            <div>
              <h1 class="text-lg font-bold text-text-primary">⚙️ 步骤控制</h1>
              <p class="text-xs text-text-muted mt-0.5">控制每日定时 Pipeline 中哪些步骤参与执行</p>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button
                class="px-3 py-1.5 rounded-lg border border-amber-500/40 text-xs text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 cursor-pointer transition-colors"
                @click="applyTokenSavingConfig"
              >省 Token 模式</button>
              <button
                class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary bg-bg-elevated hover:bg-bg-hover cursor-pointer transition-colors"
                @click="doResetStepConfig"
              >恢复默认</button>
            </div>
          </div>

          <!-- Info banner -->
          <div class="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300">
            此配置影响定时调度和手动触发的正常 Pipeline 运行。使用「重跑单步」功能时会忽略此配置。
            灰色关闭的步骤属于核心步骤，不可禁用。
          </div>

          <!-- Loading -->
          <div v-if="stepConfigLoading" class="flex items-center justify-center py-16 gap-2 text-text-muted">
            <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>

          <template v-else>
            <!-- Error -->
            <div v-if="stepConfigError" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400">
              {{ stepConfigError }}
            </div>

            <!-- Step groups -->
            <div
              v-for="[groupName, groupSteps] in stepsByGroup"
              :key="groupName"
              class="rounded-xl border border-border bg-bg-card overflow-hidden"
            >
              <!-- Group header -->
              <div class="px-4 py-2.5 border-b border-border bg-bg-elevated flex items-center justify-between">
                <span class="text-sm font-semibold text-text-primary">{{ groupName }}</span>
                <span class="text-xs text-text-muted">{{ enabledCountInGroup(groupSteps) }} / {{ groupSteps.length }} 启用</span>
              </div>

              <!-- Steps -->
              <div
                v-for="step in groupSteps"
                :key="step.key"
                class="px-4 py-3 border-b border-border last:border-b-0 flex items-start gap-3"
              >
                <!-- Toggle / Always-on indicator -->
                <div class="pt-0.5 shrink-0">
                  <button
                    v-if="step.can_disable"
                    class="relative inline-flex w-9 h-5 rounded-full transition-colors cursor-pointer focus:outline-none"
                    :class="stepConfig[step.key] !== false ? 'bg-blue-600' : 'bg-gray-600'"
                    @click="toggleStep(step.key)"
                    :title="stepConfig[step.key] !== false ? '点击禁用' : '点击启用'"
                  >
                    <span
                      class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform"
                      :class="stepConfig[step.key] !== false ? 'translate-x-4' : 'translate-x-0'"
                    ></span>
                  </button>
                  <span v-else class="text-[10px] text-text-muted border border-border rounded px-1 py-0.5 whitespace-nowrap">必须</span>
                </div>

                <!-- Step info -->
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span
                      class="text-sm font-medium"
                      :class="stepConfig[step.key] !== false ? 'text-text-primary' : 'text-text-muted line-through'"
                    >{{ step.label }}</span>
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      :class="costClass(step.cost_level)"
                    >{{ costLabel(step.cost_level) }}</span>
                  </div>
                  <p class="text-xs text-text-muted mt-0.5">{{ step.description }}</p>
                  <!-- Dependencies -->
                  <div v-if="step.requires.length > 0" class="flex flex-wrap gap-1 mt-1.5">
                    <span
                      v-for="req in step.requires"
                      :key="req"
                      class="text-[10px] px-1.5 py-0.5 rounded-md border"
                      :class="stepConfig[req] === false
                        ? 'border-red-500/50 text-red-400 bg-red-500/10'
                        : 'border-border text-text-muted bg-bg-elevated'"
                    >依赖: {{ defMap[req]?.label || req }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Save -->
            <div class="flex items-center justify-between gap-3">
              <p v-if="stepConfigSuccess" class="text-xs text-green-400">{{ stepConfigSuccess }}</p>
              <div v-else></div>
              <button
                class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium cursor-pointer transition-colors"
                :disabled="stepConfigSaving"
                @click="saveStepConfig"
              >{{ stepConfigSaving ? '保存中...' : '保存配置' }}</button>
            </div>
          </template>

        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: 论文推荐配置 -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'paper-recommend-config'" class="flex-1 overflow-auto p-3 sm:p-6 pb-24">
        <div class="max-w-3xl mx-auto space-y-5">
        <!-- Header -->
        <div class="flex items-center justify-between shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">⭐ 论文推荐配置</h1>
            <p class="text-xs text-text-muted mt-0.5">选好配置后，点击底部「保存所有更改」一次性应用</p>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="sysConfigSuccessMsg" class="text-xs text-green-400 flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
              {{ sysConfigSuccessMsg }}
            </span>
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="async () => { await Promise.all([loadSystemConfig(), loadLlmConfigs(), loadPromptConfigs()]); detectLlmSelections(); detectPromptSelections(); snapshotSelections(); initWordLimits(); initMineruToken(); initAdminSearchCategories() }"
            >
              🔄 刷新
            </button>
          </div>
        </div>

        <!-- Global loading / error -->
        <div v-if="configLoading" class="flex items-center justify-center py-16 text-text-muted">
          <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin mr-2"></span>
          加载中...
        </div>
        <div v-else-if="configError" class="text-red-400 text-sm py-4">{{ configError }}</div>

        <template v-else>
          <!-- 缺少配置库时的快捷入口 -->
          <div v-if="llmConfigs.length === 0 || promptConfigs.length === 0" class="flex gap-3">
            <div v-if="llmConfigs.length === 0" class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted">
              <span class="text-base shrink-0">🤖</span>
              <span class="flex-1">尚未创建任何模型配置</span>
              <button class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors shrink-0" @click="activeTab = 'llm-config'">➕ 创建模型配置</button>
            </div>
            <div v-if="promptConfigs.length === 0" class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted">
              <span class="text-base shrink-0">📝</span>
              <span class="flex-1">尚未创建任何提示词配置</span>
              <button class="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors shrink-0" @click="activeTab = 'prompt-config'">➕ 创建提示词</button>
            </div>
          </div>

          <!-- ── 全局快捷应用区 ── -->
          <div class="rounded-xl bg-blue-500/5 border border-blue-500/20 overflow-hidden">
            <div class="px-5 py-3 border-b border-blue-500/15 flex items-center gap-2">
              <span class="text-sm">⚡</span>
              <span class="text-sm font-semibold text-blue-300">全局快捷设置</span>
              <span class="text-[11px] text-text-muted ml-1">— 将同一配置批量填入所有模块，之后还可以逐项微调</span>
            </div>
            <div class="px-5 py-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <!-- 统一模型 -->
              <div class="flex items-center gap-2">
                <span class="text-xs text-text-secondary shrink-0 w-20">统一模型</span>
                <select v-model="quickFillLlmId" class="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-blue-500/50 cursor-pointer">
                  <option :value="null">— 选择模型 —</option>
                  <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
                <button
                  :disabled="!quickFillLlmId"
                  class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="applyQuickFillLlm('recommend')"
                >填入所有</button>
              </div>
              <!-- 统一提示词 -->
              <div class="flex items-center gap-2">
                <span class="text-xs text-text-secondary shrink-0 w-20">统一提示词</span>
                <select v-model="quickFillPromptId" class="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50 cursor-pointer">
                  <option :value="null">— 选择提示词 —</option>
                  <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
                <button
                  :disabled="!quickFillPromptId"
                  class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-600 hover:bg-purple-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="applyQuickFillPrompt('recommend')"
                >填入所有</button>
              </div>
            </div>
          </div>

          <!-- MinerU Token -->
          <div class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🔑</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">MinerU Token</h2>
                <p class="text-[11px] text-text-muted">用于 PDF 解析的 MinerU 服务凭证，在 mineru.net/apiManage/token 申请</p>
              </div>
            </div>
            <div class="px-5 py-4 flex items-center gap-2">
              <div class="relative flex-1">
                <input
                  v-model="mineruTokenValue"
                  :type="mineruTokenVisible ? 'text' : 'password'"
                  placeholder="请输入 MinerU Token"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors pr-10 font-mono"
                />
                <button class="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors text-xs select-none" @click="mineruTokenVisible = !mineruTokenVisible">{{ mineruTokenVisible ? '🙈' : '👁' }}</button>
              </div>
              <button :disabled="savingMineruToken" class="shrink-0 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-50" @click="handleSaveMineruToken">{{ savingMineruToken ? '保存中…' : '💾 保存' }}</button>
            </div>
          </div>

          <!-- arXiv 检索分类配置 -->
          <div class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🔍</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">arXiv 检索分类</h2>
                <p class="text-[11px] text-text-muted">系统默认从哪些 arXiv 分类中拉取论文；用户未自定义时沿用此设置</p>
              </div>
            </div>
            <div class="px-5 py-4 space-y-3">
              <!-- 快捷标签 -->
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="cat in ARXIV_COMMON_CATEGORIES"
                  :key="cat.code"
                  class="px-2.5 py-1 rounded-full text-xs font-medium border transition-colors"
                  :class="adminSearchCategories.includes(cat.code)
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-transparent border-border text-text-secondary hover:border-blue-500/50 hover:text-text-primary'"
                  @click="toggleAdminCategory(cat.code)"
                >{{ cat.code }} <span class="opacity-70">{{ cat.label }}</span></button>
              </div>
              <!-- 当前选中（含自定义）-->
              <div v-if="adminSearchCategories.length" class="flex flex-wrap gap-1.5 pt-1">
                <span
                  v-for="code in adminSearchCategories"
                  :key="code"
                  class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-blue-600/20 border border-blue-500/40 text-blue-300"
                >
                  {{ code }}
                  <button class="hover:text-red-400 transition-colors leading-none" @click="removeAdminCategory(code)">×</button>
                </span>
              </div>
              <!-- 自定义输入 -->
              <div class="flex items-center gap-2">
                <input
                  v-model="adminCategoryCustomInput"
                  placeholder="自定义分类代码，如 cs.NE"
                  class="flex-1 px-3 py-1.5 bg-bg-elevated border border-border rounded-lg text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors"
                  @keydown.enter.prevent="addAdminCustomCategory"
                />
                <button class="shrink-0 px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-xs text-text-secondary hover:border-blue-500/50 hover:text-text-primary transition-colors" @click="addAdminCustomCategory">+ 添加</button>
                <button :disabled="savingAdminCategories" class="shrink-0 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-50" @click="handleSaveAdminCategories">{{ savingAdminCategories ? '保存中…' : '💾 保存' }}</button>
              </div>
            </div>
          </div>

          <!-- 论文推荐功能模块卡片 -->
          <div
            v-for="mod in recommendConfigModules"
            :key="mod.key"
            class="rounded-xl bg-bg-card border border-border overflow-hidden"
          >
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h2>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>
            <div class="divide-y divide-border/50">
              <!-- LLM row -->
              <div v-if="mod.llmPrefix" class="px-5 py-3 flex items-center gap-3">
                <!-- dirty indicator -->
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0 transition-colors"
                  :class="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? 'bg-amber-400' : 'bg-transparent'"
                  :title="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? '已修改，待保存' : ''"
                ></span>
                <div class="w-28 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">调用模型</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="selectedLlmConfigIds[mod.llmPrefix]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ llmConfigs.find(c => c.id === selectedLlmConfigIds[mod.llmPrefix])?.name || '—' }}</span>
                    <span class="text-text-muted truncate">· {{ configValues[prefixModelKey[mod.llmPrefix]] }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">{{ llmConfigs.length === 0 ? '暂无模型配置' : '未配置' }}</div>
                </div>
                <select
                  v-model="selectedLlmConfigIds[mod.llmPrefix]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border text-text-primary text-xs focus:outline-none focus:ring-1 cursor-pointer transition-colors"
                  :class="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? 'border-amber-500/60 focus:ring-amber-500/40' : 'border-border focus:ring-blue-500/50'"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
              </div>
              <!-- Prompt rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.variable" class="px-5 py-3 flex items-center gap-3">
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0 transition-colors"
                  :class="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? 'bg-amber-400' : 'bg-transparent'"
                  :title="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? '已修改，待保存' : ''"
                ></span>
                <div class="w-28 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary truncate">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="selectedPromptConfigIds[prompt.variable]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ promptConfigs.find(c => c.id === selectedPromptConfigIds[prompt.variable])?.name || '—' }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">{{ promptConfigs.length === 0 ? '暂无提示词配置' : '未配置' }}</div>
                </div>
                <select
                  v-model="selectedPromptConfigIds[prompt.variable]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border text-text-primary text-xs focus:outline-none focus:ring-1 cursor-pointer transition-colors"
                  :class="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? 'border-amber-500/60 focus:ring-amber-500/40' : 'border-border focus:ring-purple-500/50'"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 字数上限配置 -->
          <div class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <span class="text-base leading-none">📏</span>
                <div>
                  <h2 class="text-sm font-semibold text-text-primary">字数上限配置</h2>
                  <p class="text-[11px] text-text-muted">控制摘要各部分的字数上限（按去空白字符计），超出则调用模型压缩</p>
                </div>
              </div>
              <button :disabled="savingWordLimits" class="px-4 py-1.5 rounded-lg bg-green-600 hover:bg-green-500 text-white text-xs font-medium transition-colors disabled:opacity-50 shrink-0" @click="handleSaveWordLimits">{{ savingWordLimits ? '保存中...' : '💾 保存' }}</button>
            </div>
            <div class="p-5">
              <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                <div v-for="(defaultVal, key) in wordLimitDefaults" :key="key">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">{{ wordLimitLabels[key] }}</label>
                  <div class="flex items-center gap-1.5">
                    <input v-model.number="wordLimitValues[key]" type="number" step="10" min="10" class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors" />
                    <button v-if="wordLimitValues[key] !== defaultVal" class="shrink-0 px-2 py-1.5 rounded text-[11px] border border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors" title="重置为默认值" @click="wordLimitValues[key] = defaultVal">↺</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaultVal }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
        </div><!-- /max-w-3xl -->

        <!-- ── 底部 Sticky 保存栏 ── -->
        <div class="fixed bottom-0 left-0 lg:left-[var(--settings-sidebar-w)] right-0 z-20 pointer-events-none">
          <div class="max-w-3xl mx-auto px-3 sm:px-6 pb-4 pointer-events-auto">
            <transition name="slide-up">
              <div
                v-if="!configLoading && !configError"
                class="flex items-center justify-between gap-4 px-5 py-3.5 rounded-2xl border shadow-lg backdrop-blur-md transition-all"
                :class="recommendDirtyCount > 0 ? 'bg-bg-card/95 border-amber-500/40 shadow-amber-500/10' : 'bg-bg-card/80 border-border/60 shadow-black/20'"
              >
                <div class="flex items-center gap-2.5 text-sm">
                  <span v-if="recommendDirtyCount > 0" class="flex items-center gap-1.5 text-amber-400 font-medium">
                    <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0"></span>
                    {{ recommendDirtyCount }} 项待保存
                  </span>
                  <span v-else class="text-text-muted text-xs">所有配置已是最新</span>
                </div>
                <button
                  :disabled="batchSaving && batchSaveScope === 'recommend'"
                  class="shrink-0 px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
                  :class="recommendDirtyCount > 0 ? 'bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-600/30' : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover'"
                  @click="handleBatchSave('recommend')"
                >
                  {{ batchSaving && batchSaveScope === 'recommend' ? '保存中…' : '💾 保存所有更改' }}
                </button>
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: 灵感生成配置 -->
      <!-- ============================================================= -->
      <div v-else-if="activeTab === 'idea-generate-config'" class="flex-1 overflow-auto p-3 sm:p-6 pb-24">
        <div class="max-w-3xl mx-auto space-y-5">
        <!-- Header -->
        <div class="flex items-center justify-between shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">💡 灵感生成配置</h1>
            <p class="text-xs text-text-muted mt-0.5">选好配置后，点击底部「保存所有更改」一次性应用</p>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="sysConfigSuccessMsg" class="text-xs text-green-400 flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
              {{ sysConfigSuccessMsg }}
            </span>
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="async () => { await Promise.all([loadSystemConfig(), loadLlmConfigs(), loadPromptConfigs()]); detectLlmSelections(); detectPromptSelections(); snapshotSelections() }"
            >
              🔄 刷新
            </button>
          </div>
        </div>

        <!-- Global loading / error -->
        <div v-if="configLoading" class="flex items-center justify-center py-16 text-text-muted">
          <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin mr-2"></span>
          加载中...
        </div>
        <div v-else-if="configError" class="text-red-400 text-sm py-4">{{ configError }}</div>

        <template v-else>
          <!-- 缺少配置库时的快捷入口 -->
          <div v-if="llmConfigs.length === 0 || promptConfigs.length === 0" class="flex gap-3">
            <div v-if="llmConfigs.length === 0" class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted">
              <span class="text-base shrink-0">🤖</span>
              <span class="flex-1">尚未创建任何模型配置</span>
              <button class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors shrink-0" @click="activeTab = 'llm-config'">➕ 创建模型配置</button>
            </div>
            <div v-if="promptConfigs.length === 0" class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted">
              <span class="text-base shrink-0">📝</span>
              <span class="flex-1">尚未创建任何提示词配置</span>
              <button class="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors shrink-0" @click="activeTab = 'prompt-config'">➕ 创建提示词</button>
            </div>
          </div>

          <!-- ── 全局快捷应用区 ── -->
          <div class="rounded-xl bg-orange-500/5 border border-orange-500/20 overflow-hidden">
            <div class="px-5 py-3 border-b border-orange-500/15 flex items-center gap-2">
              <span class="text-sm">⚡</span>
              <span class="text-sm font-semibold text-orange-300">全局快捷设置</span>
              <span class="text-[11px] text-text-muted ml-1">— 将同一配置批量填入所有阶段，之后还可以逐项微调</span>
            </div>
            <div class="px-5 py-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <!-- 统一模型 -->
              <div class="flex items-center gap-2">
                <span class="text-xs text-text-secondary shrink-0 w-20">统一模型</span>
                <select v-model="quickFillLlmId" class="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-orange-500/50 cursor-pointer">
                  <option :value="null">— 选择模型 —</option>
                  <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
                <button
                  :disabled="!quickFillLlmId"
                  class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-orange-600 hover:bg-orange-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="applyQuickFillLlm('idea')"
                >填入所有</button>
              </div>
              <!-- 统一提示词 -->
              <div class="flex items-center gap-2">
                <span class="text-xs text-text-secondary shrink-0 w-20">统一提示词</span>
                <select v-model="quickFillPromptId" class="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-orange-400/50 cursor-pointer">
                  <option :value="null">— 选择提示词 —</option>
                  <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
                <button
                  :disabled="!quickFillPromptId"
                  class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-orange-500 hover:bg-orange-400 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="applyQuickFillPrompt('idea')"
                >填入所有</button>
              </div>
            </div>
          </div>

          <!-- 灵感生成功能模块卡片 -->
          <div
            v-for="mod in ideaConfigModules"
            :key="mod.key"
            class="rounded-xl bg-bg-card border border-border overflow-hidden"
          >
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h2>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>
            <div class="divide-y divide-border/50">
              <!-- LLM row -->
              <div v-if="mod.llmPrefix" class="px-5 py-3 flex items-center gap-3">
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0 transition-colors"
                  :class="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? 'bg-amber-400' : 'bg-transparent'"
                  :title="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? '已修改，待保存' : ''"
                ></span>
                <div class="w-28 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">调用模型</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="selectedLlmConfigIds[mod.llmPrefix]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ llmConfigs.find(c => c.id === selectedLlmConfigIds[mod.llmPrefix])?.name || '—' }}</span>
                    <span class="text-text-muted truncate">· {{ configValues[prefixModelKey[mod.llmPrefix]] }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">{{ llmConfigs.length === 0 ? '暂无模型配置' : '未配置' }}</div>
                </div>
                <select
                  v-model="selectedLlmConfigIds[mod.llmPrefix]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border text-text-primary text-xs focus:outline-none focus:ring-1 cursor-pointer transition-colors"
                  :class="selectedLlmConfigIds[mod.llmPrefix] !== originalLlmConfigIds[mod.llmPrefix] ? 'border-amber-500/60 focus:ring-amber-500/40' : 'border-border focus:ring-orange-500/50'"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
              </div>
              <!-- Prompt rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.variable" class="px-5 py-3 flex items-center gap-3">
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0 transition-colors"
                  :class="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? 'bg-amber-400' : 'bg-transparent'"
                  :title="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? '已修改，待保存' : ''"
                ></span>
                <div class="w-28 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary truncate">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div v-if="selectedPromptConfigIds[prompt.variable]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ promptConfigs.find(c => c.id === selectedPromptConfigIds[prompt.variable])?.name || '—' }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">{{ promptConfigs.length === 0 ? '暂无提示词配置' : '未配置' }}</div>
                </div>
                <select
                  v-model="selectedPromptConfigIds[prompt.variable]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border text-text-primary text-xs focus:outline-none focus:ring-1 cursor-pointer transition-colors"
                  :class="selectedPromptConfigIds[prompt.variable] !== originalPromptConfigIds[prompt.variable] ? 'border-amber-500/60 focus:ring-amber-500/40' : 'border-border focus:ring-orange-500/50'"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>
              </div>
            </div>
          </div>
        </template>
        </div><!-- /max-w-3xl -->

        <!-- ── 底部 Sticky 保存栏 ── -->
        <div class="fixed bottom-0 left-0 lg:left-[var(--settings-sidebar-w)] right-0 z-20 pointer-events-none">
          <div class="max-w-3xl mx-auto px-3 sm:px-6 pb-4 pointer-events-auto">
            <transition name="slide-up">
              <div
                v-if="!configLoading && !configError"
                class="flex items-center justify-between gap-4 px-5 py-3.5 rounded-2xl border shadow-lg backdrop-blur-md transition-all"
                :class="ideaDirtyCount > 0 ? 'bg-bg-card/95 border-amber-500/40 shadow-amber-500/10' : 'bg-bg-card/80 border-border/60 shadow-black/20'"
              >
                <div class="flex items-center gap-2.5 text-sm">
                  <span v-if="ideaDirtyCount > 0" class="flex items-center gap-1.5 text-amber-400 font-medium">
                    <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0"></span>
                    {{ ideaDirtyCount }} 项待保存
                  </span>
                  <span v-else class="text-text-muted text-xs">所有配置已是最新</span>
                </div>
                <button
                  :disabled="batchSaving && batchSaveScope === 'idea'"
                  class="shrink-0 px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
                  :class="ideaDirtyCount > 0 ? 'bg-orange-600 hover:bg-orange-500 shadow-md shadow-orange-600/30' : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover'"
                  @click="handleBatchSave('idea')"
                >
                  {{ batchSaving && batchSaveScope === 'idea' ? '保存中…' : '💾 保存所有更改' }}
                </button>
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: AI 功能默认配置                                        -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'feature-defaults-config'" class="flex-1 overflow-auto p-3 sm:p-6 pb-24">
        <div class="max-w-3xl mx-auto space-y-5">

          <!-- Header -->
          <div class="flex items-center justify-between shrink-0">
            <div>
              <h1 class="text-lg font-bold text-text-primary">🎛️ AI 功能默认配置</h1>
              <p class="text-xs text-text-muted mt-0.5">管理问答、对比分析、深度研究等功能的全局默认参数，无需改代码</p>
            </div>
            <div class="flex items-center gap-3">
              <span v-if="featureDefaultsSuccessMsg" class="text-xs text-green-400 flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                {{ featureDefaultsSuccessMsg }}
              </span>
              <button
                class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
                @click="loadFeatureDefaults"
              >🔄 刷新</button>
            </div>
          </div>

          <!-- Loading / Error -->
          <div v-if="featureDefaultsLoading" class="flex items-center justify-center py-16 text-text-muted">
            <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin mr-2"></span>
            加载中...
          </div>
          <div v-else-if="featureDefaultsError" class="text-red-400 text-sm py-4">{{ featureDefaultsError }}</div>

          <template v-else>
            <!-- 说明横幅 -->
            <div class="rounded-xl bg-blue-500/5 border border-blue-500/20 px-5 py-3.5 flex items-start gap-3">
              <span class="text-base shrink-0 mt-0.5">ℹ️</span>
              <p class="text-xs text-blue-200/80 leading-relaxed">
                这里配置的是<strong class="text-blue-300">全局默认值</strong>——当用户未自行设置时生效。用户个人设置优先级更高，不受此处影响。
                每个功能卡片右上角可「恢复内置默认」，修改后点击底部「保存」生效。
              </p>
            </div>

            <!-- Feature Cards -->
            <div
              v-for="meta in FEATURE_DEFAULTS_META"
              :key="meta.feature"
              class="rounded-xl bg-bg-card border overflow-hidden transition-colors"
              :class="isFeatureDefaultsDirty(meta.feature) ? 'border-amber-500/40' : 'border-border'"
            >
              <!-- Card Header -->
              <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
                <span class="text-base leading-none">{{ meta.icon }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <h2 class="text-sm font-semibold text-text-primary">{{ meta.label }}</h2>
                    <span
                      v-if="featureDefaultsData.find(e => e.feature === meta.feature)?.has_admin_overrides"
                      class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30"
                    >已自定义</span>
                    <span
                      v-if="isFeatureDefaultsDirty(meta.feature)"
                      class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30 animate-pulse"
                    >待保存</span>
                  </div>
                  <p class="text-[11px] text-text-muted">{{ meta.desc }}</p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <button
                    v-if="featureDefaultsData.find(e => e.feature === meta.feature)?.has_admin_overrides"
                    :disabled="featureDefaultsResetting === meta.feature"
                    class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary hover:border-red-500/50 hover:text-red-400 transition-colors disabled:opacity-50"
                    @click="handleResetFeatureDefaults(meta.feature)"
                  >{{ featureDefaultsResetting === meta.feature ? '重置中…' : '↺ 恢复内置默认' }}</button>
                  <button
                    :disabled="featureDefaultsSaving === meta.feature || !isFeatureDefaultsDirty(meta.feature)"
                    class="px-4 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    :class="isFeatureDefaultsDirty(meta.feature) ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-bg-elevated text-text-muted border border-border'"
                    @click="handleSaveFeatureDefaults(meta.feature)"
                  >{{ featureDefaultsSaving === meta.feature ? '保存中…' : '💾 保存' }}</button>
                </div>
              </div>

              <!-- Fields -->
              <div class="p-5 space-y-4" v-if="featureDefaultsEdits[meta.feature]">

                <!-- LLM Config Selection -->
                <div>
                  <h3 class="text-xs font-semibold text-text-secondary mb-3 flex items-center gap-1.5">
                    <span>🤖</span> 默认调用模型
                  </h3>
                  <div class="flex items-center gap-3">
                    <!-- dirty indicator -->
                    <span
                      class="w-1.5 h-1.5 rounded-full shrink-0 transition-colors"
                      :class="featureDefaultsEdits[meta.feature]['admin_llm_config_id'] !== featureDefaultsSnapshot[meta.feature]?.['admin_llm_config_id'] ? 'bg-amber-400' : 'bg-transparent'"
                    ></span>
                    <div class="flex-1 min-w-0">
                      <div v-if="featureDefaultsEdits[meta.feature]['admin_llm_config_id']" class="flex items-center gap-1.5 text-xs mb-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0"></span>
                        <span class="font-medium text-text-secondary">
                          {{ llmConfigs.find(c => c.id === featureDefaultsEdits[meta.feature]['admin_llm_config_id'])?.name || '—' }}
                        </span>
                        <span class="text-text-muted truncate">
                          · {{ llmConfigs.find(c => c.id === featureDefaultsEdits[meta.feature]['admin_llm_config_id'])?.model || '' }}
                        </span>
                      </div>
                      <div v-else class="text-[11px] text-text-muted italic mb-1.5">
                        未指定（将使用系统全局兜底模型）
                      </div>
                    </div>
                    <select
                      v-model="featureDefaultsEdits[meta.feature]['admin_llm_config_id']"
                      class="w-44 px-2.5 py-1.5 rounded-lg bg-bg-elevated border text-text-primary text-xs focus:outline-none focus:ring-1 cursor-pointer transition-colors"
                      :class="featureDefaultsEdits[meta.feature]['admin_llm_config_id'] !== featureDefaultsSnapshot[meta.feature]?.['admin_llm_config_id'] ? 'border-amber-500/60 focus:ring-amber-500/40' : 'border-border focus:ring-blue-500/50'"
                    >
                      <option :value="null">— 不指定（全局兜底）—</option>
                      <option :value="undefined">— 不指定（全局兜底）—</option>
                      <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                    </select>
                    <button
                      v-if="featureDefaultsEdits[meta.feature]['admin_llm_config_id']"
                      class="shrink-0 px-2.5 py-1.5 rounded-lg border border-border text-[11px] text-text-muted hover:text-red-400 hover:border-red-500/50 transition-colors"
                      @click="featureDefaultsEdits[meta.feature]['admin_llm_config_id'] = null"
                    >✕ 清除</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-1.5 ml-4">
                    当用户未配置自己的模型时，优先使用此处指定的模型；未指定则 fallback 到系统全局配置
                  </p>
                </div>

                <!-- Numeric params row -->
                <div>
                  <h3 class="text-xs font-semibold text-text-secondary mb-3 flex items-center gap-1.5">
                    <span>⚙️</span> 模型参数
                  </h3>
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div v-for="field in meta.editableFields" :key="field">
                      <label class="block text-[11px] font-medium text-text-secondary mb-1">
                        {{ { temperature: '温度 (temperature)', max_tokens: '最大 Tokens', input_hard_limit: '输入硬上限', input_safety_margin: '安全边距' }[field] || field }}
                      </label>
                      <input
                        v-model.number="featureDefaultsEdits[meta.feature][field]"
                        type="number"
                        :step="field === 'temperature' ? 0.05 : 128"
                        :min="field === 'temperature' ? 0 : 0"
                        :max="field === 'temperature' ? 2 : undefined"
                        class="w-full px-3 py-2 bg-bg-elevated border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors"
                        :class="featureDefaultsEdits[meta.feature][field] !== featureDefaultsSnapshot[meta.feature]?.[field] ? 'border-amber-500/60' : 'border-border'"
                      />
                      <p class="text-[10px] text-text-muted mt-0.5">
                        默认: {{ featureDefaultsData.find(e => e.feature === meta.feature)?.hardcoded_defaults?.[field] }}
                      </p>
                    </div>
                  </div>
                </div>

                <!-- Special fields (selects / extra numbers) -->
                <div v-if="meta.specialFields && meta.specialFields.length">
                  <h3 class="text-xs font-semibold text-text-secondary mb-3 flex items-center gap-1.5">
                    <span>🔧</span> 功能特有设置
                  </h3>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div v-for="sf in meta.specialFields" :key="sf.key">
                      <label class="block text-[11px] font-medium text-text-secondary mb-1">{{ sf.label }}</label>
                      <select
                        v-if="sf.type === 'select'"
                        v-model="featureDefaultsEdits[meta.feature][sf.key]"
                        class="w-full px-3 py-2 bg-bg-elevated border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors cursor-pointer"
                        :class="featureDefaultsEdits[meta.feature][sf.key] !== featureDefaultsSnapshot[meta.feature]?.[sf.key] ? 'border-amber-500/60' : 'border-border'"
                      >
                        <option v-for="opt in sf.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                      </select>
                      <input
                        v-else-if="sf.type === 'number'"
                        v-model.number="featureDefaultsEdits[meta.feature][sf.key]"
                        type="number"
                        min="1"
                        class="w-full px-3 py-2 bg-bg-elevated border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors"
                        :class="featureDefaultsEdits[meta.feature][sf.key] !== featureDefaultsSnapshot[meta.feature]?.[sf.key] ? 'border-amber-500/60' : 'border-border'"
                      />
                      <p class="text-[10px] text-text-muted mt-0.5">
                        默认: {{ featureDefaultsData.find(e => e.feature === meta.feature)?.hardcoded_defaults?.[sf.key] }}
                      </p>
                    </div>
                  </div>
                </div>

                <!-- Prompt fields -->
                <div v-if="meta.promptFields.length">
                  <h3 class="text-xs font-semibold text-text-secondary mb-3 flex items-center gap-1.5">
                    <span>📝</span> 系统提示词
                  </h3>
                  <div class="space-y-3">
                    <div v-for="pf in meta.promptFields" :key="pf.key" class="rounded-lg border overflow-hidden transition-colors"
                      :class="featureDefaultsEdits[meta.feature][pf.key] !== featureDefaultsSnapshot[meta.feature]?.[pf.key] ? 'border-amber-500/40' : 'border-border'"
                    >
                      <!-- Prompt header -->
                      <button
                        class="w-full flex items-center justify-between px-4 py-2.5 bg-bg-elevated/50 hover:bg-bg-elevated transition-colors text-left"
                        @click="featurePromptExpanded[_featurePromptKey(meta.feature, pf.key)] = !featurePromptExpanded[_featurePromptKey(meta.feature, pf.key)]"
                      >
                        <span class="text-xs font-medium text-text-secondary">{{ pf.label }}</span>
                        <div class="flex items-center gap-2">
                          <span
                            v-if="featureDefaultsEdits[meta.feature][pf.key] !== featureDefaultsSnapshot[meta.feature]?.[pf.key]"
                            class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"
                          ></span>
                          <span class="text-text-muted text-xs">{{ featurePromptExpanded[_featurePromptKey(meta.feature, pf.key)] ? '▲ 收起' : '▼ 展开' }}</span>
                        </div>
                      </button>
                      <!-- Prompt textarea -->
                      <div v-show="featurePromptExpanded[_featurePromptKey(meta.feature, pf.key)]" class="px-4 pb-4 pt-2">
                        <textarea
                          v-model="featureDefaultsEdits[meta.feature][pf.key]"
                          rows="10"
                          class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-xs text-text-primary font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors resize-y"
                          placeholder="留空则使用内置默认提示词"
                        ></textarea>
                        <div class="flex items-center justify-between mt-2">
                          <p class="text-[10px] text-text-muted">{{ (featureDefaultsEdits[meta.feature][pf.key] || '').length }} 字符</p>
                          <button
                            class="text-[10px] text-text-muted hover:text-text-secondary transition-colors"
                            @click="featureDefaultsEdits[meta.feature][pf.key] = featureDefaultsData.find(e => e.feature === meta.feature)?.hardcoded_defaults?.[pf.key] || ''"
                          >↺ 恢复该字段默认</button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </template>

        </div><!-- /max-w-3xl -->

        <!-- 底部 Sticky 保存栏 -->
        <div class="fixed bottom-0 left-0 lg:left-[var(--settings-sidebar-w)] right-0 z-20 pointer-events-none">
          <div class="max-w-3xl mx-auto px-3 sm:px-6 pb-4 pointer-events-auto">
            <transition name="slide-up">
              <div
                v-if="!featureDefaultsLoading && !featureDefaultsError"
                class="flex items-center justify-between gap-4 px-5 py-3.5 rounded-2xl border shadow-lg backdrop-blur-md transition-all"
                :class="featureDefaultsDirtyCount > 0 ? 'bg-bg-card/95 border-amber-500/40 shadow-amber-500/10' : 'bg-bg-card/80 border-border/60 shadow-black/20'"
              >
                <div class="flex items-center gap-2.5 text-sm">
                  <span v-if="featureDefaultsDirtyCount > 0" class="flex items-center gap-1.5 text-amber-400 font-medium">
                    <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0"></span>
                    {{ featureDefaultsDirtyCount }} 个功能有未保存的修改
                  </span>
                  <span v-else class="text-text-muted text-xs">所有功能默认配置已保存</span>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    v-for="meta in FEATURE_DEFAULTS_META.filter(m => isFeatureDefaultsDirty(m.feature))"
                    :key="meta.feature"
                    :disabled="featureDefaultsSaving === meta.feature"
                    class="shrink-0 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 shadow-md shadow-blue-600/30 transition-all disabled:opacity-60"
                    @click="handleSaveFeatureDefaults(meta.feature)"
                  >
                    {{ featureDefaultsSaving === meta.feature ? '保存中…' : `保存 ${meta.label}` }}
                  </button>
                </div>
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: LLM Config Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'llm-config'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">🤖 模型配置管理</h1>
            <p class="text-xs text-text-muted mt-0.5">管理大模型配置，支持应用到不同功能模块</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="loadLlmConfigs"
            >
              🔄 刷新
            </button>
            <button
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
              @click="startEditLlmConfig()"
            >
              ➕ 新建配置
            </button>
          </div>
        </div>

        <!-- OpenRouter Key Pool Card -->
        <div class="rounded-xl bg-bg-card border border-border shrink-0">
          <button
            class="w-full flex items-center justify-between px-4 py-3 text-left"
            @click="keyPoolExpanded = !keyPoolExpanded; if (keyPoolExpanded && !keyPoolStatus) loadKeyPool()"
          >
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-text-primary">🔑 OpenRouter 免费 Key 池</span>
              <span v-if="keyPoolStatus" class="px-2 py-0.5 rounded-full text-[10px]" :class="keyPoolStatus.available_keys > 0 ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'">
                {{ keyPoolStatus.available_keys }}/{{ keyPoolStatus.total_keys }} 可用
              </span>
              <span v-else-if="keyPoolLoading" class="text-xs text-text-muted">加载中...</span>
            </div>
            <span class="text-text-muted text-xs">{{ keyPoolExpanded ? '▲ 收起' : '▼ 展开管理' }}</span>
          </button>
          <div v-if="keyPoolExpanded" class="px-4 pb-4 border-t border-border">
            <div v-if="keyPoolLoading" class="py-4 text-center text-text-muted text-sm">加载中...</div>
            <template v-else>
              <div v-if="keyPoolStatus && keyPoolStatus.total_keys > 0" class="mt-3 mb-3">
                <div class="text-xs text-text-muted mb-2">当前 {{ keyPoolStatus.total_keys }} 个 Key，每日限额 {{ keyPoolStatus.daily_limit }} 次 / Key</div>
                <div class="flex flex-wrap gap-2">
                  <div v-for="k in keyPoolStatus.keys" :key="k.id" class="flex items-center gap-1.5 px-2 py-1 rounded bg-bg-elevated border border-border text-xs font-mono">
                    <span class="text-text-secondary">{{ k.masked_key }}</span>
                    <span :class="k.remaining_today > 0 ? 'text-green-400' : 'text-red-400'">
                      {{ k.remaining_today }}/{{ keyPoolStatus.daily_limit }}
                    </span>
                  </div>
                </div>
              </div>
              <div v-else-if="keyPoolStatus" class="mt-3 mb-2 text-xs text-text-muted">暂无 Key，请在下方填入</div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <div class="col-span-2">
                  <label class="block text-xs text-text-muted mb-1">新 Keys（每行一个，保存后全量替换）</label>
                  <textarea
                    v-model="keyPoolKeysText"
                    rows="4"
                    placeholder="sk-or-v1-xxx&#10;sk-or-v1-yyy"
                    class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs font-mono resize-y"
                  ></textarea>
                </div>
                <div>
                  <label class="block text-xs text-text-muted mb-1">每日每 Key 调用上限</label>
                  <input v-model.number="keyPoolDailyLimit" type="number" min="1" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
                </div>
              </div>
              <div class="flex items-center gap-2 mt-3">
                <button
                  :disabled="keyPoolSaving"
                  class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium disabled:opacity-50"
                  @click="saveKeyPool"
                >
                  {{ keyPoolSaving ? '保存中...' : '💾 保存 Key 池' }}
                </button>
                <button class="px-3 py-1.5 rounded-lg border border-border text-text-secondary text-xs hover:bg-bg-hover" @click="loadKeyPool">
                  🔄 刷新状态
                </button>
              </div>
              <p v-if="keyPoolError" class="mt-2 text-xs text-red-400">{{ keyPoolError }}</p>
            </template>
          </div>
        </div>

        <div v-if="llmConfigLoading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="llmConfigError" class="flex-1 flex items-center justify-center text-red-400">{{ llmConfigError }}</div>

        <!-- Edit Form -->
        <div v-if="llmConfigEditing !== null || Object.keys(llmConfigForm).length > 0" class="rounded-xl bg-bg-card border border-border p-5 shrink-0">
          <h2 class="text-sm font-semibold text-text-primary mb-4">{{ llmConfigEditing?.id ? '编辑配置' : '新建配置' }}</h2>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-text-muted mb-1">配置名称 *</label>
              <input v-model="llmConfigForm.name" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">备注</label>
              <input v-model="llmConfigForm.remark" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">
                Base URL
                <span v-if="!llmConfigForm.use_openrouter_free_pool"> *</span>
                <span v-else class="text-green-400 ml-1">（池模式自动填充）</span>
              </label>
              <input v-model="llmConfigForm.base_url" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">
                API Key
                <span v-if="!llmConfigForm.use_openrouter_free_pool"> *</span>
                <span v-else class="text-green-400 ml-1">（使用 Key 池，可留空）</span>
              </label>
              <input v-model="llmConfigForm.api_key" type="password" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono" />
            </div>
            <div class="col-span-2">
              <div class="flex items-center justify-between mb-1">
                <label class="text-xs text-text-muted">Model *</label>
                <button
                  type="button"
                  :disabled="freeModelsLoading"
                  class="px-2 py-0.5 rounded text-[11px] border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-50"
                  @click="loadFreeModels"
                >
                  {{ freeModelsLoading ? '获取中...' : '📋 获取免费模型列表' }}
                </button>
              </div>
              <input v-model="llmConfigForm.model" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
              <div v-if="freeModelsExpanded && freeModels.length > 0" class="mt-1 max-h-52 overflow-y-auto rounded-lg bg-bg-elevated border border-border divide-y divide-border/50">
                <button
                  v-for="m in freeModels"
                  :key="m.id"
                  type="button"
                  class="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-bg-hover transition-colors"
                  @click="pickFreeModel(m)"
                >
                  <span class="text-xs text-text-primary truncate">{{ m.name || m.id }}</span>
                  <span class="text-[10px] text-text-muted font-mono ml-2 shrink-0">{{ m.context_length ? m.context_length.toLocaleString() + ' ctx' : '' }}</span>
                </button>
              </div>
              <button v-if="freeModelsExpanded" type="button" class="mt-1 text-[11px] text-text-muted hover:text-text-secondary" @click="freeModelsExpanded = false">收起列表</button>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Max Tokens</label>
              <input v-model.number="llmConfigForm.max_tokens" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Temperature</label>
              <input v-model.number="llmConfigForm.temperature" type="number" step="0.1" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Concurrency</label>
              <input v-model.number="llmConfigForm.concurrency" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Input Hard Limit</label>
              <input v-model.number="llmConfigForm.input_hard_limit" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Input Safety Margin</label>
              <input v-model.number="llmConfigForm.input_safety_margin" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div class="flex items-center justify-between rounded-lg bg-bg-elevated border border-border px-3 py-2">
              <div>
                <label class="block text-xs text-text-muted">思考模式</label>
                <p class="text-[11px] text-text-muted/70 mt-0.5">是否生效取决于模型/服务商支持</p>
              </div>
              <button
                type="button"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                :class="llmConfigForm.enable_thinking ? 'bg-blue-600' : 'bg-bg-hover border border-border'"
                @click="llmConfigForm.enable_thinking = !llmConfigForm.enable_thinking"
              >
                <span
                  class="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform"
                  :class="llmConfigForm.enable_thinking ? 'translate-x-6' : 'translate-x-1'"
                ></span>
              </button>
            </div>
            <!-- OpenRouter Free Key Pool toggle -->
            <div class="flex items-center justify-between py-2 px-3 rounded-lg bg-bg-elevated border border-border">
              <div>
                <p class="text-sm font-medium text-text-primary">使用 OpenRouter 免费 Key 池</p>
                <p class="text-xs text-text-muted mt-0.5">启用后运行时自动轮换，API Key 可留空</p>
              </div>
              <button type="button"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors ml-3 shrink-0"
                :class="llmConfigForm.use_openrouter_free_pool ? 'bg-green-600' : 'bg-bg-hover border border-border'"
                @click="llmConfigForm.use_openrouter_free_pool = !llmConfigForm.use_openrouter_free_pool"
              >
                <span class="inline-block h-4 w-4 rounded-full bg-white shadow transition-transform"
                  :class="llmConfigForm.use_openrouter_free_pool ? 'translate-x-6' : 'translate-x-1'" />
              </button>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Endpoint</label>
              <input v-model="llmConfigForm.endpoint" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Completion Window</label>
              <input v-model="llmConfigForm.completion_window" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Out Root</label>
              <input v-model="llmConfigForm.out_root" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">JSONL Root</label>
              <input v-model="llmConfigForm.jsonl_root" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
          </div>
          <div class="flex items-center gap-2 mt-4">
            <button
              :disabled="llmConfigSaving"
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
              @click="saveLlmConfig"
            >
              {{ llmConfigSaving ? '保存中...' : '💾 保存' }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-text-secondary text-sm font-medium hover:bg-bg-hover"
              @click="llmConfigEditing = null; llmConfigForm = {}"
            >
              取消
            </button>
          </div>
        </div>

        <!-- Config List -->
        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">名称</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">Base URL</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">Model</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="config in llmConfigs" :key="config.id" class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors">
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ config.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">
                  <div class="flex items-center gap-2">
                    <span>{{ config.name }}</span>
                    <span v-if="config.enable_thinking" class="px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400 text-[10px] font-medium">思考</span>
                    <span v-if="config.use_openrouter_free_pool" class="px-1.5 py-0.5 rounded bg-green-500/15 text-green-400 text-[10px] font-medium">Key池</span>
                  </div>
                </td>
                <td class="px-4 py-3 text-text-secondary text-xs font-mono truncate max-w-[200px]">{{ config.base_url }}</td>
                <td class="px-4 py-3 text-text-secondary text-xs">{{ config.model }}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <select
                      :disabled="llmConfigApplying === config.id"
                      class="px-2 py-1 rounded bg-bg-elevated border border-border text-text-primary text-xs"
                      @change="applyLlmConfigHandler(config.id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">应用到...</option>
                      <option v-for="opt in usagePrefixOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                    </select>
                    <button
                      class="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs hover:bg-blue-500/30"
                      @click="startEditLlmConfig(config)"
                    >
                      编辑
                    </button>
                    <button
                      class="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs hover:bg-red-500/30"
                      @click="deleteLlmConfigHandler(config.id)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="llmConfigs.length === 0">
                <td colspan="5" class="px-4 py-10 text-center text-text-muted">暂无配置</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Prompt Config Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'prompt-config'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">📝 提示词配置管理</h1>
            <p class="text-xs text-text-muted mt-0.5">管理提示词配置，支持应用到不同功能模块</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="loadPromptConfigs"
            >
              🔄 刷新
            </button>
            <button
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
              @click="startEditPromptConfig()"
            >
              ➕ 新建配置
            </button>
          </div>
        </div>

        <div v-if="promptConfigLoading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="promptConfigError" class="flex-1 flex items-center justify-center text-red-400">{{ promptConfigError }}</div>

        <!-- Edit Form -->
        <div v-if="promptConfigEditing !== null || Object.keys(promptConfigForm).length > 0" class="rounded-xl bg-bg-card border border-border p-5 shrink-0">
          <h2 class="text-sm font-semibold text-text-primary mb-4">{{ promptConfigEditing?.id ? '编辑配置' : '新建配置' }}</h2>
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-xs text-text-muted mb-1">配置名称 *</label>
              <input v-model="promptConfigForm.name" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">备注</label>
              <input v-model="promptConfigForm.remark" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
          </div>
          <div>
            <label class="block text-xs text-text-muted mb-1">提示词内容 *</label>
            <textarea
              v-model="promptConfigForm.prompt_content"
              class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono resize-y min-h-[200px]"
            />
          </div>
          <div class="flex items-center gap-2 mt-4">
            <button
              :disabled="promptConfigSaving"
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
              @click="savePromptConfig"
            >
              {{ promptConfigSaving ? '保存中...' : '💾 保存' }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-text-secondary text-sm font-medium hover:bg-bg-hover"
              @click="promptConfigEditing = null; promptConfigForm = {}"
            >
              取消
            </button>
          </div>
        </div>

        <!-- Config List -->
        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">名称</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">内容预览</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="config in promptConfigs" :key="config.id" class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors">
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ config.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">{{ config.name }}</td>
                <td class="px-4 py-3 text-text-secondary text-xs max-w-[300px] truncate">{{ config.prompt_content.substring(0, 100) }}{{ config.prompt_content.length > 100 ? '...' : '' }}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <select
                      :disabled="promptConfigApplying === config.id"
                      class="px-2 py-1 rounded bg-bg-elevated border border-border text-text-primary text-xs"
                      @change="applyPromptConfigHandler(config.id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">应用到...</option>
                      <option v-for="opt in promptVariableOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                    </select>
                    <button
                      class="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs hover:bg-blue-500/30"
                      @click="startEditPromptConfig(config)"
                    >
                      编辑
                    </button>
                    <button
                      class="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs hover:bg-red-500/30"
                      @click="deletePromptConfigHandler(config.id)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="promptConfigs.length === 0">
                <td colspan="4" class="px-4 py-10 text-center text-text-muted">暂无配置</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: User Custom Config Audit (用户配置审计)                 -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'user-custom-configs'" class="flex-1 flex flex-col p-3 sm:p-6 gap-4 overflow-auto">
        <!-- Header -->
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">🔍 用户配置审计</h1>
            <p class="text-xs text-text-muted mt-0.5">查看哪些用户配置了独立的模型预设或提示词预设，以及后台实际执行了几套用户个性化配置</p>
          </div>
          <button
            class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="loadCustomConfigs"
          >🔄 刷新</button>
        </div>

        <!-- Loading / Error -->
        <div v-if="customConfigsLoading" class="flex items-center justify-center py-16 text-text-muted">
          <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin mr-2"></span>加载中...
        </div>
        <div v-else-if="customConfigsError" class="text-red-400 text-sm bg-red-900/20 rounded-lg p-4">{{ customConfigsError }}</div>

        <template v-else-if="customConfigsData">
          <!-- Summary cards -->
          <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 shrink-0">
            <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
              <span class="text-2xl font-bold text-tinder-blue">{{ customConfigsData.summary.total_users_with_custom_config }}</span>
              <span class="text-xs text-text-muted">已自定义配置的用户</span>
            </div>
            <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
              <span class="text-2xl font-bold text-green-400">{{ customConfigsData.summary.total_active_llm_preset_refs }}</span>
              <span class="text-xs text-text-muted">LLM 预设引用数（活跃）</span>
            </div>
            <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
              <span class="text-2xl font-bold text-violet-400">{{ customConfigsData.summary.total_active_prompt_preset_refs }}</span>
              <span class="text-xs text-text-muted">提示词预设引用数（活跃）</span>
            </div>
            <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
              <span class="text-2xl font-bold text-amber-400">{{ customConfigsData.summary.total_unused_llm_presets }}</span>
              <span class="text-xs text-text-muted">未引用 LLM 预设</span>
            </div>
            <div class="rounded-xl bg-bg-elevated border border-border p-4 flex flex-col gap-1">
              <span class="text-2xl font-bold text-amber-400">{{ customConfigsData.summary.total_unused_prompt_presets }}</span>
              <span class="text-xs text-text-muted">未引用提示词预设</span>
            </div>
          </div>

          <!-- Empty state -->
          <div v-if="customConfigsData.users.length === 0" class="flex-1 flex items-center justify-center text-text-muted text-sm">
            暂无用户配置了独立参数
          </div>

          <!-- User list -->
          <div v-else class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="sticky top-0 z-10">
                <tr class="bg-bg-sidebar border-b border-border">
                  <th class="text-left px-4 py-3 font-medium text-text-muted w-8"></th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">用户</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">等级</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">涉及功能</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">LLM 引用</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">Prompt 引用</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">创建预设</th>
                  <th class="text-left px-4 py-3 font-medium text-text-muted">最后更新</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="u in customConfigsData.users" :key="u.user_id">
                  <!-- Row -->
                  <tr
                    class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors cursor-pointer"
                    @click="toggleCustomConfigUser(u.user_id)"
                  >
                    <td class="px-4 py-3 text-text-muted text-xs">
                      {{ customConfigsExpandedUsers.has(u.user_id) ? '▲' : '▼' }}
                    </td>
                    <td class="px-4 py-3">
                      <div class="font-medium text-text-primary">{{ u.username }}</div>
                      <div class="text-[11px] text-text-muted font-mono">uid {{ u.user_id }}</div>
                    </td>
                    <td class="px-4 py-3">
                      <span class="px-2 py-0.5 rounded-full text-[11px] font-medium"
                        :class="u.tier === 'pro_plus' ? 'bg-amber-500/20 text-amber-400' : u.tier === 'pro' ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-500/20 text-text-muted'"
                      >{{ u.tier === 'pro_plus' ? 'Pro+' : u.tier === 'pro' ? 'Pro' : 'Free' }}</span>
                    </td>
                    <td class="px-4 py-3 text-text-secondary">{{ u.feature_count }} 个</td>
                    <td class="px-4 py-3">
                      <span :class="u.llm_preset_ref_count > 0 ? 'text-green-400' : 'text-text-muted'">{{ u.llm_preset_ref_count }}</span>
                      <span class="text-text-muted text-xs ml-1">活跃 / {{ u.total_llm_presets }} 创建</span>
                    </td>
                    <td class="px-4 py-3">
                      <span :class="u.prompt_preset_ref_count > 0 ? 'text-violet-400' : 'text-text-muted'">{{ u.prompt_preset_ref_count }}</span>
                      <span class="text-text-muted text-xs ml-1">活跃 / {{ u.total_prompt_presets }} 创建</span>
                    </td>
                    <td class="px-4 py-3 text-text-muted text-xs">
                      <span v-if="u.unused_llm_presets.length || u.unused_prompt_presets.length" class="text-amber-400">
                        {{ u.unused_llm_presets.length + u.unused_prompt_presets.length }} 个未引用
                      </span>
                      <span v-else class="text-text-muted">—</span>
                    </td>
                    <td class="px-4 py-3 text-text-muted text-xs">
                      {{ u.last_updated ? new Date(u.last_updated).toLocaleDateString('zh-CN') : '—' }}
                    </td>
                  </tr>

                  <!-- Expanded detail -->
                  <tr v-if="customConfigsExpandedUsers.has(u.user_id)" class="border-b border-border/50 bg-bg-elevated/30">
                    <td colspan="8" class="px-6 py-4">
                      <div class="space-y-4">

                        <!-- Feature configs -->
                        <div v-if="u.feature_configs.length">
                          <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">功能配置详情</h3>
                          <div class="space-y-2">
                            <div
                              v-for="fc in u.feature_configs"
                              :key="fc.feature"
                              class="rounded-lg border border-border bg-bg-card p-3"
                            >
                              <div class="flex items-center gap-2 mb-2">
                                <span class="text-xs font-semibold text-text-primary">{{ featureLabel(fc.feature) }}</span>
                                <span class="text-[10px] text-text-muted font-mono">{{ fc.feature }}</span>
                                <span v-if="fc.has_direct_llm_config" class="px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-400 text-[10px]">含直连 LLM</span>
                                <span class="ml-auto text-[10px] text-text-muted">{{ new Date(fc.updated_at).toLocaleString('zh-CN') }}</span>
                              </div>

                              <!-- LLM preset refs -->
                              <div v-if="Object.keys(fc.llm_preset_refs).length" class="mb-2">
                                <p class="text-[10px] text-text-muted mb-1">🤖 引用的 LLM 预设</p>
                                <div class="flex flex-wrap gap-2">
                                  <div
                                    v-for="(ref, field) in fc.llm_preset_refs"
                                    :key="field"
                                    class="rounded bg-green-500/10 border border-green-500/20 px-2 py-1 text-[11px]"
                                  >
                                    <span class="text-green-400 font-medium">{{ ref.preset_name }}</span>
                                    <span class="text-text-muted ml-1">· {{ ref.model || '—' }}</span>
                                    <span v-if="ref.temperature != null" class="text-text-muted ml-1">T={{ ref.temperature }}</span>
                                    <span v-if="ref.max_tokens != null" class="text-text-muted ml-1">max={{ ref.max_tokens }}</span>
                                    <span v-if="ref.enable_thinking" class="text-blue-400 ml-1">思考</span>
                                    <span class="text-text-muted/60 block text-[10px] font-mono">{{ field }}</span>
                                  </div>
                                </div>
                              </div>

                              <!-- Prompt preset refs -->
                              <div v-if="Object.keys(fc.prompt_preset_refs).length" class="mb-2">
                                <p class="text-[10px] text-text-muted mb-1">📝 引用的提示词预设</p>
                                <div class="flex flex-wrap gap-2">
                                  <div
                                    v-for="(ref, field) in fc.prompt_preset_refs"
                                    :key="field"
                                    class="rounded bg-violet-500/10 border border-violet-500/20 px-2 py-1 text-[11px] max-w-xs"
                                  >
                                    <span class="text-violet-400 font-medium">{{ ref.preset_name }}</span>
                                    <span class="text-text-muted/60 block text-[10px] font-mono">{{ field }}</span>
                                    <span class="text-text-muted block text-[10px] truncate">{{ ref.content_preview }}</span>
                                  </div>
                                </div>
                              </div>

                              <!-- Direct params -->
                              <div v-if="Object.keys(fc.direct_params).length">
                                <p class="text-[10px] text-text-muted mb-1">⚙️ 直接设置的参数</p>
                                <div class="flex flex-wrap gap-1.5">
                                  <span
                                    v-for="(val, key) in fc.direct_params"
                                    :key="key"
                                    class="rounded bg-bg-elevated border border-border px-2 py-0.5 text-[11px] text-text-secondary font-mono"
                                  >
                                    {{ key }}: {{ Array.isArray(val) ? val.join(', ') : val }}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <!-- Unused presets -->
                        <div v-if="u.unused_llm_presets.length || u.unused_prompt_presets.length">
                          <h3 class="text-xs font-semibold text-amber-400/80 uppercase tracking-wider mb-2">未引用的预设（已创建但无功能引用）</h3>
                          <div class="flex flex-wrap gap-2">
                            <div
                              v-for="p in u.unused_llm_presets"
                              :key="'llm-' + p.id"
                              class="rounded bg-amber-500/10 border border-amber-500/20 px-2 py-1 text-[11px]"
                            >
                              <span class="text-amber-400">🤖 {{ p.name }}</span>
                              <span class="text-text-muted ml-1">{{ p.model }}</span>
                            </div>
                            <div
                              v-for="p in u.unused_prompt_presets"
                              :key="'prompt-' + p.id"
                              class="rounded bg-amber-500/10 border border-amber-500/20 px-2 py-1 text-[11px] max-w-[200px]"
                            >
                              <span class="text-amber-400">📝 {{ p.name }}</span>
                              <span class="text-text-muted block text-[10px] truncate">{{ p.content_preview }}</span>
                            </div>
                          </div>
                        </div>

                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </template>

        <!-- Not loaded yet -->
        <div v-else class="flex-1 flex items-center justify-center text-text-muted text-sm">
          点击刷新加载数据
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: PDF 清理                                                -->
      <!-- ============================================================= -->
      <AdminPdfCleanupPanel v-if="activeTab === 'pdf-cleanup'" />

    </div>
  </div>

  <!-- ================================================================= -->
  <!-- User Detail Modal                                                   -->
  <!-- ================================================================= -->
  <Teleport to="body">
    <Transition name="fade-modal">
      <div
        v-if="userDetailVisible"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @keydown="handleUserDetailKeydown"
        @click.self="closeUserDetail"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="closeUserDetail"></div>

        <!-- Panel -->
        <div
          class="relative z-10 w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl bg-bg-card border border-border shadow-2xl overflow-hidden"
          @click.stop
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <div class="flex items-center gap-3">
              <span class="text-lg">👤</span>
              <div>
                <h2 class="text-base font-semibold text-text-primary">
                  用户详情
                  <span v-if="userDetail" class="text-text-muted font-normal ml-1.5 text-sm">
                    #{{ userDetail.user.id }} · {{ userDetail.user.username }}
                  </span>
                </h2>
              </div>
            </div>
            <button
              class="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
              @click="closeUserDetail"
            >✕</button>
          </div>

          <!-- Body -->
          <div class="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            <!-- Loading -->
            <div v-if="userDetailLoading" class="flex items-center justify-center py-16 gap-2 text-text-muted">
              <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
              加载中...
            </div>

            <!-- Error -->
            <div v-else-if="userDetailError" class="flex items-center justify-center py-16 text-red-400 text-sm">
              {{ userDetailError }}
            </div>

            <!-- Content -->
            <template v-else-if="userDetail">
              <!-- Section: 基本信息 -->
              <section>
                <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">基本信息</h3>
                <div class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">用户 ID</span>
                    <span class="font-mono text-text-primary">{{ userDetail.user.id }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">用户名</span>
                    <span class="text-text-primary font-medium">{{ userDetail.user.username }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">昵称</span>
                    <span class="text-text-secondary">{{ userDetail.user.nickname || '—' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">角色</span>
                    <span class="px-2 py-0.5 rounded-full text-xs" :class="roleBadgeClass(userDetail.user.role)">
                      {{ roleLabel(userDetail.user.role) }}
                    </span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">等级</span>
                    <span class="text-text-secondary">{{ tierLabel(userDetail.user.tier) }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">到期时间</span>
                    <span class="text-text-secondary text-xs">
                      {{ userDetail.user.tier_expires_at ? formatDateTime(userDetail.user.tier_expires_at) : (userDetail.user.tier === 'free' ? '—' : '长期') }}
                    </span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">手机号</span>
                    <span class="text-text-secondary font-mono text-xs">
                      {{ userDetail.user.phone || '未绑定' }}
                      <span v-if="userDetail.user.phone && userDetail.user.phone_verified" class="ml-1 text-green-400 text-[10px]">已验证</span>
                      <span v-else-if="userDetail.user.phone" class="ml-1 text-amber-400 text-[10px]">未验证</span>
                    </span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">密码</span>
                    <span class="text-text-secondary text-xs">
                      {{ userDetail.user.has_password ? '已设置' : '未设置' }}
                      <span v-if="userDetail.user.is_phone_auto_created" class="ml-1 text-blue-400 text-[10px]">手机自动注册</span>
                    </span>
                  </div>
                </div>
              </section>

              <div class="border-t border-border"></div>

              <!-- Section: 时间与会话 -->
              <section>
                <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">时间与会话</h3>
                <div class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">注册时间</span>
                    <span class="text-text-secondary text-xs">{{ userDetail.user.created_at ? new Date(userDetail.user.created_at).toLocaleString('zh-CN') : '—' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">最后登录</span>
                    <span class="text-text-secondary text-xs">{{ userDetail.user.last_login_at ? new Date(userDetail.user.last_login_at).toLocaleString('zh-CN') : '从未登录' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">资料更新</span>
                    <span class="text-text-secondary text-xs">{{ userDetail.user.updated_at ? new Date(userDetail.user.updated_at).toLocaleString('zh-CN') : '—' }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-text-muted w-16 shrink-0">活跃会话</span>
                    <span class="text-text-secondary">
                      {{ userDetail.active_sessions }}
                      <span class="text-text-muted text-xs ml-1">个</span>
                    </span>
                  </div>
                </div>
              </section>

              <div class="border-t border-border"></div>

              <!-- Section: 订阅历史 -->
              <section>
                <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                  订阅历史
                  <span class="ml-1 font-normal normal-case text-text-muted">（最近 {{ userDetail.subscription_history.length }} 条）</span>
                </h3>
                <div v-if="userDetail.subscription_history.length === 0" class="text-sm text-text-muted italic py-4 text-center">暂无订阅记录</div>
                <div v-else class="overflow-x-auto rounded-lg border border-border">
                  <table class="w-full text-xs">
                    <thead>
                      <tr class="bg-bg-elevated border-b border-border text-text-muted">
                        <th class="text-left px-3 py-2 font-medium">来源</th>
                        <th class="text-left px-3 py-2 font-medium">等级变更</th>
                        <th class="text-left px-3 py-2 font-medium">开始</th>
                        <th class="text-left px-3 py-2 font-medium">截止</th>
                        <th class="text-left px-3 py-2 font-medium">备注</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="record in userDetail.subscription_history"
                        :key="record.id"
                        class="border-b border-border/50 hover:bg-bg-hover/20"
                      >
                        <td class="px-3 py-2 text-text-secondary">{{ sourceLabel(record.source) }}</td>
                        <td class="px-3 py-2">
                          <span class="text-text-muted">{{ tierLabel(record.from_tier as any) }}</span>
                          <span class="mx-1 text-text-muted">→</span>
                          <span class="text-text-primary font-medium">{{ tierLabel(record.to_tier as any) }}</span>
                        </td>
                        <td class="px-3 py-2 text-text-muted font-mono">
                          {{ record.start_at ? new Date(record.start_at).toLocaleDateString('zh-CN') : '—' }}
                        </td>
                        <td class="px-3 py-2 text-text-muted font-mono">
                          {{ record.end_at ? new Date(record.end_at).toLocaleDateString('zh-CN') : '长期' }}
                        </td>
                        <td class="px-3 py-2 text-text-muted max-w-[120px] truncate" :title="record.note || ''">
                          {{ record.note || '—' }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>

              <div class="border-t border-border"></div>

              <!-- Section: 管理员操作 -->
              <section>
                <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">管理员操作</h3>

                <!-- 反馈消息 -->
                <div v-if="actionMsg" class="mb-3 px-3 py-2 rounded-lg bg-green-500/10 border border-green-500/30 text-green-400 text-sm">{{ actionMsg }}</div>
                <div v-if="actionError" class="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{{ actionError }}</div>

                <!-- 普通操作 -->
                <div class="flex flex-wrap gap-2 mb-4">
                  <!-- 重置密码 -->
                  <button
                    class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary bg-bg-elevated hover:bg-bg-hover disabled:opacity-50 cursor-pointer transition-colors"
                    :disabled="actionBusy"
                    @click="showResetPwdForm = !showResetPwdForm; clearActionFeedback()"
                  >
                    🔑 重置密码
                  </button>
                  <!-- 强制下线 -->
                  <button
                    class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-secondary bg-bg-elevated hover:bg-bg-hover disabled:opacity-50 cursor-pointer transition-colors"
                    :disabled="actionBusy"
                    @click="handleAdminForceLogout"
                  >
                    ⚡ 强制下线
                  </button>
                </div>

                <!-- 重置密码表单（展开） -->
                <div v-if="showResetPwdForm" class="mb-4 p-3 rounded-lg border border-border bg-bg-elevated">
                  <label class="block text-xs text-text-muted mb-1.5">新密码（至少 8 位）</label>
                  <div class="flex gap-2">
                    <input
                      v-model="resetPwdValue"
                      type="password"
                      placeholder="输入新密码"
                      class="flex-1 px-3 py-1.5 rounded-lg bg-bg-card border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                      @keydown.enter="handleAdminResetPassword"
                    />
                    <button
                      class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs disabled:opacity-50 cursor-pointer"
                      :disabled="actionBusy || resetPwdValue.length < 8"
                      @click="handleAdminResetPassword"
                    >
                      {{ actionBusy ? '保存中...' : '确认重置' }}
                    </button>
                    <button
                      class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-muted hover:bg-bg-hover cursor-pointer"
                      @click="showResetPwdForm = false; resetPwdValue = ''"
                    >取消</button>
                  </div>
                </div>

                <!-- 账号状态操作 -->
                <div class="flex flex-wrap gap-2 mb-4">
                  <button
                    v-if="!userDetail.user.is_disabled"
                    class="px-3 py-1.5 rounded-lg border border-amber-500/40 text-xs text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 disabled:opacity-50 cursor-pointer transition-colors"
                    :disabled="actionBusy"
                    @click="handleAdminDisable"
                  >
                    🚫 禁用账号
                  </button>
                  <button
                    v-else
                    class="px-3 py-1.5 rounded-lg border border-green-500/40 text-xs text-green-400 bg-green-500/10 hover:bg-green-500/20 disabled:opacity-50 cursor-pointer transition-colors"
                    :disabled="actionBusy"
                    @click="handleAdminEnable"
                  >
                    ✅ 启用账号
                  </button>
                  <span v-if="userDetail.user.is_disabled" class="text-xs text-amber-400 flex items-center">当前账号已禁用</span>
                </div>

                <!-- 危险操作区 -->
                <div class="border border-red-500/20 rounded-lg p-3 bg-red-500/5">
                  <p class="text-xs text-red-400 font-semibold mb-2">危险操作</p>
                  <p class="text-xs text-text-muted mb-3">永久删除账号后无法恢复，该用户的登录凭据将被清除。</p>
                  <button
                    v-if="!showDeleteConfirm"
                    class="px-3 py-1.5 rounded-lg border border-red-500/40 text-xs text-red-400 bg-red-500/10 hover:bg-red-500/20 disabled:opacity-50 cursor-pointer transition-colors"
                    :disabled="actionBusy"
                    @click="openDeleteConfirm"
                  >
                    🗑️ 永久删除账号
                  </button>
                  <div v-else class="space-y-2">
                    <p class="text-xs text-red-400">请输入用户名 <span class="font-mono font-bold">{{ userDetail.user.username }}</span> 确认删除：</p>
                    <div class="flex gap-2">
                      <input
                        v-model="deleteConfirmInput"
                        type="text"
                        placeholder="输入用户名确认"
                        class="flex-1 px-3 py-1.5 rounded-lg bg-bg-card border border-red-500/40 text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-red-500/50"
                        @keydown.enter="handleAdminDelete"
                      />
                      <button
                        class="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs disabled:opacity-50 cursor-pointer"
                        :disabled="actionBusy || deleteConfirmInput !== userDetail.user.username"
                        @click="handleAdminDelete"
                      >
                        {{ actionBusy ? '删除中...' : '确认删除' }}
                      </button>
                      <button
                        class="px-3 py-1.5 rounded-lg border border-border text-xs text-text-muted hover:bg-bg-hover cursor-pointer"
                        @click="showDeleteConfirm = false; deleteConfirmInput = ''"
                      >取消</button>
                    </div>
                  </div>
                </div>
              </section>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

.fade-modal-enter-active,
.fade-modal-leave-active {
  transition: opacity 0.2s ease;
}
.fade-modal-enter-active .relative.z-10,
.fade-modal-leave-active .relative.z-10 {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-modal-enter-from,
.fade-modal-leave-to {
  opacity: 0;
}
.fade-modal-enter-from .relative.z-10,
.fade-modal-leave-to .relative.z-10 {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

.settings-sidebar {
  width: var(--settings-sidebar-w);
}
</style>
