import { reportAnalyticsEvents } from '../api'

interface PendingEvent {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}

let _queue: PendingEvent[] = []
let _flushTimer: ReturnType<typeof setTimeout> | null = null
const FLUSH_INTERVAL_MS = 10_000
const MAX_QUEUE_SIZE = 20

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
    // analytics errors must never break the app
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (_queue.length > 0) {
      const payload = JSON.stringify({ events: _queue })
      try {
        navigator.sendBeacon('/api/analytics/events', new Blob([payload], { type: 'application/json' }))
      } catch { /* ignore */ }
      _queue = []
    }
  })
}

export function trackPageView(pageName: string, meta?: Record<string, unknown>) {
  _enqueue({ event_type: 'page_view', target_type: 'page', target_id: pageName, meta })
}

export function trackPaperCardView(paperId: string) {
  _enqueue({ event_type: 'paper_card_view', target_type: 'paper', target_id: paperId })
}

export function trackPaperView(paperId: string, durationSeconds?: number) {
  _enqueue({ event_type: 'paper_view', target_type: 'paper', target_id: paperId, value: durationSeconds })
}

export function trackPaperViewDuration(paperId: string, durationSeconds: number) {
  _enqueue({ event_type: 'paper_view_duration', target_type: 'paper', target_id: paperId, value: durationSeconds })
}

export function trackSessionDuration(durationSeconds: number) {
  _enqueue({ event_type: 'session_duration', value: durationSeconds })
}

export function trackKbAction(action: string, paperId: string) {
  _enqueue({ event_type: `kb_${action}`, target_type: 'paper', target_id: paperId })
}

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

export function flushAnalytics() {
  _flush()
}
