/**
 * Analytics event tracking composable.
 *
 * Collects user behavior events (page views, paper views, session duration, etc.)
 * and sends them to the backend in batches to minimize network overhead.
 *
 * Usage:
 *   import { trackPageView, trackPaperView, trackEvent } from '@/composables/useAnalytics'
 *   trackPageView('digest')
 *   trackPaperView('2602.05810', 45.2)  // paperId, durationSeconds
 */

import { reportAnalyticsEvents } from '../api'

interface PendingEvent {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Batch queue – events are collected and flushed periodically
// ---------------------------------------------------------------------------
let _queue: PendingEvent[] = []
let _flushTimer: ReturnType<typeof setTimeout> | null = null
const FLUSH_INTERVAL_MS = 10_000 // flush every 10 seconds
const MAX_QUEUE_SIZE = 20        // or when 20 events accumulate

function _enqueue(event: PendingEvent) {
  _queue.push(event)
  if (_queue.length >= MAX_QUEUE_SIZE) {
    _flush()
  } else if (!_flushTimer) {
    _flushTimer = setTimeout(_flush, FLUSH_INTERVAL_MS)
  }
}

async function _flush() {
  if (_flushTimer) {
    clearTimeout(_flushTimer)
    _flushTimer = null
  }
  if (_queue.length === 0) return
  const batch = _queue.splice(0)
  try {
    await reportAnalyticsEvents(batch)
  } catch {
    // Silently ignore – analytics should never break the app
  }
}

// Flush on page unload
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (_queue.length > 0) {
      // Use sendBeacon for reliability during page unload
      const payload = JSON.stringify({ events: _queue })
      const url = '/api/analytics/events'
      try {
        navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }))
      } catch {
        // fallback: ignore
      }
      _queue = []
    }
  })
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Track a page view event */
export function trackPageView(pageName: string, meta?: Record<string, unknown>) {
  _enqueue({
    event_type: 'page_view',
    target_type: 'page',
    target_id: pageName,
    meta,
  })
}

/** Track a paper card being viewed in the recommendation list */
export function trackPaperCardView(paperId: string) {
  _enqueue({
    event_type: 'paper_card_view',
    target_type: 'paper',
    target_id: paperId,
  })
}

/** Track paper detail page view with optional duration */
export function trackPaperView(paperId: string, durationSeconds?: number) {
  _enqueue({
    event_type: 'paper_view',
    target_type: 'paper',
    target_id: paperId,
    value: durationSeconds,
  })
}

/** Track time spent on a paper detail page */
export function trackPaperViewDuration(paperId: string, durationSeconds: number) {
  _enqueue({
    event_type: 'paper_view_duration',
    target_type: 'paper',
    target_id: paperId,
    value: durationSeconds,
  })
}

/** Track session duration (called periodically or on unload) */
export function trackSessionDuration(durationSeconds: number) {
  _enqueue({
    event_type: 'session_duration',
    value: durationSeconds,
  })
}

/** Track a knowledge base action (save, note, annotation, dismiss) */
export function trackKbAction(action: string, paperId: string) {
  _enqueue({
    event_type: `kb_${action}`,
    target_type: 'paper',
    target_id: paperId,
  })
}

/** Generic event tracker */
export function trackEvent(eventType: string, opts?: {
  targetType?: string
  targetId?: string
  value?: number
  meta?: Record<string, unknown>
}) {
  _enqueue({
    event_type: eventType,
    target_type: opts?.targetType,
    target_id: opts?.targetId,
    value: opts?.value,
    meta: opts?.meta,
  })
}

/** Force flush all pending events immediately */
export function flushAnalytics() {
  _flush()
}
