/**
 * Community domain types.
 * These were previously inline in shared/api/community.ts — moved here to
 * follow the established shared/types/ organisation pattern.
 */

export interface CommunityPost {
  id: number
  user_id: number
  username: string | null
  category: string
  title: string
  content?: string
  view_count: number
  reply_count: number
  like_count: number
  is_pinned: boolean
  is_closed: boolean
  last_reply_at: string | null
  created_at: string
  updated_at: string
  user_liked?: boolean
  replies?: CommunityReply[]
}

export interface CommunityReply {
  id: number
  post_id: number
  user_id: number
  username: string | null
  content: string
  like_count: number
  parent_reply_id?: number | null
  created_at: string
  updated_at: string
  user_liked?: boolean
}

export interface CommunityPostsResponse {
  total: number
  page: number
  page_size: number
  posts: CommunityPost[]
}
