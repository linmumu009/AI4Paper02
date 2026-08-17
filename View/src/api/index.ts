// ============================================================================
// View/src/api/index.ts — Transport initialization + compatibility layer
//
// All networking now goes through the shared ApiClient/ApiTransport system:
//   - BrowserTransport  (default)  — web dev preview via Vite proxy
//   - TauriTransport               — production Tauri desktop via Rust IPC
//
// The `http` re-exported below is a Proxy that always delegates to the
// active transport's Axios instance.  Existing View components import
// specific functions from this file and continue to work without change.
// ============================================================================

import { configureTransport, apiClient, http } from '@shared/api/client'
import { TauriTransport } from '@shared/api/transport/tauri'
import { toApiKbScope, type KbScope } from './knowledgeBase'
import type {
  DatesResponse,
  PapersResponse,
  PaperDetailResponse,
  DigestResponse,
  PipelineStatusResponse,
  EngagementSignInStatusResponse,
  EngagementRecordTaskPayload,
  EngagementRewardGrant,
  EngagementActiveForFeatureResponse,
  EngagementUseRewardResponse,
  KbTree,
  KbFolder,
  KbPaper,
  KbNote,
  KbNotesResponse,
  KbAnnotation,
  KbAnnotationsResponse,
  KbCompareResult,
  KbCompareResultsTree,
  PaperSummary,
  AuthPayload,
  AuthRegisterPayload,
  AuthSmsLoginPayload,
  SmsSendPayload,
  SmsSendResponse,
  SmsVerifyPayload,
  SmsVerifyResponse,
  AuthActionResponse,
  AuthMeResponse,
  AuthLogoutResponse,
  UserPaper,
  UserPapersListResponse,
  UserPaperProcessStatusResponse,
  UserPaperTranslateStatusResponse,
  UserPaperFilesResponse,
  UserPaperTree,
  AdminUsersResponse,
  AdminUserDetailResponse,
  SubscriptionStatusResponse,
  SubscriptionRedeemResponse,
  AdminIssueRedeemKeysResponse,
  AdminRedeemKeyListResponse,
  UserTier,
  UserRole,
  PipelineRunStatus,
  PipelineStepConfigResponse,
  ScheduleConfig,
  SystemConfigResponse,
  SystemConfigUpdateResponse,
  ChatMessage,
  ChatHistoryResponse,
} from '../types/paper'

// ---------------------------------------------------------------------------
// API origin + transport setup
// ---------------------------------------------------------------------------

function _normaliseApiBase(raw: string): string {
  let s = (raw || '').trim().replace(/\/+$/, '')
  if (s.toLowerCase().endsWith('/api')) s = s.slice(0, -4)
  return s
}

export const API_ORIGIN: string = import.meta.env.PROD
  ? _normaliseApiBase(import.meta.env.VITE_API_BASE || '')
  : ''

const HAS_TAURI_RUNTIME = typeof window !== 'undefined' && Boolean(
  (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__,
)

if (import.meta.env.PROD && HAS_TAURI_RUNTIME && !API_ORIGIN) {
  console.error(
    '[AI4Papers] VITE_API_BASE is not configured — all API requests will fail in the ' +
    'desktop app.  Set VITE_API_BASE=https://your-server.com in exe/.env.production and rebuild.',
  )
}

/** True when running inside the Tauri desktop shell. */
export const IS_TAURI = HAS_TAURI_RUNTIME && !!API_ORIGIN

if (IS_TAURI) {
  configureTransport(new TauriTransport(API_ORIGIN))
}

// ---------------------------------------------------------------------------
// Compatibility shims for components that import these symbols from '../api'
// ---------------------------------------------------------------------------

/** Read the current session token (Tauri: localStorage; browser: empty string). */
export function getSessionToken(): string { return apiClient.getToken() }
/** Persist a session token (used after login in Tauri). */
export function setSessionToken(token: string): void { apiClient.setToken(token) }
/** Remove the persisted session token. */
export function clearSessionToken(): void { apiClient.clearToken() }

/** Fetch plain text via the active transport (Tauri-safe). */
export async function tauriFetchText(url: string): Promise<string> {
  return apiClient.fetchText(url)
}
/** Fetch a PDF and return a Blob URL (Tauri-safe). */
export async function tauriFetchPdfBlobUrl(url: string): Promise<string> {
  return apiClient.fetchPdfBlobUrl(url)
}

// Re-export the shared http proxy so any component that does
//   `import { http } from '../api'` continues to compile.
export { http }

/** 获取所有可用日期 */
export async function fetchDates(): Promise<DatesResponse> {
  const { data } = await http.get<DatesResponse>('/dates')
  return data
}

/** 获取某天的论文列表 */
export async function fetchPapers(
  date: string,
  search?: string,
  institution?: string,
): Promise<PapersResponse> {
  const { data } = await http.get<PapersResponse>('/papers', {
    params: { date, search: search || undefined, institution: institution || undefined },
  })
  return data
}

const paperDetailRequests = new Map<string, Promise<PaperDetailResponse>>()

/** 获取单篇论文详情；并发中的相同 ID 共享同一个请求。 */
export function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const existing = paperDetailRequests.get(paperId)
  if (existing) return existing

  const request = http
    .get<PaperDetailResponse>(`/papers/${paperId}`)
    .then(({ data }) => data)
  paperDetailRequests.set(paperId, request)
  request.then(
    () => {
      if (paperDetailRequests.get(paperId) === request) paperDetailRequests.delete(paperId)
    },
    () => {
      if (paperDetailRequests.get(paperId) === request) paperDetailRequests.delete(paperId)
    },
  )
  return request
}

/** 获取每日摘要 */
export async function fetchDigest(date: string): Promise<DigestResponse> {
  const { data } = await http.get<DigestResponse>(`/digest/${date}`)
  return data
}

/** 获取 Pipeline 状态 */
export async function fetchPipelineStatus(date: string): Promise<PipelineStatusResponse> {
  const { data } = await http.get<PipelineStatusResponse>('/pipeline/status', {
    params: { date },
  })
  return data
}

export * from './knowledgeBase'

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

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
  // Belt-and-suspenders for desktop: explicitly persist session_id even though
  // the response interceptor already does this.  Covers edge cases where the
  // interceptor fires before JSON parsing completes or the adapter path differs.
  if (API_ORIGIN) {
    const sid = (data as any)?.session_id
    if (sid) setSessionToken(sid)
  }
  return data
}

export async function authLoginSms(payload: AuthSmsLoginPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login/sms', payload)
  if (API_ORIGIN) {
    const sid = (data as any)?.session_id
    if (sid) setSessionToken(sid)
  }
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

export async function updateAuthProfile(payload: {
  nickname?: string
  username?: string
}): Promise<AuthActionResponse> {
  const { data } = await http.put<AuthActionResponse>('/auth/profile', payload)
  return data
}

export async function setAuthPassword(payload: { password: string }): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/set-password', payload)
  return data
}

export async function changeAuthPassword(payload: {
  old_password: string
  new_password: string
}): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/change-password', payload)
  return data
}

// ---------------------------------------------------------------------------
// Subscription API
// ---------------------------------------------------------------------------

export async function fetchSubscriptionStatus(): Promise<SubscriptionStatusResponse> {
  const { data } = await http.get<SubscriptionStatusResponse>('/subscription/me')
  return data
}

export async function redeemSubscriptionKey(payload: {
  code: string
  device_id?: string
}): Promise<SubscriptionRedeemResponse> {
  const { data } = await http.post<SubscriptionRedeemResponse>('/subscription/redeem', payload)
  return data
}

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  const { data } = await http.get<AdminUsersResponse>('/admin/users')
  return data
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetailResponse> {
  const { data } = await http.get<AdminUserDetailResponse>(`/admin/users/${userId}/detail`)
  return data
}

export async function updateAdminUserTier(
  userId: number,
  tier: UserTier,
): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/tier`, { tier })
  return data
}

export async function updateAdminUserRole(
  userId: number,
  role: UserRole,
): Promise<AuthActionResponse> {
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
  batch_id?: string
  limit?: number
}): Promise<AdminRedeemKeyListResponse> {
  const { data } = await http.get<AdminRedeemKeyListResponse>('/admin/subscription/keys', { params })
  return data
}

export async function disableAdminRedeemKey(keyId: number): Promise<{ ok: boolean }> {
  const { data } = await http.patch<{ ok: boolean }>(`/admin/subscription/keys/${keyId}/disable`)
  return data
}

export async function adminResetUserPassword(
  userId: number,
  newPassword: string,
): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>(`/admin/users/${userId}/reset-password`, {
    new_password: newPassword,
  })
  return data
}

export async function adminForceLogout(
  userId: number,
): Promise<{ ok: boolean; sessions_deleted: number }> {
  const { data } = await http.post<{ ok: boolean; sessions_deleted: number }>(
    `/admin/users/${userId}/force-logout`,
  )
  return data
}

export async function adminDisableUser(userId: number): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>(`/admin/users/${userId}/disable`)
  return data
}

export async function adminEnableUser(userId: number): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>(`/admin/users/${userId}/enable`)
  return data
}

export async function adminDeleteUser(userId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/admin/users/${userId}`)
  return data
}

// ---------------------------------------------------------------------------
// Pipeline API
// ---------------------------------------------------------------------------

export async function runPipeline(params: {
  pipeline?: string
  date?: string
  sllm?: number | null
  zo?: string
  force?: boolean
  /** 多用户编排模式：shared + per_user（含所有自定义配置用户） */
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
  // Arxiv 检索参数
  days?: number | null
  categories?: string | null
  extra_query?: string | null
  max_papers?: number | null
  anchor_tz?: string | null
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/run', params)
  return data
}

export async function getPipelineRunStatus(): Promise<PipelineRunStatus> {
  const { data } = await http.get<PipelineRunStatus>('/admin/pipeline/status')
  return data
}

export async function stopPipeline(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/stop')
  return data
}

export async function fetchPipelineStepConfig(): Promise<PipelineStepConfigResponse> {
  const { data } = await http.get<PipelineStepConfigResponse>('/admin/pipeline/step-config')
  return data
}

export async function savePipelineStepConfig(config: Record<string, boolean>): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/step-config', { config })
  return data
}

export async function resetPipelineStepConfig(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/step-config/reset')
  return data
}

export async function getScheduleConfig(): Promise<ScheduleConfig> {
  const { data } = await http.get<ScheduleConfig>('/admin/schedule')
  return data
}

export async function updateScheduleConfig(config: {
  enabled: boolean
  hour: number
  minute: number
  pipeline?: string
  sllm?: number | null
  zo?: string
  user_id?: number | null
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
}): Promise<{ ok: boolean; schedule: ScheduleConfig }> {
  const { data } = await http.post<{ ok: boolean; schedule: ScheduleConfig }>('/admin/schedule', config)
  return data
}

export interface ScheduleHistoryRecord {
  run_id: string
  trigger: string
  date_str: string
  started_at: string
  finished_at: string | null
  user_count: number
  user_ids: number[]
  exit_code: number | null
  success: boolean
  pipeline?: string
}

export async function getScheduleHistory(limit = 50): Promise<ScheduleHistoryRecord[]> {
  const { data } = await http.get<{ records: ScheduleHistoryRecord[]; total: number }>(
    '/admin/schedule/history',
    { params: { limit } },
  )
  return data.records
}

// ---------------------------------------------------------------------------
// User Settings API
// ---------------------------------------------------------------------------

export interface UserSettingsResponse {
  ok: boolean
  feature: string
  settings: Record<string, any>
  defaults: Record<string, any>
}

/** 获取指定功能的用户设置（含默认值） */
export async function fetchUserSettings(feature: string): Promise<UserSettingsResponse> {
  const { data } = await http.get<UserSettingsResponse>(`/user/settings/${feature}`)
  return data
}

/** 保存指定功能的用户设置 */
export async function saveUserSettings(feature: string, settings: Record<string, any>): Promise<UserSettingsResponse> {
  const { data } = await http.put<UserSettingsResponse>(`/user/settings/${feature}`, { settings })
  return data
}

// ---------------------------------------------------------------------------
// System Config API
// ---------------------------------------------------------------------------

/** 获取系统配置 */
export async function getSystemConfig(): Promise<SystemConfigResponse> {
  const { data } = await http.get<SystemConfigResponse>('/admin/config')
  return data
}

/** 更新系统配置 */
export async function updateSystemConfig(config: Record<string, any>): Promise<SystemConfigUpdateResponse> {
  const { data } = await http.post<SystemConfigUpdateResponse>('/admin/config', { config })
  return data
}

/** 重置系统配置为默认值 */
export async function resetSystemConfig(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/config/reset')
  return data
}

// ---------------------------------------------------------------------------
// Feature Defaults API (AI 功能默认配置)
// ---------------------------------------------------------------------------

export interface AdminFeatureDefaultEntry {
  feature: string
  has_admin_overrides: boolean
  effective_defaults: Record<string, any>
  hardcoded_defaults: Record<string, any>
  admin_overrides: Record<string, any>
}

export interface AdminFeatureDefaultsListResponse {
  ok: boolean
  features: AdminFeatureDefaultEntry[]
}

export interface AdminFeatureDefaultResponse {
  ok: boolean
  feature: string
  effective_defaults: Record<string, any>
  hardcoded_defaults: Record<string, any>
  admin_overrides: Record<string, any>
  has_admin_overrides: boolean
}

/** 获取所有 AI 功能的默认配置 */
export async function fetchAdminFeatureDefaults(): Promise<AdminFeatureDefaultsListResponse> {
  const { data } = await http.get<AdminFeatureDefaultsListResponse>('/admin/feature-defaults')
  return data
}

/** 获取单个 AI 功能的默认配置 */
export async function fetchAdminFeatureDefault(feature: string): Promise<AdminFeatureDefaultResponse> {
  const { data } = await http.get<AdminFeatureDefaultResponse>(`/admin/feature-defaults/${feature}`)
  return data
}

/** 保存 AI 功能的管理员默认配置覆盖 */
export async function saveAdminFeatureDefault(feature: string, settings: Record<string, any>): Promise<{ ok: boolean; feature: string; effective_defaults: Record<string, any>; message: string }> {
  const { data } = await http.put(`/admin/feature-defaults/${feature}`, { settings })
  return data
}

/** 重置 AI 功能默认配置为内置默认值 */
export async function resetAdminFeatureDefault(feature: string): Promise<{ ok: boolean; feature: string; message: string }> {
  const { data } = await http.delete(`/admin/feature-defaults/${feature}`)
  return data
}

// ---------------------------------------------------------------------------
// Custom Config Audit API (用户配置审计)
// ---------------------------------------------------------------------------

export interface AuditLlmPresetRef {
  preset_id: number
  preset_name: string
  model: string
  base_url: string
  has_api_key: boolean
  temperature?: number | null
  max_tokens?: number | null
  enable_thinking?: boolean
}

export interface AuditPromptPresetRef {
  preset_id: number
  preset_name: string
  content_preview: string
}

export interface AuditFeatureConfig {
  feature: string
  updated_at: string
  llm_preset_refs: Record<string, AuditLlmPresetRef>
  prompt_preset_refs: Record<string, AuditPromptPresetRef>
  direct_params: Record<string, any>
  has_direct_llm_config: boolean
}

export interface AuditUserRecord {
  user_id: number
  username: string
  tier: string
  role: string
  feature_count: number
  llm_preset_ref_count: number
  prompt_preset_ref_count: number
  total_llm_presets: number
  total_prompt_presets: number
  unused_llm_presets: Array<{ id: number; name: string; model: string; base_url: string; has_api_key: boolean }>
  unused_prompt_presets: Array<{ id: number; name: string; content_preview: string }>
  last_updated: string | null
  feature_configs: AuditFeatureConfig[]
}

export interface CustomConfigAuditResponse {
  ok: boolean
  summary: {
    total_users_with_custom_config: number
    total_active_llm_preset_refs: number
    total_active_prompt_preset_refs: number
    total_unused_llm_presets: number
    total_unused_prompt_presets: number
  }
  users: AuditUserRecord[]
}

export async function fetchAdminCustomConfigs(): Promise<CustomConfigAuditResponse> {
  const { data } = await http.get<CustomConfigAuditResponse>('/admin/users/custom-configs')
  return data
}

// ---------------------------------------------------------------------------
// LLM Config API
// ---------------------------------------------------------------------------

export interface LlmConfig {
  id: number
  name: string
  remark?: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number
  temperature?: number
  concurrency?: number
  input_hard_limit?: number
  input_safety_margin?: number
  endpoint?: string
  completion_window?: string
  out_root?: string
  jsonl_root?: string
  enable_thinking?: boolean
  use_openrouter_free_pool?: boolean
  created_at: string
  updated_at: string
}

export interface LlmConfigsResponse {
  ok: boolean
  configs: LlmConfig[]
}

export interface LlmConfigResponse {
  ok: boolean
  config: LlmConfig
}

export interface ApplyLlmConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有模型配置 */
export async function fetchLlmConfigs(): Promise<LlmConfigsResponse> {
  const { data } = await http.get<LlmConfigsResponse>('/admin/llm-configs')
  return data
}

/** 获取单个模型配置 */
export async function fetchLlmConfig(configId: number): Promise<LlmConfigResponse> {
  const { data } = await http.get<LlmConfigResponse>(`/admin/llm-configs/${configId}`)
  return data
}

/** 创建模型配置 */
export async function createLlmConfig(config: Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>): Promise<LlmConfigResponse> {
  const { data } = await http.post<LlmConfigResponse>('/admin/llm-configs', config)
  return data
}

/** 更新模型配置 */
export async function updateLlmConfig(configId: number, config: Partial<LlmConfig>): Promise<LlmConfigResponse> {
  const { data } = await http.put<LlmConfigResponse>(`/admin/llm-configs/${configId}`, config)
  return data
}

/** 删除模型配置 */
export async function deleteLlmConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/llm-configs/${configId}`)
  return data
}

/** 应用模型配置到config.py */
export async function applyLlmConfig(configId: number, usagePrefix: string): Promise<ApplyLlmConfigResponse> {
  const { data } = await http.post<ApplyLlmConfigResponse>(`/admin/llm-configs/${configId}/apply`, {
    usage_prefix: usagePrefix,
  })
  return data
}

// ---------------------------------------------------------------------------
// OpenRouter Key Pool API
// ---------------------------------------------------------------------------

export interface OpenRouterKeyInfo {
  id: number
  masked_key: string
  enabled: boolean
  used_today: number
  remaining_today: number
}

export interface OpenRouterKeyPoolStatus {
  ok: boolean
  daily_limit: number
  total_keys: number
  available_keys: number
  keys: OpenRouterKeyInfo[]
  message?: string
}

export interface OpenRouterFreeModel {
  id: string
  name: string
  context_length: number | null
}

export interface OpenRouterFreeModelsResponse {
  ok: boolean
  models: OpenRouterFreeModel[]
  total: number
}

/** 获取 OpenRouter Key 池状态（Key 已脱敏） */
export async function fetchOpenRouterKeyPool(): Promise<OpenRouterKeyPoolStatus> {
  const { data } = await http.get<OpenRouterKeyPoolStatus>('/admin/openrouter-key-pool')
  return data
}

/** 保存 OpenRouter Key 池（全量替换，每行一个 Key） */
export async function saveOpenRouterKeyPool(keysText: string, dailyLimit: number): Promise<OpenRouterKeyPoolStatus> {
  const { data } = await http.put<OpenRouterKeyPoolStatus>('/admin/openrouter-key-pool', {
    keys_text: keysText,
    daily_limit: dailyLimit,
  })
  return data
}

/** 从 OpenRouter 拉取免费模型列表 */
export async function fetchOpenRouterFreeModels(): Promise<OpenRouterFreeModelsResponse> {
  const { data } = await http.get<OpenRouterFreeModelsResponse>('/admin/openrouter-free-models')
  return data
}

// ---------------------------------------------------------------------------
// Prompt Config API
// ---------------------------------------------------------------------------

export interface PromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
  created_at: string
  updated_at: string
}

export interface PromptConfigsResponse {
  ok: boolean
  configs: PromptConfig[]
}

export interface PromptConfigResponse {
  ok: boolean
  config: PromptConfig
}

export interface ApplyPromptConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有提示词配置 */
export async function fetchPromptConfigs(): Promise<PromptConfigsResponse> {
  const { data } = await http.get<PromptConfigsResponse>('/admin/prompt-configs')
  return data
}

/** 获取单个提示词配置 */
export async function fetchPromptConfig(configId: number): Promise<PromptConfigResponse> {
  const { data } = await http.get<PromptConfigResponse>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 创建提示词配置 */
export async function createPromptConfig(config: Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>): Promise<PromptConfigResponse> {
  const { data } = await http.post<PromptConfigResponse>('/admin/prompt-configs', config)
  return data
}

/** 更新提示词配置 */
export async function updatePromptConfig(configId: number, config: Partial<PromptConfig>): Promise<PromptConfigResponse> {
  const { data } = await http.put<PromptConfigResponse>(`/admin/prompt-configs/${configId}`, config)
  return data
}

/** 删除提示词配置 */
export async function deletePromptConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 应用提示词配置到config.py */
export async function applyPromptConfig(configId: number, variableName: string): Promise<ApplyPromptConfigResponse> {
  const { data } = await http.post<ApplyPromptConfigResponse>(`/admin/prompt-configs/${configId}/apply`, {
    variable_name: variableName,
  })
  return data
}

export interface BatchApplyItem_Llm {
  config_id: number
  prefix: string
}

export interface BatchApplyItem_Prompt {
  config_id: number
  variable: string
}

export interface BatchApplyConfigResponse {
  ok: boolean
  message: string
  applied_count: number
  errors: string[]
  config: Record<string, any>
}

/** 批量应用模型配置和提示词配置（一次性写入） */
export async function batchApplyConfigs(
  llmApplies: BatchApplyItem_Llm[],
  promptApplies: BatchApplyItem_Prompt[],
): Promise<BatchApplyConfigResponse> {
  const { data } = await http.post<BatchApplyConfigResponse>('/admin/config/batch-apply', {
    llm_applies: llmApplies,
    prompt_applies: promptApplies,
  })
  return data
}

// ---------------------------------------------------------------------------
// User LLM Presets API
// ---------------------------------------------------------------------------

import type { UserLlmPreset, UserPromptPreset } from '../types/paper'

export interface UserLlmPresetsResponse {
  ok: boolean
  presets: UserLlmPreset[]
}

export interface UserLlmPresetResponse {
  ok: boolean
  preset: UserLlmPreset
}

/** 获取用户的所有模型预设 */
export async function fetchUserLlmPresets(): Promise<UserLlmPresetsResponse> {
  const { data } = await http.get<UserLlmPresetsResponse>('/user/llm-presets')
  return data
}

/** 创建模型预设 */
export async function createUserLlmPreset(preset: Omit<UserLlmPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserLlmPresetResponse> {
  const { data } = await http.post<UserLlmPresetResponse>('/user/llm-presets', preset)
  return data
}

/** 更新模型预设 */
export async function updateUserLlmPreset(presetId: number, preset: Partial<UserLlmPreset>): Promise<UserLlmPresetResponse> {
  const { data } = await http.put<UserLlmPresetResponse>(`/user/llm-presets/${presetId}`, preset)
  return data
}

/** 删除模型预设 */
export async function deleteUserLlmPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/llm-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// User Prompt Presets API
// ---------------------------------------------------------------------------

export interface UserPromptPresetsResponse {
  ok: boolean
  presets: UserPromptPreset[]
}

export interface UserPromptPresetResponse {
  ok: boolean
  preset: UserPromptPreset
}

/** 获取用户的所有提示词预设 */
export async function fetchUserPromptPresets(): Promise<UserPromptPresetsResponse> {
  const { data } = await http.get<UserPromptPresetsResponse>('/user/prompt-presets')
  return data
}

/** 创建提示词预设 */
export async function createUserPromptPreset(preset: Omit<UserPromptPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserPromptPresetResponse> {
  const { data } = await http.post<UserPromptPresetResponse>('/user/prompt-presets', preset)
  return data
}

/** 更新提示词预设 */
export async function updateUserPromptPreset(presetId: number, preset: Partial<UserPromptPreset>): Promise<UserPromptPresetResponse> {
  const { data } = await http.put<UserPromptPresetResponse>(`/user/prompt-presets/${presetId}`, preset)
  return data
}

/** 删除提示词预设 */
export async function deleteUserPromptPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/prompt-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// Idea Generation v2 API (灵感生成)
// ---------------------------------------------------------------------------

import type {
  IdeaAtom,
  IdeaCandidate,
  IdeaQuestion,
  IdeaSourcePaper,
  IdeaPlan,
  IdeaFeedback,
  IdeaExemplar,
  IdeaBenchmark,
  IdeaPromptVersion,
  Announcement,
  AnnouncementsResponse,
  AnnouncementResponse,
  SubscriptionHistoryResponse,
} from '../types/paper'

// -- Atoms --

export interface IdeaAtomsResponse { ok: boolean; atoms: IdeaAtom[] }
export interface IdeaAtomResponse { ok: boolean; atom: IdeaAtom }

export async function fetchIdeaAtoms(params?: {
  paper_id?: string; atom_type?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaAtomsResponse> {
  const { data } = await http.get<IdeaAtomsResponse>('/idea/atoms', { params })
  return data
}

export async function fetchIdeaAtom(atomId: number): Promise<IdeaAtomResponse> {
  const { data } = await http.get<IdeaAtomResponse>(`/idea/atoms/${atomId}`)
  return data
}

export interface IdeaQuestionResponse {
  ok: boolean
  question: IdeaQuestion
}

/**
 * 读取单条研究问题的完整内容（含 question_text、strategy、context）。
 * 用于在灵感详情面板显示具体的研究问题文本，替代 "关联研究问题 #N"。
 */
export async function fetchIdeaQuestion(questionId: number): Promise<IdeaQuestionResponse> {
  const { data } = await http.get<IdeaQuestionResponse>(`/idea/questions/${questionId}`)
  return data
}

export interface IdeaSourcePapersResponse {
  ok: boolean
  papers: Record<string, IdeaSourcePaper>
}

/**
 * 批量查询来源论文的轻量元数据（标题、摘要、机构、来源类型）。
 * 后端按优先顺序查找：用户上传论文 → KB 论文 → 推荐流水线论文。
 * @param paperIds 待查询的 paper_id 列表（最多 20 个）
 */
export async function fetchIdeaSourcePapers(
  paperIds: string[],
): Promise<Record<string, IdeaSourcePaper>> {
  if (!paperIds.length) return {}
  const params = new URLSearchParams()
  for (const pid of paperIds) params.append('paper_ids', pid)
  const { data } = await http.get<IdeaSourcePapersResponse>(
    `/idea/source-papers?${params.toString()}`,
  )
  return data.papers ?? {}
}

export async function updateIdeaAtom(atomId: number, payload: Partial<IdeaAtom>): Promise<IdeaAtomResponse> {
  const { data } = await http.patch<IdeaAtomResponse>(`/idea/atoms/${atomId}`, payload)
  return data
}

export async function deleteIdeaAtom(atomId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/atoms/${atomId}`)
  return data
}

export async function extractIdeaAtoms(paperId: string, dateStr?: string): Promise<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }> {
  const { data } = await http.post<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }>('/idea/atoms/extract', {
    paper_id: paperId,
    date_str: dateStr ?? '',
  }, { timeout: 300000 })
  return data
}

// -- Candidates --

export interface IdeaCandidatesResponse { ok: boolean; candidates: IdeaCandidate[] }
export interface IdeaCandidateResponse { ok: boolean; candidate: IdeaCandidate }

export async function fetchIdeaCandidates(params?: {
  status?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaCandidatesResponse> {
  const { data } = await http.get<IdeaCandidatesResponse>('/idea/candidates', { params })
  return data
}

export async function fetchIdeaCandidate(candidateId: number): Promise<IdeaCandidateResponse> {
  const { data } = await http.get<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`)
  return data
}

export async function updateIdeaCandidate(candidateId: number, payload: Partial<IdeaCandidate>): Promise<IdeaCandidateResponse> {
  const { data } = await http.patch<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`, payload)
  return data
}

export async function deleteIdeaCandidate(candidateId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/candidates/${candidateId}`)
  return data
}

export interface GenerateForPaperResponse { candidates: IdeaCandidate[]; count: number }

export async function generateCandidatesForPaper(paperId: string, force = false): Promise<GenerateForPaperResponse> {
  const { data } = await http.post<GenerateForPaperResponse>('/idea/candidates/generate-for-paper', { paper_id: paperId, force }, { timeout: 300000 })
  return data
}

/**
 * Generate idea candidates via SSE stream.
 * Returns a raw Response — caller reads the stream line by line.
 */
export async function generateIdeasStream(
  payload: { question_id?: number; custom_question?: string; strategies?: string[] },
  signal?: AbortSignal,
): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: '/idea/candidates/generate',
    body: payload,
    signal,
  })
}

export async function reviewIdeaCandidate(candidateId: number, payload: {
  action: 'approve' | 'reject' | 'revise'; feedback?: string; scores?: Record<string, number>
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/idea/candidates/${candidateId}/review`, payload)
  return data
}

// -- Plans --

export interface IdeaPlanResponse { ok: boolean; plan: IdeaPlan }

export async function fetchIdeaPlan(candidateId: number): Promise<IdeaPlanResponse> {
  const { data } = await http.get<IdeaPlanResponse>(`/idea/plans/${candidateId}`)
  return data
}

export async function createIdeaPlan(candidateId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.post<IdeaPlanResponse>(`/idea/plans`, { candidate_id: candidateId, ...payload })
  return data
}

export function streamGeneratePlan(_candidateId: number): EventSource {
  throw new Error('Use fetchGeneratePlanStream instead')
}

/**
 * Generate a research plan for a candidate via SSE stream.
 * Returns a raw Response — caller reads the stream line by line.
 */
export async function fetchGeneratePlanStream(
  candidateId: number,
  _rewardId?: number,
  signal?: AbortSignal,
): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: '/idea/plans/generate',
    body: { candidate_id: candidateId },
    signal,
  })
}

export async function updateIdeaPlan(planId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.patch<IdeaPlanResponse>(`/idea/plans/${planId}`, payload)
  return data
}

export async function deleteIdeaPlan(planId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/plans/${planId}`)
  return data
}

// -- Feedback --

export interface IdeaFeedbackResponse { ok: boolean; feedback: IdeaFeedback }
export interface IdeaFeedbackListResponse { ok: boolean; feedback_events: IdeaFeedback[] }

export async function createIdeaFeedback(payload: {
  candidate_id?: number; atom_id?: number; action: string; context?: Record<string, any>
}): Promise<IdeaFeedbackResponse> {
  const { data } = await http.post<IdeaFeedbackResponse>('/idea/feedback', payload)
  return data
}


export async function fetchIdeaFeedback(params?: {
  event_type?: string; candidate_id?: number; atom_id?: number; limit?: number; offset?: number
}): Promise<IdeaFeedbackListResponse> {
  const { data } = await http.get<IdeaFeedbackListResponse>('/idea/feedback', { params })
  return data
}

// -- Exemplars --

export interface IdeaExemplarsResponse { ok: boolean; exemplars: IdeaExemplar[] }
export interface IdeaExemplarResponse { ok: boolean; exemplar: IdeaExemplar }

export async function fetchIdeaExemplars(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaExemplarsResponse> {
  const { data } = await http.get<IdeaExemplarsResponse>('/idea/exemplars', { params })
  return data
}

export async function fetchIdeaExemplar(exemplarId: number): Promise<IdeaExemplarResponse> {
  const { data } = await http.get<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`)
  return data
}

export async function createIdeaExemplar(payload: {
  candidate_id: number; name: string; description?: string; tags?: string[]
}): Promise<IdeaExemplarResponse> {
  const { data } = await http.post<IdeaExemplarResponse>('/idea/exemplars', payload)
  return data
}

export async function updateIdeaExemplar(exemplarId: number, payload: Partial<IdeaExemplar>): Promise<IdeaExemplarResponse> {
  const { data } = await http.patch<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`, payload)
  return data
}

export async function deleteIdeaExemplar(exemplarId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/exemplars/${exemplarId}`)
  return data
}

// -- Benchmarks --

export interface IdeaBenchmarksResponse { ok: boolean; benchmarks: IdeaBenchmark[] }
export interface IdeaBenchmarkResponse { ok: boolean; benchmark: IdeaBenchmark }

export async function fetchIdeaBenchmarks(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaBenchmarksResponse> {
  const { data } = await http.get<IdeaBenchmarksResponse>('/idea/benchmarks', { params })
  return data
}

export async function fetchIdeaBenchmark(benchmarkId: number): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.get<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

export async function createIdeaBenchmark(payload: {
  name: string; description?: string; questions?: string[]; expected_outputs?: string[]
}): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.post<IdeaBenchmarkResponse>('/idea/benchmarks', payload)
  return data
}

export async function updateIdeaBenchmark(benchmarkId: number, payload: Partial<IdeaBenchmark>): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.patch<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`, payload)
  return data
}

export async function deleteIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

// -- Prompt Templates --

export interface IdeaPromptVersionsResponse { ok: boolean; templates: IdeaPromptVersion[] }
export interface IdeaPromptVersionResponse { ok: boolean; template: IdeaPromptVersion }

export async function fetchIdeaPromptVersions(params?: {
  stage?: string; name?: string; is_active?: boolean; limit?: number; offset?: number
}): Promise<IdeaPromptVersionsResponse> {
  const { data } = await http.get<IdeaPromptVersionsResponse>('/idea/prompt-versions', { params })
  return data
}

export async function fetchIdeaPromptVersion(versionId: number): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.get<IdeaPromptVersionResponse>(`/idea/prompt-versions/${versionId}`)
  return data
}

export async function createIdeaPromptVersion(payload: {
  name: string; stage: string; content: string; version?: number; is_active?: boolean
}): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.post<IdeaPromptVersionResponse>('/idea/prompt-versions', payload)
  return data
}

export async function updateIdeaPromptVersion(versionId: number, payload: Partial<IdeaPromptVersion>): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.patch<IdeaPromptVersionResponse>(`/idea/prompt-versions/${versionId}`, payload)
  return data
}

export async function deleteIdeaPromptVersion(versionId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/prompt-versions/${versionId}`)
  return data
}

// -- Stats --

export interface IdeaStatsResponse {
  ok: boolean
  stats: {
    total_atoms: number
    total_candidates: number
    total_approved: number
    total_archived: number
    total_plans: number
    total_exemplars: number
    total_benchmarks: number
    atoms_by_type: Record<string, number>
    candidates_by_status: Record<string, number>
  }
}

export async function fetchIdeaStats(): Promise<IdeaStatsResponse> {
  const { data } = await http.get<IdeaStatsResponse>('/idea/stats')
  return data
}

// -- Idea Digest (permission-filtered, date-scoped) --

export interface IdeaDigestResponse {
  ok: boolean
  candidates: import('../types/paper').IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
  effective_date: string
  is_fallback: boolean
}

/** 获取指定日期的灵感推荐（按用户配额过滤来源论文） */
export async function fetchIdeaDigest(date: string): Promise<IdeaDigestResponse> {
  const { data } = await http.get<IdeaDigestResponse>(`/idea/digest/${date}`)
  return data
}

// ---------------------------------------------------------------------------
// Announcement API (公告)
// ---------------------------------------------------------------------------

/** 获取公告列表 */
export async function fetchAnnouncements(params?: {
  limit?: number
  offset?: number
}): Promise<AnnouncementsResponse> {
  const { data } = await http.get<AnnouncementsResponse>('/announcements', { params })
  return data
}

/** 获取单条公告详情 */
export async function fetchAnnouncementById(id: number): Promise<AnnouncementResponse> {
  const { data } = await http.get<AnnouncementResponse>(`/announcements/${id}`)
  return data
}

/** 管理员创建公告 */
export async function createAnnouncement(payload: {
  title: string
  content: string
  tag?: string
  is_pinned?: boolean
}): Promise<AnnouncementResponse> {
  const { data } = await http.post<AnnouncementResponse>('/admin/announcements', payload)
  return data
}

/** 管理员更新公告 */
export async function updateAnnouncement(
  id: number,
  payload: {
    title?: string
    content?: string
    tag?: string
    is_pinned?: boolean
  },
): Promise<AnnouncementResponse> {
  const { data } = await http.put<AnnouncementResponse>(`/admin/announcements/${id}`, payload)
  return data
}

/** 管理员删除公告 */
export async function deleteAnnouncement(id: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/admin/announcements/${id}`)
  return data
}

/** 获取当前用户未读公告数量 */
export async function fetchUnreadAnnouncementCount(): Promise<{ ok: boolean; count: number }> {
  const { data } = await http.get<{ ok: boolean; count: number }>('/announcements/unread-count')
  return data
}

/** 将指定公告标记为已读 */
export async function markAnnouncementsRead(ids: number[]): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-read', {
    announcement_ids: ids,
  })
  return data
}

/** 将全部公告标记为已读 */
export async function markAllAnnouncementsRead(): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-read', { all: true })
  return data
}

// ---------------------------------------------------------------------------
// Subscription History API (订阅记录)
// ---------------------------------------------------------------------------

/** 获取当前用户订阅变更历史 */
export async function fetchSubscriptionHistory(): Promise<SubscriptionHistoryResponse> {
  const { data } = await http.get<SubscriptionHistoryResponse>('/subscription/history')
  return data
}

// ---------------------------------------------------------------------------
// Admin Analytics API (管理员数据统计分析)
// ---------------------------------------------------------------------------

import type {
  AnalyticsOverviewResponse,
  AnalyticsUsersResponse,
  AnalyticsPapersResponse,
  AnalyticsTrendsResponse,
  AnalyticsFeaturesResponse,
  AnalyticsRetentionResponse,
  AnalyticsEngagementSigninResponse,
  AnalyticsActivationResponse,
  AnalyticsActivatedRetentionResponse,
  AnalyticsContentFunnelResponse,
  AnalyticsValueRetentionResponse,
  AnalyticsContentStepFunnelResponse,
  AnalyticsAiFeatureResponse,
  AnalyticsEngagementDepthResponse,
} from '../types/paper'

/** 获取平台总览统计 */
export async function fetchAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  const { data } = await http.get<AnalyticsOverviewResponse>('/admin/analytics/overview')
  return data
}

/** 获取用户活跃度排行 */
export async function fetchAnalyticsUsers(params?: {
  limit?: number
  offset?: number
}): Promise<AnalyticsUsersResponse> {
  const { data } = await http.get<AnalyticsUsersResponse>('/admin/analytics/users', { params })
  return data
}

/** 获取论文热度排行 */
export async function fetchAnalyticsPapers(params?: {
  limit?: number
}): Promise<AnalyticsPapersResponse> {
  const { data } = await http.get<AnalyticsPapersResponse>('/admin/analytics/papers', { params })
  return data
}

/** 获取趋势数据 */
export async function fetchAnalyticsTrends(params?: {
  days?: number
}): Promise<AnalyticsTrendsResponse> {
  const { data } = await http.get<AnalyticsTrendsResponse>('/admin/analytics/trends', { params })
  return data
}

/** 获取功能使用统计 */
export async function fetchAnalyticsFeatures(): Promise<AnalyticsFeaturesResponse> {
  const { data } = await http.get<AnalyticsFeaturesResponse>('/admin/analytics/features')
  return data
}

/** 获取留存率数据 */
export async function fetchAnalyticsRetention(params?: {
  weeks?: number
}): Promise<AnalyticsRetentionResponse> {
  const { data } = await http.get<AnalyticsRetentionResponse>('/admin/analytics/retention', { params })
  return data
}

/** 获取任务签到漏斗数据（A/B 与止损监控） */
export async function fetchAnalyticsEngagementSignin(params?: {
  days?: number
}): Promise<AnalyticsEngagementSigninResponse> {
  const { data } = await http.get<AnalyticsEngagementSigninResponse>(
    '/admin/analytics/engagement-signin',
    { params },
  )
  return data
}

/** 获取新用户激活漏斗数据 */
export async function fetchAnalyticsActivation(params?: {
  days?: number
  activation_window_days?: number
  tier?: string
}): Promise<AnalyticsActivationResponse> {
  const { data } = await http.get<AnalyticsActivationResponse>('/admin/analytics/activation', { params })
  return data
}

/** 获取激活用户留存数据 */
export async function fetchAnalyticsActivatedRetention(params?: {
  weeks?: number
}): Promise<AnalyticsActivatedRetentionResponse> {
  const { data } = await http.get<AnalyticsActivatedRetentionResponse>('/admin/analytics/activated-retention', { params })
  return data
}

/** 获取内容与功能转化漏斗数据 */
export async function fetchAnalyticsContentFunnel(params?: {
  days?: number
}): Promise<AnalyticsContentFunnelResponse> {
  const { data } = await http.get<AnalyticsContentFunnelResponse>('/admin/analytics/content-funnel', { params })
  return data
}

/** 获取激活用户价值行为留存数据（比会话留存更真实） */
export async function fetchAnalyticsValueRetention(params?: {
  weeks?: number
}): Promise<AnalyticsValueRetentionResponse> {
  const { data } = await http.get<AnalyticsValueRetentionResponse>('/admin/analytics/value-retention', { params })
  return data
}

/** 获取内容漏斗步骤数据（卡片曝光→详情→收藏→深度行为） */
export async function fetchAnalyticsContentStepFunnel(params?: {
  days?: number
}): Promise<AnalyticsContentStepFunnelResponse> {
  const { data } = await http.get<AnalyticsContentStepFunnelResponse>('/admin/analytics/content-step-funnel', { params })
  return data
}

/** 获取 AI 功能采用数据（深度研究 / 论文聊天 / 灵感生成） */
export async function fetchAnalyticsAiFeatures(params?: {
  days?: number
}): Promise<AnalyticsAiFeatureResponse> {
  const { data } = await http.get<AnalyticsAiFeatureResponse>('/admin/analytics/ai-features', { params })
  return data
}

/** 获取参与深度数据（session 时长 + 论文阅读时长） */
export async function fetchAnalyticsEngagementDepth(params?: {
  days?: number
}): Promise<AnalyticsEngagementDepthResponse> {
  const { data } = await http.get<AnalyticsEngagementDepthResponse>('/admin/analytics/engagement-depth', { params })
  return data
}

/** 获取 Pipeline 各步骤数据量追踪 */
export async function fetchPipelineDataTracking(params?: {
  user_id?: number
  days?: number
}): Promise<import('../types/paper').PipelineDataTrackingResponse> {
  const { data } = await http.get('/admin/pipeline/data-tracking', { params })
  return data
}

// ---------------------------------------------------------------------------
// Pipeline Observability – runs / steps / events / artifacts / rerun
// ---------------------------------------------------------------------------

export interface PipelineStepRun {
  id: number; run_id: number; step_name: string; phase: string
  user_id: number; date_str: string
  status: 'pending' | 'running' | 'skipped' | 'soft_failed' | 'failed' | 'completed' | 'cancelled'
  attempt: number; skip_reason: string; error_type: string; error_message: string
  log_file: string; input_params: Record<string, any>; metrics: Record<string, any>
  started_at: string | null; finished_at: string | null; duration_ms: number | null
  exit_code: number | null; created_at: string
}

export interface PipelineArtifact {
  id: number; run_id: number; step_run_id: number; artifact_type: string
  storage: string; path_or_table: string; record_count: number | null
  byte_size: number | null; created_at: string
}

export interface PipelineEvent {
  id: number; run_id: number; step_run_id: number
  level: 'debug' | 'info' | 'warning' | 'error'
  event_type: string; message: string; payload: Record<string, any>; created_at: string
}

export interface PipelineRunRecord {
  id: number; run_type: string; pipeline: string; user_id: number; date_str: string
  status: string; phase: string; trigger: string; parent_run_id: number | null
  started_at: string | null; finished_at: string | null; config: Record<string, any>
  log_file?: string; username?: string; nickname?: string
  step_counts?: Record<string, number>; step_total?: number; step_failed?: number
  step_completed?: number; step_skipped?: number; step_soft_failed?: number
  child_runs?: Array<{ id: number; user_id: number; phase: string; status: string; username?: string; nickname?: string }>
}

export interface PipelineRunLogResponse {
  run_id: number
  has_file: boolean
  lines: string[]
  total_lines: number
  log_file: string
}

export async function fetchPipelineRuns(params?: { limit?: number; date?: string; user_id?: number }): Promise<{ runs: PipelineRunRecord[]; total: number }> {
  const { data } = await http.get<{ runs: PipelineRunRecord[]; total: number }>('/admin/pipeline/runs', { params })
  return data
}

export async function fetchPipelineRunDetail(runId: number): Promise<PipelineRunRecord> {
  const { data } = await http.get<PipelineRunRecord>(`/admin/pipeline/runs/${runId}`)
  return data
}

export async function fetchPipelineRunSteps(runId: number): Promise<{ run_id: number; steps: PipelineStepRun[]; total: number }> {
  const { data } = await http.get<{ run_id: number; steps: PipelineStepRun[]; total: number }>(`/admin/pipeline/runs/${runId}/steps`)
  return data
}

export async function fetchPipelineRunEvents(runId: number, params?: { step_run_id?: number; limit?: number }): Promise<{ run_id: number; events: PipelineEvent[]; total: number }> {
  const { data } = await http.get<{ run_id: number; events: PipelineEvent[]; total: number }>(`/admin/pipeline/runs/${runId}/events`, { params })
  return data
}

export async function fetchPipelineRunArtifacts(runId: number): Promise<{ run_id: number; artifacts: PipelineArtifact[]; total: number }> {
  const { data } = await http.get<{ run_id: number; artifacts: PipelineArtifact[]; total: number }>(`/admin/pipeline/runs/${runId}/artifacts`)
  return data
}

export async function rerunPipeline(params: {
  run_id: number; from_step?: string | null; only_step?: string | null; force?: boolean
}): Promise<{ ok: boolean; message: string; new_run_id: number; log_file: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; new_run_id: number; log_file: string }>('/admin/pipeline/rerun', params)
  return data
}

export async function fetchPipelineRunLog(
  runId: number,
  params?: { tail?: number; full?: boolean },
): Promise<PipelineRunLogResponse> {
  const { data } = await http.get<PipelineRunLogResponse>(`/admin/pipeline/runs/${runId}/log`, { params })
  return data
}

// ---------------------------------------------------------------------------
// Analytics Event Tracking (用户行为事件上报)
// ---------------------------------------------------------------------------

/** 上报单个事件 */
export async function reportAnalyticsEvent(event: {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}): Promise<{ ok: boolean; event_id: number }> {
  const { data } = await http.post<{ ok: boolean; event_id: number }>('/analytics/event', event)
  return data
}

/** 批量上报事件 */
export async function reportAnalyticsEvents(events: Array<{
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}>): Promise<{ ok: boolean; count: number }> {
  const { data } = await http.post<{ ok: boolean; count: number }>('/analytics/events', { events })
  return data
}

// ---------------------------------------------------------------------------
// Engagement API (任务签到)
// ---------------------------------------------------------------------------

/** 获取当前用户任务签到状态 */
export async function fetchEngagementSignInStatus(): Promise<EngagementSignInStatusResponse> {
  const { data } = await http.get<EngagementSignInStatusResponse>('/engagement/signin-status')
  return data
}

/** 上报一次任务动作（view/collect/analyze） */
export async function recordEngagementTask(
  payload: EngagementRecordTaskPayload,
): Promise<EngagementSignInStatusResponse> {
  const { data } = await http.post<EngagementSignInStatusResponse>('/engagement/tasks/record', payload)
  return data
}

/** 获取奖励记录（完整列表，用于成就页面） */
export async function fetchEngagementRewards(params?: {
  status?: 'active' | 'used' | 'expired'
  limit?: number
}): Promise<{ ok: boolean; rewards: EngagementRewardGrant[] }> {
  const { data } = await http.get<{ ok: boolean; rewards: EngagementRewardGrant[] }>(
    '/engagement/rewards',
    { params },
  )
  return data
}

/** 查询某功能下当前用户的可用奖励 */
export async function fetchActiveRewardsForFeature(
  feature: 'chat' | 'idea_gen' | 'compare' | 'research' | 'upload',
): Promise<EngagementActiveForFeatureResponse> {
  const { data } = await http.get<EngagementActiveForFeatureResponse>(
    '/engagement/rewards/active-for-feature',
    { params: { feature } },
  )
  return data
}

/** 核销（使用）一个奖励 */
export async function useEngagementReward(
  rewardId: number,
  context: string,
): Promise<EngagementUseRewardResponse> {
  const { data } = await http.post<EngagementUseRewardResponse>(
    `/engagement/rewards/${rewardId}/use`,
    { context },
  )
  return data
}

export interface ActivityCalendarDay {
  day_key: string
  completed: boolean
  partial: boolean
  tasks_done: number
}

export interface ActivityCalendarResponse {
  ok: boolean
  days: number
  today: string
  calendar: ActivityCalendarDay[]
}

/** 获取用户近 N 天的活动日历（成就页热力图） */
export async function fetchActivityCalendar(days = 60): Promise<ActivityCalendarResponse> {
  const { data } = await http.get<ActivityCalendarResponse>('/engagement/activity-calendar', {
    params: { days },
  })
  return data
}

export interface StreakFreezeStatus {
  freeze_allowed: boolean
  freeze_quota: number
  freeze_used: number
  freeze_remaining: number
  streak_would_break: boolean
  missed_day: string | null
}

/** 获取连续保护状态 */
export async function fetchStreakFreezeStatus(): Promise<StreakFreezeStatus> {
  const { data } = await http.get<StreakFreezeStatus & { ok: boolean }>('/engagement/freeze-status')
  return data
}

/** 使用连续保护冻结昨天的缺失 */
export async function useStreakFreeze(): Promise<{
  ok: boolean
  success: boolean
  message: string
  new_streak: number
  frozen_day: string
  freeze_remaining: number
}> {
  const { data } = await http.post('/engagement/freeze')
  return data
}

// ---------------------------------------------------------------------------
// User-uploaded papers API
// ---------------------------------------------------------------------------

/** 手动录入论文 */
export async function importUserPaperManual(payload: {
  title: string
  authors?: string[]
  abstract?: string
  institution?: string
  year?: number | null
  external_url?: string
}): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/manual', payload)
  return data
}

/** 通过 arXiv ID 导入 */
export async function importUserPaperArxiv(arxivId: string): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/arxiv', { arxiv_id: arxivId })
  return data
}

/** 上传 PDF 并录入论文 */
export async function importUserPaperPdf(
  file: File,
  meta: {
    title?: string
    authors?: string[]
    abstract?: string
    institution?: string
    year?: number | null
    external_url?: string
  } = {},
): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const params: Record<string, string> = {}
  if (meta.title) params.title = meta.title
  if (meta.authors) params.authors = JSON.stringify(meta.authors)
  if (meta.abstract) params.abstract = meta.abstract
  if (meta.institution) params.institution = meta.institution
  if (meta.year != null) params.year = String(meta.year)
  if (meta.external_url) params.external_url = meta.external_url
  const { data } = await http.post<UserPaper>('/user-papers/import/pdf', form, {
    params,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 并发控制：以最多 concurrency 个并发执行 fn(item)，返回 PromiseSettledResult 数组。 */
async function concurrentMap<T, R>(
  items: T[],
  fn: (item: T) => Promise<R>,
  concurrency: number,
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length)
  let index = 0
  async function worker() {
    while (index < items.length) {
      const i = index++
      try {
        const value = await fn(items[i])
        results[i] = { status: 'fulfilled', value }
      } catch (reason: unknown) {
        results[i] = { status: 'rejected', reason }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker))
  return results
}

export async function batchProcessUserPapers(
  paperIds: string[],
  rewardId?: number,
): Promise<{ results: Array<{ paper_id: string; ok: boolean; message: string }>; priority: number; reward_applied: boolean }> {
  const { data } = await http.post('/user-papers/batch-process', {
    paper_ids: paperIds,
    reward_id: rewardId,
  })
  return data
}

function normalizeUserPapersListPayload(data: unknown): UserPapersListResponse {
  let payload = data as any

  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload)
    } catch {
      const preview = (payload as string).slice(0, 120)
      throw new Error(`接口返回非JSON: ${preview}`)
    }
  }

  if (Array.isArray(payload)) {
    return { total: payload.length, papers: payload }
  }

  if (!payload || typeof payload !== 'object') {
    throw new Error(`接口返回类型异常: ${typeof payload}`)
  }

  if (payload.detail) {
    throw new Error(String(payload.detail))
  }

  const papers =
    Array.isArray(payload.papers) ? payload.papers
      : Array.isArray(payload.items) ? payload.items
        : Array.isArray(payload.records) ? payload.records
          : null

  if (!Array.isArray(papers)) {
    const keys = Object.keys(payload).join(',')
    throw new Error(`接口返回缺少papers字段 (keys: ${keys})`)
  }

  const total =
    typeof payload.total === 'number' ? payload.total
      : typeof payload.count === 'number' ? payload.count
        : papers.length

  return { total, papers }
}

/** 获取我的上传论文列表 */
export async function fetchUserPapers(opts?: {
  source_type?: string
  search?: string
  institution?: string
  limit?: number
  offset?: number
}): Promise<UserPapersListResponse> {
  const { data } = await http.get<UserPapersListResponse>('/user-papers', { params: opts })
  return normalizeUserPapersListPayload(data)
}

/** 获取该用户所有不重复机构名列表 */
export async function fetchUserPaperInstitutions(): Promise<string[]> {
  const { data } = await http.get<{ institutions: string[] }>('/user-papers/institutions')
  return Array.isArray(data?.institutions) ? data.institutions : []
}

/** 获取单篇上传论文详情 */
export async function fetchUserPaperDetail(paperId: string): Promise<UserPaper> {
  const { data } = await http.get<UserPaper>(`/user-papers/${paperId}`)
  return data
}

/** 更新论文元数据 */
export async function updateUserPaper(
  paperId: string,
  payload: Partial<{
    title: string
    authors: string[]
    abstract: string
    institution: string
    year: number | null
    external_url: string
  }>,
): Promise<UserPaper> {
  const { data } = await http.patch<UserPaper>(`/user-papers/${paperId}`, payload)
  return data
}

/** 为已录入论文补传 PDF */
export async function uploadUserPaperPdf(paperId: string, file: File): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<UserPaper>(`/user-papers/${paperId}/upload-pdf`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 删除上传论文 */
export async function deleteUserPaper(paperId: string): Promise<{ ok: boolean; paper_id: string }> {
  const { data } = await http.delete<{ ok: boolean; paper_id: string }>(`/user-papers/${paperId}`)
  return data
}

/** 触发单篇论文流水线处理（可选 reward_id 用于快速处理加速券） */
export async function processUserPaper(
  paperId: string,
  rewardId?: number,
): Promise<{ ok: boolean; message: string; paper_id: string; priority?: number; reward_applied?: boolean }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string; priority?: number; reward_applied?: boolean }>(
    `/user-papers/${paperId}/process`,
    rewardId !== undefined ? { reward_id: rewardId } : {},
  )
  return data
}

/** 查询单篇论文处理状态 */
export async function fetchUserPaperProcessStatus(paperId: string): Promise<UserPaperProcessStatusResponse> {
  const { data } = await http.get<UserPaperProcessStatusResponse>(
    `/user-papers/${paperId}/process-status`,
  )
  return data
}

/** 获取我的论文文件夹树 */
export async function fetchUserPaperTree(): Promise<UserPaperTree> {
  const { data } = await http.get<UserPaperTree>('/user-papers/tree')
  return data
}

/** 手动触发 MinerU 全文翻译（中文 + 中英对照） */
export async function translateUserPaper(
  paperId: string,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/translate`,
  )
  return data
}

/** 重新触发全文翻译（与 translate 相同，用于删除译稿后重新生成） */
export async function retranslateUserPaper(
  paperId: string,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/retranslate`,
  )
  return data
}

export type UserPaperDerivativeType = 'mineru' | 'zh' | 'bilingual'

/** 删除 MinerU 解析或翻译产物文件 */
export async function deleteUserPaperDerivative(
  paperId: string,
  derivativeType: UserPaperDerivativeType,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/derivatives/${derivativeType}`,
  )
  return data
}

/** 查询翻译任务状态 */
export async function fetchUserPaperTranslateStatus(
  paperId: string,
): Promise<UserPaperTranslateStatusResponse> {
  const { data } = await http.get<UserPaperTranslateStatusResponse>(
    `/user-papers/${paperId}/translate-status`,
  )
  return data
}

/** 论文关联文件是否存在及静态 URL */
export async function fetchUserPaperFiles(paperId: string): Promise<UserPaperFilesResponse> {
  const { data } = await http.get<UserPaperFilesResponse>(`/user-papers/${paperId}/files`)
  return data
}

/** 批量移动我的论文到目标文件夹 (null = 根目录) */
export async function moveUserPapers(
  paperIds: string[],
  targetFolderId: number | null,
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/user-papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
  })
  return data
}

/** 步骤名 → 中文展示文案 */
export function userPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '等待处理...',
    queued_priority: '等待处理（优先）...',
    starting: '初始化...',
    pdf_prepare: '准备 PDF...',
    pdf_download: '下载 PDF...',
    pdf_mineru: 'MinerU 版面解析中...',
    pdf_extract: '提取文本（PyMuPDF）...',
    pdf_info: '识别机构信息...',
    paper_summary: '生成论文摘要...',
    summary_limit: '精简结构化摘要...',
    paper_assets: '生成结构化分析...',
    done: '处理完成',
    '': '',
  }
  return labels[step] ?? step
}

/** KB 步骤名 → 中文展示文案 */
export function kbPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '等待处理...',
    starting: '初始化...',
    pdf_attach: '查找/复制 PDF...',
    pdf_recover: '重新获取 PDF...',
    pdf_mineru: 'MinerU 版面解析中...',
    pdf_extract: '提取文本（PyMuPDF）...',
    done: '处理完成',
    '': '',
  }
  return labels[step] ?? step
}

// ---------------------------------------------------------------------------
// KB Paper Process / Translate API
// ---------------------------------------------------------------------------

import type {
  KbPaperProcessStatusResponse,
  KbPaperTranslateStatusResponse,
  KbPaperFilesResponse,
} from '../types/paper'

/** 触发 KB 论文 MinerU 解析 */
export async function processKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/process`,
    null,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 查询 KB 论文处理状态 */
export async function fetchKbPaperProcessStatus(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperProcessStatusResponse> {
  const { data } = await http.get<KbPaperProcessStatusResponse>(
    `/kb/papers/${paperId}/process-status`,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 触发 KB 论文翻译 */
export async function translateKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/translate`,
    null,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 重新翻译 KB 论文 */
export async function retranslateKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/retranslate`,
    null,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 查询 KB 论文翻译状态 */
export async function fetchKbPaperTranslateStatus(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperTranslateStatusResponse> {
  const { data } = await http.get<KbPaperTranslateStatusResponse>(
    `/kb/papers/${paperId}/translate-status`,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 获取 KB 论文关联文件静态链接 */
export async function fetchKbPaperFiles(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperFilesResponse> {
  const { data } = await http.get<KbPaperFilesResponse>(
    `/kb/papers/${paperId}/files`,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

/** 删除 KB 论文衍生文件 */
export async function deleteKbPaperDerivative(
  paperId: string,
  derivativeType: 'mineru' | 'zh' | 'bilingual',
  scope: KbScope = 'kb',
): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(
    `/kb/papers/${paperId}/derivatives/${derivativeType}`,
    { params: { scope: toApiKbScope(scope) } },
  )
  return data
}

// ---------------------------------------------------------------------------
// Download API
// ---------------------------------------------------------------------------

/** 下载最新客户端安装包（后端按版本号选择，优先 exe） */
export async function downloadLatestInstaller(): Promise<void> {
  await apiClient.download({
    path: '/download/latest-installer',
    fallbackName: 'AI4Papers-latest.exe',
  })
}

/** 下载单个论文衍生文件（触发浏览器下载） */
export async function downloadPaperFile(
  paperId: string,
  fileType: 'pdf' | 'mineru' | 'zh' | 'bilingual',
  scope: 'kb' | 'mypapers' = 'kb',
  format: 'md' | 'docx' | 'pdf' = 'md',
): Promise<void> {
  const params = new URLSearchParams({ paper_id: paperId, file_type: fileType, scope, format })

  if (fileType === 'bilingual' && format === 'pdf') {
    try {
      const raw = localStorage.getItem('ai4papers-bilingual-theme')
      if (raw) {
        const t = JSON.parse(raw) as Record<string, unknown>
        if (typeof t.hue === 'number') params.set('hue', String(t.hue))
        if (typeof t.saturation === 'number') params.set('sat', String(t.saturation))
        if (typeof t.intensity === 'number') params.set('intensity', String(t.intensity))
        if (typeof t.fontSize === 'number') params.set('font_size', String(t.fontSize))
      }
    } catch { /* 读取失败时后端使用默认值 */ }
  }

  const ext = fileType === 'pdf' ? 'pdf' : format
  const fallbackName = fileType === 'pdf' ? `${paperId}.pdf` : `${paperId}_${fileType}.${ext}`

  await apiClient.download({
    path: `/download/paper-file?${params.toString()}`,
    fallbackName,
  })
}

/** 下载深度研究结果（MD / DOCX / PDF） */
export async function downloadResearchResult(
  sessionId: number,
  format: 'md' | 'docx' | 'pdf' = 'md',
): Promise<void> {
  const ext = format === 'docx' ? 'docx' : format === 'pdf' ? 'pdf' : 'md'
  await apiClient.download({
    path: `/research/${sessionId}/download?format=${format}`,
    fallbackName: `research_${sessionId}.${ext}`,
  })
}

/** 下载/导出笔记（触发浏览器下载） */
export async function downloadNote(noteId: number): Promise<void> {
  await apiClient.download({
    path: `/download/note/${noteId}`,
    fallbackName: `note_${noteId}.md`,
  })
}

export interface BatchDownloadItem {
  paper_id: string
  file_types: ('pdf' | 'mineru' | 'zh' | 'bilingual')[]
  scope: 'kb' | 'mypapers'
  include_notes?: boolean
}

/** 批量下载（返回 zip，触发浏览器保存） */
export async function downloadBatch(items: BatchDownloadItem[]): Promise<void> {
  await apiClient.download({
    path: '/download/batch',
    fallbackName: 'papers_export.zip',
    method: 'POST',
    body: { items },
  })
}

// ---------------------------------------------------------------------------
// Community API
// ---------------------------------------------------------------------------

export interface CommunityPost {
  id: number
  user_id: number
  username: string | null
  category: string
  title: string
  content?: string
  view_count: number
  reply_count: number
  like_count: number
  is_pinned: boolean
  is_closed: boolean
  last_reply_at: string | null
  created_at: string
  updated_at: string
  user_liked?: boolean
  replies?: CommunityReply[]
}

export interface CommunityReply {
  id: number
  post_id: number
  user_id: number
  username: string | null
  content: string
  like_count: number
  parent_reply_id?: number | null
  created_at: string
  updated_at: string
  user_liked?: boolean
}

export interface CommunityPostsResponse {
  total: number
  page: number
  page_size: number
  posts: CommunityPost[]
}

export async function fetchCommunityPosts(params: {
  category?: string
  page?: number
  page_size?: number
  sort?: string
}): Promise<CommunityPostsResponse> {
  const resp = await http.get('/community/posts', { params })
  return resp.data
}

export async function fetchCommunityPost(id: number): Promise<CommunityPost> {
  const resp = await http.get(`/community/posts/${id}`)
  return resp.data
}

export async function createCommunityPost(data: {
  category: string
  title: string
  content: string
}): Promise<CommunityPost> {
  const resp = await http.post('/community/posts', data)
  return resp.data
}

export async function updateCommunityPost(
  id: number,
  data: { category?: string; title?: string; content?: string },
): Promise<CommunityPost> {
  const resp = await http.put(`/community/posts/${id}`, data)
  return resp.data
}

export async function deleteCommunityPost(id: number): Promise<void> {
  await http.delete(`/community/posts/${id}`)
}

export async function createCommunityReply(
  postId: number,
  data: { content: string; parent_reply_id?: number | null },
): Promise<CommunityReply> {
  const resp = await http.post(`/community/posts/${postId}/replies`, data)
  return resp.data
}

export async function updateCommunityReply(
  replyId: number,
  data: { content: string },
): Promise<CommunityReply> {
  const resp = await http.put(`/community/replies/${replyId}`, data)
  return resp.data
}

export async function deleteCommunityReply(replyId: number): Promise<void> {
  await http.delete(`/community/replies/${replyId}`)
}

export async function toggleCommunityLike(
  targetType: 'post' | 'reply',
  targetId: number,
): Promise<{ liked: boolean; like_count: number }> {
  const resp = await http.post('/community/like', { target_type: targetType, target_id: targetId })
  return resp.data
}

export async function pinCommunityPost(
  postId: number,
  pinned: boolean,
): Promise<{ ok: boolean; is_pinned: boolean }> {
  const resp = await http.put(`/community/posts/${postId}/pin`, { pinned })
  return resp.data
}

export async function closeCommunityPost(
  postId: number,
  closed: boolean,
): Promise<{ ok: boolean; is_closed: boolean }> {
  const resp = await http.put(`/community/posts/${postId}/close`, { closed })
  return resp.data
}

// ---------------------------------------------------------------------------
// Deep Research Q&A API
// ---------------------------------------------------------------------------

import type { ResearchSession, ResearchConfig } from '../types/paper'

export interface StartResearchPayload {
  question: string
  paper_ids: string[]
  scope?: string
  config?: ResearchConfig
  signal?: AbortSignal
  reward_id?: number
  project_id?: number
}

export {
  fetchResearchProjects,
  createResearchProject,
  fetchResearchProject,
  updateResearchProject,
  archiveResearchProject,
  restoreResearchProject,
  deleteResearchProject,
  addResearchProjectAsset,
  removeResearchProjectAsset,
} from '@shared/api/projects'

/** Start a deep research session — returns a fetch Response for SSE streaming */
export async function fetchResearchStream(payload: StartResearchPayload): Promise<Response> {
  const { signal, ...body } = payload
  return apiClient.stream({
    method: 'POST',
    path: '/research/start',
    body,
    signal,
  })
}

/** List user's research sessions */
export async function fetchResearchSessions(limit = 20, savedOnly = false): Promise<{ sessions: ResearchSession[] }> {
  const { data } = await http.get<{ sessions: ResearchSession[] }>('/research/sessions', {
    params: { limit, saved_only: savedOnly || undefined },
  })
  return data
}

/** Save or unsave a research session */
export async function saveResearchSession(sessionId: number, saved = true): Promise<void> {
  await http.patch(`/research/${sessionId}/save`, null, { params: { saved } })
}

/** Rename a research session (update its question field) */
export async function renameResearchSession(sessionId: number, question: string): Promise<void> {
  await http.patch(`/research/${sessionId}/rename`, { question })
}

/** Get research session folder tree */
export async function fetchResearchTree(): Promise<import('../types/paper').ResearchTree> {
  const { data } = await http.get('/research/tree')
  return data
}

/** Batch-move research sessions to a target folder (null = root) */
export async function moveResearchSessions(sessionIds: number[], targetFolderId: number | null): Promise<void> {
  await http.patch('/research/move', { session_ids: sessionIds, target_folder_id: targetFolderId })
}

/** Get a single research session with all rounds */
export async function fetchResearchSession(sessionId: number): Promise<ResearchSession> {
  const { data } = await http.get<ResearchSession>(`/research/${sessionId}`)
  return data
}

/** Delete a research session */
export async function deleteResearchSession(sessionId: number): Promise<void> {
  await http.delete(`/research/${sessionId}`)
}

/** Continue a completed session with Round 3 (full-text deep read) — returns a fetch Response for SSE streaming */
export async function fetchResearchContinueRound3(sessionId: number, signal?: AbortSignal): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: `/research/${sessionId}/continue-round3`,
    signal,
  })
}

/** Follow-up on a completed session reusing its R1 results — returns a fetch Response for SSE streaming */
export async function fetchResearchFollowup(
  sessionId: number,
  payload: { question: string; context?: string },
  signal?: AbortSignal,
): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: `/research/${sessionId}/followup`,
    body: payload,
    signal,
  })
}

/** Cancel a running research session so a new one can be started */
export async function cancelResearchSession(sessionId: number): Promise<void> {
  await http.post(`/research/${sessionId}/cancel`)
}

// ---------------------------------------------------------------------------
// Entitlements
// ---------------------------------------------------------------------------

import type { UserEntitlements } from '../types/paper'

/** Fetch current user's full entitlement snapshot (tier, quotas, gates, storage). */
export async function fetchEntitlements(): Promise<UserEntitlements> {
  const { data } = await http.get<UserEntitlements & { ok: boolean }>('/entitlements/me')
  return data
}

// ---------------------------------------------------------------------------
// Auto-classify API
// ---------------------------------------------------------------------------

export interface AutoClassifyFolder {
  name: string
  description: string
  folder_id?: number | null
  parent_id?: number | null
  origin?: 'user' | 'ai' | 'system'
  suggestion_reason?: string
  paper_count?: number
  /** Stable client key used to preserve unsynced parent-child relationships */
  _key?: string
  /** References the parent's client key when it has no folder_id yet */
  _parent_key?: string | null
}

export interface AutoClassifyFolderSuggestion extends AutoClassifyFolder {
  origin: 'ai'
  parent_path: string
  suggestion_reason: string
  paper_ids: string[]
  paper_count: number
}

/** 获取待分类论文数量 */
export async function fetchAutoClassifyPendingCount(scope = 'kb'): Promise<{ pending: number }> {
  const { data } = await http.get<{ pending: number }>('/kb/auto-classify/pending-count', { params: { scope } })
  return data
}

/** 获取「未分类」文件夹中的论文数量，用于提示用户扩充目录 */
export async function fetchAutoClassifyUnclassifiedCount(scope = 'kb'): Promise<{ unclassified: number }> {
  const { data } = await http.get<{ unclassified: number }>('/kb/auto-classify/unclassified-count', { params: { scope } })
  return data
}

/** 根据收藏论文和现有目录生成预览建议；此调用不会创建目录或移动论文 */
export async function suggestAutoClassifyFolders(
  scope = 'kb',
  maxSuggestions = 8,
): Promise<{
  ok: boolean
  suggestions: AutoClassifyFolderSuggestion[]
  analyzed_papers: number
  existing_folders: number
}> {
  const { data } = await http.post(
    '/kb/auto-classify/suggest-folders',
    { scope, max_suggestions: maxSuggestions },
  )
  return data
}

/** 同步分类目录定义到实际 KB 文件夹，返回填充了 folder_id 的列表 */
export async function syncAutoClassifyFolders(
  folders: AutoClassifyFolder[],
  scope = 'kb'
): Promise<{ ok: boolean; folders: AutoClassifyFolder[] }> {
  const { data } = await http.post<{ ok: boolean; folders: AutoClassifyFolder[] }>(
    '/kb/auto-classify/sync-folders',
    { folders, scope }
  )
  return data
}

/** 重新分类知识库中所有论文 */
export async function reclassifyAllKbPapers(scope = 'kb'): Promise<{ ok: boolean; enqueued: number }> {
  const { data } = await http.post<{ ok: boolean; enqueued: number }>(
    '/kb/auto-classify/reclassify-all',
    { scope }
  )
  return data
}

/** 手动触发单篇论文分类 */
export async function classifyKbPaper(paperId: string, scope = 'kb'): Promise<{ ok: boolean; enqueued: boolean }> {
  const { data } = await http.post<{ ok: boolean; enqueued: boolean }>(
    `/kb/papers/${paperId}/classify`,
    null,
    { params: { scope } }
  )
  return data
}

/** 更新知识库论文阅读状态 */
export async function updateKbPaperReadStatus(
  paperId: string,
  status: 'unread' | 'reading' | 'read',
  scope = 'kb'
): Promise<{ ok: boolean }> {
  const { data } = await http.patch<{ ok: boolean }>(
    `/kb/papers/${paperId}/read-status`,
    { status, scope }
  )
  return data
}

// ---------------------------------------------------------------------------
// Preference Learning API
// ---------------------------------------------------------------------------

export interface NudgeBody {
  paper_id: string
  direction: 'more' | 'less'
  categories?: string[]
  keywords?: string[]
  institution_tier?: number
}

export interface CategoryDetail {
  category: string
  weight: number
  direction: 'positive' | 'negative'
  signal_count: number
  last_signal_at: string | null
}

export interface PreferenceProfileSummary {
  has_enough_data: boolean
  total_feedback_count: number
  top_categories: { category: string; weight: number }[]
  top_keywords: { keyword: string; weight: number }[]
  negative_categories: string[]
  positive_category_details: CategoryDetail[]
  negative_category_details: CategoryDetail[]
  min_feedback_needed: number
  built_at: string
  score_weights?: { theme: number; pref: number; novel: number } | null
  exploration_ratio?: number | null
}

export interface CalibrationHistoryEntry {
  calibrated_at: string
  ndcg_old: number
  ndcg_new: number
  n_impressions: number
  n_saves: number
}

export interface CalibrationStatus {
  has_personal_weights: boolean
  score_weights: { theme: number; pref: number; novel: number }
  last_calibrated: string | null
  ndcg_old: number | null
  ndcg_new: number | null
  ndcg_improvement: number | null
  n_impressions_last: number | null
  n_saves_last: number | null
  history: CalibrationHistoryEntry[]
  profile_built_at: string
}

/** Send 'more like this' or 'less like this' preference signal for a paper. */
export async function nudgePaper(body: NudgeBody): Promise<{ ok: boolean; direction: string }> {
  const { data } = await http.post<{ ok: boolean; direction: string }>('/preferences/nudge', body)
  return data
}

/** Get the current user's preference profile summary. */
export async function fetchPreferenceProfile(): Promise<PreferenceProfileSummary> {
  const { data } = await http.get<PreferenceProfileSummary>('/preferences/profile')
  return data
}

/** Force-rebuild the preference profile (useful after bulk actions). */
export async function rebuildPreferenceProfile(): Promise<PreferenceProfileSummary> {
  const { data } = await http.post<PreferenceProfileSummary>('/preferences/rebuild')
  return data
}

/** Send a direct category-level calibration signal (more / less / reset). */
export async function categoryNudge(
  category: string,
  direction: 'more' | 'less' | 'reset',
): Promise<{ ok: boolean; category: string; direction: string }> {
  const { data } = await http.post('/preferences/category-nudge', { category, direction })
  return data
}

export interface SuppressionContribution {
  type: 'category_positive' | 'category_negative' | 'keyword_positive' | 'keyword_negative' | 'tier_mismatch'
  key: string
  delta: number
  label: string
}

export interface SuppressedPaper {
  paper_id: string
  short_title: string
  '📖标题': string
  institution: string
  categories: string[]
  institution_tier?: number
  relevance_score: number
  pref_score: number
  theme_score: number
  contributions: SuppressionContribution[]
  suppression_summary: string
}

/** Fetch papers that were suppressed by the preference filter for a given date. */
export async function fetchSuppressions(date: string, topN = 5): Promise<{
  date: string
  count: number
  suppressions: SuppressedPaper[]
}> {
  const { data } = await http.get('/preferences/suppressions', { params: { date, top_n: topN } })
  return data
}

/** Get the current user's calibration status (personal weights, NDCG, history). */
export async function fetchCalibrationStatus(): Promise<CalibrationStatus> {
  const { data } = await http.get<CalibrationStatus>('/preferences/calibration/status')
  return data
}

// ---------------------------------------------------------------------------
// PDF Cleanup API
// ---------------------------------------------------------------------------

export interface PdfCleanupResult {
  dry_run: boolean
  retention_days: number
  managed_sources?: string[]
  sources?: Record<string, {
    scanned: number
    deletable: number
    deleted: number
    reclaimable_bytes: number
    freed_bytes: number
  }>
  scanned: number
  deletable: number
  deleted: number
  skipped_saved: number
  skipped_recent: number
  reclaimable_bytes?: number
  freed_bytes: number
  freed_mb: number
  errors: string[]
  started_at: string
  finished_at: string
}

export interface PdfCleanupStatus {
  ok: boolean
  auto_enabled: boolean
  retention_days: number
  auto_hour: number
  auto_minute: number
  scheduler_alive: boolean
  managed_sources?: string[]
  last_run_at: string | null
  last_success_date?: string | null
  last_result: PdfCleanupResult | null
}

export interface PdfCleanupRunResponse extends PdfCleanupResult {
  ok: boolean
}

/** 获取 PDF 清理状态（配置 + 最近运行结果） */
export async function fetchPdfCleanupStatus(): Promise<PdfCleanupStatus> {
  const { data } = await http.get<PdfCleanupStatus>('/admin/pdf-cleanup/status')
  return data
}

/** 手动触发 PDF 清理（dry_run=true 为预览，false 为实际删除） */
export async function runPdfCleanup(
  dryRun: boolean,
  retentionDays?: number,
): Promise<PdfCleanupRunResponse> {
  const { data } = await http.post<PdfCleanupRunResponse>('/admin/pdf-cleanup/run', {
    dry_run: dryRun,
    retention_days: retentionDays ?? null,
  })
  return data
}

/** 保存 PDF 清理配置 */
export async function savePdfCleanupConfig(config: {
  retention_days: number
  auto_enabled: boolean
  auto_hour: number
  auto_minute: number
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pdf-cleanup/config', config)
  return data
}
