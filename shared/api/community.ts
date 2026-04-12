import { http } from './http'
import type { CommunityPost, CommunityReply, CommunityPostsResponse } from '../types/community'

// Re-export from canonical types so consumers can import from either location
export type { CommunityPost, CommunityReply, CommunityPostsResponse }


export async function fetchCommunityPosts(params: {
  category?: string
  page?: number
  page_size?: number
  sort?: string
}): Promise<CommunityPostsResponse> {
  const { data } = await http.get<CommunityPostsResponse>('/community/posts', { params })
  return data
}

export async function fetchCommunityPost(id: number): Promise<CommunityPost> {
  const { data } = await http.get<CommunityPost>(`/community/posts/${id}`)
  return data
}

export async function createCommunityPost(payload: { category: string; title: string; content: string }): Promise<CommunityPost> {
  const { data } = await http.post<CommunityPost>('/community/posts', payload)
  return data
}

export async function updateCommunityPost(id: number, payload: { category?: string; title?: string; content?: string }): Promise<CommunityPost> {
  const { data } = await http.put<CommunityPost>(`/community/posts/${id}`, payload)
  return data
}

export async function deleteCommunityPost(id: number): Promise<void> {
  await http.delete(`/community/posts/${id}`)
}

export async function createCommunityReply(postId: number, payload: { content: string; parent_reply_id?: number | null }): Promise<CommunityReply> {
  const { data } = await http.post<CommunityReply>(`/community/posts/${postId}/replies`, payload)
  return data
}

export async function updateCommunityReply(replyId: number, payload: { content: string }): Promise<CommunityReply> {
  const { data } = await http.put<CommunityReply>(`/community/replies/${replyId}`, payload)
  return data
}

export async function deleteCommunityReply(replyId: number): Promise<void> {
  await http.delete(`/community/replies/${replyId}`)
}

export async function toggleCommunityLike(targetType: 'post' | 'reply', targetId: number): Promise<{ liked: boolean; like_count: number }> {
  const { data } = await http.post<{ liked: boolean; like_count: number }>('/community/like', { target_type: targetType, target_id: targetId })
  return data
}

export async function pinCommunityPost(postId: number, pinned: boolean): Promise<{ ok: boolean; is_pinned: boolean }> {
  const { data } = await http.put<{ ok: boolean; is_pinned: boolean }>(`/community/posts/${postId}/pin`, { pinned })
  return data
}

export async function closeCommunityPost(postId: number, closed: boolean): Promise<{ ok: boolean; is_closed: boolean }> {
  const { data } = await http.put<{ ok: boolean; is_closed: boolean }>(`/community/posts/${postId}/close`, { closed })
  return data
}
