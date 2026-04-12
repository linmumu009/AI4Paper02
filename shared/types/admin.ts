import type { AuthUser, UserTier } from './auth'

// ---------------------------------------------------------------------------
// Pipeline types
// ---------------------------------------------------------------------------

export interface PipelineRunStatus {
  running: boolean
  current_step: string | null
  logs: string[]
  started_at: string | null
  finished_at: string | null
  exit_code: number | null
  params: {
    pipeline?: string
    date?: string
    sllm?: number | null
    zo?: string
    days?: number | null
    categories?: string | null
    extra_query?: string | null
    max_papers?: number | null
    anchor_tz?: string | null
  }
  run_id?: string | null
}

export interface ScheduleConfig {
  enabled: boolean
  hour: number
  minute: number
  pipeline: string
  sllm: number | null
  zo: string
  user_id?: number | null
  last_run_date?: string | null
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
  scheduler_alive?: boolean
}

export interface PipelineDataTrackingRecord {
  date: string
  arxiv_search: number | null
  dedup: number | null
  theme_scored: number | null
  theme_passed: number | null
  institution_info: number | null
  final_selected: number | null
  summary_raw: number | null
  summary_limit: number | null
  paper_assets: number | null
}

export interface PipelineDataTrackingResponse {
  records: PipelineDataTrackingRecord[]
}

// ---------------------------------------------------------------------------
// System Config types
// ---------------------------------------------------------------------------

export interface SystemConfigItem {
  key: string
  value: any
  type: string
  description: string
  is_sensitive: boolean
}

export interface SystemConfigGroup {
  name: string
  items: SystemConfigItem[]
}

export interface SystemConfigResponse {
  ok: boolean
  groups: SystemConfigGroup[]
  defaults: Record<string, any>
}

export interface SystemConfigUpdateResponse {
  ok: boolean
  config: Record<string, any>
}

// ---------------------------------------------------------------------------
// LLM Config types
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
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Prompt Config types
// ---------------------------------------------------------------------------

export interface PromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// User Preset types
// ---------------------------------------------------------------------------

export interface UserLlmPreset {
  id: number
  user_id: number
  name: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number | null
  temperature?: number | null
  input_hard_limit?: number | null
  input_safety_margin?: number | null
  created_at: string
  updated_at: string
}

export interface UserPromptPreset {
  id: number
  user_id: number
  name: string
  prompt_content: string
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Analytics (数据统计分析)
// ---------------------------------------------------------------------------

export interface AnalyticsOverviewResponse {
  ok: boolean
  total_users: number
  active_today: number
  active_7d: number
  active_30d: number
  new_today: number
  new_7d: number
  new_30d: number
  tier_distribution: Record<string, number>
  content_stats: {
    papers_saved: number
    notes_written: number
    annotations: number
    dismissed: number
    compare_results: number
    ideas_generated: number
  }
  today_events: {
    page_views: number
    paper_views: number
  }
}

export interface AnalyticsUserActivity {
  user_id: number
  username: string
  role: string
  tier: string
  created_at: string
  last_login_at: string | null
  papers_saved: number
  notes_written: number
  annotations: number
  dismissed: number
  compare_results: number
  total_page_views: number
  total_time_spent_seconds: number
}

export interface AnalyticsUsersResponse {
  ok: boolean
  users: AnalyticsUserActivity[]
  total: number
}

export interface AnalyticsPaperPopularity {
  paper_id: string
  title: string
  save_count: number
  note_count: number
  annotation_count: number
  dismiss_count: number
  view_count: number
  avg_view_duration: number
  first_saved_at: string
}

export interface AnalyticsPapersResponse {
  ok: boolean
  papers: AnalyticsPaperPopularity[]
}

export interface AnalyticsTrendsResponse {
  ok: boolean
  dates: string[]
  new_users: number[]
  active_users: number[]
  papers_saved: number[]
  notes_written: number[]
  page_views: number[]
}

export interface AnalyticsFeaturesResponse {
  ok: boolean
  features: Record<string, number>
}

export interface RetentionCohort {
  week: string
  cohort_size: number
  retention: number[]
}

export interface AnalyticsRetentionResponse {
  ok: boolean
  cohorts: RetentionCohort[]
  weeks: number
}

export interface AnalyticsEngagementSigninResponse {
  ok: boolean
  days: number
  dates: string[]
  task_recorded: number[]
  day_completed: number[]
  milestone_granted: number[]
  completion_rate: number[]
  grant_rate: number[]
  unique_users: {
    task_recorded: number
    day_completed: number
    milestone_granted: number
  }
}

export interface ActivationFunnelUser {
  user_id: number
  username: string
  created_at: string
  last_login_at: string | null
  tier: string
  is_pending: boolean
}

export interface ActivationTierBreakdown {
  registered: number
  activated: number
  rate: number
}

export interface AnalyticsActivationResponse {
  ok: boolean
  activation_rate_overall: number
  dates: string[]
  daily_registrations: number[]
  daily_activations: number[]
  activation_funnel: {
    registered: number
    activated: number
    pending: number
    not_activated: number
  }
  recent_unactivated: ActivationFunnelUser[]
  tier_breakdown: Record<string, ActivationTierBreakdown>
  activation_definition?: string
}

export interface AnalyticsValueRetentionResponse {
  ok: boolean
  cohorts: RetentionCohort[]
  weeks: number
  total_activated: number
  definition: string
}

export interface ContentStepFunnelStep {
  step: string
  label: string
  users: number
  note: string
}

export interface ContentStepFunnelAnomalyPaper {
  paper_id: string
  title: string
  view_users: number
  save_users: number
  save_rate: number
}

export interface AnalyticsContentStepFunnelResponse {
  ok: boolean
  days: number
  funnel: ContentStepFunnelStep[]
  high_view_low_save: ContentStepFunnelAnomalyPaper[]
}

export interface AnalyticsActivatedRetentionResponse {
  ok: boolean
  cohorts: RetentionCohort[]
  weeks: number
  total_activated: number
}

export interface ContentFunnelPaper {
  paper_id: string
  title: string
  save_count: number
  view_count: number
  view_to_save_rate: number | null
}

export interface AnalyticsContentFunnelResponse {
  ok: boolean
  days: number
  dates: string[]
  daily_paper_views: number[]
  daily_saves: number[]
  daily_notes: number[]
  totals: {
    paper_views: number
    saves: number
    notes: number
    annotations: number
    compares: number
    key_actions: number
  }
  conversion_rate: number
  top_papers: ContentFunnelPaper[]
}

export interface AiFeatureDetail {
  label: string
  users: number
  sessions?: number
  messages?: number
  generated?: number
  daily: number[]
}

export interface AnalyticsAiFeatureResponse {
  ok: boolean
  days: number
  dates: string[]
  total_activated: number
  penetration_rate: number
  features: {
    research: AiFeatureDetail
    chat: AiFeatureDetail
    idea: AiFeatureDetail
  }
  combined_daily: number[]
  note?: string
}

export interface AnalyticsEngagementDepthResponse {
  ok: boolean
  days: number
  dates: string[]
  avg_session_duration_by_day: (number | null)[]
  avg_paper_read_duration_by_day: (number | null)[]
  window_avg_session_seconds: number | null
  window_avg_paper_read_seconds: number | null
  session_duration_distribution: {
    lt30s: number
    s30_120: number
    m2_10: number
    gt10m: number
  }
  data_available: boolean
  note?: string
}

// Re-export auth types needed in admin context
export type { AuthUser, UserTier }
