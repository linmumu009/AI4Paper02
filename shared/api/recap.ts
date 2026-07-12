import { http } from './http'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RecapTheme {
  name: string
  paper_ids: string[]
  insight: string
}

export interface RecapContent {
  title: string
  summary: string
  paper_count: number
  themes: RecapTheme[]
  connections: string[]
  recommended_revisit: string[]
  next_questions: string[]
}

export interface RecapPaperSummary {
  paper_id: string
  title: string
  title_en: string
  institution: string
  categories: string[]
  saved_at: string
}

export type RecapStatus = 'ok' | 'insufficient_papers' | 'no_llm_config' | 'generating' | 'error'

export interface WeeklyRecapResponse {
  status: RecapStatus
  week_start: string
  week_end: string
  paper_count: number
  recap: RecapContent | null
  papers: RecapPaperSummary[]
}

export interface RecapHistoryItem {
  id: number
  week_start: string
  week_end: string
  paper_ids: string[]
  recap: RecapContent
  status: string
  created_at: string
  updated_at: string
}

export interface ReviewCard {
  paper_id?: string
  _paper_id?: string
  card_kind: 'review'
  review_reason: string
  days_since_saved: number
  saved_at: string
  short_title?: string
  '📖标题'?: string
  title?: string
  institution?: string
  institution_tier?: number
  categories?: string[]
  abstract?: string
  relevance_score?: number
  [key: string]: unknown
}

export type ReviewResponse = 'remember' | 'reread' | 'dismiss_forever' | 'skip'

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchCurrentRecap(force = false): Promise<WeeklyRecapResponse> {
  const { data } = await http.get<WeeklyRecapResponse>('/recaps/current', {
    params: force ? { force: true } : {},
  })
  return data
}

export async function generateRecap(): Promise<WeeklyRecapResponse> {
  const { data } = await http.post<WeeklyRecapResponse>('/recaps/current/generate')
  return data
}

export async function fetchRecapHistory(limit = 12): Promise<{ recaps: RecapHistoryItem[] }> {
  const { data } = await http.get<{ recaps: RecapHistoryItem[] }>('/recaps/history', {
    params: { limit },
  })
  return data
}

export async function fetchReviewCards(limit = 3): Promise<{ cards: ReviewCard[]; count: number }> {
  const { data } = await http.get<{ cards: ReviewCard[]; count: number }>('/recaps/review-cards', {
    params: { limit },
  })
  return data
}

export async function recordReviewResponse(
  paperId: string,
  response: ReviewResponse,
): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>(
    `/recaps/review-cards/${encodeURIComponent(paperId)}/response`,
    { response },
  )
  return data
}
