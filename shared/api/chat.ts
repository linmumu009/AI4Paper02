import { http } from './http'
import type { ChatMessage, ChatHistoryResponse } from '../types/research'

/** Read session_id from a non-HttpOnly cookie if available, for Bearer token fallback. */
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)session_id=([^;]*)/)
    if (match) headers['Authorization'] = `Bearer ${decodeURIComponent(match[1])}`
  }
  return headers
}

export async function fetchChatHistory(paperId: string): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatHistoryResponse>(`/papers/${encodeURIComponent(paperId)}/chat`)
  return data.messages
}

export async function fetchPaperChatStream(paperId: string, message: string): Promise<Response> {
  return fetch(`/api/papers/${encodeURIComponent(paperId)}/chat`, {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify({ message }),
  })
}

export async function clearChatHistory(paperId: string): Promise<void> {
  await http.delete(`/papers/${encodeURIComponent(paperId)}/chat`)
}

export async function fetchGeneralChatHistory(): Promise<ChatMessage[]> {
  const { data } = await http.get<{ messages: ChatMessage[] }>('/chat/general')
  return data.messages
}

export async function fetchGeneralChatStream(message: string): Promise<Response> {
  return fetch('/api/chat/general', {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify({ message }),
  })
}

export async function clearGeneralChatHistory(): Promise<void> {
  await http.delete('/chat/general')
}
