import { http } from './http'
import type { ResearchSession, ResearchTree } from '../types/research'

function getAuthHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...extra }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)session_id=([^;]*)/)
    if (match) headers['Authorization'] = `Bearer ${decodeURIComponent(match[1])}`
  }
  return headers
}

interface StartResearchPayload {
  question: string
  paper_ids: string[]
  scope?: string
  config?: {
    top_n?: number
    force_full_read?: boolean
  }
  reward_id?: number
}

export async function fetchResearchStream(payload: StartResearchPayload): Promise<Response> {
  return fetch('/api/research/start', {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify(payload),
  })
}

export async function fetchResearchSessions(limit = 20, savedOnly = false): Promise<{ sessions: ResearchSession[] }> {
  const { data } = await http.get<{ sessions: ResearchSession[] }>('/research/sessions', { params: { limit, saved_only: savedOnly } })
  return data
}

export async function saveResearchSession(sessionId: number, saved = true): Promise<void> {
  await http.patch(`/research/${sessionId}/save`, undefined, { params: { saved } })
}

export async function renameResearchSession(sessionId: number, question: string): Promise<void> {
  await http.patch(`/research/${sessionId}/rename`, { question })
}

export async function fetchResearchTree(): Promise<ResearchTree> {
  const { data } = await http.get<ResearchTree>('/research/tree')
  return data
}

export async function moveResearchSessions(sessionIds: number[], targetFolderId: number | null): Promise<void> {
  await http.patch('/research/move', { session_ids: sessionIds, target_folder_id: targetFolderId })
}

export async function fetchResearchSession(sessionId: number): Promise<ResearchSession> {
  const { data } = await http.get<ResearchSession>(`/research/${sessionId}`)
  return data
}

export async function deleteResearchSession(sessionId: number): Promise<void> {
  await http.delete(`/research/${sessionId}`)
}

export async function fetchResearchContinueRound3(sessionId: number, signal?: AbortSignal): Promise<Response> {
  return fetch(`/api/research/${sessionId}/continue-round3`, {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    signal,
  })
}

export async function fetchResearchFollowup(sessionId: number, followupQuestion: string, signal?: AbortSignal): Promise<Response> {
  return fetch(`/api/research/${sessionId}/followup`, {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify({ question: followupQuestion }),
    signal,
  })
}

export async function cancelResearchSession(sessionId: number): Promise<void> {
  await http.post(`/research/${sessionId}/cancel`)
}
