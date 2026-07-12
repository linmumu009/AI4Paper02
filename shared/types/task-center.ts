export type TaskKind =
  | 'kb_process'
  | 'kb_translate'
  | 'kb_classify'
  | 'user_paper_process'
  | 'user_paper_translate'
  | 'pipeline_run'
  | 'deep_research'
  | 'paper_compare'

export type TaskStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'skipped'
  | 'none'

export type TaskAction = 'view' | 'retry' | 'cancel' | 'continue'

export interface TaskCenterItem {
  id: string
  kind: TaskKind
  status: TaskStatus
  title: string
  subtitle?: string
  entity_id?: string
  entity_type?: 'paper' | 'run' | 'research_session' | 'compare_result'
  step?: string
  progress?: number
  error?: string
  created_at?: string
  updated_at?: string
  actions: TaskAction[]
  source: 'kb' | 'my_papers' | 'admin_pipeline' | 'research' | 'compare'
}

export interface TaskCenterSummary {
  running_count: number
  pending_count: number
  failed_count: number
  total_active: number
}

export interface TaskCenterListResponse {
  items: TaskCenterItem[]
  summary: TaskCenterSummary
}

export interface TaskActionResponse {
  ok: boolean
  message: string
}
