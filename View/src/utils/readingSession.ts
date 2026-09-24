import type { KbScope } from '../api'

export const readingSessionKey = 'ai4papers.active-reader'
export interface ReadingSession {
  path: string
  paperId: string
  paperTitle?: string
  scope?: KbScope
  mineruUrl?: string | null
  zhUrl?: string | null
  bilingualUrl?: string | null
  translating?: boolean
  version: string
  mode: 'mineru' | 'zh' | 'bilingual'
}
export function readReadingSession(): ReadingSession | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(readingSessionKey) || 'null')
    return value && value.path === location.pathname + location.search && typeof value.paperId === 'string'
      && ['mineru', 'zh', 'bilingual'].includes(value.mode) ? value : null
  } catch { return null }
}
