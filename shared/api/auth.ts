import { http } from './http'
import type {
  AuthPayload, AuthRegisterPayload, AuthSmsLoginPayload,
  SmsSendPayload, SmsSendResponse, SmsVerifyPayload, SmsVerifyResponse,
  AuthActionResponse, AuthMeResponse, AuthLogoutResponse,
  AdminUsersResponse, AdminUserDetailResponse,
  SubscriptionStatusResponse, SubscriptionRedeemResponse, SubscriptionHistoryResponse,
  AdminIssueRedeemKeysResponse, AdminRedeemKeyListResponse,
  UserTier, UserRole,
} from '../types/auth'

export async function authSendSms(payload: SmsSendPayload): Promise<SmsSendResponse> {
  const { data } = await http.post<SmsSendResponse>('/auth/sms/send', payload)
  return data
}

export async function authVerifySms(payload: SmsVerifyPayload): Promise<SmsVerifyResponse> {
  const { data } = await http.post<SmsVerifyResponse>('/auth/sms/verify', payload)
  return data
}

export async function authRegister(payload: AuthRegisterPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/register', payload)
  return data
}

export async function authLogin(payload: AuthPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login', payload)
  return data
}

export async function authLoginSms(payload: AuthSmsLoginPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login/sms', payload)
  return data
}

export async function authMe(): Promise<AuthMeResponse> {
  const { data } = await http.get<AuthMeResponse>('/auth/me')
  return data
}

export async function checkUsername(username: string, excludeUserId?: number): Promise<{ available: boolean; message: string }> {
  const params: Record<string, any> = { username }
  if (excludeUserId !== undefined) params.exclude_user_id = excludeUserId
  const { data } = await http.get<{ available: boolean; message: string }>('/auth/check-username', { params })
  return data
}

export async function authLogout(): Promise<AuthLogoutResponse> {
  const { data } = await http.post<AuthLogoutResponse>('/auth/logout')
  return data
}

export async function fetchAuthProfile(): Promise<AuthActionResponse> {
  const { data } = await http.get<AuthActionResponse>('/auth/profile')
  return data
}

export async function updateAuthProfile(payload: { nickname?: string; username?: string }): Promise<AuthActionResponse> {
  const { data } = await http.put<AuthActionResponse>('/auth/profile', payload)
  return data
}

export async function setAuthPassword(payload: { password: string }): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/set-password', payload)
  return data
}

export async function changeAuthPassword(payload: { old_password: string; new_password: string }): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/change-password', payload)
  return data
}

export async function fetchSubscriptionStatus(): Promise<SubscriptionStatusResponse> {
  const { data } = await http.get<SubscriptionStatusResponse>('/subscription/me')
  return data
}

export async function redeemSubscriptionKey(payload: { code: string; device_id?: string }): Promise<SubscriptionRedeemResponse> {
  const { data } = await http.post<SubscriptionRedeemResponse>('/subscription/redeem', payload)
  return data
}

export async function fetchSubscriptionHistory(): Promise<SubscriptionHistoryResponse> {
  const { data } = await http.get<SubscriptionHistoryResponse>('/subscription/history')
  return data
}

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  const { data } = await http.get<AdminUsersResponse>('/admin/users')
  return data
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetailResponse> {
  const { data } = await http.get<AdminUserDetailResponse>(`/admin/users/${userId}/detail`)
  return data
}

export async function updateAdminUserTier(userId: number, tier: UserTier): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/tier`, { tier })
  return data
}

export async function updateAdminUserRole(userId: number, role: UserRole): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/role`, { role })
  return data
}

export async function issueAdminRedeemKeys(payload: {
  plan_tier: 'pro' | 'pro_plus'
  duration_days: number
  key_count: number
  valid_days?: number | null
  max_uses?: number
  note?: string
}): Promise<AdminIssueRedeemKeysResponse> {
  const { data } = await http.post<AdminIssueRedeemKeysResponse>('/admin/subscription/keys/batch', payload)
  return data
}

export async function fetchAdminRedeemKeys(params?: {
  status?: string
  plan_tier?: string
}): Promise<AdminRedeemKeyListResponse> {
  const { data } = await http.get<AdminRedeemKeyListResponse>('/admin/subscription/keys', { params })
  return data
}

export async function disableAdminRedeemKey(keyId: number): Promise<{ ok: boolean }> {
  const { data } = await http.patch<{ ok: boolean }>(`/admin/subscription/keys/${keyId}/disable`)
  return data
}

export async function adminResetUserPassword(userId: number, newPassword: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>(`/admin/users/${userId}/reset-password`, { new_password: newPassword })
  return data
}

export async function adminForceLogout(userId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/admin/users/${userId}/force-logout`)
  return data
}

export async function adminDisableUser(userId: number): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/disable`)
  return data
}

export async function adminEnableUser(userId: number): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/enable`)
  return data
}

export async function adminDeleteUser(userId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/admin/users/${userId}`)
  return data
}
