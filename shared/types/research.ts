// ---------------------------------------------------------------------------
// Deep Research Q&A types
// ---------------------------------------------------------------------------

export interface ResearchConfig {
  top_n?: number
  force_full_read?: boolean
}

export interface ResearchRankingItem {
  paper_id: string
  score: number
  level: 'high' | 'medium' | 'low'
  reason: string
}

export interface ResearchRound {
  id: number
  session_id: number
  round_number: number
  round_type: 'relevance' | 'summary_analysis' | 'full_text'
  input_paper_ids: string[]
  output: Record<string, unknown>
  status: string
  created_at: string
}

export interface ResearchSession {
  id: number
  user_id: number
  question: string
  paper_ids: string[]
  config: ResearchConfig
  status: 'pending' | 'running' | 'done' | 'error'
  saved: boolean
  folder_id?: number | null
  created_at: string
  updated_at: string
  rounds?: ResearchRound[]
}

export interface ResearchFolder {
  id: number
  name: string
  parent_id: number | null
  children: ResearchFolder[]
  sessions: ResearchSession[]
  created_at: string
  updated_at: string
}

export interface ResearchTree {
  folders: ResearchFolder[]
  sessions: ResearchSession[]
}

// SSE event types emitted by the backend during a research session
export type ResearchSseEvent =
  | { type: 'session_created'; session_id: number }
  | { type: 'round_start'; round: number; title: string; total_papers?: number; selected_papers?: number; papers_count?: number; paper_titles?: Record<string, string> }
  | { type: 'progress'; round: number; message: string }
  | { type: 'relevance_result'; round: 1; rankings: ResearchRankingItem[]; selected_ids: string[]; top_n: number; paper_titles: Record<string, string> }
  | { type: 'text'; round: number; content: string }
  | { type: 'round_done'; round: number; action?: string; papers?: string[]; decision_reason?: string }
  | { type: 'final_answer' }
  | { type: 'error'; round?: number; content: string; running_session_id?: number }

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
