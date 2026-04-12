import { computed, ref } from 'vue'
import {
  fetchActiveRewardsForFeature,
  fetchEngagementSignInStatus,
  recordEngagementTask,
  useStreakFreeze,
} from '../api'
import type { EngagementRewardGrant, EngagementSignInStatusResponse, EngagementStreakFreezeStatus } from '../types/engagement'
import { useEntitlements } from './useEntitlements'

const status = ref<EngagementSignInStatusResponse | null>(null)
const loading = ref(false)
const loaded = ref(false)
const loadError = ref(false)
const streakBroken = ref(false)
const newRewardCodes = ref(new Set<string>())
const activeRewardsChat = ref<EngagementRewardGrant[]>([])
const activeRewardsIdeaGen = ref<EngagementRewardGrant[]>([])
const activeRewardsCompare = ref<EngagementRewardGrant[]>([])
const activeRewardsResearch = ref<EngagementRewardGrant[]>([])
const activeRewardsUpload = ref<EngagementRewardGrant[]>([])

const _HONORARY_CODES = new Set(['day1_focus_badge', 'day14_researcher_badge', 'day100_legend_badge'])

export function isHonoraryReward(code: string): boolean {
  return _HONORARY_CODES.has(code)
}

export function rewardIcon(code: string, day?: number): string {
  if (code?.includes('chat_boost')) return '💬'
  if (code?.includes('idea_boost')) return '💡'
  if (code?.includes('compare')) return '🔬'
  if (code?.includes('research_accelerator') || code?.includes('research_premium')) return '⚡'
  if (code?.includes('fast_track')) return '🚀'
  if (code?.includes('badge')) return '🏆'
  if (day !== undefined) {
    if (day >= 7) return '🏆'
    if (day >= 5) return '⭐'
    if (day >= 3) return '🔥'
    if (day >= 2) return '💬'
  }
  return '🌱'
}

export function rewardStatusLabel(s: string | undefined): string {
  if (s === 'active') return '可使用'
  if (s === 'used') return '已使用'
  if (s === 'expired') return '已过期'
  return s ?? ''
}

export function rewardStatusColor(s: string | undefined): string {
  if (s === 'active') return 'text-tinder-green'
  if (s === 'used') return 'text-text-muted'
  return 'text-tinder-pink'
}

export function rewardStatusClass(s: string | undefined): string {
  if (s === 'active') return 'bg-tinder-green/15 text-tinder-green'
  if (s === 'used') return 'bg-bg-elevated text-text-muted'
  if (s === 'expired') return 'bg-red-500/10 text-red-400'
  return 'bg-bg-elevated text-text-muted'
}

export interface MilestoneRewardPreview {
  name: string
  code: string
  brief: string
}

export const MILESTONE_REWARD_PREVIEW: Record<number, MilestoneRewardPreview> = {
  1:   { name: '研究启动徽章',   code: 'day1_focus_badge',              brief: '永久荣誉徽章，代表你研究习惯的起点' },
  2:   { name: '对话增强券',     code: 'day2_chat_boost_ticket',         brief: '发起 AI 对话时使用，AI 可读取 1.5 倍论文上下文，理解更全面' },
  3:   { name: '快速处理加速券', code: 'day3_fast_track_ticket',         brief: '上传论文时插队优先处理，不用等待排队' },
  4:   { name: '灵感增强券',     code: 'day4_idea_boost_ticket',         brief: '生成研究灵感时 AI 读取 1.5 倍知识原子，灵感更多元深入' },
  5:   { name: '扩展对比券',     code: 'day5_compare_plus_ticket',       brief: '在当前套餐基础上额外 +2 篇对比名额，横向比较更多论文' },
  7:   { name: '深度研究加速券', code: 'day7_research_accelerator',      brief: '深度研究时获得 1.5 倍上下文额度和 30 篇精选范围，让 AI 分析更深入' },
  14:  { name: '研究达人徽章',   code: 'day14_researcher_badge',         brief: '永久荣誉徽章 + 免费用户额外解锁 3 天 Pro 试用' },
  30:  { name: '高级对比券',     code: 'day30_compare_premium_ticket',   brief: '在当前套餐基础上额外 +4 篇对比名额，适合做系统性文献综述' },
  60:  { name: '全能研究券',     code: 'day60_research_premium_ticket',  brief: '2 倍上下文 + 30 篇精选范围 + 额外 +4 篇对比名额，一张券全面增强' },
  100: { name: '传奇研究者徽章', code: 'day100_legend_badge',            brief: '永久荣誉徽章，100 天连续研究的见证' },
}

export interface RewardUsageHint {
  text: string
  route?: string
  routeLabel?: string
}

export const REWARD_USAGE_HINTS: Record<string, RewardUsageHint> = {
  day2_chat_boost_ticket: { text: '打开任意论文详情页或通用助手，在对话框附近开启此券。下次对话 AI 可读取 1.5 倍的论文上下文，回答更深入', route: '/', routeLabel: '去发起对话' },
  day3_fast_track_ticket: { text: '下次上传论文时，在上传对话框中打开此券——论文会跳过普通队列优先处理，省去等待', route: '/my-papers', routeLabel: '去上传论文' },
  day4_idea_boost_ticket: { text: '打开灵感生成面板，在生成前开启此券。AI 将从 1.5 倍的知识原子池中提取灵感，生成更多元、更有深度的研究方向', route: '/', routeLabel: '去生成灵感' },
  day5_compare_plus_ticket: { text: '打开日报或灵感页面，选中多篇论文发起对比，对比面板会显示此券。开启后在当前套餐基础上额外 +2 篇对比名额', route: '/', routeLabel: '去发起对比' },
  day7_research_accelerator: { text: '发起深度研究时，在研究面板顶部开启此券。AI 获得 1.5 倍上下文额度和最多 30 篇精选范围，分析结果更完整', route: '/', routeLabel: '去发起深度研究' },
  day30_compare_premium_ticket: { text: '发起论文对比时，在对比面板中使用此券，在当前套餐基础上额外 +4 篇对比名额——适合做系统性文献综述', route: '/', routeLabel: '去发起对比' },
  day60_research_premium_ticket: { text: '发起深度研究或对比时，在对应面板中开启此券：2 倍上下文 + 最多 30 篇精选 + 额外 +4 篇对比名额，一券全覆盖', route: '/', routeLabel: '去发起研究或对比' },
}

export interface EngagementToastItem {
  id: number
  type: 'completion' | 'milestone' | 'streak_break' | 'reward_expiring' | 'reward_error' | 'task_done' | 'reward_used' | 'freeze_success' | 'freeze_error' | 'pro_trial'
  streak?: number
  action?: 'view' | 'collect' | 'analyze'
  reward?: { reward_name: string; description: string; streak_day: number; reward_code: string }
  message?: string
  nextMilestone?: { day: number; name: string; brief: string }
}

const toastQueue = ref<EngagementToastItem[]>([])
let _toastId = 0
let _streakBreakNotified = false
const _expiringNotified = new Set<number>()

export interface TaskItem {
  key: 'view' | 'collect' | 'analyze'
  label: string
  hint: string
  done: boolean
}

export function useEngagement() {
  const progressText = computed(() => {
    const p = status.value?.progress
    if (!p) return '今日研究进度：0/3'
    return `今日研究进度：${p.progress_count}/${p.target_count}`
  })

  const streakText = computed(() => {
    const s = status.value?.streak
    if (!s) return '连续有效研究日：0'
    const next = s.next_milestones?.[0]
    return next ? `连续有效研究日：${s.current}（下个里程碑：第 ${next} 天）` : `连续有效研究日：${s.current}`
  })

  const taskItems = computed<TaskItem[]>(() => {
    const tasks = status.value?.progress?.tasks
    return [
      { key: 'view',    label: '浏览', hint: '打开任意论文详情或 PDF',           done: tasks?.view    ?? false },
      { key: 'collect', label: '收藏', hint: '右滑或点击收藏论文',               done: tasks?.collect ?? false },
      { key: 'analyze', label: '分析', hint: '向 AI 提问、发起对比或深度研究',    done: tasks?.analyze ?? false },
    ]
  })

  const allDone = computed(() => status.value?.progress?.completed ?? false)

  async function loadStatus(force = false) {
    if (loading.value) return
    if (loaded.value && !force) return
    loading.value = true
    try {
      status.value = await fetchEngagementSignInStatus()
      loaded.value = true
      loadError.value = false

      if (!_streakBreakNotified) {
        const streak = status.value?.streak
        if (streak && streak.current === 0 && streak.longest > 0) {
          _streakBreakNotified = true
          streakBroken.value = true
          toastQueue.value.push({ id: ++_toastId, type: 'streak_break' })
        }
      }

      const rewards = status.value?.rewards ?? []
      for (const r of rewards) {
        if (r.status !== 'active' || !r.expires_at) continue
        if (isHonoraryReward(r.reward_code)) continue
        const rid = r.id ?? 0
        if (rid && _expiringNotified.has(rid)) continue
        const diffDays = Math.ceil((new Date(r.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
        if (diffDays <= 3 && diffDays >= 0) {
          if (rid) _expiringNotified.add(rid)
          const expiryMsg = diffDays === 0 ? '今日到期，请及时使用' : `还剩 ${diffDays} 天到期`
          toastQueue.value.push({
            id: ++_toastId, type: 'reward_expiring', message: expiryMsg,
            reward: { reward_name: r.reward_name, description: r.description, streak_day: r.streak_day, reward_code: r.reward_code },
          })
          break
        }
      }
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
    }
  }

  async function record(action: 'view' | 'collect' | 'analyze', source: string, targetId?: string) {
    try {
      const prevTasks = status.value?.progress?.tasks
      const wasAlreadyDone = prevTasks?.[action] ?? false
      const next = await recordEngagementTask({ action, source, target_id: targetId })
      status.value = next
      loaded.value = true

      const nowDone = next.progress?.tasks?.[action] ?? false
      if (!wasAlreadyDone && nowDone && !next.just_completed) {
        toastQueue.value.push({ id: ++_toastId, type: 'task_done', action })
      }

      if (next.just_completed) {
        const nextMsDay = next.streak?.next_milestones?.[0]
        const nextMsPreview = nextMsDay ? MILESTONE_REWARD_PREVIEW[nextMsDay] : undefined
        toastQueue.value.push({
          id: ++_toastId, type: 'completion', streak: next.streak?.current,
          nextMilestone: nextMsPreview && nextMsDay ? { day: nextMsDay, name: nextMsPreview.name, brief: nextMsPreview.brief } : undefined,
        })
      }

      if (next.just_granted_reward) {
        const r = next.just_granted_reward
        newRewardCodes.value = new Set([...Array.from(newRewardCodes.value), r.reward_code])
        toastQueue.value.push({
          id: ++_toastId, type: 'milestone', streak: next.streak?.current,
          reward: { reward_name: r.reward_name, description: r.description, streak_day: r.streak_day, reward_code: r.reward_code ?? '' },
        })
      }

      if ((next as any).just_granted_pro_trial) {
        const trial = (next as any).just_granted_pro_trial as { message: string; trial_days: number; trial_expires_at: string }
        toastQueue.value.push({ id: ++_toastId, type: 'pro_trial', message: trial.message })
        try {
          const ent = useEntitlements()
          await ent.refreshEntitlements(true)
        } catch { /* best-effort */ }
      }

      return next
    } catch {
      return null
    }
  }

  function dismissToast(id: number) {
    const idx = toastQueue.value.findIndex(t => t.id === id)
    if (idx >= 0) toastQueue.value.splice(idx, 1)
  }

  function dismissStreakBroken() { streakBroken.value = false }
  function markRewardsRead() { newRewardCodes.value = new Set() }
  function isNewReward(code: string): boolean { return newRewardCodes.value.has(code) }
  const hasNewRewards = computed(() => newRewardCodes.value.size > 0)
  function notifyRewardUsed(rewardName: string) {
    toastQueue.value.push({ id: ++_toastId, type: 'reward_used', message: rewardName })
  }

  const freezeStatus = computed<EngagementStreakFreezeStatus | null>(() => status.value?.freeze ?? null)

  async function applyStreakFreeze(): Promise<boolean> {
    try {
      const result = await useStreakFreeze()
      if (result.success) {
        toastQueue.value.push({ id: ++_toastId, type: 'freeze_success', message: result.message })
        await loadStatus(true)
        return true
      }
      return false
    } catch (e: any) {
      const detail = e?.response?.data?.detail || '连续保护使用失败，请稍后重试'
      toastQueue.value.push({ id: ++_toastId, type: 'freeze_error', message: detail })
      return false
    }
  }

  async function loadActiveRewards(feature: 'chat' | 'idea_gen' | 'compare' | 'research' | 'upload') {
    try {
      const res = await fetchActiveRewardsForFeature(feature)
      if (feature === 'chat') activeRewardsChat.value = res.rewards
      else if (feature === 'idea_gen') activeRewardsIdeaGen.value = res.rewards
      else if (feature === 'compare') activeRewardsCompare.value = res.rewards
      else if (feature === 'research') activeRewardsResearch.value = res.rewards
      else if (feature === 'upload') activeRewardsUpload.value = res.rewards
    } catch { /* best-effort */ }
  }

  const bestChatReward = computed<EngagementRewardGrant | null>(() => {
    const rewards = activeRewardsChat.value.filter(r => r.status === 'active')
    if (!rewards.length) return null
    return rewards.reduce((best, r) => ((r.boost?.input_hard_limit_multiplier ?? 1) > (best.boost?.input_hard_limit_multiplier ?? 1) ? r : best))
  })
  const bestIdeaGenReward = computed<EngagementRewardGrant | null>(() => activeRewardsIdeaGen.value.filter(r => r.status === 'active')[0] ?? null)
  const bestCompareReward = computed<EngagementRewardGrant | null>(() => {
    const rewards = activeRewardsCompare.value.filter(r => r.status === 'active')
    if (!rewards.length) return null
    return rewards.reduce((best, r) => ((r.boost?.compare_items_delta ?? 0) > (best.boost?.compare_items_delta ?? 0) ? r : best))
  })
  const bestResearchReward = computed<EngagementRewardGrant | null>(() => {
    const rewards = activeRewardsResearch.value.filter(r => r.status === 'active')
    if (!rewards.length) return null
    return rewards.reduce((best, r) => ((r.boost?.input_hard_limit_multiplier ?? 1) > (best.boost?.input_hard_limit_multiplier ?? 1) ? r : best))
  })
  const bestUploadReward = computed<EngagementRewardGrant | null>(() => activeRewardsUpload.value.filter(r => r.status === 'active')[0] ?? null)

  const highestBadge = computed<{ code: string; name: string; emoji: string } | null>(() => {
    const rewards = status.value?.rewards ?? []
    const badgeOrder = ['day100_legend_badge', 'day14_researcher_badge', 'day1_focus_badge']
    const emojiMap: Record<string, string> = { day100_legend_badge: '🌟', day14_researcher_badge: '🎓', day1_focus_badge: '🌱' }
    for (const code of badgeOrder) {
      const r = rewards.find(r => r.reward_code === code)
      if (r) return { code, name: r.reward_name, emoji: emojiMap[code] ?? '🏆' }
    }
    return null
  })

  return {
    status, loading, loaded, loadError, streakBroken, toastQueue,
    progressText, streakText, taskItems, allDone,
    loadStatus, record, dismissToast, dismissStreakBroken,
    hasNewRewards, isNewReward, markRewardsRead, notifyRewardUsed,
    activeRewardsChat, activeRewardsIdeaGen, activeRewardsCompare, activeRewardsResearch, activeRewardsUpload,
    bestChatReward, bestIdeaGenReward, bestCompareReward, bestResearchReward, bestUploadReward,
    loadActiveRewards, highestBadge, freezeStatus, applyStreakFreeze,
  }
}
