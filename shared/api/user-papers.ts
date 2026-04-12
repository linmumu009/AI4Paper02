import { http } from './http'
import type {
  UserPaper, UserPapersListResponse, UserPaperProcessStatusResponse,
  UserPaperTranslateStatusResponse, UserPaperFilesResponse, UserPaperTree,
} from '../types/user-papers'

export type UserPaperDerivativeType = 'mineru' | 'zh' | 'bilingual'

export async function importUserPaperManual(payload: {
  title: string
  authors?: string[]
  abstract?: string
  institution?: string
  year?: number | null
  external_url?: string
}): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/manual', payload)
  return data
}

export async function importUserPaperArxiv(arxivId: string): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/arxiv', { arxiv_id: arxivId })
  return data
}

export async function importUserPaperPdf(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<UserPaper>('/user-papers/import/pdf', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
    onUploadProgress: onProgress
      ? (e: any) => {
          if (e.total) onProgress(Math.round((e.loaded / e.total) * 100))
        }
      : undefined,
  })
  return data
}

export interface BatchProcessResult {
  paper_id: string
  ok: boolean
  message: string
}

export async function batchProcessUserPapers(
  paperIds: string[],
  opts?: { reward_id?: number },
): Promise<{ results: BatchProcessResult[]; priority: number; reward_applied: boolean }> {
  const { data } = await http.post<{ results: BatchProcessResult[]; priority: number; reward_applied: boolean }>(
    '/user-papers/batch-process',
    { paper_ids: paperIds, ...opts },
  )
  return data
}

export async function fetchUserPapers(opts?: {
  folder_id?: number | null
  status?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<UserPapersListResponse> {
  const { data } = await http.get<UserPapersListResponse>('/user-papers', { params: opts })
  return data
}

export async function fetchUserPaperInstitutions(): Promise<string[]> {
  const { data } = await http.get<{ institutions: string[] }>('/user-papers/institutions')
  return data.institutions
}

export async function fetchUserPaperDetail(paperId: string): Promise<UserPaper> {
  const { data } = await http.get<UserPaper>(`/user-papers/${paperId}`)
  return data
}

export async function updateUserPaper(paperId: string, payload: {
  title?: string
  authors?: string[]
  abstract?: string
  institution?: string
  year?: number | null
  external_url?: string
}): Promise<UserPaper> {
  const { data } = await http.patch<UserPaper>(`/user-papers/${paperId}`, payload)
  return data
}

export async function uploadUserPaperPdf(paperId: string, file: File): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<UserPaper>(`/user-papers/${paperId}/upload-pdf`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
  return data
}

export async function deleteUserPaper(paperId: string): Promise<{ ok: boolean; paper_id: string }> {
  const { data } = await http.delete<{ ok: boolean; paper_id: string }>(`/user-papers/${paperId}`)
  return data
}

export async function processUserPaper(
  paperId: string,
  opts?: { reward_id?: number },
): Promise<{ ok: boolean; message: string; paper_id: string; priority: number; reward_applied: boolean }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string; priority: number; reward_applied: boolean }>(
    `/user-papers/${paperId}/process`,
    opts ?? {},
  )
  return data
}

export async function fetchUserPaperProcessStatus(paperId: string): Promise<UserPaperProcessStatusResponse> {
  const { data } = await http.get<UserPaperProcessStatusResponse>(`/user-papers/${paperId}/process-status`)
  return data
}

export async function fetchUserPaperTree(): Promise<UserPaperTree> {
  const { data } = await http.get<UserPaperTree>('/user-papers/tree')
  return data
}

export async function translateUserPaper(paperId: string, opts?: { force?: boolean }): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>(`/user-papers/${paperId}/translate`, opts)
  return data
}

export async function retranslateUserPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>(`/user-papers/${paperId}/retranslate`)
  return data
}

export async function deleteUserPaperDerivative(paperId: string, type: UserPaperDerivativeType): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user-papers/${paperId}/derivatives/${type}`)
  return data
}

export async function fetchUserPaperTranslateStatus(paperId: string): Promise<UserPaperTranslateStatusResponse> {
  const { data } = await http.get<UserPaperTranslateStatusResponse>(`/user-papers/${paperId}/translate-status`)
  return data
}

export async function fetchUserPaperFiles(paperId: string): Promise<UserPaperFilesResponse> {
  const { data } = await http.get<UserPaperFilesResponse>(`/user-papers/${paperId}/files`)
  return data
}

export async function moveUserPapers(paperIds: string[], targetFolderId: number | null): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/user-papers/move', { paper_ids: paperIds, target_folder_id: targetFolderId })
  return data
}

export function userPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '排队中',
    queued_priority: '优先处理',
    starting: '启动中',
    pdf_prepare: '准备 PDF',
    pdf_download: '下载 PDF',
    pdf_extract: '提取文本',
    pdf_mineru: 'MinerU 解析',
    pdf_info: '解析论文信息',
    paper_summary: '生成摘要',
    summary_limit: '摘要限流',
    paper_assets: '生成详细分析',
    done: '已完成',
  }
  return labels[step] || step
}
