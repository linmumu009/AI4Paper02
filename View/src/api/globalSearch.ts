import { http } from '@shared/api/client'
import type { GlobalSearchResponse, GlobalSearchScope } from '@shared/types/search'
export type { GlobalSearchResult, GlobalSearchResultType, GlobalSearchResponse, GlobalSearchScope, PaperCollectionStatus } from '@shared/types/search'

export async function fetchGlobalSearch(query: string, limit = 30, scope: GlobalSearchScope = 'all'): Promise<GlobalSearchResponse> {
  const { data } = await http.get<GlobalSearchResponse>('/search', {
    params: { q: query, limit, scope },
  })
  return data
}
