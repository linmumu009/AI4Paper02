import type { KbTree } from './kb'

// ---------------------------------------------------------------------------
// Inspiration v2 types (灵感生成 v2)
// ---------------------------------------------------------------------------

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

export interface IdeaQuestion {
  id: number
  user_id: number
  source_atom_ids: number[]
  question_text: string
  strategy: string
  context: Record<string, any>
  created_at: string
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

export interface IdeaFeedback {
  id: number
  user_id: number
  candidate_id: number
  action: 'collect' | 'discard' | 'modify' | 'implement' | 'rate' | 'view'
  context: Record<string, any>
  created_at: string
}

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

export interface IdeaPromptVersion {
  id: number
  user_id: number
  stage: string
  version: number
  prompt_text: string
  metrics: Record<string, any>
  created_at: string
}

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

export interface IdeaStats {
  atom_count: number
  question_count: number
  candidate_count: number
  published_count: number
  exemplar_count: number
  atom_type_distribution: Record<string, number>
}

// Response types

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

export interface IdeaDigestResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}
