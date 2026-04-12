import type { PaperSummary, PaperAssets } from './paper'

export type UserPaperSourceType = 'pdf' | 'arxiv' | 'manual'
export type UserPaperProcessStatus = 'none' | 'pending' | 'processing' | 'completed' | 'failed'
export type UserPaperTranslateStatus = 'none' | 'processing' | 'completed' | 'failed'
export type UserPaperProcessStep =
  | 'queued'
  | 'queued_priority'
  | 'starting'
  | 'pdf_prepare'
  | 'pdf_download'
  | 'pdf_extract'
  | 'pdf_mineru'
  | 'pdf_info'
  | 'paper_summary'
  | 'summary_limit'
  | 'paper_assets'
  | 'done'
  | ''

export interface UserPaper {
  id: number
  paper_id: string
  user_id: number
  source_type: UserPaperSourceType
  source_ref: string
  title: string
  authors: string[]
  abstract: string
  institution: string
  year: number | null
  pdf_path: string | null
  pdf_static_url?: string | null
  mineru_static_url?: string | null
  zh_static_url?: string | null
  bilingual_static_url?: string | null
  external_url: string
  arxiv_pdf_url?: string | null
  summary_json: string | null
  paper_assets_json: string | null
  process_status: UserPaperProcessStatus
  process_step: UserPaperProcessStep
  process_error: string
  process_started_at: string | null
  process_finished_at: string | null
  translate_status?: UserPaperTranslateStatus
  translate_error?: string
  translate_progress?: number
  translate_started_at?: string | null
  translate_finished_at?: string | null
  summary?: PaperSummary | null
  paper_assets?: PaperAssets | null
  source?: 'user_upload'
  folder_id?: number | null
  created_at: string
  updated_at: string
}

export interface UserPaperFolder {
  id: number
  user_id: number
  scope: string
  name: string
  parent_id: number | null
  created_at: string
  updated_at: string
  children: UserPaperFolder[]
  papers: UserPaper[]
}

export interface UserPaperTree {
  folders: UserPaperFolder[]
  papers: UserPaper[]
}

export interface UserPaperProcessStatusResponse {
  paper_id: string
  process_status: UserPaperProcessStatus
  process_step: UserPaperProcessStep
  process_error: string
  process_started_at: string | null
  process_finished_at: string | null
}

export interface UserPaperTranslateStatusResponse {
  paper_id: string
  translate_status: UserPaperTranslateStatus
  translate_error: string
  translate_progress: number
  translate_started_at: string | null
  translate_finished_at: string | null
  busy: boolean
}

export type UserPaperFileViewMode = 'pdf' | 'mineru' | 'zh' | 'bilingual'

export interface UserPaperViewMdPayload {
  paperId: string
  title: string
  pdfUrl: string | null
  mdUrl: string | null
  viewMode?: UserPaperFileViewMode
  mineruUrl?: string | null
  zhUrl?: string | null
  bilingualUrl?: string | null
  scope?: 'kb' | 'mypapers'
  translateInProgress?: boolean
}

export interface UserPaperFilesResponse {
  paper_id: string
  pdf_static_url: string | null | undefined
  mineru_static_url: string | null | undefined
  zh_static_url: string | null | undefined
  bilingual_static_url: string | null | undefined
  exists: {
    pdf: boolean
    mineru: boolean
    zh: boolean
    bilingual: boolean
  }
  translate_status: UserPaperTranslateStatus
}

export interface UserPapersListResponse {
  total: number
  papers: UserPaper[]
}
