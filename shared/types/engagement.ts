// ---------------------------------------------------------------------------
// Engagement (任务签到)
// ---------------------------------------------------------------------------

export interface EngagementTaskProgress {
  tasks: {
    view: boolean
    collect: boolean
    analyze: boolean
  }
  progress_count: number
  target_count: number
  completed: boolean
}

export interface EngagementStreakInfo {
  current: number
  longest: number
  milestones: number[]
  next_milestones: number[]
}

export interface EngagementRewardBoost {
  upload_priority?: number
  compare_items_delta?: number
  input_hard_limit_multiplier?: number
  max_top_n?: number
  atoms_limit_multiplier?: number
}

export interface EngagementRewardGrant {
  id?: number
  day_key?: string
  streak_day: number
  reward_code: string
  reward_name: string
  description: string
  status?: 'active' | 'used' | 'expired'
  expires_at?: string | null
  used_at?: string | null
  used_context?: string | null
  created_at?: string
  payload?: Record<string, unknown>
  boost?: EngagementRewardBoost
}

export interface EngagementActiveForFeatureResponse {
  ok: boolean
  feature: string
  rewards: EngagementRewardGrant[]
}

export interface EngagementUseRewardResponse {
  ok: boolean
  id: number
  reward_code: string
  reward_name: string
  description: string
  status: 'used'
  used_at: string
  used_context: string
  boost: EngagementRewardBoost
}

export interface EngagementStreakFreezeStatus {
  freeze_allowed: boolean
  freeze_quota: number
  freeze_used: number
  freeze_remaining: number
  streak_would_break: boolean
  missed_day: string | null
}

/** @deprecated Use EngagementStreakFreezeStatus */
export type StreakFreezeStatus = EngagementStreakFreezeStatus

export interface ActivityCalendarEntry {
  day_key: string
  completed: boolean
  partial: boolean
  tasks_done: number
}

export interface ActivityCalendarResponse {
  ok: boolean
  days: number
  today: string
  calendar: ActivityCalendarEntry[]
}

export interface EngagementStatusPayload {
  day_key: string
  progress: EngagementTaskProgress
  streak: EngagementStreakInfo
  rewards: EngagementRewardGrant[]
  freeze?: EngagementStreakFreezeStatus
  action?: 'view' | 'collect' | 'analyze'
  source?: string
  target_id?: string
  just_completed?: boolean
  just_granted_reward?: EngagementRewardGrant | null
  tier?: string
  trial_granted?: boolean
}

export interface EngagementSignInStatusResponse extends EngagementStatusPayload {
  ok: boolean
}

export interface EngagementRecordTaskPayload {
  action: 'view' | 'collect' | 'analyze'
  source?: string
  target_id?: string
}

// ---------------------------------------------------------------------------
// Entitlement types
// ---------------------------------------------------------------------------

export interface QuotaStatus {
  limit: number | null
  used: number
  remaining: number | null
  period: 'daily' | 'monthly' | 'total' | null
}

export interface EntitlementGates {
  general_chat: boolean
  note_file_upload: boolean
  llm_preset: boolean
  prompt_preset: boolean
  export_docx_pdf: boolean
  batch_export: boolean
  translate: boolean
}

export interface EntitlementStorageItem {
  limit: number | null
  used: number
  remaining: number | null
}

export interface EntitlementStorage {
  kb_papers: EntitlementStorageItem
  kb_folders: EntitlementStorageItem
  kb_notes: EntitlementStorageItem
  kb_compare_results: EntitlementStorageItem
}

export interface UserEntitlements {
  tier: 'free' | 'pro' | 'pro_plus'
  tier_label: string
  quotas: {
    chat: QuotaStatus
    compare: QuotaStatus
    research: QuotaStatus
    idea_gen: QuotaStatus
    upload: QuotaStatus
    translate: QuotaStatus
    export: QuotaStatus
  }
  gates: EntitlementGates
  storage: EntitlementStorage
  session_caps: {
    compare_max_items: number
  }
  retention: {
    research_history_days: number | null
  }
  browse: {
    limit: number | null
  }
}
