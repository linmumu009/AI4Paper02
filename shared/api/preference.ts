/**
 * Preference API — user preference learning closed loop.
 *
 * Endpoints under /api/preferences:
 *   GET  /profile              – current user's preference profile summary
 *   POST /nudge                – send 'more like this' / 'less like this' signal (paper-level)
 *   POST /category-nudge       – send more / less / reset signal for a whole category
 *   POST /rebuild              – force-rebuild preference profile
 *   GET  /suppressions         – Why-NOT: papers suppressed by the preference filter
 *   GET  /calibration/status   – per-user calibration status (Week 4)
 */
import { http } from './http'

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

export type NudgeDirection = 'more' | 'less'

export interface NudgeBody {
  paper_id: string
  direction: NudgeDirection
  categories?: string[]
  keywords?: string[]
  institution_tier?: number
}

/** A single Why-NOT contribution explaining why a paper was suppressed. */
export interface SuppressionContribution {
  type: 'category_positive' | 'category_negative' | 'keyword_positive' | 'keyword_negative' | 'tier_mismatch'
  key: string
  delta: number
  label: string
}

/** A paper that was suppressed by the preference filter. */
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

export interface SuppressionsResponse {
  date: string
  count: number
  suppressions: SuppressedPaper[]
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

export async function getPreferenceProfile(): Promise<PreferenceProfileSummary> {
  const res = await http.get<PreferenceProfileSummary>('/preferences/profile')
  return res.data
}

export async function nudgePaper(body: NudgeBody): Promise<{ ok: boolean; direction: NudgeDirection }> {
  const res = await http.post<{ ok: boolean; direction: NudgeDirection }>('/preferences/nudge', body)
  return res.data
}

export async function rebuildProfile(): Promise<PreferenceProfileSummary> {
  const res = await http.post<PreferenceProfileSummary>('/preferences/rebuild')
  return res.data
}

export async function getSuppressions(date: string, topN = 5): Promise<SuppressionsResponse> {
  const res = await http.get<SuppressionsResponse>('/preferences/suppressions', {
    params: { date, top_n: topN },
  })
  return res.data
}

export async function getCalibrationStatus(): Promise<CalibrationStatus> {
  const res = await http.get<CalibrationStatus>('/preferences/calibration/status')
  return res.data
}

export async function categoryNudge(
  category: string,
  direction: 'more' | 'less' | 'reset',
): Promise<{ ok: boolean; category: string; direction: string }> {
  const res = await http.post('/preferences/category-nudge', { category, direction })
  return res.data
}
