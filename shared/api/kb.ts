import { http } from './http'
import type {
  KbTree, KbFolder, KbPaper, KbNote, KbNotesResponse,
  KbAnnotation, KbAnnotationsResponse, KbCompareResult, KbCompareResultsTree,
} from '../types/kb'
import type { PaperSummary } from '../types/paper'

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)session_id=([^;]*)/)
    if (match) headers['Authorization'] = `Bearer ${decodeURIComponent(match[1])}`
  }
  return headers
}

export type KbScope = 'kb' | 'inspiration' | 'mypapers' | 'research'

export async function fetchKbTree(scope: KbScope = 'kb'): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree', { params: { scope } })
  return data
}

export async function createKbFolder(name: string, parentId?: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', { name, parent_id: parentId ?? null, scope })
  return data
}

export async function renameKbFolder(folderId: number, name: string, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name, scope })
  return data
}

export async function moveKbFolder(folderId: number, targetParentId: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, { target_parent_id: targetParentId, scope })
  return data
}

export async function deleteKbFolder(folderId: number, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`, { params: { scope } })
}

export async function addKbPaper(paperId: string, paperData: PaperSummary, folderId?: number | null, scope: KbScope = 'kb'): Promise<KbPaper> {
  const { data } = await http.post<KbPaper>('/kb/papers', { paper_id: paperId, paper_data: paperData, folder_id: folderId ?? null, scope })
  return data
}

export async function removeKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`, { params: { scope } })
}

export async function moveKbPapers(paperIds: string[], targetFolderId: number | null, scope: KbScope = 'kb'): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/kb/papers/move', { paper_ids: paperIds, target_folder_id: targetFolderId, scope })
  return data
}

export async function checkPaperInKb(paperId: string, scope: KbScope = 'kb'): Promise<boolean> {
  const { data } = await http.get<{ exists: boolean }>(`/kb/papers/${encodeURIComponent(paperId)}/exists`, { params: { scope } })
  return data.exists
}

export async function dismissPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/kb/dismiss', { paper_id: paperId })
  return data
}

export async function renameKbPaper(paperId: string, title: string, scope: KbScope = 'kb'): Promise<KbPaper> {
  const { data } = await http.patch<KbPaper>(`/kb/papers/${paperId}/rename`, { title, scope })
  return data
}

export async function fetchNotes(paperId: string, scope: KbScope = 'kb'): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`, { params: { scope } })
  return data
}

export async function createNote(paperId: string, title = '未命名笔记', content = '', scope: KbScope = 'kb'): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content, scope })
  return data
}

export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

export async function updateNote(noteId: number, payload: { title?: string; content?: string }): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

export async function uploadNoteFile(paperId: string, file: File, scope: KbScope = 'kb'): Promise<KbNote> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/upload`, form, {
    params: { scope },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

export async function addNoteLink(paperId: string, title: string, url: string, scope: KbScope = 'kb'): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/link`, { title, url, scope })
  return data
}

export async function fetchAnnotations(paperId: string, scope: KbScope = 'kb'): Promise<KbAnnotationsResponse> {
  const { data } = await http.get<KbAnnotationsResponse>(`/kb/papers/${paperId}/annotations`, { params: { scope } })
  return data
}

export async function createAnnotation(paperId: string, payload: { page: number; type?: string; content?: string; color?: string; position_data?: string }, scope: KbScope = 'kb'): Promise<KbAnnotation> {
  const { data } = await http.post<KbAnnotation>(`/kb/papers/${paperId}/annotations`, { ...payload, scope })
  return data
}

export async function updateAnnotation(annotationId: number, payload: { content?: string; color?: string; position_data?: string }): Promise<KbAnnotation> {
  const { data } = await http.patch<KbAnnotation>(`/kb/annotations/${annotationId}`, payload)
  return data
}

export async function deleteAnnotation(annotationId: number): Promise<void> {
  await http.delete(`/kb/annotations/${annotationId}`)
}

export async function fetchCompareResultsTree(): Promise<KbCompareResultsTree> {
  const { data } = await http.get<KbCompareResultsTree>('/kb/compare-results/tree')
  return data
}

export async function saveCompareResult(title: string, markdown: string, paperIds: string[], folderId?: number | null): Promise<KbCompareResult> {
  const { data } = await http.post<KbCompareResult>('/kb/compare-results', { title, markdown, paper_ids: paperIds, folder_id: folderId ?? null })
  return data
}

export async function fetchCompareResult(resultId: number): Promise<KbCompareResult> {
  const { data } = await http.get<KbCompareResult>(`/kb/compare-results/${resultId}`)
  return data
}

export async function renameCompareResult(resultId: number, title: string): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}`, { title })
  return data
}

export async function moveCompareResult(resultId: number, targetFolderId: number | null): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}/move`, { target_folder_id: targetFolderId })
  return data
}

export async function deleteCompareResult(resultId: number): Promise<void> {
  await http.delete(`/kb/compare-results/${resultId}`)
}

export async function fetchCompareStream(
  paperIds: string[],
  scope: KbScope = 'kb',
  compareResultIds?: number[],
  rewardId?: number,
): Promise<Response> {
  const body: Record<string, unknown> = { paper_ids: paperIds, scope }
  if (compareResultIds && compareResultIds.length > 0) body.compare_result_ids = compareResultIds
  if (rewardId !== undefined) body.reward_id = rewardId
  return fetch('/api/kb/compare', {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify(body),
  })
}

export async function updateKbPaperReadStatus(paperId: string, readStatus: 'unread' | 'reading' | 'read', scope = 'kb'): Promise<{ ok: boolean }> {
  const { data } = await http.patch<{ ok: boolean }>(`/kb/papers/${paperId}/read-status`, { status: readStatus, scope })
  return data
}

export async function fetchAutoClassifyPendingCount(scope = 'kb'): Promise<{ pending: number }> {
  const { data } = await http.get<{ pending: number }>('/kb/auto-classify/pending-count', { params: { scope } })
  return data
}

export async function fetchAutoClassifyUnclassifiedCount(scope = 'kb'): Promise<{ unclassified: number }> {
  const { data } = await http.get<{ unclassified: number }>('/kb/auto-classify/unclassified-count', { params: { scope } })
  return data
}

export async function syncAutoClassifyFolders(scope = 'kb', dryRun = false): Promise<{ ok: boolean; enqueued: number; dry_run_report?: any }> {
  const { data } = await http.post<{ ok: boolean; enqueued: number; dry_run_report?: any }>('/kb/auto-classify/sync-folders', { scope, dry_run: dryRun })
  return data
}

export async function reclassifyAllKbPapers(scope = 'kb'): Promise<{ ok: boolean; enqueued: number }> {
  const { data } = await http.post<{ ok: boolean; enqueued: number }>('/kb/auto-classify/reclassify-all', { scope })
  return data
}

export async function classifyKbPaper(paperId: string, scope = 'kb'): Promise<{ ok: boolean; enqueued: boolean }> {
  const { data } = await http.post<{ ok: boolean; enqueued: boolean }>(`/kb/papers/${paperId}/classify`, { scope })
  return data
}

/**
 * Export the entire knowledge base as a portable JSON archive.
 * Triggers a browser download via the API's Content-Disposition header.
 */
export function downloadKbExport(scope: 'kb' | 'idea_library' = 'kb'): void {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  const params = new URLSearchParams({ scope })
  const a = document.createElement('a')
  a.href = `${base}/kb/export?${params.toString()}`
  a.download = `kb_export_${scope}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
