import type { PaperSummary } from './paper'

export interface KbPaper {
  id: number
  paper_id: string
  folder_id: number | null
  paper_data: PaperSummary
  created_at: string
  note_count?: number
  pdf_static_url?: string | null
  mineru_static_url?: string | null
  zh_static_url?: string | null
  bilingual_static_url?: string | null
  process_status?: 'none' | 'pending' | 'processing' | 'completed' | 'failed'
  process_step?: string
  process_error?: string
  translate_status?: 'none' | 'processing' | 'completed' | 'failed'
  translate_progress?: number
  translate_error?: string
  classify_status?: 'none' | 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  classify_folder_id?: number | null
  classify_confidence?: number | null
  classify_error?: string
  classify_reason?: string
  read_status?: 'unread' | 'reading' | 'read'
}

export interface KbPaperProcessStatusResponse {
  paper_id: string
  process_status: 'none' | 'pending' | 'processing' | 'completed' | 'failed'
  process_step: string
  process_error: string
}

export interface KbPaperTranslateStatusResponse {
  paper_id: string
  translate_status: 'none' | 'processing' | 'completed' | 'failed'
  translate_progress: number
  translate_error: string
  busy: boolean
}

export interface KbPaperFilesResponse {
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
  process_status: string
  process_step: string
  translate_status: string
  translate_progress: number
}

export interface KbNote {
  id: number
  paper_id: string
  type: 'markdown' | 'file' | 'link'
  title: string
  content?: string
  file_path?: string
  file_url?: string
  file_size?: number
  mime_type?: string
  created_at: string
  updated_at: string
}

export interface KbNotesResponse {
  paper_id: string
  notes: KbNote[]
}

export interface KbAnnotation {
  id: number
  paper_id: string
  page: number
  type: 'highlight' | 'text' | 'box'
  content: string
  color: string
  position_data: string
  created_at: string
  updated_at: string
}

export interface KbAnnotationsResponse {
  paper_id: string
  annotations: KbAnnotation[]
}

export interface KbFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbFolder[]
  papers: KbPaper[]
  created_at: string
  updated_at: string
}

export interface KbTree {
  folders: KbFolder[]
  papers: KbPaper[]
}

export interface KbMenuItem {
  key: string
  label: string
  danger?: boolean
  disabled?: boolean
  icon?: 'research' | 'compare'
}

export interface KbCompareResult {
  id: number
  title: string
  markdown: string
  paper_ids: string[]
  folder_id: number | null
  created_at: string
  updated_at: string
}

export interface KbCompareFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbCompareFolder[]
  results: KbCompareResult[]
  created_at: string
  updated_at: string
}

export interface KbCompareResultsTree {
  folders: KbCompareFolder[]
  results: KbCompareResult[]
}

export interface CompareCartItem {
  id: string
  title: string
  source: 'kb' | 'mypapers' | 'compare'
  type: 'paper' | 'compare_result'
}
