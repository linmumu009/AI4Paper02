import { http } from '@shared/api/client'

export type GlobalSearchResultType = 'paper' | 'note' | 'compare' | 'research' | 'user_paper'

export interface GlobalSearchResult {
  type: GlobalSearchResultType
  id: string
  title: string
  subtitle: string
  route: string
  updated_at: string
  score: number
}

export interface GlobalSearchResponse {
  query: string
  results: GlobalSearchResult[]
  total: number
}

export async function fetchGlobalSearch(query: string, limit = 30): Promise<GlobalSearchResponse> {
  const { data } = await http.get<GlobalSearchResponse>('/search', {
    params: { q: query, limit },
  })
  return data
}
