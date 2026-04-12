<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchUserSettings, saveUserSettings,
  fetchUserLlmPresets,
  fetchUserPromptPresets,
  checkUsername, fetchSubscriptionStatus, redeemSubscriptionKey,
  fetchAnnouncements, fetchSubscriptionHistory,
  fetchEngagementRewards,
  fetchActivityCalendar,
} from '../api'
import type { ActivityCalendarDay } from '../api'
import type { UserLlmPreset, UserPromptPreset, Announcement, SubscriptionHistoryRecord, EngagementRewardGrant } from '../types/paper'
import { currentUser, saveProfile, setPassword, changePassword, refreshProfile } from '../stores/auth'
import { useEngagement, isHonoraryReward, rewardIcon, rewardStatusLabel, rewardStatusClass, REWARD_USAGE_HINTS } from '../composables/useEngagement'
import { useEntitlements } from '../composables/useEntitlements'
import UserBar from '../components/UserBar.vue'
import LlmPresetsPanel from '../components/LlmPresetsPanel.vue'
import PromptPresetsPanel from '../components/PromptPresetsPanel.vue'
import PresetSelector from '../components/PresetSelector.vue'
// Entitlement & engagement organism components
import UsageDashboard from '../components/entitlement/UsageDashboard.vue'
import PricingTable from '../components/entitlement/PricingTable.vue'
import StreakHeroCard from '../components/engagement/StreakHeroCard.vue'
import MilestoneTimeline from '../components/engagement/MilestoneTimeline.vue'
import ActivityCalendar from '../components/engagement/ActivityCalendar.vue'
import RewardCard from '../components/engagement/RewardCard.vue'
import AutoClassifyPanel from '../components/AutoClassifyPanel.vue'

const route = useRoute()
const router = useRouter()

// ---------------------------------------------------------------------------
// Page mode: /profile shows account items only; /advanced-settings shows the rest
// ---------------------------------------------------------------------------

const PROFILE_KEYS = new Set(['account_info', 'announcements', 'subscription', 'achievements'])

const isAdvancedMode = computed(() => route.name === 'advanced-settings')

// ---------------------------------------------------------------------------
// Sidebar navigation
// ---------------------------------------------------------------------------

interface NavItem {
  key: string
  label: string
  icon: string
  enabled: boolean
  group: string
}

const navItems: NavItem[] = [
  { key: 'account_info', label: '资料设置', icon: 'user', enabled: true, group: '账号设置' },
  { key: 'announcements', label: '公告', icon: 'bell', enabled: true, group: '账号设置' },
  { key: 'subscription', label: '订阅', icon: 'credit-card', enabled: true, group: '账号设置' },
  { key: 'achievements', label: '研究成就', icon: 'trophy', enabled: true, group: '账号设置' },
  { key: 'llm_presets', label: '模型预设', icon: 'cpu', enabled: true, group: '预设管理' },
  { key: 'prompt_presets', label: '提示词预设', icon: 'scroll', enabled: true, group: '预设管理' },
  { key: 'compare', label: '对比分析', icon: 'compare', enabled: true, group: '功能配置' },
  { key: 'inspiration', label: '灵感涌现', icon: 'lightbulb', enabled: true, group: '功能配置' },
  { key: 'idea_generate', label: '灵感生成', icon: 'zap', enabled: true, group: '功能配置' },
  { key: 'paper_recommend', label: '推荐论文参数', icon: 'star', enabled: true, group: '功能配置' },
  { key: 'auto_classify', label: '自动分类', icon: 'folder-tree', enabled: true, group: '功能配置' },
  { key: 'paper_summary', label: '论文解读', icon: 'article', enabled: false, group: '功能配置' },
  { key: 'theme_filter', label: '主题筛选', icon: 'filter', enabled: false, group: '功能配置' },
]

const visibleNavItems = computed(() =>
  navItems.filter(item => isAdvancedMode.value ? !PROFILE_KEYS.has(item.key) : PROFILE_KEYS.has(item.key))
)

const activeNav = ref('account_info')
const showSettingsSidebar = ref(false)

// ---------------------------------------------------------------------------
// Account info / profile state
// ---------------------------------------------------------------------------

const showWelcomeBanner = ref(false)
const profileNickname = ref('')
const profileUsername = ref('')
const profileSaving = ref(false)
const profileSaveSuccess = ref(false)
const profileSaveError = ref('')

const pwdNew = ref('')
const pwdConfirm = ref('')
const pwdOld = ref('')
const pwdSaving = ref(false)
const pwdSuccess = ref(false)
const pwdError = ref('')
const subscriptionLoading = ref(false)
const subscriptionError = ref('')
const subscriptionTier = ref<'free' | 'pro' | 'pro_plus'>('free')
const subscriptionExpireAt = ref<string | null>(null)
const redeemCode = ref('')
const redeemSaving = ref(false)
const redeemSuccess = ref('')
const redeemError = ref('')

// ---------------------------------------------------------------------------
// 实时校验：用户名可用性
// ---------------------------------------------------------------------------
type CheckStatus = 'idle' | 'checking' | 'ok' | 'error'
const usernameCheckStatus = ref<CheckStatus>('idle')
const usernameCheckMsg = ref('')

let _usernameDebounceTimer: ReturnType<typeof setTimeout> | null = null

watch(profileUsername, (val) => {
  if (_usernameDebounceTimer) clearTimeout(_usernameDebounceTimer)
  const trimmed = val.trim()
  // 与当前用户名相同时不检查
  if (trimmed === (currentUser.value?.username || '')) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length === 0) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length < 3) {
    usernameCheckStatus.value = 'error'
    usernameCheckMsg.value = '至少 3 位'
    return
  }
  usernameCheckStatus.value = 'checking'
  usernameCheckMsg.value = ''
  _usernameDebounceTimer = setTimeout(async () => {
    try {
      const res = await checkUsername(trimmed, currentUser.value?.id)
      if (profileUsername.value.trim() !== trimmed) return // 已过期
      usernameCheckStatus.value = res.available ? 'ok' : 'error'
      usernameCheckMsg.value = res.available ? '' : res.message
    } catch {
      usernameCheckStatus.value = 'idle'
    }
  }, 300)
})

// ---------------------------------------------------------------------------
// 实时校验：密码
// ---------------------------------------------------------------------------
const pwdNewStatus = computed<CheckStatus>(() => {
  if (!pwdNew.value) return 'idle'
  return pwdNew.value.length >= 8 ? 'ok' : 'error'
})
const pwdNewMsg = computed(() => pwdNew.value && pwdNew.value.length < 8 ? '至少 8 位' : '')

const pwdConfirmStatus = computed<CheckStatus>(() => {
  if (!pwdConfirm.value) return 'idle'
  return pwdConfirm.value === pwdNew.value ? 'ok' : 'error'
})
const pwdConfirmMsg = computed(() => pwdConfirm.value && pwdConfirm.value !== pwdNew.value ? '两次密码不一致' : '')

function initProfileForm() {
  profileNickname.value = currentUser.value?.nickname || ''
  profileUsername.value = currentUser.value?.username || ''
  usernameCheckStatus.value = 'idle'
  usernameCheckMsg.value = ''
}

async function handleSaveProfile() {
  profileSaving.value = true
  profileSaveError.value = ''
  profileSaveSuccess.value = false
  try {
    await saveProfile({
      nickname: profileNickname.value.trim() || undefined,
      username: profileUsername.value.trim() || undefined,
    })
    profileSaveSuccess.value = true
    setTimeout(() => { profileSaveSuccess.value = false }, 2500)
  } catch (e: any) {
    profileSaveError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally {
    profileSaving.value = false
  }
}

async function handleSetPassword() {
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次密码不一致'; return }
  pwdSaving.value = true
  pwdError.value = ''
  pwdSuccess.value = false
  try {
    await setPassword(pwdNew.value)
    pwdNew.value = ''
    pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2500)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '设置失败'
  } finally {
    pwdSaving.value = false
  }
}

async function handleChangePassword() {
  if (!pwdOld.value) { pwdError.value = '请输入旧密码'; return }
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '新密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次新密码不一致'; return }
  pwdSaving.value = true
  pwdError.value = ''
  pwdSuccess.value = false
  try {
    await changePassword(pwdOld.value, pwdNew.value)
    pwdOld.value = ''
    pwdNew.value = ''
    pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2500)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '修改失败'
  } finally {
    pwdSaving.value = false
  }
}

function tierText(tier: string): string {
  if (tier === 'pro_plus') return 'Pro+'
  if (tier === 'pro') return 'Pro'
  return 'Free'
}

const formattedExpireAt = computed(() => {
  if (!subscriptionExpireAt.value) return '未开通时长权益'
  const d = new Date(subscriptionExpireAt.value)
  if (Number.isNaN(d.getTime())) return subscriptionExpireAt.value
  return d.toLocaleString()
})

function getRedeemDeviceId(): string {
  const key = 'ai4papers_device_id'
  const existing = localStorage.getItem(key)
  if (existing) return existing
  let created = ''
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    created = window.crypto.randomUUID()
  } else {
    created = `dev_${Math.random().toString(36).slice(2)}_${Date.now()}`
  }
  localStorage.setItem(key, created)
  return created
}

async function loadSubscription() {
  subscriptionLoading.value = true
  subscriptionError.value = ''
  try {
    const res = await fetchSubscriptionStatus()
    subscriptionTier.value = res.tier
    subscriptionExpireAt.value = res.tier_expires_at
  } catch (e: any) {
    subscriptionError.value = e?.response?.data?.detail || e?.message || '加载会员状态失败'
  } finally {
    subscriptionLoading.value = false
  }
}

async function handleRedeemCode() {
  const code = redeemCode.value.trim()
  if (!code) {
    redeemError.value = '请输入兑换码'
    return
  }
  redeemSaving.value = true
  redeemError.value = ''
  redeemSuccess.value = ''
  try {
    const res = await redeemSubscriptionKey({
      code,
      device_id: getRedeemDeviceId(),
    })
    await refreshProfile()
    await loadSubscription()
    redeemCode.value = ''
    redeemSuccess.value = `兑换成功，已开通 ${tierText(res.plan_tier)} ${res.duration_days} 天`
  } catch (e: any) {
    redeemError.value = e?.response?.data?.detail || e?.message || '兑换失败'
  } finally {
    redeemSaving.value = false
  }
}

// Compute sidebar groups (filtered by current page mode)
const navGroups = computed(() => {
  const groups: { name: string; items: NavItem[] }[] = []
  const seen = new Set<string>()
  for (const item of visibleNavItems.value) {
    if (!seen.has(item.group)) {
      seen.add(item.group)
      groups.push({ name: item.group, items: [] })
    }
    groups.find(g => g.name === item.group)!.items.push(item)
  }
  return groups
})

// ---------------------------------------------------------------------------
// Feature Settings state (compare / inspiration)
// ---------------------------------------------------------------------------

const form = reactive<Record<string, any>>({})
const defaults = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

const showApiKey = ref(false)

// ---------------------------------------------------------------------------
// Load / Save settings
// ---------------------------------------------------------------------------

async function loadSettings(feature: string) {
  loading.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const res = await fetchUserSettings(feature)
    defaults.value = res.defaults || {}
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
  } catch (e: any) {
    saveError.value = e?.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const toSave: Record<string, any> = { ...form }
    const res = await saveUserSettings(activeNav.value, toSave)
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
    defaults.value = res.defaults || {}
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function resetField(key: string) {
  if (key in defaults.value) {
    form[key] = defaults.value[key]
  }
}

// ---------------------------------------------------------------------------
// Computed helpers for feature settings
// ---------------------------------------------------------------------------

const noDefaultKeys = new Set([
  'llm_base_url', 'llm_api_key', 'llm_model', 'llm_preset_id', 'prompt_preset_id',
  // Per-module preset IDs for paper_recommend
  'theme_select_llm_preset_id', 'org_llm_preset_id', 'summary_llm_preset_id', 'summary_limit_llm_preset_id',
  'theme_select_prompt_preset_id', 'org_prompt_preset_id', 'summary_prompt_preset_id',
  'summary_limit_prompt_intro_preset_id', 'summary_limit_prompt_method_preset_id',
  'summary_limit_prompt_findings_preset_id', 'summary_limit_prompt_opinion_preset_id',
  // MinerU 服务密钥
  'mineru_token',
  // Per-phase preset IDs for idea_generate (每阶段独立 1:1)
  'ingest_llm_preset_id',    'ingest_prompt_preset_id',
  'question_llm_preset_id',  'question_prompt_preset_id',
  'candidate_llm_preset_id', 'candidate_prompt_preset_id',
  'review_llm_preset_id',    'review_prompt_preset_id',
  'revise_llm_preset_id',    'revise_prompt_preset_id',
  'plan_llm_preset_id',      'plan_prompt_preset_id',
  'eval_llm_preset_id',      'eval_prompt_preset_id',
])

// Toggle visibility for token-type fields
const mineruTokenVisible = ref(false)

// Module definitions for paper_recommend preset-based config
const recommendModules = [
  {
    key: 'theme_select',
    label: '主题相关性评分',
    icon: '🎯',
    desc: '对论文进行主题相关性评分，筛选相关论文',
    llmFormKey: 'theme_select_llm_preset_id',
    prompts: [
      { formKey: 'theme_select_prompt_preset_id', label: '评分提示词' },
    ],
  },
  {
    key: 'org',
    label: '机构判别',
    icon: '🏛️',
    desc: '提取论文作者机构信息',
    llmFormKey: 'org_llm_preset_id',
    prompts: [
      { formKey: 'org_prompt_preset_id', label: '机构判别提示词' },
    ],
  },
  {
    key: 'summary',
    label: '摘要生成',
    icon: '📄',
    desc: '生成论文中文摘要笔记',
    llmFormKey: 'summary_llm_preset_id',
    prompts: [
      { formKey: 'summary_prompt_preset_id', label: '摘要生成提示词' },
    ],
  },
  {
    key: 'summary_limit',
    label: '摘要精简',
    icon: '✂️',
    desc: '压缩摘要各部分至字数上限（按需触发）',
    llmFormKey: 'summary_limit_llm_preset_id',
    prompts: [
      { formKey: 'summary_limit_prompt_intro_preset_id', label: '文章简介精简提示词' },
      { formKey: 'summary_limit_prompt_method_preset_id', label: '重点思路精简提示词' },
      { formKey: 'summary_limit_prompt_findings_preset_id', label: '分析总结精简提示词' },
      { formKey: 'summary_limit_prompt_opinion_preset_id', label: '个人观点精简提示词' },
    ],
  },
]

// Module definitions for idea_generate preset-based config
const ideaModules = [
  {
    key: 'ingest',
    label: '原子抽取 (idea_ingest)',
    icon: '⚗️',
    desc: '从论文全文中抽取结构化"灵感原子"',
    llmFormKey: 'ingest_llm_preset_id',
    prompts: [
      { formKey: 'ingest_prompt_preset_id', label: '原子抽取提示词' },
    ],
  },
  {
    key: 'question',
    label: '研究问题生成 (idea_question)',
    icon: '❓',
    desc: '从局限性原子挖掘有价值的研究问题',
    llmFormKey: 'question_llm_preset_id',
    prompts: [
      { formKey: 'question_prompt_preset_id', label: '研究问题生成提示词' },
    ],
  },
  {
    key: 'candidate',
    label: '灵感候选生成 (idea_candidate)',
    icon: '💡',
    desc: '基于研究问题与原子生成多策略灵感候选',
    llmFormKey: 'candidate_llm_preset_id',
    prompts: [
      { formKey: 'candidate_prompt_preset_id', label: '灵感候选生成提示词' },
    ],
  },
  {
    key: 'review',
    label: '灵感评审 (idea_review)',
    icon: '🔍',
    desc: '多评委对灵感候选进行评审打分',
    llmFormKey: 'review_llm_preset_id',
    prompts: [
      { formKey: 'review_prompt_preset_id', label: '灵感评审提示词' },
    ],
  },
  {
    key: 'revise',
    label: '灵感修订 (idea_revise)',
    icon: '✏️',
    desc: '根据评审反馈自动修订灵感候选',
    llmFormKey: 'revise_llm_preset_id',
    prompts: [
      { formKey: 'revise_prompt_preset_id', label: '灵感修订提示词' },
    ],
  },
  {
    key: 'plan',
    label: '实验计划生成 (idea_plan)',
    icon: '📋',
    desc: '为通过评审的灵感生成可执行实验计划',
    llmFormKey: 'plan_llm_preset_id',
    prompts: [
      { formKey: 'plan_prompt_preset_id', label: '实验计划生成提示词' },
    ],
  },
  {
    key: 'eval',
    label: '评测回放 (idea_eval)',
    icon: '🔁',
    desc: '对历史问题集重新生成灵感用于版本对比',
    llmFormKey: 'eval_llm_preset_id',
    prompts: [
      { formKey: 'eval_prompt_preset_id', label: '评测回放提示词' },
    ],
  },
]

function hasDefault(key: string): boolean {
  return !noDefaultKeys.has(key) && key in defaults.value
}

function isDefault(key: string): boolean {
  if (!hasDefault(key)) return false
  return form[key] === defaults.value[key]
}

// Determine if user is using a preset or manual config for the current feature
const usePresetMode = computed(() => {
  return !!form.llm_preset_id
})

const usePromptPresetMode = computed(() => {
  return !!form.prompt_preset_id
})

// ---------------------------------------------------------------------------
// LLM Presets — lightweight list used by feature settings pill selectors
// Full CRUD is handled by LlmPresetsPanel component
// ---------------------------------------------------------------------------

const llmPresets = ref<UserLlmPreset[]>([])

async function loadLlmPresets() {
  try {
    const res = await fetchUserLlmPresets()
    llmPresets.value = res.presets
  } catch {}
}

// ---------------------------------------------------------------------------
// Prompt Presets — lightweight list used by feature settings pill selectors
// Full CRUD is handled by PromptPresetsPanel component
// ---------------------------------------------------------------------------

const promptPresets = ref<UserPromptPreset[]>([])

async function loadPromptPresets() {
  try {
    const res = await fetchUserPromptPresets()
    promptPresets.value = res.presets
  } catch {}
}

// ---------------------------------------------------------------------------
// Achievements (engagement) state
// ---------------------------------------------------------------------------

const engagement = useEngagement()
const ent = useEntitlements()
const achievementRewards = ref<EngagementRewardGrant[]>([])
const achievementsLoading = ref(false)
const activityCalendar = ref<ActivityCalendarDay[]>([])
const activityCalendarToday = ref('')

const MILESTONES = [1, 2, 3, 4, 5, 7, 14, 30, 60, 100]

async function loadAchievements() {
  if (achievementsLoading.value) return
  achievementsLoading.value = true
  try {
    const [, rewardsRes, calendarRes] = await Promise.all([
      engagement.loadStatus(true),
      fetchEngagementRewards({ limit: 200 }),
      fetchActivityCalendar(60),
    ])
    achievementRewards.value = rewardsRes.rewards
    activityCalendar.value = calendarRes.calendar
    activityCalendarToday.value = calendarRes.today
  } catch {
    // Silent failure
  } finally {
    achievementsLoading.value = false
  }
}

function calendarDayClass(day: ActivityCalendarDay): string {
  if (day.completed) return 'bg-tinder-green/80'
  if (day.partial) return 'bg-tinder-green/25'
  return 'bg-bg-elevated'
}

function calendarDayTitle(day: ActivityCalendarDay): string {
  const label = day.completed ? '全部完成' : day.partial ? `完成 ${day.tasks_done}/3` : '未记录'
  return `${day.day_key} · ${label}`
}

// rewardStatusLabel, rewardStatusClass, isHonoraryReward, rewardIcon imported from useEngagement.ts (P5)

function milestoneUnlocked(day: number): boolean {
  return achievementRewards.value.some(r => r.streak_day === day)
}

function milestoneReward(day: number): EngagementRewardGrant | undefined {
  return achievementRewards.value.find(r => r.streak_day === day)
}

// Computed helpers for new organism components
const unlockedMilestoneDays = computed(() =>
  new Set(achievementRewards.value.map(r => r.streak_day))
)

const nextMilestoneDay = computed(() =>
  engagement.status.value?.streak?.next_milestones?.[0] ?? null
)

// Rewards grouped by status for the achievements page
const activeAchievementRewards = computed(() =>
  achievementRewards.value.filter(r => r.status === 'active')
)
const usedAchievementRewards = computed(() =>
  achievementRewards.value.filter(r => r.status === 'used')
)
const expiredAchievementRewards = computed(() =>
  achievementRewards.value.filter(r => r.status === 'expired')
)

function formatDate(iso: string | undefined | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const thisYear = new Date().getFullYear()
    if (d.getFullYear() !== thisYear) {
      return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
    }
    return d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
  } catch {
    return iso
  }
}

// Announcements state
// ---------------------------------------------------------------------------

const announcements = ref<Announcement[]>([])
const announcementsLoading = ref(false)
const announcementsError = ref('')
const announcementsTotal = ref(0)
const expandedAnnouncements = ref<Set<number>>(new Set())

async function loadAnnouncements() {
  announcementsLoading.value = true
  announcementsError.value = ''
  try {
    const res = await fetchAnnouncements({ limit: 50 })
    announcements.value = res.announcements
    announcementsTotal.value = res.total
  } catch (e: any) {
    announcementsError.value = e?.response?.data?.detail || e?.message || '加载公告失败'
  } finally {
    announcementsLoading.value = false
  }
}

function toggleAnnouncement(id: number) {
  if (expandedAnnouncements.value.has(id)) {
    expandedAnnouncements.value.delete(id)
  } else {
    expandedAnnouncements.value.add(id)
  }
}

function announcementTagLabel(tag: string): string {
  const map: Record<string, string> = {
    important: '重要',
    general: '一般',
    update: '更新',
    maintenance: '维护',
  }
  return map[tag] || tag
}

function announcementTagClass(tag: string): string {
  const map: Record<string, string> = {
    important: 'bg-red-500/15 text-red-400 border-red-500/20',
    general: 'bg-gray-500/15 text-text-muted border-gray-500/20',
    update: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    maintenance: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  }
  return map[tag] || 'bg-gray-500/15 text-text-muted border-gray-500/20'
}

function formatAnnouncementDate(ts: string): string {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return ts
  }
}

// ---------------------------------------------------------------------------
// Subscription page state
// ---------------------------------------------------------------------------

const subscriptionHistory = ref<SubscriptionHistoryRecord[]>([])
const subscriptionHistoryLoading = ref(false)
const subscriptionHistoryError = ref('')

async function loadSubscriptionHistory() {
  subscriptionHistoryLoading.value = true
  subscriptionHistoryError.value = ''
  try {
    const res = await fetchSubscriptionHistory()
    subscriptionHistory.value = res.history
  } catch (e: any) {
    subscriptionHistoryError.value = e?.response?.data?.detail || e?.message || '加载订阅记录失败'
  } finally {
    subscriptionHistoryLoading.value = false
  }
}

function historySourceLabel(source: string): string {
  const map: Record<string, string> = {
    redeem: '兑换码',
    admin: '管理员操作',
    expiry: '到期回收',
    manual: '手动调整',
  }
  return map[source] || source
}

function tierLabel(tier: string): string {
  if (tier === 'pro_plus') return 'Pro+'
  if (tier === 'pro') return 'Pro'
  return 'Free'
}

function formatHistoryDate(ts: string): string {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return ts
  }
}

// ---------------------------------------------------------------------------
// Feature accent color helper
// ---------------------------------------------------------------------------

function accentColor(feature: string): string {
  if (feature === 'inspiration') return '#f59e0b'
  if (feature === 'idea_generate') return '#f97316'
  if (feature === 'paper_recommend') return '#ec4899'
  return '#8b5cf6'
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

function getDefaultNav(): string {
  if (isAdvancedMode.value) {
    return visibleNavItems.value.find(i => i.enabled)?.key ?? 'llm_presets'
  }
  return 'account_info'
}

onMounted(() => {
  const defaultNav = getDefaultNav()
  const tabQuery = route.query.tab as string | undefined
  if (tabQuery && visibleNavItems.value.find(i => i.key === tabQuery && i.enabled)) {
    activeNav.value = tabQuery
  } else {
    activeNav.value = defaultNav
  }
  if (route.query.welcome === '1') {
    showWelcomeBanner.value = true
  }
  initProfileForm()
  loadSubscription()
  loadLlmPresets()
  loadPromptPresets()
})

watch(() => route.name, () => {
  activeNav.value = getDefaultNav()
})

watch(() => route.query.tab, (tabQuery) => {
  if (tabQuery && visibleNavItems.value.find(i => i.key === tabQuery && i.enabled)) {
    activeNav.value = tabQuery as string
  }
})

watch(activeNav, (feature) => {
  if (feature === 'compare' || feature === 'inspiration' || feature === 'idea_generate' || feature === 'paper_recommend') {
    loadSettings(feature)
  } else if (feature === 'account_info') {
    initProfileForm()
    loadSubscription()
  } else if (feature === 'announcements') {
    loadAnnouncements()
  } else if (feature === 'subscription') {
    loadSubscription()
    loadSubscriptionHistory()
    ent.refreshEntitlements(true)
  } else if (feature === 'achievements') {
    loadAchievements()
  }
})

watch(() => currentUser.value, () => {
  if (activeNav.value === 'account_info') {
    initProfileForm()
    loadSubscription()
  }
})
</script>

<template>
  <div class="h-full flex overflow-hidden relative">

    <!-- Mobile sidebar overlay backdrop -->
    <div
      v-if="showSettingsSidebar"
      class="fixed inset-0 z-20 bg-black/60 md:hidden"
      @click="showSettingsSidebar = false"
    />

    <!-- Mobile settings nav toggle button -->
    <button
      v-if="!showSettingsSidebar"
      class="absolute top-2 left-2 z-10 md:hidden w-8 h-8 flex items-center justify-center rounded-full bg-bg-card border border-border text-text-secondary hover:bg-bg-hover transition-colors"
      :title="isAdvancedMode ? '高级设置导航' : '个人中心导航'"
      @click="showSettingsSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>

    <!-- ========== Left sidebar navigation ========== -->
    <aside
      :class="[
        'z-30 lg:z-auto settings-sidebar h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300',
        showSettingsSidebar
          ? 'fixed lg:relative inset-y-0 left-0 translate-x-0'
          : 'fixed lg:relative inset-y-0 left-0 -translate-x-full lg:translate-x-0'
      ]"
    >
      <!-- Mobile close button (hidden once sidebar is persistent at lg) -->
      <button
        class="lg:hidden absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary border-none cursor-pointer"
        @click="showSettingsSidebar = false"
      >✕</button>
      <!-- Header -->
      <div class="px-4 py-5 border-b border-border">
        <h1 class="text-base font-bold text-text-primary flex items-center gap-2">
          <!-- profile icon -->
          <svg v-if="!isAdvancedMode" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
          </svg>
          <!-- settings icon -->
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          {{ isAdvancedMode ? '高级设置' : '个人中心' }}
        </h1>
        <p class="text-xs text-text-muted mt-1">{{ currentUser?.username }}</p>
      </div>

      <!-- Nav items (grouped) -->
      <nav class="flex-1 overflow-y-auto p-2">
        <div v-for="group in navGroups" :key="group.name" class="mb-1">
          <div class="px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted/60">
            {{ group.name }}
          </div>
          <div class="space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.key"
              class="w-full px-3 py-2 text-left text-sm flex items-center gap-2.5 rounded-lg transition-all duration-150"
              :class="[
                item.enabled
                  ? (activeNav === item.key
                      ? 'bg-bg-elevated text-text-primary font-medium shadow-sm'
                      : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer')
                  : 'text-text-muted cursor-not-allowed opacity-40',
              ]"
              :disabled="!item.enabled"
              @click="item.enabled && (activeNav = item.key, showSettingsSidebar = false)"
            >
              <!-- Icon: user -->
              <svg v-if="item.icon === 'user'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
              </svg>
              <!-- Icon: cpu -->
              <svg v-else-if="item.icon === 'cpu'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" />
              </svg>
              <!-- Icon: scroll -->
              <svg v-else-if="item.icon === 'scroll'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" /><path d="M19 17V5a2 2 0 0 0-2-2H4" />
              </svg>
              <!-- Icon: compare -->
              <svg v-else-if="item.icon === 'compare'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <!-- Icon: lightbulb -->
              <svg v-else-if="item.icon === 'lightbulb'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              <!-- Icon: zap (灵感生成) -->
              <svg v-else-if="item.icon === 'zap'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <!-- Icon: star -->
              <svg v-else-if="item.icon === 'star'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
              <!-- Icon: folder-tree (自动分类) -->
              <svg v-else-if="item.icon === 'folder-tree'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                <line x1="12" y1="11" x2="12" y2="17"/><polyline points="9 14 12 17 15 14"/>
              </svg>
              <!-- Icon: article -->
              <svg v-else-if="item.icon === 'article'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
              </svg>
              <!-- Icon: filter -->
              <svg v-else-if="item.icon === 'filter'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <!-- Icon: bell (公告) -->
              <svg v-else-if="item.icon === 'bell'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
              <!-- Icon: credit-card (订阅) -->
              <svg v-else-if="item.icon === 'credit-card'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
              </svg>
              <!-- Icon: trophy (研究成就) -->
              <svg v-else-if="item.icon === 'trophy'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="8 21 12 17 16 21"/><line x1="12" y1="17" x2="12" y2="11"/><path d="M7 4H2v3a5 5 0 0 0 5 5h0"/><path d="M17 4h5v3a5 5 0 0 1-5 5h0"/><rect x="7" y="2" width="10" height="9" rx="1"/>
              </svg>

              <span class="truncate">{{ item.label }}</span>
              <span v-if="!item.enabled" class="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted shrink-0">即将推出</span>
              <!-- Lock indicator for gated preset sections -->
              <span
                v-else-if="(item.key === 'llm_presets' && ent.isGated('llm_preset')) || (item.key === 'prompt_presets' && ent.isGated('prompt_preset'))"
                class="ml-auto text-amber-400/70 shrink-0"
                title="需要 Pro 套餐"
              >🔒</span>

              <!-- Active indicator -->
              <div v-else-if="item.enabled && activeNav === item.key" class="ml-auto w-1.5 h-1.5 rounded-full bg-[#8b5cf6] shrink-0"></div>
            </button>
          </div>
        </div>
      </nav>
      <!-- Bottom user entry -->
      <UserBar />
    </aside>

    <!-- ========== Right content area ========== -->
    <div class="flex-1 h-full overflow-y-auto min-w-0">

      <!-- ============================== -->
      <!-- ============================== -->
      <!-- Announcements page             -->
      <!-- ============================== -->
      <div v-if="activeNav === 'announcements'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Page header -->
        <div class="mb-6">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
            公告
          </h2>
          <p class="text-xs text-text-muted mt-1">来自平台的通知与公告</p>
        </div>

        <!-- Loading -->
        <div v-if="announcementsLoading" class="flex items-center justify-center py-16">
          <svg class="w-6 h-6 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
          </svg>
        </div>

        <!-- Error -->
        <div v-else-if="announcementsError" class="rounded-xl border border-red-400/20 bg-red-500/5 px-4 py-4 text-sm text-red-400">
          {{ announcementsError }}
        </div>

        <!-- Empty -->
        <div v-else-if="announcements.length === 0" class="text-center py-16">
          <div class="w-14 h-14 mx-auto mb-4 rounded-2xl bg-bg-elevated flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-text-muted opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </div>
          <p class="text-sm text-text-muted">暂无公告</p>
        </div>

        <!-- Announcement list -->
        <div v-else class="space-y-3">
          <div
            v-for="item in announcements"
            :key="item.id"
            class="rounded-xl border bg-bg-card overflow-hidden transition-all"
            :class="item.tag === 'important' ? 'border-red-500/25' : 'border-border'"
          >
            <!-- Card header -->
            <div
              class="px-5 py-4 flex items-start gap-3 cursor-pointer select-none"
              @click="toggleAnnouncement(item.id)"
            >
              <!-- Pin icon -->
              <div v-if="item.is_pinned" class="shrink-0 mt-0.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#fd267a]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M16 3a1 1 0 0 1 .707 1.707L13 8.414V15a1 1 0 0 1-.553.894l-4 2A1 1 0 0 1 7 17v-5.586l-3.707-3.707A1 1 0 0 1 4 7h12z"/>
                </svg>
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-semibold text-text-primary">{{ item.title }}</span>
                  <span
                    class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium shrink-0"
                    :class="announcementTagClass(item.tag)"
                  >{{ announcementTagLabel(item.tag) }}</span>
                </div>
                <p class="text-xs text-text-muted mt-0.5">{{ formatAnnouncementDate(item.created_at) }}</p>
              </div>
              <!-- Chevron -->
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="w-4 h-4 text-text-muted shrink-0 mt-0.5 transition-transform duration-200"
                :class="expandedAnnouncements.has(item.id) ? 'rotate-180' : ''"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
            <!-- Card content -->
            <div v-if="expandedAnnouncements.has(item.id)" class="px-5 pb-5 border-t border-border/50">
              <p class="text-sm text-text-secondary whitespace-pre-wrap mt-4 leading-relaxed">{{ item.content }}</p>
              <div class="mt-3 flex justify-end">
                <button
                  class="text-xs text-text-muted hover:text-tinder-pink transition-colors bg-transparent border-none cursor-pointer px-0"
                  @click.stop="router.push(`/announcements/${item.id}`)"
                >查看详情页 →</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ============================== -->
      <!-- Subscription page              -->
      <!-- ============================== -->
      <div v-if="activeNav === 'subscription'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Page header -->
        <div class="mb-6">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>
            </svg>
            订阅
          </h2>
          <p class="text-xs text-text-muted mt-1">查看套餐权益并开通会员</p>
        </div>

        <!-- Section 1: Pricing comparison table — now uses PricingTable component -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-1">套餐方案</h3>
          <p class="text-xs text-text-muted mb-4">订阅时长根据兑换码而定（通常为 30 / 90 / 365 天）</p>

          <!-- Pricing comparison table component (responsive: table on md+, cards on mobile) -->
          <PricingTable :current-tier="(subscriptionTier as 'free' | 'pro' | 'pro_plus')" />
          <!-- LEGACY TABLE REMOVED (was ~200 lines) -->
          <div class="hidden">
            <table class="w-full min-w-[520px] text-xs border-collapse">
              <!-- ── Column headers ── -->
              <thead>
                <tr>
                  <th class="text-left text-text-muted font-medium py-2 px-3 w-[38%]"></th>
                  <!-- Free -->
                  <th class="text-center py-2 px-2 w-[20%]">
                    <div
                      class="rounded-lg py-2 px-1"
                      :class="subscriptionTier === 'free' ? 'bg-border/60 border border-border-light' : ''"
                    >
                      <div class="font-semibold text-text-secondary text-[11px] mb-0.5">Free</div>
                      <div class="text-text-muted text-[10px]">免费</div>
                      <div v-if="subscriptionTier === 'free'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-border text-text-secondary inline-block">当前套餐</div>
                    </div>
                  </th>
                  <!-- Pro -->
                  <th class="text-center py-2 px-2 w-[20%]">
                    <div
                      class="rounded-lg py-2 px-1"
                      :class="subscriptionTier === 'pro' ? 'bg-blue-500/10 border border-blue-500/40' : ''"
                    >
                      <div class="font-bold text-blue-400 text-[11px] mb-0.5">Pro</div>
                      <div class="text-blue-400/70 text-[10px]">¥9.9 / 月</div>
                      <div v-if="subscriptionTier === 'pro'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 inline-block">当前套餐</div>
                    </div>
                  </th>
                  <!-- Pro+ -->
                  <th class="text-center py-2 px-2 w-[22%]">
                    <div
                      class="rounded-lg py-2 px-1 relative"
                      :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/10 border border-violet-500/40' : 'bg-violet-500/5 border border-violet-500/20'"
                    >
                      <div
                        v-if="subscriptionTier !== 'pro_plus'"
                        class="absolute -top-2 left-1/2 -translate-x-1/2 text-[9px] px-1.5 py-0.5 rounded-full font-semibold whitespace-nowrap"
                        style="background: linear-gradient(135deg, #fd267a33, #a855f733); color: #d580ff; border: 1px solid #a855f730;"
                      >推荐</div>
                      <div class="font-bold text-[11px] mb-0.5" style="background: linear-gradient(135deg, #fd267a, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro+</div>
                      <div class="text-violet-400/70 text-[10px]">¥19.9 / 月</div>
                      <div v-if="subscriptionTier === 'pro_plus'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 inline-block">当前套餐</div>
                    </div>
                  </th>
                </tr>
              </thead>

              <tbody class="divide-y divide-border/40">

                <!-- ── Group: 浏览与发现 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">浏览与发现</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">每日浏览论文</td>
                  <td class="px-2 py-2 text-center text-text-muted">5 篇</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">20 篇</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">50 篇</td>
                </tr>

                <!-- ── Group: AI 功能 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">AI 功能</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">AI 论文问答</td>
                  <td class="px-2 py-2 text-center text-text-muted">10 条/天</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">无限</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">无限</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">通用 AI 助手</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary leading-snug">对比分析<span class="block text-[10px] text-text-muted">（每次最多篇数）</span></td>
                  <td class="px-2 py-2 text-center text-text-muted leading-snug">3 次/月<span class="block text-[10px]">2 篇/次</span></td>
                  <td class="px-2 py-2 text-center text-text-secondary leading-snug" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">30 次/月<span class="block text-[10px]">5 篇/次</span></td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium leading-snug" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">100 次/月<span class="block text-[10px] font-normal">8 篇/次</span></td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">深度研究</td>
                  <td class="px-2 py-2 text-center text-text-muted">2 次/月</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">15 次/月</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">50 次/月</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">灵感生成</td>
                  <td class="px-2 py-2 text-center text-text-muted">3 次/月</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">30 次/月</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">100 次/月</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">全文翻译</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">10 次/月</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">50 次/月</td>
                </tr>

                <!-- ── Group: 知识库与存储 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">知识库与存储</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">论文收藏</td>
                  <td class="px-2 py-2 text-center text-text-muted">20 篇</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">100 篇</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">500 篇</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">文件夹</td>
                  <td class="px-2 py-2 text-center text-text-muted">3 个</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">10 个</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">30 个</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">笔记</td>
                  <td class="px-2 py-2 text-center text-text-muted">10 条</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">50 条</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">200 条</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">保存对比结果</td>
                  <td class="px-2 py-2 text-center text-text-muted">3 条</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">20 条</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">100 条</td>
                </tr>

                <!-- ── Group: 论文上传 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">论文上传</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">上传自有论文</td>
                  <td class="px-2 py-2 text-center text-text-muted">2 篇/月</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">30 篇/月</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">100 篇/月</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">笔记附件上传</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>

                <!-- ── Group: 导出 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">导出</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">Markdown 导出</td>
                  <td class="px-2 py-2 text-center text-tinder-green">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">DOCX / PDF 导出</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">批量导出</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-text-muted/60" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>

                <!-- ── Group: 高级设置与历史 ── -->
                <tr class="bg-bg-elevated/40">
                  <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">高级设置与历史</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">自定义模型预设</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">自定义提示词预设</td>
                  <td class="px-2 py-2 text-center text-text-muted/60">✗</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">✓</td>
                  <td class="px-2 py-2 text-center text-tinder-green" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">✓</td>
                </tr>
                <tr class="hover:bg-bg-elevated/20 transition-colors">
                  <td class="px-3 py-2 text-text-secondary">研究历史保留</td>
                  <td class="px-2 py-2 text-center text-text-muted">3 天</td>
                  <td class="px-2 py-2 text-center text-text-secondary" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">14 天</td>
                  <td class="px-2 py-2 text-center text-tinder-green font-medium" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">30 天</td>
                </tr>

                <!-- ── CTA row ── -->
                <tr>
                  <td class="px-3 pt-4 pb-2 text-[10px] text-text-muted">扫码添加微信购买</td>
                  <td class="px-2 pt-4 pb-2 text-center">
                    <span v-if="subscriptionTier === 'free'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-border text-text-muted">当前套餐</span>
                  </td>
                  <td class="px-2 pt-4 pb-2 text-center" :class="subscriptionTier === 'pro' ? 'bg-blue-500/5' : ''">
                    <span v-if="subscriptionTier === 'pro'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-blue-500/20 text-blue-300">当前套餐</span>
                    <span v-else-if="subscriptionTier !== 'pro_plus'" class="inline-block text-[11px] px-2 py-1 rounded-md font-medium text-blue-300" style="background: linear-gradient(135deg, #3b82f620, #2563eb20); border: 1px solid #3b82f640;">¥9.9 / 月起</span>
                  </td>
                  <td class="px-2 pt-4 pb-2 text-center" :class="subscriptionTier === 'pro_plus' ? 'bg-violet-500/5' : ''">
                    <span v-if="subscriptionTier === 'pro_plus'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-violet-500/20 text-violet-300">当前套餐</span>
                    <span v-else class="inline-block text-[11px] px-2 py-1 rounded-md font-medium text-violet-300" style="background: linear-gradient(135deg, #7c3aed20, #a855f720); border: 1px solid #a855f740;">¥19.9 / 月起</span>
                  </td>
                </tr>

              </tbody>
            </table>
          </div>
        </section>

        <!-- Section 1b: Usage dashboard — now uses UsageDashboard component (was 220+ lines) -->
        <section v-if="ent.loaded.value" class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-4">当前用量</h3>
          <UsageDashboard />
          <!-- LEGACY QUOTA ROWS REMOVED — rendered by UsageDashboard component -->
          <div class="hidden">
          <!-- Quota usage rows (legacy, kept for reference) -->
          <div class="space-y-3">
            <!-- chat -->
            <div v-if="ent.limit('chat') !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">AI 论文问答</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="ent.quotaFraction('chat') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, ent.quotaFraction('chat') * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('chat') }}</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">AI 论文问答</span>
              <span class="text-[11px] text-tinder-green">不限次数</span>
            </div>

            <!-- compare -->
            <div v-if="ent.limit('compare') !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">对比分析</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="ent.quotaFraction('compare') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, ent.quotaFraction('compare') * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('compare') }}</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">对比分析</span>
              <span class="text-[11px] text-tinder-green">不限次数</span>
            </div>

            <!-- research -->
            <div v-if="ent.limit('research') !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">深度研究</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="ent.quotaFraction('research') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, ent.quotaFraction('research') * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('research') }}</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">深度研究</span>
              <span class="text-[11px] text-tinder-green">不限次数</span>
            </div>

            <!-- idea_gen -->
            <div v-if="ent.limit('idea_gen') !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">灵感生成</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="ent.quotaFraction('idea_gen') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, ent.quotaFraction('idea_gen') * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('idea_gen') }}</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">灵感生成</span>
              <span class="text-[11px] text-tinder-green">不限次数</span>
            </div>

            <!-- upload -->
            <div v-if="ent.limit('upload') !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">论文上传</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="ent.quotaFraction('upload') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, ent.quotaFraction('upload') * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('upload') }}</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">论文上传</span>
              <span class="text-[11px] text-tinder-green">不限次数</span>
            </div>

            <!-- translate quota -->
            <template v-if="ent.gateAllowed('translate')">
              <div v-if="ent.limit('translate') !== null" class="flex items-center gap-3">
                <span class="text-xs text-text-secondary w-28 shrink-0">全文翻译</span>
                <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="ent.quotaFraction('translate') >= 0.8 ? 'bg-amber-400' : 'bg-tinder-blue'"
                    :style="`width: ${Math.min(100, ent.quotaFraction('translate') * 100)}%`"
                  />
                </div>
                <span class="text-[11px] text-text-muted w-16 text-right shrink-0">{{ ent.quotaSummary('translate') }}</span>
              </div>
              <div v-else class="flex items-center gap-3">
                <span class="text-xs text-text-secondary w-28 shrink-0">全文翻译</span>
                <span class="text-[11px] text-tinder-green">不限次数</span>
              </div>
            </template>

            <!-- KB papers storage -->
            <div v-if="ent.kbPaperStorage.value.limit !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">知识库论文</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="(ent.kbPaperStorage.value.remaining ?? 1) <= 5 ? 'bg-amber-400' : 'bg-tinder-green'"
                  :style="`width: ${Math.min(100, (ent.kbPaperStorage.value.used / (ent.kbPaperStorage.value.limit || 1)) * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">
                {{ ent.kbPaperStorage.value.used }}/{{ ent.kbPaperStorage.value.limit }} 篇
              </span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">知识库论文</span>
              <span class="text-[11px] text-tinder-green">不限篇数</span>
            </div>

            <!-- KB notes storage -->
            <div v-if="ent.kbNoteStorage.value.limit !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">知识库笔记</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="(ent.kbNoteStorage.value.remaining ?? 1) <= 3 ? 'bg-amber-400' : 'bg-tinder-green'"
                  :style="`width: ${Math.min(100, (ent.kbNoteStorage.value.used / (ent.kbNoteStorage.value.limit || 1)) * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">
                {{ ent.kbNoteStorage.value.used }}/{{ ent.kbNoteStorage.value.limit }} 篇
              </span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">知识库笔记</span>
              <span class="text-[11px] text-tinder-green">不限篇数</span>
            </div>

            <!-- KB compare results storage -->
            <div v-if="ent.kbCompareResultStorage.value.limit !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">保存对比结果</span>
              <div class="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="(ent.kbCompareResultStorage.value.remaining ?? 1) <= 1 ? 'bg-amber-400' : 'bg-tinder-blue'"
                  :style="`width: ${Math.min(100, (ent.kbCompareResultStorage.value.used / (ent.kbCompareResultStorage.value.limit || 1)) * 100)}%`"
                />
              </div>
              <span class="text-[11px] text-text-muted w-16 text-right shrink-0">
                {{ ent.kbCompareResultStorage.value.used }}/{{ ent.kbCompareResultStorage.value.limit }} 条
              </span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">保存对比结果</span>
              <span class="text-[11px] text-tinder-green">不限条数</span>
            </div>

            <!-- Browse limit -->
            <div v-if="ent.browseLimit.value !== null" class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">每日浏览论文</span>
              <span class="text-[11px] text-text-muted">每日最多 {{ ent.browseLimit.value }} 篇</span>
            </div>
            <div v-else class="flex items-center gap-3">
              <span class="text-xs text-text-secondary w-28 shrink-0">每日浏览论文</span>
              <span class="text-[11px] text-tinder-green">不限篇数</span>
            </div>
          </div>

          <!-- Feature gates -->
          <div class="mt-4 pt-4 border-t border-border grid grid-cols-2 gap-2 text-[11px]">
            <div class="flex items-center gap-1.5">
              <span :class="ent.gateAllowed('general_chat') ? 'text-tinder-green' : 'text-text-muted'">
                {{ ent.gateAllowed('general_chat') ? '✓' : '✗' }}
              </span>
              <span :class="ent.gateAllowed('general_chat') ? 'text-text-secondary' : 'text-text-muted'">通用 AI 助手</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-tinder-green">✓</span>
              <span class="text-text-secondary">
                全文翻译 {{ ent.quotaSummary('translate') }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <span :class="ent.gateAllowed('note_file_upload') ? 'text-tinder-green' : 'text-text-muted'">
                {{ ent.gateAllowed('note_file_upload') ? '✓' : '✗' }}
              </span>
              <span :class="ent.gateAllowed('note_file_upload') ? 'text-text-secondary' : 'text-text-muted'">笔记附件上传</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-tinder-green">✓</span>
              <span class="text-text-secondary">
                导出 {{ ent.quotaSummary('export') }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <span :class="ent.gateAllowed('batch_export') ? 'text-tinder-green' : 'text-text-muted'">
                {{ ent.gateAllowed('batch_export') ? '✓' : '✗' }}
              </span>
              <span :class="ent.gateAllowed('batch_export') ? 'text-text-secondary' : 'text-text-muted'">批量导出</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span :class="ent.gateAllowed('llm_preset') ? 'text-tinder-green' : 'text-text-muted'">
                {{ ent.gateAllowed('llm_preset') ? '✓' : '✗' }}
              </span>
              <span :class="ent.gateAllowed('llm_preset') ? 'text-text-secondary' : 'text-text-muted'">自定义模型预设</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span :class="ent.gateAllowed('prompt_preset') ? 'text-tinder-green' : 'text-text-muted'">
                {{ ent.gateAllowed('prompt_preset') ? '✓' : '✗' }}
              </span>
              <span :class="ent.gateAllowed('prompt_preset') ? 'text-text-secondary' : 'text-text-muted'">自定义提示词预设</span>
            </div>
          </div>
          </div><!-- end hidden legacy quota rows -->
        </section>

        <!-- Section 2: Purchase method -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-4">购买方式</h3>
          <div class="flex flex-col sm:flex-row items-start gap-5">
            <!-- WeChat QR placeholder -->
            <div class="shrink-0 flex flex-col items-center gap-2">
              <div class="w-32 h-32 rounded-xl border-2 border-dashed border-border overflow-hidden bg-bg-elevated flex items-center justify-center">
                <img
                  src="/wechat.jpg"
                  alt="微信二维码"
                  class="w-full h-full object-cover rounded-xl"
                  @error="(e: Event) => ((e.target as HTMLImageElement).style.display = 'none')"
                />
              </div>
              <p class="text-[11px] text-text-muted">扫码添加微信</p>
            </div>
            <!-- Instructions -->
            <div class="flex-1 space-y-3 text-sm text-text-secondary">
              <div class="flex items-start gap-2">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[#fd267a]/15 text-[#fd267a] text-[10px] font-bold flex items-center justify-center mt-0.5">1</span>
                <span>扫描左侧二维码，或搜索微信号添加好友</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[#fd267a]/15 text-[#fd267a] text-[10px] font-bold flex items-center justify-center mt-0.5">2</span>
                <span>告知所需套餐（Pro / Pro+）和时长，完成付款</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[#fd267a]/15 text-[#fd267a] text-[10px] font-bold flex items-center justify-center mt-0.5">3</span>
                <span>收到兑换码后，在下方「兑换会员」区域输入即可立即激活</span>
              </div>
              <div class="mt-2 pt-3 border-t border-border/50 text-xs text-text-muted leading-relaxed">
                如有问题，可发消息咨询，通常在工作日 12 小时内回复。
              </div>
            </div>
          </div>
        </section>

        <!-- Section 3: Redeem -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-1">兑换会员</h3>
          <p class="text-xs text-text-muted mb-4">已有兑换码？输入下方即可立即激活会员权益。</p>

          <!-- How to get a redeem code -->
          <div class="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-3 space-y-2">
            <div class="flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <p class="text-xs font-semibold text-blue-300">如何获取兑换码？</p>
            </div>
            <p class="text-[11px] text-text-secondary leading-relaxed">
              目前仅支持通过<strong class="text-text-primary">兑换码</strong>激活会员。兑换码通过以下方式获取：
            </p>
            <ul class="text-[11px] text-text-secondary space-y-1 pl-2">
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>内测邀请 / 内部发放渠道</li>
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>联系管理员或官方客服申请购买</li>
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>参与官方活动或合作推广</li>
            </ul>
          </div>

          <!-- Current subscription status -->
          <div class="mb-4 rounded-lg border border-border bg-bg-elevated px-3 py-3">
            <div class="flex items-center gap-2 text-sm">
              <span class="text-text-secondary">当前套餐：</span>
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="subscriptionTier === 'pro_plus'
                  ? 'bg-violet-500/15 text-violet-300'
                  : subscriptionTier === 'pro'
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'bg-gray-500/15 text-text-muted'"
              >
                {{ tierText(subscriptionTier) }}
              </span>
            </div>
            <p class="mt-1 text-xs text-text-muted">
              到期时间：{{ subscriptionExpireAt ? new Date(subscriptionExpireAt).toLocaleDateString('zh-CN') : '未开通' }}
            </p>
            <p v-if="subscriptionLoading" class="mt-1 text-[11px] text-text-muted">会员状态加载中...</p>
            <p v-else-if="subscriptionError" class="mt-1 text-[11px] text-[#fd267a]">{{ subscriptionError }}</p>
          </div>

          <!-- Redeem input -->
          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">兑换码</label>
            <input
              v-model="redeemCode"
              type="text"
              maxlength="64"
              placeholder="请输入兑换码，如 XXXX-XXXX-XXXX-XXXX"
              class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
              @keyup.enter="handleRedeemCode"
            />
          </div>

          <div class="mt-4 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white cursor-pointer hover:opacity-90 transition-all disabled:opacity-50"
              style="background: linear-gradient(135deg, #fd267a, #ff6036); box-shadow: 0 4px 15px #fd267a33;"
              :disabled="redeemSaving"
              @click="handleRedeemCode"
            >{{ redeemSaving ? '兑换中...' : '立即兑换' }}</button>
            <span v-if="redeemSuccess" class="text-xs text-green-500">{{ redeemSuccess }}</span>
            <span v-else-if="redeemError" class="text-xs text-[#fd267a]">{{ redeemError }}</span>
          </div>
        </section>

        <!-- Section 4: Subscription history -->
        <section class="rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-4">订阅记录</h3>

          <div v-if="subscriptionHistoryLoading" class="flex items-center gap-2 text-xs text-text-muted py-4">
            <svg class="w-4 h-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
            </svg>
            加载中...
          </div>
          <div v-else-if="subscriptionHistoryError" class="text-xs text-red-400 py-2">{{ subscriptionHistoryError }}</div>
          <div v-else-if="subscriptionHistory.length === 0" class="text-xs text-text-muted py-4 text-center">暂无订阅记录</div>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-xs">
              <thead>
                <tr class="border-b border-border text-text-muted">
                  <th class="text-left pb-2 pr-3 font-medium">来源</th>
                  <th class="text-left pb-2 pr-3 font-medium">变更</th>
                  <th class="text-left pb-2 pr-3 font-medium">开始</th>
                  <th class="text-left pb-2 font-medium">到期</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border/50">
                <tr v-for="record in subscriptionHistory" :key="record.id" class="text-text-secondary">
                  <td class="py-2.5 pr-3">
                    <span class="px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">{{ historySourceLabel(record.source) }}</span>
                  </td>
                  <td class="py-2.5 pr-3 whitespace-nowrap">
                    <span
                      class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                      :class="record.from_tier === 'free' ? 'bg-gray-500/10 text-text-muted' : 'bg-blue-500/10 text-blue-400'"
                    >{{ tierLabel(record.from_tier) }}</span>
                    <span class="mx-1 text-text-muted">→</span>
                    <span
                      class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                      :class="record.to_tier === 'free' ? 'bg-gray-500/10 text-text-muted' : record.to_tier === 'pro_plus' ? 'bg-violet-500/10 text-violet-400' : 'bg-blue-500/10 text-blue-400'"
                    >{{ tierLabel(record.to_tier) }}</span>
                  </td>
                  <td class="py-2.5 pr-3 whitespace-nowrap">{{ formatHistoryDate(record.start_at) }}</td>
                  <td class="py-2.5 whitespace-nowrap text-text-muted">{{ record.end_at ? formatHistoryDate(record.end_at) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <!-- Account Info page              -->
      <!-- ============================== -->
      <!-- ============================== -->
      <!-- Achievements page              -->
      <!-- ============================== -->
      <div v-if="activeNav === 'achievements'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Page header -->
        <div class="mb-6">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="8 21 12 17 16 21"/><line x1="12" y1="17" x2="12" y2="11"/><path d="M7 4H2v3a5 5 0 0 0 5 5h0"/><path d="M17 4h5v3a5 5 0 0 1-5 5h0"/><rect x="7" y="2" width="10" height="9" rx="1"/>
            </svg>
            研究成就
          </h2>
          <p class="text-xs text-text-muted mt-1">每日完成浏览、收藏、分析三项任务，连续研究可解锁对比扩展、深度分析等实用特权</p>
        </div>

        <!-- Loading -->
        <div v-if="achievementsLoading" class="flex items-center justify-center py-16">
          <svg class="w-6 h-6 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
          </svg>
        </div>

        <template v-else>
          <!-- Streak Hero Card — circular ring progress + goal text -->
          <div class="mb-5">
            <StreakHeroCard
              :current-streak="engagement.status.value?.streak?.current ?? 0"
              :longest-streak="engagement.status.value?.streak?.longest ?? 0"
              :next-milestone-day="nextMilestoneDay"
            />
          </div>

          <!-- Activity calendar heatmap — with week labels and month separators -->
          <div v-if="activityCalendar.length > 0" class="rounded-xl border border-border bg-bg-card p-4 mb-5">
            <h3 class="text-sm font-semibold text-text-primary mb-3">近 60 天研究记录</h3>
            <ActivityCalendar
              :days="activityCalendar"
              :today="activityCalendarToday"
            />
          </div>

          <!-- Milestone Timeline — vertical narrative timeline -->
          <div class="rounded-xl border border-border bg-bg-card p-4 mb-5">
            <h3 class="text-sm font-semibold text-text-primary mb-4">里程碑路线</h3>
            <MilestoneTimeline
              :current-streak="engagement.status.value?.streak?.current ?? 0"
              :milestones="MILESTONES"
              :unlocked-days="unlockedMilestoneDays"
            />
          </div>

          <!-- Rewards list — grouped by status, using RewardCard component -->
          <div class="rounded-xl border border-border bg-bg-card overflow-hidden mb-5">
            <div class="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 class="text-sm font-semibold text-text-primary">奖励记录</h3>
              <span v-if="activeAchievementRewards.length > 0" class="text-[11px] px-2 py-0.5 rounded-full bg-tinder-green/15 text-tinder-green">
                {{ activeAchievementRewards.length }} 个可用
              </span>
            </div>
            <div v-if="achievementRewards.length === 0" class="flex flex-col items-center justify-center py-12">
              <span class="text-3xl mb-3">🎯</span>
              <p class="text-sm text-text-muted">还没有奖励记录</p>
              <p class="text-xs text-text-muted mt-1">每日完成浏览、收藏、分析三项任务，连续研究可解锁奖励</p>
            </div>
            <div v-else class="px-4 py-3 space-y-4">
              <!-- Active rewards (highlighted) -->
              <template v-if="activeAchievementRewards.length > 0">
                <p class="text-[10px] font-semibold text-tinder-green uppercase tracking-wide">可使用</p>
                <div class="space-y-3">
                  <RewardCard
                    v-for="r in activeAchievementRewards"
                    :key="r.id ?? r.reward_code"
                    :reward="r"
                    :show-cta="true"
                  />
                </div>
              </template>

              <!-- Used rewards -->
              <template v-if="usedAchievementRewards.length > 0">
                <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide pt-2">已使用</p>
                <div class="space-y-3">
                  <RewardCard
                    v-for="r in usedAchievementRewards"
                    :key="r.id ?? r.reward_code"
                    :reward="r"
                    :show-cta="false"
                  />
                </div>
              </template>

              <!-- Expired rewards -->
              <template v-if="expiredAchievementRewards.length > 0">
                <p class="text-[10px] font-semibold text-text-muted uppercase tracking-wide pt-2">已过期</p>
                <div class="space-y-3 opacity-60">
                  <RewardCard
                    v-for="r in expiredAchievementRewards"
                    :key="r.id ?? r.reward_code"
                    :reward="r"
                    :show-cta="false"
                  />
                </div>
              </template>
            </div>
          </div>

          <!-- Rules explanation -->
          <div class="rounded-xl border border-border bg-bg-elevated/50 p-4">
            <h3 class="text-sm font-semibold text-text-primary mb-3">激励规则说明</h3>
            <ul class="space-y-2">
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-tinder-green">✓</span>
                <span>每日完成 <strong class="text-text-primary">浏览 + 收藏 + 分析</strong> 三项任务，即可积累有效研究日</span>
              </li>
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-tinder-green">✓</span>
                <span>连续达到里程碑天数（1 / 2 / 3 / 4 / 5 / 7 / 14 / 30 / 60 / 100 天）时自动解锁对应奖励</span>
              </li>
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span>
                <span><strong class="text-text-primary">扩展对比券</strong>：使用后本次可对比最多 8 篇论文（默认限制 5 篇）</span>
              </li>
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span>
                <span><strong class="text-text-primary">深度研究加速券</strong>：使用后获得 1.5 倍分析上下文长度和更多论文精选范围</span>
              </li>
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-[#f59e0b]">⚡</span>
                <span><strong class="text-text-primary">快速处理加速券</strong>：上传论文时使用，论文将被优先处理分析</span>
              </li>
              <li class="flex items-start gap-2 text-xs text-text-secondary">
                <span class="shrink-0 mt-0.5 text-text-muted">ℹ</span>
                <span>功能券均有有效期（14-30 天），请及时使用；徽章类奖励永久保留</span>
              </li>
            </ul>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Account Info page              -->
      <!-- ============================== -->
      <div v-if="activeNav === 'account_info'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">

        <!-- Welcome banner for new users -->
        <Transition
          enter-active-class="transition duration-300 ease-out"
          enter-from-class="opacity-0 -translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-200 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 -translate-y-2"
        >
          <div v-if="showWelcomeBanner" class="mb-6 rounded-xl bg-gradient-to-r from-[#fd267a]/10 to-[#ff6036]/10 border border-[#fd267a]/20 px-5 py-4 flex items-start gap-3">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <div class="flex-1">
              <p class="text-sm font-semibold text-text-primary">欢迎加入！</p>
              <p class="text-xs text-text-muted mt-0.5">你的账号已通过手机号自动创建，建议设置昵称和密码，方便后续使用。</p>
            </div>
            <button class="text-text-muted hover:text-text-primary transition-colors" @click="showWelcomeBanner = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </Transition>

        <!-- Page header -->
        <div class="mb-6">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            资料设置
          </h2>
          <p class="text-xs text-text-muted mt-1">管理你的个人信息和登录凭证</p>
        </div>

        <!-- ── Section 1: Basic info ── -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-4">基本信息</h3>

          <div class="space-y-4">
            <!-- Nickname -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">昵称</label>
              <input
                v-model="profileNickname"
                type="text"
                maxlength="64"
                placeholder="设置一个显示昵称（可选）"
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
              />
            </div>

            <!-- Username -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">
                用户名
                <span v-if="currentUser?.is_phone_auto_created" class="ml-1.5 text-[#fd267a] text-[10px] font-normal">建议修改</span>
              </label>
              <div class="relative">
                <input
                  v-model="profileUsername"
                  type="text"
                  minlength="3"
                  maxlength="32"
                  placeholder="3-32 位字母/数字/._-"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="usernameCheckStatus === 'error' ? 'border-red-400/60' : usernameCheckStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <!-- 检查中 spinner -->
                <span v-if="usernameCheckStatus === 'checking'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-text-muted animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
                  </svg>
                </span>
                <!-- 可用对勾 -->
                <span v-else-if="usernameCheckStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <!-- 不可用叉号 -->
                <span v-else-if="usernameCheckStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="usernameCheckStatus === 'error' && usernameCheckMsg" class="text-[11px] text-red-400 mt-1">{{ usernameCheckMsg }}</p>
              <p v-else-if="currentUser?.is_phone_auto_created" class="text-[10px] text-text-muted mt-1">
                当前用户名为系统自动生成（{{ currentUser?.username }}），建议修改为你自己的用户名
              </p>
            </div>

            <!-- Phone (read-only) -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">绑定手机号</label>
              <div class="flex items-center gap-2 px-3 py-2.5 bg-bg border border-border rounded-lg text-sm text-text-muted">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
                </svg>
                <span>{{ currentUser?.phone || '未绑定' }}</span>
                <span v-if="currentUser?.phone_verified" class="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/10 text-green-500 font-medium">已验证</span>
              </div>
            </div>
          </div>

          <!-- Save basic info -->
          <div class="mt-5 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-brand-gradient hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
              :disabled="profileSaving"
              @click="handleSaveProfile"
            >{{ profileSaving ? '保存中...' : '保存' }}</button>
            <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
              <span v-if="profileSaveSuccess" class="text-xs text-green-500 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                已保存
              </span>
              <span v-else-if="profileSaveError" class="text-xs text-[#fd267a]">{{ profileSaveError }}</span>
            </Transition>
          </div>
        </section>

        <!-- ── Section 2: Subscription / Redeem ── -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-1">会员权限</h3>
          <p class="text-xs text-text-muted mb-4">仅支持 Pro / Pro+ 兑换开通，不影响管理员权限体系。</p>

          <!-- How to get a redeem code -->
          <div class="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-3 space-y-2">
            <div class="flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 shrink-0 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <p class="text-xs font-semibold text-blue-300">如何获取兑换码？</p>
            </div>
            <p class="text-[11px] text-text-secondary leading-relaxed">
              目前仅支持通过<strong class="text-text-primary">兑换码</strong>激活会员。兑换码通过以下方式获取：
            </p>
            <ul class="text-[11px] text-text-secondary space-y-1 pl-2">
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>内测邀请 / 内部发放渠道</li>
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>联系管理员或官方客服申请购买</li>
              <li class="flex items-start gap-1.5"><span class="shrink-0 text-blue-400 mt-0.5">•</span>参与官方活动或合作推广</li>
            </ul>
          </div>

          <div class="mb-4 rounded-lg border border-border bg-bg-elevated px-3 py-3">
            <div class="flex items-center gap-2 text-sm">
              <span class="text-text-secondary">当前套餐：</span>
              <span
                class="px-2 py-0.5 rounded-full text-xs font-medium"
                :class="subscriptionTier === 'pro_plus'
                  ? 'bg-violet-500/15 text-violet-300'
                  : subscriptionTier === 'pro'
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'bg-gray-500/15 text-text-muted'"
              >
                {{ tierText(subscriptionTier) }}
              </span>
            </div>
            <p class="mt-1 text-xs text-text-muted">到期时间：{{ formattedExpireAt }}</p>
            <p v-if="subscriptionLoading" class="mt-1 text-[11px] text-text-muted">会员状态加载中...</p>
            <p v-else-if="subscriptionError" class="mt-1 text-[11px] text-[#fd267a]">{{ subscriptionError }}</p>
          </div>

          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">兑换码</label>
            <input
              v-model="redeemCode"
              type="text"
              maxlength="64"
              placeholder="请输入兑换码，如 XXXX-XXXX-XXXX-XXXX"
              class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
            />
          </div>

          <div class="mt-4 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-brand-gradient hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
              :disabled="redeemSaving"
              @click="handleRedeemCode"
            >{{ redeemSaving ? '兑换中...' : '立即兑换' }}</button>
            <span v-if="redeemSuccess" class="text-xs text-green-500">{{ redeemSuccess }}</span>
            <span v-else-if="redeemError" class="text-xs text-[#fd267a]">{{ redeemError }}</span>
          </div>
        </section>

        <!-- ── Section 2: Password ── -->
        <section class="rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-1">密码</h3>
          <p class="text-xs text-text-muted mb-4">
            {{ currentUser?.has_password ? '修改登录密码（需提供旧密码）' : '为账号设置密码，可以使用用户名+密码方式登录' }}
          </p>

          <div class="space-y-3">
            <!-- Old password (only when password exists) -->
            <div v-if="currentUser?.has_password">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">旧密码</label>
              <input
                v-model="pwdOld"
                type="password"
                maxlength="128"
                placeholder="请输入旧密码"
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
              />
            </div>

            <!-- New password -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">{{ currentUser?.has_password ? '新密码' : '密码' }}</label>
              <div class="relative">
                <input
                  v-model="pwdNew"
                  type="password"
                  maxlength="128"
                  placeholder="至少 8 位"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="pwdNewStatus === 'error' ? 'border-red-400/60' : pwdNewStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <span v-if="pwdNewStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <span v-else-if="pwdNewStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="pwdNewMsg" class="text-[11px] text-red-400 mt-1">{{ pwdNewMsg }}</p>
            </div>

            <!-- Confirm password -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">确认密码</label>
              <div class="relative">
                <input
                  v-model="pwdConfirm"
                  type="password"
                  maxlength="128"
                  placeholder="再次输入密码"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="pwdConfirmStatus === 'error' ? 'border-red-400/60' : pwdConfirmStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <span v-if="pwdConfirmStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <span v-else-if="pwdConfirmStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="pwdConfirmMsg" class="text-[11px] text-red-400 mt-1">{{ pwdConfirmMsg }}</p>
            </div>
          </div>

          <div class="mt-5 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-brand-gradient hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
              :disabled="pwdSaving"
              @click="currentUser?.has_password ? handleChangePassword() : handleSetPassword()"
            >{{ pwdSaving ? '保存中...' : (currentUser?.has_password ? '修改密码' : '设置密码') }}</button>
            <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
              <span v-if="pwdSuccess" class="text-xs text-green-500 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                已{{ currentUser?.has_password ? '修改' : '设置' }}
              </span>
              <span v-else-if="pwdError" class="text-xs text-[#fd267a]">{{ pwdError }}</span>
            </Transition>
          </div>
        </section>
      </div>

      <!-- ============================== -->
      <!-- LLM Presets page -->
      <!-- ============================== -->
      <LlmPresetsPanel
        v-else-if="activeNav === 'llm_presets'"
        class="h-full overflow-y-auto"
        @refresh="loadLlmPresets"
      />

      <!-- ============================== -->
      <!-- Prompt Presets page -->
      <!-- ============================== -->
      <PromptPresetsPanel
        v-else-if="activeNav === 'prompt_presets'"
        class="h-full overflow-y-auto"
        @refresh="loadPromptPresets"
      />

      <!-- ============================== -->
      <!-- Feature settings: compare / inspiration -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'compare' || activeNav === 'inspiration'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#8b5cf6] border-r-[#6366f1] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-8">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg v-if="activeNav === 'compare'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" :style="{ color: accentColor(activeNav) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" :style="{ color: accentColor(activeNav) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              {{ activeNav === 'compare' ? '对比分析设置' : activeNav === 'inspiration' ? '灵感涌现设置' : '灵感生成设置' }}
            </h2>
            <p class="text-xs text-text-muted mt-1">
              {{ activeNav === 'compare' ? '配置论文对比分析所使用的大语言模型参数' : activeNav === 'inspiration' ? '配置灵感涌现分析所使用的大语言模型参数' : '配置灵感生成所使用的大语言模型参数' }}
            </p>
          </div>

          <!-- ===== LLM Config Section ===== -->
          <fieldset class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">LLM 连接配置</legend>

            <!-- Preset selector -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-2">选择模型预设</label>
              <PresetSelector
                v-model="form.llm_preset_id"
                :presets="llmPresets"
                :none-option="{ label: '手动配置' }"
                :show-model-hint="true"
                :accent-color="accentColor(activeNav)"
                :on-go-to-create="() => activeNav = 'llm_presets'"
              />
              <p v-if="form.llm_preset_id" class="text-[11px] text-text-muted mt-2 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                使用预设「{{ llmPresets.find(p => p.id === Number(form.llm_preset_id))?.name || '—' }}」中的 URL、Key、Model 等连接参数
              </p>
            </div>

            <!-- Manual config fields (only shown when no preset selected) -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="opacity-0 max-h-0"
              enter-to-class="opacity-100 max-h-[500px]"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="opacity-100 max-h-[500px]"
              leave-to-class="opacity-0 max-h-0"
            >
              <div v-if="!form.llm_preset_id" class="overflow-hidden">
                <!-- LLM Base URL -->
                <div class="mb-4">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
                  <input
                    v-model="form.llm_base_url"
                    type="text"
                    placeholder="例如: https://api.openai.com/v1"
                    class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors"
                    :style="{ '--tw-ring-color': accentColor(activeNav) }"
                    :class="`focus:border-[${accentColor(activeNav)}]`"
                  />
                </div>
                <!-- LLM API Key -->
                <div class="mb-4">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
                  <div class="relative">
                    <input
                      v-model="form.llm_api_key"
                      :type="showApiKey ? 'text' : 'password'"
                      placeholder="sk-..."
                      class="w-full px-3 py-2 pr-10 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors font-mono"
                    />
                    <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-secondary" @click="showApiKey = !showApiKey">
                      <svg v-if="showApiKey" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
                      <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
                    </button>
                  </div>
                </div>
                <!-- LLM Model -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">Model</label>
                  <input
                    v-model="form.llm_model"
                    type="text"
                    placeholder="例如: gpt-4o, claude-sonnet-4-20250514, qwen-plus"
                    class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors"
                  />
                </div>
              </div>
            </Transition>
          </fieldset>

          <!-- ===== System Prompt Section ===== -->
          <fieldset class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">System Prompt</legend>

            <!-- Prompt preset selector -->
            <div class="mb-4">
              <label class="block text-xs font-medium text-text-secondary mb-2">选择提示词预设</label>
              <PresetSelector
                v-model="form.prompt_preset_id"
                :presets="promptPresets"
                :none-option="{ label: '自定义' }"
                accent-color="#059669"
                :on-go-to-create="() => activeNav = 'prompt_presets'"
              />
              <p v-if="form.prompt_preset_id" class="text-[11px] text-text-muted mt-2 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                使用预设「{{ promptPresets.find(p => p.id === Number(form.prompt_preset_id))?.name || '—' }}」作为系统提示词
              </p>
            </div>

            <!-- Custom prompt textarea (only when no preset) -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="opacity-0"
              enter-to-class="opacity-100"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <div v-if="!form.prompt_preset_id">
                <div class="flex items-center justify-between mb-1.5">
                  <label class="text-xs font-medium text-text-secondary">{{ activeNav === 'compare' ? '对比分析系统提示词' : activeNav === 'inspiration' ? '灵感涌现系统提示词' : '灵感生成系统提示词' }}</label>
                  <button
                    v-if="hasDefault('system_prompt')"
                    :disabled="isDefault('system_prompt')"
                    class="shrink-0 px-3 py-1 rounded-lg text-xs border transition-colors"
                    :class="isDefault('system_prompt')
                      ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                      : `border-[${accentColor(activeNav)}]/30 text-[${accentColor(activeNav)}] bg-[${accentColor(activeNav)}]/10 hover:bg-[${accentColor(activeNav)}]/20 cursor-pointer`"
                    :style="!isDefault('system_prompt') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                    @click="resetField('system_prompt')"
                  >恢复默认</button>
                </div>
                <textarea
                  v-model="form.system_prompt"
                  rows="12"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors resize-y leading-relaxed font-mono"
                  placeholder="输入系统提示词..."
                ></textarea>
              </div>
            </Transition>
          </fieldset>

          <!-- ===== Data Source (compare only) ===== -->
          <fieldset v-if="activeNav === 'compare'" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">数据源配置</legend>
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">对比分析数据源</label>
              <div class="flex items-center gap-2">
                <select
                  v-model="form.data_source"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors appearance-none cursor-pointer"
                >
                  <option value="full_text">全文</option>
                  <option value="abstract">原文摘要</option>
                  <option value="summary">系统总结</option>
                </select>
                <button
                  v-if="hasDefault('data_source')"
                  :disabled="isDefault('data_source')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('data_source')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  @click="resetField('data_source')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ { full_text: '全文', abstract: '原文摘要', summary: '系统总结' }[defaults.data_source] || defaults.data_source }}</p>
              <div class="mt-3 text-[11px] text-text-muted space-y-1">
                <p><span class="text-text-secondary font-medium">全文</span> — 使用 MinerU 从 PDF 提取的完整 Markdown 正文</p>
                <p><span class="text-text-secondary font-medium">原文摘要</span> — 仅使用论文原始摘要，Token 消耗最低</p>
                <p><span class="text-text-secondary font-medium">系统总结</span> — 使用系统生成的中文结构化摘要（默认）</p>
              </div>
            </div>
          </fieldset>

          <!-- Data source info for inspiration -->
          <fieldset v-if="activeNav === 'inspiration'" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">数据源</legend>
            <div class="flex items-center gap-2 text-sm text-text-secondary">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>数据源固定为<span class="text-text-primary font-medium">选中的灵感涌现条目内容</span>，无需额外配置。</span>
            </div>
          </fieldset>

          <!-- ===== Generation Parameters (only when using manual config, not preset) ===== -->
          <fieldset v-if="!form.llm_preset_id" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">生成参数</legend>

            <!-- Temperature -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">Temperature</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.temperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('temperature')"
                  :disabled="isDefault('temperature')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('temperature')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('temperature') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('temperature')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.temperature }}</p>
            </div>

            <!-- Max Tokens -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">Max Tokens</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.max_tokens"
                  type="number"
                  step="256"
                  min="256"
                  max="32768"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('max_tokens')"
                  :disabled="isDefault('max_tokens')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('max_tokens')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('max_tokens') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('max_tokens')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.max_tokens }}</p>
            </div>

            <!-- Input Hard Limit -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">输入硬上限 (Input Hard Limit)</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.input_hard_limit"
                  type="number"
                  step="1024"
                  min="1024"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('input_hard_limit')"
                  :disabled="isDefault('input_hard_limit')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('input_hard_limit')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('input_hard_limit') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('input_hard_limit')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_hard_limit }}</p>
            </div>

            <!-- Input Safety Margin -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">安全边距 (Safety Margin)</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.input_safety_margin"
                  type="number"
                  step="256"
                  min="0"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('input_safety_margin')"
                  :disabled="isDefault('input_safety_margin')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('input_safety_margin')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('input_safety_margin') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('input_safety_margin')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_safety_margin }}</p>
            </div>
          </fieldset>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8">
            <div class="text-xs">
              <Transition
                enter-active-class="transition duration-200 ease-out"
                enter-from-class="opacity-0"
                enter-to-class="opacity-100"
                leave-active-class="transition duration-150 ease-in"
                leave-from-class="opacity-100"
                leave-to-class="opacity-0"
              >
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving
                ? 'opacity-50 cursor-not-allowed'
                : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? accentColor(activeNav) + '80' : `linear-gradient(135deg, #6366f1, ${accentColor(activeNav)})`,
                boxShadow: saving ? 'none' : `0 10px 25px ${accentColor(activeNav)}33`,
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Idea Generate Config page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'idea_generate'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#f97316] border-r-[#fb923c] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-6">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#f97316]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              灵感生成配置
            </h2>
            <p class="text-xs text-text-muted mt-1">
              为各处理阶段配置大语言模型与提示词预设，未配置时使用系统默认值。
            </p>
          </div>

          <!-- ===== 全局 LLM 兜底配置 ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🌐</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">全局默认模型</h3>
                <p class="text-[11px] text-text-muted">当某阶段未单独配置模型时使用此预设；也可手动填写 URL/Key/Model</p>
              </div>
            </div>
            <div class="px-5 py-4">
              <!-- Global LLM preset selector -->
              <div class="mb-3">
                <label class="block text-xs font-medium text-text-secondary mb-2">选择全局模型预设</label>
                <PresetSelector
                  v-model="form.llm_preset_id"
                  :presets="llmPresets"
                  :none-option="{ label: '手动配置' }"
                  :show-model-hint="true"
                  accent-color="#f97316"
                  :on-go-to-create="() => activeNav = 'llm_presets'"
                />
              </div>
              <!-- Manual config (when no preset) -->
              <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 max-h-0" enter-to-class="opacity-100 max-h-[300px]" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100 max-h-[300px]" leave-to-class="opacity-0 max-h-0">
                <div v-if="!form.llm_preset_id" class="overflow-hidden mt-3 space-y-3">
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">API URL</label>
                    <input v-model="form.llm_base_url" type="text" placeholder="https://api.openai.com/v1" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">API Key</label>
                    <input v-model="form.llm_api_key" type="password" placeholder="sk-..." class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">Model</label>
                    <input v-model="form.llm_model" type="text" placeholder="例如: gpt-4o, claude-sonnet-4" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                </div>
              </Transition>
            </div>
          </div>

          <!-- ===== 级联策略说明卡片 (idea_generate) ===== -->
          <div class="mb-4 rounded-xl border border-[#f97316]/30 bg-[#f97316]/5 p-4">
            <div class="flex items-start gap-3">
              <span class="text-lg shrink-0 mt-0.5">💡</span>
              <div class="flex-1 min-w-0">
                <h4 class="text-sm font-semibold text-text-primary mb-1.5">模型参数取用策略</h4>
                <p class="text-xs text-text-secondary leading-relaxed mb-2">
                  每个阶段的模型按以下优先级解析：<span class="font-medium text-text-primary">阶段专用预设 → 全局预设 → 首阶段预设（原子抽取）→ 系统默认</span>。
                </p>
                <p class="text-xs text-text-secondary leading-relaxed mb-2">
                  这意味着：<strong class="text-text-primary">只需为「原子抽取」设置自定义模型</strong>，后续所有阶段（研究问题、灵感候选、评审、修订等）将自动继承该模型，无需逐一配置。
                </p>
                <div class="flex items-center gap-1.5 mt-2 p-2 bg-green-500/10 rounded-lg border border-green-500/20">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-green-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                  <span class="text-[11px] text-green-400/90">推荐策略：仅配置首阶段预设，使用默认级联，避免重复配置且大幅降低使用成本。</span>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 阶段模块配置卡片 ===== -->
          <div v-for="mod in ideaModules" :key="mod.key" class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Module header -->
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>

            <div class="divide-y divide-border/50">
              <!-- LLM preset row (only show module-specific rows, not the global "plan" row that uses llm_preset_id) -->
              <div v-if="mod.llmFormKey !== 'llm_preset_id'" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-36 shrink-0 flex items-center gap-1.5 pt-1.5">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">专用模型预设</span>
                </div>
                <div class="flex-1 min-w-0">
                  <PresetSelector
                    v-model="form[mod.llmFormKey]"
                    :presets="llmPresets"
                    :show-model-hint="true"
                    accent-color="#f97316"
                    placeholder="使用全局默认"
                    :on-go-to-create="() => activeNav = 'llm_presets'"
                  />
                  <template v-if="!form[mod.llmFormKey] && llmPresets.length > 0">
                    <p v-if="mod.key !== 'ingest' && form.ingest_llm_preset_id" class="text-[11px] text-amber-400/80 mt-1.5 flex items-center gap-1 italic">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                      继承自：原子抽取（{{ llmPresets.find(p => p.id === Number(form.ingest_llm_preset_id))?.name || '已配置' }}）
                    </p>
                    <p v-else class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用全局默认配置</p>
                  </template>
                </div>
              </div>

              <!-- Prompt preset rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.formKey" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-36 shrink-0 flex items-center gap-1.5 pt-1.5">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <PresetSelector
                    v-model="form[prompt.formKey]"
                    :presets="promptPresets"
                    accent-color="#f97316"
                    placeholder="使用系统默认提示词"
                    :on-go-to-create="() => activeNav = 'prompt_presets'"
                  />
                  <p v-if="!form[prompt.formKey] && promptPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认提示词</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8 mt-4">
            <div class="text-xs">
              <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving ? 'opacity-50 cursor-not-allowed' : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? '#f9731680' : 'linear-gradient(135deg, #ea580c, #f97316)',
                boxShadow: saving ? 'none' : '0 10px 25px #f9731633',
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Paper Recommend Config page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'paper_recommend'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#ec4899] border-r-[#f472b6] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-6">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#ec4899]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
              推荐论文参数配置
            </h2>
            <p class="text-xs text-text-muted mt-1">
              为各处理阶段配置大语言模型与提示词预设，未配置时使用系统默认值。
            </p>
          </div>

          <!-- ===== MinerU Token ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🔑</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">MinerU Token</h3>
                <p class="text-[11px] text-text-muted">用于 PDF 解析的 MinerU 服务凭证；留空则使用系统默认配置</p>
              </div>
            </div>
            <div class="px-5 py-4 flex items-center gap-2">
              <div class="relative flex-1">
                <input
                  v-model="form.mineru_token"
                  :type="mineruTokenVisible ? 'text' : 'password'"
                  placeholder="留空使用系统配置"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors pr-10 font-mono"
                />
                <button
                  class="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors text-xs select-none"
                  @click="mineruTokenVisible = !mineruTokenVisible"
                >{{ mineruTokenVisible ? '🙈' : '👁' }}</button>
              </div>
            </div>
          </div>

          <!-- ===== 级联策略说明卡片 (paper_recommend) ===== -->
          <div class="mb-4 rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
            <div class="flex items-start gap-3">
              <span class="text-lg shrink-0 mt-0.5">💡</span>
              <div class="flex-1 min-w-0">
                <h4 class="text-sm font-semibold text-text-primary mb-1.5">模型参数取用策略</h4>
                <p class="text-xs text-text-secondary leading-relaxed mb-2">
                  每个步骤的模型按以下优先级解析：<span class="font-medium text-text-primary">步骤专用预设 → 全局预设 → 首步骤预设（主题评分）→ 系统默认</span>。
                </p>
                <p class="text-xs text-text-secondary leading-relaxed mb-2">
                  这意味着：<strong class="text-text-primary">只需为「主题相关性评分」设置自定义模型</strong>，后续所有步骤（机构判别、摘要生成、摘要精简等）将自动继承该模型，无需逐一配置。
                </p>
                <div class="flex items-center gap-1.5 mt-2 p-2 bg-green-500/10 rounded-lg border border-green-500/20">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-green-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                  <span class="text-[11px] text-green-400/90">推荐策略：仅配置首步骤预设，使用默认级联，避免重复配置且大幅降低使用成本。</span>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 功能模块配置卡片 ===== -->
          <div v-for="mod in recommendModules" :key="mod.key" class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Module header — matches admin style -->
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>

            <div class="divide-y divide-border/50">
              <!-- LLM preset row -->
              <div class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5 pt-1.5">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">调用模型预设</span>
                </div>
                <div class="flex-1 min-w-0">
                  <PresetSelector
                    v-model="form[mod.llmFormKey]"
                    :presets="llmPresets"
                    :show-model-hint="true"
                    accent-color="#ec4899"
                    placeholder="使用全局默认"
                    :on-go-to-create="() => activeNav = 'llm_presets'"
                  />
                  <template v-if="!form[mod.llmFormKey] && llmPresets.length > 0">
                    <p v-if="mod.key !== 'theme_select' && form.theme_select_llm_preset_id" class="text-[11px] text-amber-400/80 mt-1.5 flex items-center gap-1 italic">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                      继承自：主题相关性评分（{{ llmPresets.find(p => p.id === Number(form.theme_select_llm_preset_id))?.name || '已配置' }}）
                    </p>
                    <p v-else class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认配置</p>
                  </template>
                </div>
              </div>

              <!-- Prompt preset rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.formKey" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5 pt-1.5">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <PresetSelector
                    v-model="form[prompt.formKey]"
                    :presets="promptPresets"
                    accent-color="#059669"
                    placeholder="使用系统默认提示词"
                    :on-go-to-create="() => activeNav = 'prompt_presets'"
                  />
                  <p v-if="!form[prompt.formKey] && promptPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认配置</p>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 字数上限配置 ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">📏</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">字数上限配置</h3>
                <p class="text-[11px] text-text-muted">控制摘要各部分的字数上限（按去空白字符计），超出则调用模型压缩</p>
              </div>
            </div>

            <div class="p-5">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <!-- section_limit_intro -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">文章简介</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_intro"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_intro')"
                      :disabled="isDefault('section_limit_intro')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_intro') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_intro')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_intro }}</p>
                </div>

                <!-- section_limit_method -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">重点思路</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_method"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_method')"
                      :disabled="isDefault('section_limit_method')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_method') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_method')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_method }}</p>
                </div>

                <!-- section_limit_findings -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">分析总结</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_findings"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_findings')"
                      :disabled="isDefault('section_limit_findings')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_findings') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_findings')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_findings }}</p>
                </div>

                <!-- section_limit_opinion -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">个人观点</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_opinion"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_opinion')"
                      :disabled="isDefault('section_limit_opinion')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_opinion') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_opinion')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_opinion }}</p>
                </div>
              </div>

              <!-- headline_limit -->
              <div class="mt-4 pt-4 border-t border-border/50">
                <label class="block text-xs font-medium text-text-secondary mb-1.5">首行字数上限</label>
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="form.headline_limit"
                    type="number" step="1" min="10" max="50"
                    class="w-40 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                  />
                  <button
                    v-if="hasDefault('headline_limit')"
                    :disabled="isDefault('headline_limit')"
                    class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                    :class="isDefault('headline_limit') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                    @click="resetField('headline_limit')"
                  >重置</button>
                  <span class="text-[11px] text-text-muted">默认: {{ defaults.headline_limit }}</span>
                </div>
                <p class="text-[10px] text-text-muted mt-1">「机构：一句话概括」的首行长度上限</p>
              </div>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8">
            <div class="text-xs">
              <Transition
                enter-active-class="transition duration-200 ease-out"
                enter-from-class="opacity-0"
                enter-to-class="opacity-100"
                leave-active-class="transition duration-150 ease-in"
                leave-from-class="opacity-100"
                leave-to-class="opacity-0"
              >
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving
                ? 'opacity-50 cursor-not-allowed'
                : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? '#ec489980' : 'linear-gradient(135deg, #db2777, #ec4899)',
                boxShadow: saving ? 'none' : '0 10px 25px #ec489933',
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Placeholder for disabled features -->
      <!-- ============================== -->
      <AutoClassifyPanel v-else-if="activeNav === 'auto_classify'" />

      <div v-else class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-bg-elevated flex items-center justify-center">
            <span class="text-3xl opacity-30">
              <span v-if="activeNav === 'paper_summary'">📄</span>
              <span v-else-if="activeNav === 'theme_filter'">🔍</span>
              <span v-else>⚙️</span>
            </span>
          </div>
          <h3 class="text-sm font-semibold text-text-muted mb-1">{{ navItems.find(i => i.key === activeNav)?.label }}</h3>
          <p class="text-xs text-text-muted">此功能即将推出，敬请期待</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-sidebar {
  width: var(--settings-sidebar-w);
}
</style>
