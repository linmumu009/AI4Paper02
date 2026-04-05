/** 单篇论文摘要（来自 file_collect _limit.md + pdf_info.json） */
export interface PaperSummary {
  institution: string
  short_title: string
  '📖标题': string
  '🌐来源': string
  paper_id: string
  /** 推荐理由（新格式摘要新增，旧数据为空字符串） */
  '推荐理由'?: string
  '🛎️文章简介': {
    '🔸研究问题': string
    '🔸主要贡献': string
  }
  '📝重点思路': string[]
  '🔎分析总结': string[]
  '💡个人观点': string
  /** 一句话记忆版（新格式摘要新增，旧数据为空字符串） */
  '一句话记忆版'?: string
  /** Merged from theme scores */
  relevance_score?: number | null
  /** Merged from institution filter / pdf_info.json */
  is_large_institution?: boolean
  /** Institution tier: 1=T1 顶尖, 2=T2 一流, 3=T3 知名, 4=T4 一般. 0 or missing = unset (treat as T4) */
  institution_tier?: number
  /** Paper abstract from pdf_info.json */
  abstract?: string
  /** Image filenames in image/ subdirectory */
  images?: string[]
  /** Number of images */
  image_count?: number
}

/** paper_assets 中的结构化块 */
export interface AssetBlock {
  text: string
  bullets: string[]
}

/** 完整 paper_assets 条目 */
export interface PaperAssets {
  paper_id: string
  title: string
  url: string
  year: number
  blocks: {
    background: AssetBlock
    objective: AssetBlock
    method: AssetBlock
    data: AssetBlock
    experiment: AssetBlock
    metrics: AssetBlock
    results: AssetBlock
    limitations: AssetBlock
  }
}

/** GET /api/dates 响应 */
export interface DatesResponse {
  dates: string[]
}

/** GET /api/papers 响应 */
export interface PapersResponse {
  date: string
  count: number
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: UserTier | 'anonymous'
}

/** GET /api/papers/:id 响应 */
export interface PaperDetailResponse {
  summary: PaperSummary
  paper_assets: PaperAssets | null
  date: string
  images: string[]
  arxiv_url: string
  pdf_url: string
}

/** GET /api/digest/:date 响应 */
export interface DigestResponse {
  date: string
  total_papers: number
  large_institution_count: number
  avg_relevance_score: number | null
  institution_distribution: { name: string; count: number }[]
  /** Tier distribution: count of papers per institution tier level */
  tier_distribution?: { tier: number; count: number }[]
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: UserTier | 'anonymous'
}

/** Pipeline step status */
export interface PipelineStep {
  step: string
  completed: boolean
}

/** GET /api/pipeline/status 响应 */
export interface PipelineStatusResponse {
  date: string
  steps: PipelineStep[]
}

// ---------------------------------------------------------------------------
// User-uploaded papers types
// ---------------------------------------------------------------------------

/** 来源类型 */
export type UserPaperSourceType = 'pdf' | 'arxiv' | 'manual'

/** 处理状态值 */
export type UserPaperProcessStatus = 'none' | 'pending' | 'processing' | 'completed' | 'failed'

/** 全文翻译状态 */
export type UserPaperTranslateStatus = 'none' | 'processing' | 'completed' | 'failed'

/** 处理步骤标识 */
export type UserPaperProcessStep =
  | 'queued'
  | 'starting'
  | 'pdf_prepare'
  | 'pdf_download'
  | 'pdf_extract'
  | 'pdf_info'
  | 'paper_summary'
  | 'summary_limit'
  | 'paper_assets'
  | 'done'
  | ''

/** 用户自行上传/导入的论文（来自 /api/user-papers） */
export interface UserPaper {
  id: number
  paper_id: string
  user_id: number
  source_type: UserPaperSourceType
  source_ref: string
  title: string
  authors: string[]
  abstract: string
  institution: string
  year: number | null
  pdf_path: string | null
  pdf_static_url?: string | null
  /** MinerU / 翻译产物静态路径（后端 enrich） */
  mineru_static_url?: string | null
  zh_static_url?: string | null
  bilingual_static_url?: string | null
  external_url: string
  /** arXiv 导入时额外返回 */
  arxiv_pdf_url?: string | null
  summary_json: string | null
  paper_assets_json: string | null
  /** Pipeline processing status */
  process_status: UserPaperProcessStatus
  process_step: UserPaperProcessStep
  process_error: string
  process_started_at: string | null
  process_finished_at: string | null
  translate_status?: UserPaperTranslateStatus
  translate_error?: string
  /** 翻译进度 0–100，仅 translate_status=processing 时有意义 */
  translate_progress?: number
  translate_started_at?: string | null
  translate_finished_at?: string | null
  /** Parsed summary (populated when process_status === 'completed') */
  summary?: PaperSummary | null
  /** Parsed paper_assets (populated when process_status === 'completed') */
  paper_assets?: PaperAssets | null
  /** Source marker always 'user_upload' from backend */
  source?: 'user_upload'
  /** Folder placement (scope='mypapers') */
  folder_id?: number | null
  created_at: string
  updated_at: string
}

/** 我的论文文件夹（来自 kb_folders scope=mypapers） */
export interface UserPaperFolder {
  id: number
  user_id: number
  scope: string
  name: string
  parent_id: number | null
  created_at: string
  updated_at: string
  children: UserPaperFolder[]
  papers: UserPaper[]
}

/** GET /api/user-papers/tree 响应 */
export interface UserPaperTree {
  folders: UserPaperFolder[]
  papers: UserPaper[]
}

/** GET /api/user-papers/{id}/process-status 响应 */
export interface UserPaperProcessStatusResponse {
  paper_id: string
  process_status: UserPaperProcessStatus
  process_step: UserPaperProcessStep
  process_error: string
  process_started_at: string | null
  process_finished_at: string | null
}

/** GET /api/user-papers/{id}/translate-status 响应 */
export interface UserPaperTranslateStatusResponse {
  paper_id: string
  translate_status: UserPaperTranslateStatus
  translate_error: string
  translate_progress: number
  translate_started_at: string | null
  translate_finished_at: string | null
  busy: boolean
}

/** 侧栏「我的论文」子项：主区 PDF + Markdown 分栏 */
export type UserPaperFileViewMode = 'pdf' | 'mineru' | 'zh' | 'bilingual'

export interface UserPaperViewMdPayload {
  paperId: string
  title: string
  pdfUrl: string | null
  mdUrl: string | null
  /** 侧栏点击的子项类型；用于主区默认单栏展示哪一面板 */
  viewMode?: UserPaperFileViewMode
  mineruUrl?: string | null
  zhUrl?: string | null
  bilingualUrl?: string | null
  /** 论文所属的 scope，用于下载时正确路由到 API */
  scope?: 'kb' | 'mypapers'
}

/** GET /api/user-papers/{id}/files 响应 */
export interface UserPaperFilesResponse {
  paper_id: string
  pdf_static_url: string | null | undefined
  mineru_static_url: string | null | undefined
  zh_static_url: string | null | undefined
  bilingual_static_url: string | null | undefined
  exists: {
    pdf: boolean
    mineru: boolean
    zh: boolean
    bilingual: boolean
  }
  translate_status: UserPaperTranslateStatus
}

/** GET /api/user-papers 列表响应 */
export interface UserPapersListResponse {
  total: number
  papers: UserPaper[]
}

// ---------------------------------------------------------------------------
// Knowledge Base types
// ---------------------------------------------------------------------------

/** A paper saved in the knowledge base */
export interface KbPaper {
  id: number
  paper_id: string
  folder_id: number | null
  paper_data: PaperSummary
  created_at: string
  /** Number of notes/files attached (populated by tree endpoint) */
  note_count?: number
  /** Static URL for the PDF (injected by backend enrich) */
  pdf_static_url?: string | null
  /** MinerU / translation derivative static URLs */
  mineru_static_url?: string | null
  zh_static_url?: string | null
  bilingual_static_url?: string | null
  /** MinerU processing status */
  process_status?: 'none' | 'pending' | 'processing' | 'completed' | 'failed'
  process_step?: string
  process_error?: string
  /** Translation status */
  translate_status?: 'none' | 'processing' | 'completed' | 'failed'
  translate_progress?: number
  translate_error?: string
}

/** GET /api/kb/papers/:paper_id/process-status 响应 */
export interface KbPaperProcessStatusResponse {
  paper_id: string
  process_status: 'none' | 'pending' | 'processing' | 'completed' | 'failed'
  process_step: string
  process_error: string
}

/** GET /api/kb/papers/:paper_id/translate-status 响应 */
export interface KbPaperTranslateStatusResponse {
  paper_id: string
  translate_status: 'none' | 'processing' | 'completed' | 'failed'
  translate_progress: number
  translate_error: string
  busy: boolean
}

/** GET /api/kb/papers/:paper_id/files 响应 */
export interface KbPaperFilesResponse {
  paper_id: string
  pdf_static_url: string | null | undefined
  mineru_static_url: string | null | undefined
  zh_static_url: string | null | undefined
  bilingual_static_url: string | null | undefined
  exists: {
    pdf: boolean
    mineru: boolean
    zh: boolean
    bilingual: boolean
  }
  process_status: string
  process_step: string
  translate_status: string
  translate_progress: number
}

/** A note / file / link attached to a KB paper */
export interface KbNote {
  id: number
  paper_id: string
  type: 'markdown' | 'file' | 'link'
  title: string
  content?: string
  file_path?: string
  file_url?: string
  file_size?: number
  mime_type?: string
  created_at: string
  updated_at: string
}

/** GET /api/kb/papers/:paper_id/notes 响应 */
export interface KbNotesResponse {
  paper_id: string
  notes: KbNote[]
}

/** A PDF annotation (highlight / note) */
export interface KbAnnotation {
  id: number
  paper_id: string
  page: number
  type: 'highlight' | 'text' | 'box'
  content: string
  color: string
  position_data: string
  created_at: string
  updated_at: string
}

/** GET /api/kb/papers/:paper_id/annotations 响应 */
export interface KbAnnotationsResponse {
  paper_id: string
  annotations: KbAnnotation[]
}

/** A folder in the knowledge base (recursive tree) */
export interface KbFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbFolder[]
  papers: KbPaper[]
  created_at: string
  updated_at: string
}

/** GET /api/kb/tree 响应 */
export interface KbTree {
  folders: KbFolder[]
  papers: KbPaper[] // root-level papers (folder_id == null)
}

/** Context menu item */
export interface KbMenuItem {
  key: string
  label: string
  danger?: boolean
}

/** A saved compare analysis result */
export interface KbCompareResult {
  id: number
  title: string
  markdown: string
  paper_ids: string[]
  folder_id: number | null
  created_at: string
  updated_at: string
}

/** A folder in the compare results tree */
export interface KbCompareFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbCompareFolder[]
  results: KbCompareResult[]
  created_at: string
  updated_at: string
}

/** GET /api/kb/compare-results/tree 响应 */
export interface KbCompareResultsTree {
  folders: KbCompareFolder[]
  results: KbCompareResult[] // root-level results
}

/** 跨库对比清单条目（购物车模式） */
export interface CompareCartItem {
  /** paper_id 或对比结果 id（字符串化） */
  id: string
  /** 显示标题 */
  title: string
  /** 来源库 */
  source: 'kb' | 'mypapers' | 'compare'
  /** 条目类型：普通论文 或 已保存的对比报告 */
  type: 'paper' | 'compare_result'
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

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
  has_password?: boolean
  created_at: string
  updated_at: string
  last_login_at?: string | null
}

export type UserRole = 'user' | 'admin' | 'superadmin'
export type UserTier = 'free' | 'pro' | 'pro_plus'

export interface AuthPayload {
  username: string
  password: string
}

export interface AuthRegisterPayload {
  username: string
  password: string
  phone: string
  sms_code: string
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

// ---------------------------------------------------------------------------
// Subscription History types (订阅记录)
// ---------------------------------------------------------------------------

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
  /** Run identifier (YYYYMMDD_HHMMSS). Present when disk state is available. */
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
  /** New multi-user pipeline settings */
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
  /** Whether the scheduler background thread is currently alive */
  scheduler_alive?: boolean
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
// Inspiration v2 types (灵感生成 v2)
// ---------------------------------------------------------------------------

/** Structured extraction unit from a paper */
export interface IdeaAtom {
  id: number
  user_id: number
  paper_id: string
  date_str: string
  atom_type: 'claim' | 'method' | 'setup' | 'limitation' | 'tag'
  content: string
  tags: string[]
  evidence: { text: string; location: string }[]
  section: string
  source_file: string
  created_at: string
  updated_at: string
}

/** Research question mined from atoms */
export interface IdeaQuestion {
  id: number
  user_id: number
  source_atom_ids: number[]
  question_text: string
  strategy: string
  context: Record<string, any>
  created_at: string
}

/** Inspiration candidate with scores and revision history */
export interface IdeaCandidate {
  id: number
  user_id: number
  question_id: number | null
  title: string
  goal: string
  mechanism: string
  input_atom_ids: number[]
  evidence: { text: string; location: string }[]
  risks: string
  scores: IdeaCandidateScores
  status: 'draft' | 'review' | 'published' | 'archived'
  revision_history: IdeaRevisionEntry[]
  strategy: string
  folder_id: number | null
  tags: string[]
  created_at: string
  updated_at: string
}

export interface IdeaCandidateScores {
  consistency?: number
  novelty?: number
  feasibility?: number
  impact?: number
  overall?: number
  [key: string]: number | undefined
}

export interface IdeaRevisionEntry {
  type: string
  scores?: IdeaCandidateScores
  verdict?: string
  summary?: string
  changes?: Record<string, any>
  [key: string]: any
}

/** Execution / experiment plan linked to a candidate */
export interface IdeaPlan {
  id: number
  user_id: number
  candidate_id: number
  milestones: Record<string, any>[]
  metrics: string
  datasets: string
  ablation: string
  cost: string
  timeline: string
  full_plan: string
  created_at: string
  updated_at: string
}

/** User feedback event on a candidate */
export interface IdeaFeedback {
  id: number
  user_id: number
  candidate_id: number
  action: 'collect' | 'discard' | 'modify' | 'implement' | 'rate' | 'view'
  context: Record<string, any>
  created_at: string
}

/** High-quality inspiration pattern */
export interface IdeaExemplar {
  id: number
  user_id: number
  candidate_id: number | null
  pattern: Record<string, any>
  score: number
  notes: string
  created_at: string
  updated_at: string
}

/** Prompt version record */
export interface IdeaPromptVersion {
  id: number
  user_id: number
  stage: string
  version: number
  prompt_text: string
  metrics: Record<string, any>
  created_at: string
}

/** Evaluation benchmark */
export interface IdeaBenchmark {
  id: number
  user_id: number
  name: string
  question_ids: number[]
  model_version: string
  results: Record<string, any>
  created_at: string
  updated_at: string
}

/** Dashboard statistics */
export interface IdeaStats {
  atom_count: number
  question_count: number
  candidate_count: number
  published_count: number
  exemplar_count: number
  atom_type_distribution: Record<string, number>
}

// -- API Response types ---

export interface IdeaStatsResponse {
  ok: boolean
  atom_count: number
  question_count: number
  candidate_count: number
  published_count: number
  exemplar_count: number
  atom_type_distribution: Record<string, number>
}

export interface IdeaAtomsResponse {
  ok: boolean
  atoms: IdeaAtom[]
  count: number
}

export interface IdeaAtomResponse {
  ok: boolean
  atom: IdeaAtom
}

export interface IdeaQuestionsResponse {
  ok: boolean
  questions: IdeaQuestion[]
  count: number
}

export interface IdeaCandidatesResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  count: number
}

export interface IdeaCandidateResponse {
  ok: boolean
  candidate: IdeaCandidate
}

export interface IdeaPlanResponse {
  ok: boolean
  plan: IdeaPlan
}

export interface IdeaFeedbackResponse {
  ok: boolean
  feedback?: IdeaFeedback
  events?: IdeaFeedback[]
  count?: number
}

export interface IdeaExemplarsResponse {
  ok: boolean
  exemplars: IdeaExemplar[]
}

export interface IdeaPromptVersionsResponse {
  ok: boolean
  versions: IdeaPromptVersion[]
}

export interface IdeaBenchmarksResponse {
  ok: boolean
  benchmarks: IdeaBenchmark[]
}

export interface IdeaLibraryTreeResponse {
  ok: boolean
  folders: KbTree
  candidates: IdeaCandidate[]
}

/** GET /api/idea/digest/:date 响应 */
export interface IdeaDigestResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}

// ---------------------------------------------------------------------------
// Paper Chat types (论文追问问答)
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatHistoryResponse {
  paper_id: string
  messages: ChatMessage[]
}

// ---------------------------------------------------------------------------
// Analytics (数据统计分析)
// ---------------------------------------------------------------------------

/** GET /api/admin/analytics/overview */
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

/** GET /api/admin/analytics/users */
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

/** GET /api/admin/analytics/papers */
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

/** GET /api/admin/analytics/trends */
export interface AnalyticsTrendsResponse {
  ok: boolean
  dates: string[]
  new_users: number[]
  active_users: number[]
  papers_saved: number[]
  notes_written: number[]
  page_views: number[]
}

/** GET /api/admin/analytics/features */
export interface AnalyticsFeaturesResponse {
  ok: boolean
  features: Record<string, number>
}

/** GET /api/admin/analytics/retention */
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

// ---------------------------------------------------------------------------
// Pipeline data tracking types
// ---------------------------------------------------------------------------

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