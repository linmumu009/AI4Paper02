import { http } from './http'
import type {
  EngagementSignInStatusResponse,
  EngagementRecordTaskPayload,
  EngagementActiveForFeatureResponse,
  EngagementUseRewardResponse,
  EngagementRewardGrant,
  ActivityCalendarEntry,
  ActivityCalendarResponse,
  EngagementStreakFreezeStatus,
} from '../types/engagement'

// Re-export from canonical types — use these instead of locally-defined duplicates
export type { ActivityCalendarEntry, ActivityCalendarResponse } from '../types/engagement'
/** @deprecated Use EngagementStreakFreezeStatus from shared/types/engagement */
export type { EngagementStreakFreezeStatus as StreakFreezeStatus } from '../types/engagement'

export async function fetchEngagementSignInStatus(): Promise<EngagementSignInStatusResponse> {
  const { data } = await http.get<EngagementSignInStatusResponse>('/engagement/signin-status')
  return data
}

export async function recordEngagementTask(payload: EngagementRecordTaskPayload): Promise<EngagementSignInStatusResponse> {
  const { data } = await http.post<EngagementSignInStatusResponse>('/engagement/tasks/record', payload)
  return data
}

export async function fetchEngagementRewards(params?: {
  status?: string
  page?: number
  page_size?: number
}): Promise<{ rewards: EngagementRewardGrant[]; total: number }> {
  const { data } = await http.get<{ rewards: EngagementRewardGrant[]; total: number }>('/engagement/rewards', { params })
  return data
}

export async function fetchActiveRewardsForFeature(feature: string): Promise<EngagementActiveForFeatureResponse> {
  const { data } = await http.get<EngagementActiveForFeatureResponse>('/engagement/rewards/active-for-feature', { params: { feature } })
  return data
}

export async function useEngagementReward(rewardId: number, context: string): Promise<EngagementUseRewardResponse> {
  const { data } = await http.post<EngagementUseRewardResponse>(`/engagement/rewards/${rewardId}/use`, { context })
  return data
}

export async function fetchActivityCalendar(days = 60): Promise<ActivityCalendarResponse> {
  const { data } = await http.get<ActivityCalendarResponse>('/engagement/activity-calendar', { params: { days } })
  return data
}

export async function fetchStreakFreezeStatus(): Promise<EngagementStreakFreezeStatus> {
  const { data } = await http.get<EngagementStreakFreezeStatus>('/engagement/freeze-status')
  return data
}

export async function useStreakFreeze(): Promise<{ success: boolean; message: string }> {
  const { data } = await http.post<{ success: boolean; message: string }>('/engagement/freeze')
  return data
}
