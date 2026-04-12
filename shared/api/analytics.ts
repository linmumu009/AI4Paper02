import { http } from './http'

interface PendingAnalyticsEvent {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}

export async function reportAnalyticsEvent(event: {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}): Promise<void> {
  await http.post('/analytics/events', { events: [event] })
}

export async function reportAnalyticsEvents(events: PendingAnalyticsEvent[]): Promise<void> {
  if (!events.length) return
  await http.post('/analytics/events', { events })
}
