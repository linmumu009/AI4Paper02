/**
 * Research Radar API — daily aggregated summary for the radar panel.
 *
 * GET /api/radar/today?date=YYYY-MM-DD
 *
 * Aggregates five existing services into a single response.
 * Each section may be null for anonymous users or on partial failure.
 */
import { http } from './http'
import type { SuppressedPaper } from './preference'
import type { ReviewCard } from './recap'

// ── Section types ─────────────────────────────────────────────────────────

export interface RadarPapersSection {
  total_available: number
  visible_count: number
  quota_limit: number | null
  is_fallback: boolean
  effective_date: string
}

export interface RadarMissedSection {
  count: number
  preview: SuppressedPaper[]
}

export interface RadarReviewSection {
  count: number
  /** At most 1 preview card for the radar badge. */
  preview: ReviewCard[]
}

export type RadarRecapStatus =
  | 'ok'
  | 'insufficient_papers'
  | 'no_llm_config'
  | 'generating'
  | 'error'
  | 'none'

export interface RadarRecapSection {
  status: RadarRecapStatus
  paper_count: number
  week_start: string
  week_end: string
}

export interface RadarIdeasSection {
  total_available: number
  visible_count: number
  is_fallback: boolean
  effective_date: string
}

export interface RadarReactivationItem {
  kind: 'revisit' | 'question'
  title: string
  reason: string
  paper_id: string | null
}

export interface RadarReactivationSection {
  count: number
  preview: RadarReactivationItem[]
}

// ── Top-level response ────────────────────────────────────────────────────

export interface ResearchRadarResponse {
  date: string
  tier: string
  papers: RadarPapersSection
  /** null when the user is not authenticated or the section failed. */
  missed: RadarMissedSection | null
  review: RadarReviewSection | null
  recap: RadarRecapSection | null
  ideas: RadarIdeasSection | null
  /** null for anonymous users or when no recap history exists. */
  reactivation: RadarReactivationSection | null
}

// ── API function ──────────────────────────────────────────────────────────

export async function fetchResearchRadar(date: string): Promise<ResearchRadarResponse> {
  const { data } = await http.get<ResearchRadarResponse>('/radar/today', { params: { date } })
  return data
}
