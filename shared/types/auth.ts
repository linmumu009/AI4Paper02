export type UserRole = 'user' | 'admin' | 'superadmin'
export type UserTier = 'free' | 'pro' | 'pro_plus'

export interface AuthUser {
  id: number
  username: string
  nickname?: string
  role: UserRole
  tier: UserTier
  tier_expires_at?: string | null
  phone?: string | null
  phone_verified?: boolean
  is_phone_auto_created?: boolean
  is_disabled?: boolean
  has_password?: boolean
  created_at: string
  updated_at: string
  last_login_at?: string | null
}

export interface AuthPayload {
  username: string
  password: string
}

export interface AuthRegisterPayload {
  username: string
  password: string
  phone: string
  sms_token: string
}

export interface AuthSmsLoginPayload {
  phone: string
  code: string
}

export interface SmsSendPayload {
  phone: string
}

export interface SmsSendResponse {
  ok: boolean
  message: string
}

export interface SmsVerifyPayload {
  phone: string
  code: string
}

export interface SmsVerifyResponse {
  ok: boolean
  message: string
}

export interface AuthActionResponse {
  ok: boolean
  user: AuthUser
  is_new_user?: boolean
}

export interface AuthMeResponse {
  authenticated: boolean
  user: AuthUser | null
}

export interface AuthLogoutResponse {
  ok: boolean
}

export interface AdminUsersResponse {
  users: AuthUser[]
}

export interface AdminUserDetailResponse {
  user: AuthUser
  active_sessions: number
  subscription_history: SubscriptionHistoryRecord[]
}

export interface SubscriptionStatusResponse {
  ok: boolean
  tier: UserTier
  tier_label: string
  tier_expires_at: string | null
  days_left: number | null
}

export interface SubscriptionRedeemResponse {
  ok: boolean
  user: AuthUser
  batch_id: string
  plan_tier: UserTier
  duration_days: number
}

export interface AdminIssueRedeemKeysResponse {
  ok: boolean
  batch_id: string
  plan_tier: UserTier
  duration_days: number
  key_count: number
  expire_at: string | null
  codes: string[]
}

export interface AdminRedeemKeyRecord {
  id: number
  plan_tier: UserTier
  duration_days: number
  max_uses: number
  used_count: number
  expire_at: string | null
  status: 'active' | 'disabled' | 'consumed'
  batch_id: string
  created_at: string
  created_by_user_id?: number | null
  last_used_at?: string | null
  last_used_by_user_id?: number | null
}

export interface AdminRedeemKeyListResponse {
  ok: boolean
  keys: AdminRedeemKeyRecord[]
}

export interface SubscriptionHistoryRecord {
  id: number
  source: string
  source_ref: string | null
  from_tier: UserTier | 'free'
  to_tier: UserTier | 'free'
  start_at: string
  end_at: string | null
  note: string | null
  created_at: string
}

export interface SubscriptionHistoryResponse {
  ok: boolean
  history: SubscriptionHistoryRecord[]
}

// ---------------------------------------------------------------------------
// Announcement types (公告)
// ---------------------------------------------------------------------------

export type AnnouncementTag = 'important' | 'general' | 'update' | 'maintenance'

export interface Announcement {
  id: number
  title: string
  content: string
  tag: AnnouncementTag
  is_pinned: boolean
  created_by: number | null
  created_at: string
  updated_at: string
  is_read?: boolean
}

export interface AnnouncementsResponse {
  ok: boolean
  announcements: Announcement[]
  total: number
}

export interface AnnouncementResponse {
  ok: boolean
  announcement: Announcement
}
