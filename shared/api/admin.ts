import { http } from './http'
import type {
  PipelineRunStatus, ScheduleConfig, PipelineDataTrackingResponse,
  SystemConfigResponse, SystemConfigUpdateResponse,
  LlmConfig, PromptConfig, UserLlmPreset, UserPromptPreset,
  AnalyticsOverviewResponse, AnalyticsUsersResponse, AnalyticsPapersResponse,
  AnalyticsTrendsResponse, AnalyticsFeaturesResponse, AnalyticsRetentionResponse,
  AnalyticsEngagementSigninResponse, AnalyticsActivationResponse,
  AnalyticsActivatedRetentionResponse, AnalyticsContentFunnelResponse,
  AnalyticsValueRetentionResponse, AnalyticsContentStepFunnelResponse,
  AnalyticsAiFeatureResponse, AnalyticsEngagementDepthResponse,
} from '../types/admin'

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

export async function runPipeline(params: {
  pipeline?: string; date?: string; sllm?: number | null; zo?: string; force?: boolean
  multi_user?: boolean; max_concurrent_user_pipelines?: number
  days?: number | null; categories?: string | null; extra_query?: string | null
  max_papers?: number | null; anchor_tz?: string | null
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

export async function getScheduleConfig(): Promise<ScheduleConfig> {
  const { data } = await http.get<ScheduleConfig>('/admin/schedule')
  return data
}

export async function updateScheduleConfig(config: {
  enabled: boolean; hour: number; minute: number; pipeline?: string
  sllm?: number | null; zo?: string; user_id?: number | null
  multi_user?: boolean; max_concurrent_user_pipelines?: number
}): Promise<{ ok: boolean; schedule: ScheduleConfig }> {
  const { data } = await http.post<{ ok: boolean; schedule: ScheduleConfig }>('/admin/schedule', config)
  return data
}

export interface ScheduleHistoryRecord {
  run_id: string; trigger: string; date_str: string; started_at: string
  finished_at: string | null; user_count: number; user_ids: number[]
  exit_code: number | null; success: boolean; pipeline?: string
}

export async function getScheduleHistory(limit = 50): Promise<ScheduleHistoryRecord[]> {
  const { data } = await http.get<{ records: ScheduleHistoryRecord[]; total: number }>('/admin/schedule/history', { params: { limit } })
  return data.records
}

export async function fetchPipelineDataTracking(params?: { days?: number }): Promise<PipelineDataTrackingResponse> {
  const { data } = await http.get<PipelineDataTrackingResponse>('/admin/pipeline/data-tracking', { params })
  return data
}

// ---------------------------------------------------------------------------
// User Settings
// ---------------------------------------------------------------------------

export interface UserSettingsResponse {
  ok: boolean; feature: string; settings: Record<string, any>; defaults: Record<string, any>
}

export async function fetchUserSettings(feature: string): Promise<UserSettingsResponse> {
  const { data } = await http.get<UserSettingsResponse>(`/user/settings/${feature}`)
  return data
}

export async function saveUserSettings(feature: string, settings: Record<string, any>): Promise<UserSettingsResponse> {
  const { data } = await http.put<UserSettingsResponse>(`/user/settings/${feature}`, { settings })
  return data
}

// ---------------------------------------------------------------------------
// System Config
// ---------------------------------------------------------------------------

export async function getSystemConfig(): Promise<SystemConfigResponse> {
  const { data } = await http.get<SystemConfigResponse>('/admin/config')
  return data
}

export async function updateSystemConfig(config: Record<string, any>): Promise<SystemConfigUpdateResponse> {
  const { data } = await http.post<SystemConfigUpdateResponse>('/admin/config', { config })
  return data
}

export async function resetSystemConfig(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/config/reset')
  return data
}

// ---------------------------------------------------------------------------
// LLM Config
// ---------------------------------------------------------------------------

interface LlmConfigsResponse { ok: boolean; configs: LlmConfig[] }
interface LlmConfigResponse { ok: boolean; config: LlmConfig }
interface ApplyLlmConfigResponse { ok: boolean; applied: number }

export async function fetchLlmConfigs(): Promise<LlmConfigsResponse> {
  const { data } = await http.get<LlmConfigsResponse>('/admin/llm-configs')
  return data
}

export async function fetchLlmConfig(configId: number): Promise<LlmConfigResponse> {
  const { data } = await http.get<LlmConfigResponse>(`/admin/llm-configs/${configId}`)
  return data
}

export async function createLlmConfig(config: Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>): Promise<LlmConfigResponse> {
  const { data } = await http.post<LlmConfigResponse>('/admin/llm-configs', config)
  return data
}

export async function updateLlmConfig(configId: number, config: Partial<LlmConfig>): Promise<LlmConfigResponse> {
  const { data } = await http.patch<LlmConfigResponse>(`/admin/llm-configs/${configId}`, config)
  return data
}

export async function deleteLlmConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/llm-configs/${configId}`)
  return data
}

export async function applyLlmConfig(configId: number, usagePrefix: string): Promise<ApplyLlmConfigResponse> {
  const { data } = await http.post<ApplyLlmConfigResponse>(`/admin/llm-configs/${configId}/apply`, { usage_prefix: usagePrefix })
  return data
}

// ---------------------------------------------------------------------------
// Prompt Config
// ---------------------------------------------------------------------------

interface PromptConfigsResponse { ok: boolean; configs: PromptConfig[] }
interface PromptConfigResponse { ok: boolean; config: PromptConfig }
interface ApplyPromptConfigResponse { ok: boolean; applied: number }

export async function fetchPromptConfigs(): Promise<PromptConfigsResponse> {
  const { data } = await http.get<PromptConfigsResponse>('/admin/prompt-configs')
  return data
}

export async function fetchPromptConfig(configId: number): Promise<PromptConfigResponse> {
  const { data } = await http.get<PromptConfigResponse>(`/admin/prompt-configs/${configId}`)
  return data
}

export async function createPromptConfig(config: Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>): Promise<PromptConfigResponse> {
  const { data } = await http.post<PromptConfigResponse>('/admin/prompt-configs', config)
  return data
}

export async function updatePromptConfig(configId: number, config: Partial<PromptConfig>): Promise<PromptConfigResponse> {
  const { data } = await http.patch<PromptConfigResponse>(`/admin/prompt-configs/${configId}`, config)
  return data
}

export async function deletePromptConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/prompt-configs/${configId}`)
  return data
}

export async function applyPromptConfig(configId: number, variableName: string): Promise<ApplyPromptConfigResponse> {
  const { data } = await http.post<ApplyPromptConfigResponse>(`/admin/prompt-configs/${configId}/apply`, { variable_name: variableName })
  return data
}

export async function batchApplyConfigs(assignments: Array<{ usage_prefix: string; llm_config_id?: number | null; prompt_config_id?: number | null }>): Promise<{ ok: boolean; applied: number }> {
  const { data } = await http.post<{ ok: boolean; applied: number }>('/admin/configs/batch-apply', { assignments })
  return data
}

// ---------------------------------------------------------------------------
// User LLM Presets
// ---------------------------------------------------------------------------

interface UserLlmPresetsResponse { ok: boolean; presets: UserLlmPreset[] }
interface UserLlmPresetResponse { ok: boolean; preset: UserLlmPreset }

export async function fetchUserLlmPresets(): Promise<UserLlmPresetsResponse> {
  const { data } = await http.get<UserLlmPresetsResponse>('/user/llm-presets')
  return data
}

export async function createUserLlmPreset(preset: Omit<UserLlmPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserLlmPresetResponse> {
  const { data } = await http.post<UserLlmPresetResponse>('/user/llm-presets', preset)
  return data
}

export async function updateUserLlmPreset(presetId: number, preset: Partial<UserLlmPreset>): Promise<UserLlmPresetResponse> {
  const { data } = await http.patch<UserLlmPresetResponse>(`/user/llm-presets/${presetId}`, preset)
  return data
}

export async function deleteUserLlmPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/llm-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// User Prompt Presets
// ---------------------------------------------------------------------------

interface UserPromptPresetsResponse { ok: boolean; presets: UserPromptPreset[] }
interface UserPromptPresetResponse { ok: boolean; preset: UserPromptPreset }

export async function fetchUserPromptPresets(): Promise<UserPromptPresetsResponse> {
  const { data } = await http.get<UserPromptPresetsResponse>('/user/prompt-presets')
  return data
}

export async function createUserPromptPreset(preset: Omit<UserPromptPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserPromptPresetResponse> {
  const { data } = await http.post<UserPromptPresetResponse>('/user/prompt-presets', preset)
  return data
}

export async function updateUserPromptPreset(presetId: number, preset: Partial<UserPromptPreset>): Promise<UserPromptPresetResponse> {
  const { data } = await http.patch<UserPromptPresetResponse>(`/user/prompt-presets/${presetId}`, preset)
  return data
}

export async function deleteUserPromptPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/prompt-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// Analytics (Admin)
// ---------------------------------------------------------------------------

export async function fetchAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  const { data } = await http.get<AnalyticsOverviewResponse>('/admin/analytics/overview')
  return data
}

export async function fetchAnalyticsUsers(params?: { page?: number; page_size?: number; sort?: string }): Promise<AnalyticsUsersResponse> {
  const { data } = await http.get<AnalyticsUsersResponse>('/admin/analytics/users', { params })
  return data
}

export async function fetchAnalyticsPapers(params?: { days?: number; sort?: string; limit?: number }): Promise<AnalyticsPapersResponse> {
  const { data } = await http.get<AnalyticsPapersResponse>('/admin/analytics/papers', { params })
  return data
}

export async function fetchAnalyticsTrends(params?: { days?: number }): Promise<AnalyticsTrendsResponse> {
  const { data } = await http.get<AnalyticsTrendsResponse>('/admin/analytics/trends', { params })
  return data
}

export async function fetchAnalyticsFeatures(): Promise<AnalyticsFeaturesResponse> {
  const { data } = await http.get<AnalyticsFeaturesResponse>('/admin/analytics/features')
  return data
}

export async function fetchAnalyticsRetention(params?: { weeks?: number }): Promise<AnalyticsRetentionResponse> {
  const { data } = await http.get<AnalyticsRetentionResponse>('/admin/analytics/retention', { params })
  return data
}

export async function fetchAnalyticsEngagementSignin(params?: { days?: number }): Promise<AnalyticsEngagementSigninResponse> {
  const { data } = await http.get<AnalyticsEngagementSigninResponse>('/admin/analytics/engagement-signin', { params })
  return data
}

export async function fetchAnalyticsActivation(params?: { days?: number }): Promise<AnalyticsActivationResponse> {
  const { data } = await http.get<AnalyticsActivationResponse>('/admin/analytics/activation', { params })
  return data
}

export async function fetchAnalyticsActivatedRetention(params?: { weeks?: number }): Promise<AnalyticsActivatedRetentionResponse> {
  const { data } = await http.get<AnalyticsActivatedRetentionResponse>('/admin/analytics/activated-retention', { params })
  return data
}

export async function fetchAnalyticsContentFunnel(params?: { days?: number }): Promise<AnalyticsContentFunnelResponse> {
  const { data } = await http.get<AnalyticsContentFunnelResponse>('/admin/analytics/content-funnel', { params })
  return data
}

export async function fetchAnalyticsValueRetention(params?: { weeks?: number }): Promise<AnalyticsValueRetentionResponse> {
  const { data } = await http.get<AnalyticsValueRetentionResponse>('/admin/analytics/value-retention', { params })
  return data
}

export async function fetchAnalyticsContentStepFunnel(params?: { days?: number }): Promise<AnalyticsContentStepFunnelResponse> {
  const { data } = await http.get<AnalyticsContentStepFunnelResponse>('/admin/analytics/content-step-funnel', { params })
  return data
}

export async function fetchAnalyticsAiFeatures(params?: { days?: number }): Promise<AnalyticsAiFeatureResponse> {
  const { data } = await http.get<AnalyticsAiFeatureResponse>('/admin/analytics/ai-features', { params })
  return data
}

export async function fetchAnalyticsEngagementDepth(params?: { days?: number }): Promise<AnalyticsEngagementDepthResponse> {
  const { data } = await http.get<AnalyticsEngagementDepthResponse>('/admin/analytics/engagement-depth', { params })
  return data
}
