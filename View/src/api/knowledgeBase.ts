import { apiClient, http } from '@shared/api/client'
import type {
  ChatHistoryResponse,
  ChatMessage,
  KbAnnotation,
  KbAnnotationsResponse,
  KbCompareResult,
  KbCompareResultsTree,
  KbFolder,
  KbNote,
  KbNotesResponse,
  KbPaper,
  KbTree,
  PaperSummary,
} from '../types/paper'

// ---------------------------------------------------------------------------
// Knowledge Base API
// ---------------------------------------------------------------------------

export type KbScope = 'kb' | 'inspiration' | 'mypapers' | 'research'

/** 获取知识库完整树 */
export async function fetchKbTree(scope: KbScope = 'kb'): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree', { params: { scope } })
  return data
}

/** 创建文件夹 */
export async function createKbFolder(name: string, parentId?: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', {
    name,
    parent_id: parentId ?? null,
    scope,
  })
  return data
}

/** 重命名文件夹 */
export async function renameKbFolder(folderId: number, name: string, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name, scope })
  return data
}

/** 移动文件夹到新的父目录 (null = 根目录) */
export async function moveKbFolder(folderId: number, targetParentId: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, {
    target_parent_id: targetParentId,
    scope,
  })
  return data
}

/** 删除文件夹 */
export async function deleteKbFolder(folderId: number, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`, { params: { scope } })
}

/** 将论文加入知识库 */
export async function addKbPaper(
  paperId: string,
  paperData: PaperSummary,
  folderId?: number | null,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.post<KbPaper>('/kb/papers', {
    paper_id: paperId,
    paper_data: paperData,
    folder_id: folderId ?? null,
    scope,
  })
  return data
}

/** 从知识库移除论文 */
export async function removeKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`, { params: { scope } })
}

/** 批量移动论文到目标文件夹 (null = 根目录) */
export async function moveKbPapers(
  paperIds: string[],
  targetFolderId: number | null,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/kb/papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
    scope,
  })
  return data
}

// ---------------------------------------------------------------------------
// Note / File API
// ---------------------------------------------------------------------------

/** 获取论文下所有笔记/文件 */
export async function fetchNotes(paperId: string, scope: KbScope = 'kb'): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`, { params: { scope } })
  return data
}

/** 新建 Markdown 笔记 */
export async function createNote(
  paperId: string,
  title: string = '未命名笔记',
  content: string = '',
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content, scope })
  return data
}

/** 获取单个笔记详情（含内容） — scope 不需要，note_id 全局唯一 */
export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

/** 更新笔记标题/内容 — scope 不需要，note_id 全局唯一 */
export async function updateNote(
  noteId: number,
  payload: { title?: string; content?: string },
): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

/** 删除笔记/文件 — scope 不需要，note_id 全局唯一 */
export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

/** 上传文件到论文 */
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

/** 添加外部链接 */
export async function addNoteLink(
  paperId: string,
  title: string,
  url: string,
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/link`, { title, url, scope })
  return data
}

// ---------------------------------------------------------------------------
// Paper Compare (SSE streaming)
// ---------------------------------------------------------------------------

/** Initiate a streaming comparison analysis of 2-5 KB papers.
 *  Returns a raw Response whose body is an SSE text/event-stream.
 *  Each `data:` line is a JSON-encoded string chunk; the final line is `data: [DONE]`.
 */
export async function fetchCompareStream(
  paperIds: string[],
  scope: KbScope = 'kb',
  compareResultIds?: number[],
  rewardId?: number,
): Promise<Response> {
  const body: Record<string, unknown> = { paper_ids: paperIds, scope }
  if (compareResultIds && compareResultIds.length > 0) {
    body.compare_result_ids = compareResultIds
  }
  if (rewardId !== undefined) {
    body.reward_id = rewardId
  }
  return apiClient.stream({ method: 'POST', path: '/kb/compare', body })
}

// ---------------------------------------------------------------------------
// Paper Chat API (论文追问问答)
// ---------------------------------------------------------------------------

/** 获取某篇论文的聊天历史记录 */
export async function fetchChatHistory(paperId: string): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatHistoryResponse>(`/papers/${encodeURIComponent(paperId)}/chat`)
  return data.messages
}

/**
 * 向论文发送追问消息并获取 SSE 流式回复。
 * 返回原始 Response，调用方负责读取 body stream。
 * 传入 AbortSignal 可在流式回复过程中中断请求。
 */
export async function fetchPaperChatStream(paperId: string, message: string, signal?: AbortSignal): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: `/papers/${encodeURIComponent(paperId)}/chat`,
    body: { message },
    signal,
  })
}

/** 清空某篇论文的聊天记录 */
export async function clearChatHistory(paperId: string): Promise<void> {
  await http.delete(`/papers/${encodeURIComponent(paperId)}/chat`)
}

/** 通用助手聊天历史 */
export async function fetchGeneralChatHistory(): Promise<ChatMessage[]> {
  const { data } = await http.get<{ messages: ChatMessage[] }>('/chat/general')
  return data.messages
}

export async function fetchGeneralChatStream(message: string, signal?: AbortSignal): Promise<Response> {
  return apiClient.stream({
    method: 'POST',
    path: '/chat/general',
    body: { message },
    signal,
  })
}

export async function clearGeneralChatHistory(): Promise<void> {
  await http.delete('/chat/general')
}

/** 检查论文是否已在知识库 */
export async function checkPaperInKb(paperId: string, scope: KbScope = 'kb'): Promise<boolean> {
  const { data } = await http.get<{ exists: boolean }>(
    `/kb/papers/${encodeURIComponent(paperId)}/exists`,
    { params: { scope } },
  )
  return data.exists
}

// ---------------------------------------------------------------------------
// Dismiss Paper API
// ---------------------------------------------------------------------------

/** 标记论文为不感兴趣 */
export async function dismissPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/kb/dismiss', { paper_id: paperId })
  return data
}

// ---------------------------------------------------------------------------
// Paper Rename API
// ---------------------------------------------------------------------------

/** 重命名论文显示标题 */
export async function renameKbPaper(
  paperId: string,
  title: string,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.patch<KbPaper>(`/kb/papers/${paperId}/rename`, { title, scope })
  return data
}

// ---------------------------------------------------------------------------
// Compare Results API
// ---------------------------------------------------------------------------

/** 获取对比分析结果树 */
export async function fetchCompareResultsTree(): Promise<KbCompareResultsTree> {
  const { data } = await http.get<KbCompareResultsTree>('/kb/compare-results/tree')
  return data
}

/** 保存对比分析结果 */
export async function saveCompareResult(
  title: string,
  markdown: string,
  paperIds: string[],
  folderId?: number | null,
): Promise<KbCompareResult> {
  const { data } = await http.post<KbCompareResult>('/kb/compare-results', {
    title,
    markdown,
    paper_ids: paperIds,
    folder_id: folderId ?? null,
  })
  return data
}

/** 获取单个对比分析结果 */
export async function fetchCompareResult(resultId: number): Promise<KbCompareResult> {
  const { data } = await http.get<KbCompareResult>(`/kb/compare-results/${resultId}`)
  return data
}

/** 重命名对比分析结果 */
export async function renameCompareResult(resultId: number, title: string): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}`, { title })
  return data
}

/** 移动对比分析结果到文件夹 */
export async function moveCompareResult(resultId: number, targetFolderId: number | null): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}/move`, {
    target_folder_id: targetFolderId,
  })
  return data
}

/** 删除对比分析结果 */
export async function deleteCompareResult(resultId: number): Promise<void> {
  await http.delete(`/kb/compare-results/${resultId}`)
}

// ---------------------------------------------------------------------------
// Annotation API
// ---------------------------------------------------------------------------

/** 获取论文的所有批注 */
export async function fetchAnnotations(paperId: string, scope: KbScope = 'kb'): Promise<KbAnnotationsResponse> {
  const { data } = await http.get<KbAnnotationsResponse>(`/kb/papers/${paperId}/annotations`, { params: { scope } })
  return data
}

/** 创建批注 */
export async function createAnnotation(
  paperId: string,
  payload: {
    page: number
    type?: string
    content?: string
    color?: string
    position_data?: string
  },
  scope: KbScope = 'kb',
): Promise<KbAnnotation> {
  const { data } = await http.post<KbAnnotation>(`/kb/papers/${paperId}/annotations`, { ...payload, scope })
  return data
}

/** 更新批注 — scope 不需要，annotation_id 全局唯一 */
export async function updateAnnotation(
  annotationId: number,
  payload: { content?: string; color?: string },
): Promise<KbAnnotation> {
  const { data } = await http.patch<KbAnnotation>(`/kb/annotations/${annotationId}`, payload)
  return data
}

/** 删除批注 — scope 不需要，annotation_id 全局唯一 */
export async function deleteAnnotation(annotationId: number): Promise<void> {
  await http.delete(`/kb/annotations/${annotationId}`)
}
