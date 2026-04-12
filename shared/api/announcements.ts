import { http } from './http'
import type { Announcement, AnnouncementsResponse, AnnouncementResponse, AnnouncementTag } from '../types/auth'

export async function fetchAnnouncements(params?: {
  tag?: AnnouncementTag
  limit?: number
  offset?: number
  unread_only?: boolean
}): Promise<AnnouncementsResponse> {
  const { data } = await http.get<AnnouncementsResponse>('/announcements', { params })
  return data
}

export async function createAnnouncement(payload: {
  title: string
  content: string
  tag?: AnnouncementTag
  is_pinned?: boolean
}): Promise<AnnouncementResponse> {
  const { data } = await http.post<AnnouncementResponse>('/announcements', payload)
  return data
}

export async function updateAnnouncement(id: number, payload: {
  title?: string
  content?: string
  tag?: AnnouncementTag
  is_pinned?: boolean
}): Promise<AnnouncementResponse> {
  const { data } = await http.patch<AnnouncementResponse>(`/announcements/${id}`, payload)
  return data
}

export async function deleteAnnouncement(id: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/announcements/${id}`)
  return data
}

export async function fetchUnreadAnnouncementCount(): Promise<{ ok: boolean; count: number }> {
  const { data } = await http.get<{ ok: boolean; count: number }>('/announcements/unread-count')
  return data
}

export async function markAnnouncementsRead(ids: number[]): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-read', { ids })
  return data
}

export async function markAllAnnouncementsRead(): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-all-read')
  return data
}
