/**
 * Research outcome view-model derivation.
 *
 * Converts a list of RecapHistoryItem records (already fetched from
 * /recaps/history) into three progressively richer outcome models:
 *
 *   researchMap      – derived from the most recent recap (≥1)
 *   trendSummary     – derived from the 2 most recent recaps (≥2)
 *   topicEvolution   – derived from the 4 most recent recaps (≥4)
 *
 * All models degrade gracefully to null when history is insufficient.
 * No API calls are made here; callers are responsible for fetching.
 */
import type { RecapHistoryItem } from '../api/recap'

// ── View model types ────────────────────────────────────────────────────────

/** 7-day research map: single-week themes, connections and follow-up questions. */
export interface ResearchMapModel {
  title: string
  summary: string
  themes: Array<{ name: string; insight: string; paper_ids: string[] }>
  connections: string[]
  next_questions: string[]
  week_label: string
  paper_count: number
}

/** 14-day trend summary: theme movement across the two most recent recaps. */
export interface TrendSummaryModel {
  /** Themes present in both weeks — your stable focus areas. */
  persistent_themes: string[]
  /** Themes in the latest week but not the previous — newly emerging. */
  new_themes: string[]
  /** Themes in the previous week but not the latest — fading attention. */
  faded_themes: string[]
  /** [earlier week label, latest week label] */
  week_labels: [string, string]
}

/** One week's slice in the 30-day topic evolution. */
export interface TopicEvolutionWeek {
  week_label: string
  themes: string[]
  paper_count: number
}

/** 30-day topic evolution: up to 4 weeks rendered in chronological order. */
export interface TopicEvolutionModel {
  weeks: TopicEvolutionWeek[]
}

export interface ResearchOutcomes {
  /** Requires ≥1 recap. null otherwise. */
  researchMap: ResearchMapModel | null
  /** Requires ≥2 recaps. null otherwise. */
  trendSummary: TrendSummaryModel | null
  /** Requires ≥4 recaps. null otherwise. */
  topicEvolution: TopicEvolutionModel | null
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function _weekLabel(start: string, end: string): string {
  if (!start) return ''
  const fmt = (iso: string) => {
    const d = new Date(iso)
    return `${d.getMonth() + 1}/${d.getDate()}`
  }
  return end ? `${fmt(start)}–${fmt(end)}` : fmt(start)
}

function _themeNames(item: RecapHistoryItem): string[] {
  return (item.recap?.themes ?? []).map(t => t.name).filter(Boolean)
}

// ── Main derivation function ────────────────────────────────────────────────

/**
 * Pure function — safe to call in a `computed()` or a watcher.
 * Returns derived outcomes from the given recap history array.
 */
export function deriveResearchOutcomes(history: RecapHistoryItem[]): ResearchOutcomes {
  // Most-recent first
  const sorted = [...history].sort((a, b) => b.week_start.localeCompare(a.week_start))

  // ── Research map (≥1 recap) ────────────────────────────────────────────
  let researchMap: ResearchMapModel | null = null
  if (sorted.length >= 1) {
    const latest = sorted[0]!
    const rc = latest.recap
    researchMap = {
      title: rc?.title ?? '',
      summary: rc?.summary ?? '',
      themes: (rc?.themes ?? []).map(t => ({
        name: t.name,
        insight: t.insight ?? '',
        paper_ids: t.paper_ids ?? [],
      })),
      connections: rc?.connections ?? [],
      next_questions: rc?.next_questions ?? [],
      week_label: _weekLabel(latest.week_start, latest.week_end),
      paper_count: rc?.paper_count ?? (latest.paper_ids?.length ?? 0),
    }
  }

  // ── Trend summary (≥2 recaps) ──────────────────────────────────────────
  let trendSummary: TrendSummaryModel | null = null
  if (sorted.length >= 2) {
    const latest = sorted[0]!
    const prev = sorted[1]!
    const latestSet = new Set(_themeNames(latest))
    const prevSet = new Set(_themeNames(prev))

    trendSummary = {
      persistent_themes: [...latestSet].filter(t => prevSet.has(t)),
      new_themes: [...latestSet].filter(t => !prevSet.has(t)),
      faded_themes: [...prevSet].filter(t => !latestSet.has(t)),
      week_labels: [
        _weekLabel(prev.week_start, prev.week_end),
        _weekLabel(latest.week_start, latest.week_end),
      ],
    }
  }

  // ── Topic evolution (≥4 recaps) ────────────────────────────────────────
  let topicEvolution: TopicEvolutionModel | null = null
  if (sorted.length >= 4) {
    // Show oldest → newest so the timeline reads left-to-right
    topicEvolution = {
      weeks: sorted.slice(0, 4).reverse().map(item => ({
        week_label: _weekLabel(item.week_start, item.week_end),
        themes: _themeNames(item),
        paper_count: item.recap?.paper_count ?? (item.paper_ids?.length ?? 0),
      })),
    }
  }

  return { researchMap, trendSummary, topicEvolution }
}
