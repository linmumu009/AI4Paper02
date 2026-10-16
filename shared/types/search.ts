export type GlobalSearchResultType = 'paper' | 'note' | 'compare' | 'research' | 'project' | 'user_paper'
export type GlobalSearchScope = 'all' | 'mine' | 'uncollected'
export type PaperCollectionStatus = 'collected' | 'uncollected' | 'uploaded'

export interface GlobalSearchResult {
  type: GlobalSearchResultType
  id: string
  title: string
  subtitle: string
  route: string
  updated_at: string
  score: number
  collection_status?: PaperCollectionStatus
}

export interface GlobalSearchResponse {
  query: string
  results: GlobalSearchResult[]
  total: number
  has_more?: boolean
}
