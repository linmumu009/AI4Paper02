import type { ResearchSession } from './research'

export type ProjectStatus = 'active' | 'archived'
export type ProjectAssetType = 'paper' | 'note' | 'compare_result' | 'idea'

export interface ResearchProjectCounts {
  paper?: number
  note?: number
  compare_result?: number
  idea?: number
  research_session?: number
  [key: string]: number | undefined
}

export interface ResearchProjectSummary {
  id: number
  user_id: number
  legacy_folder_id: number
  name: string
  objective: string
  description: string
  status: ProjectStatus
  created_at: string
  updated_at: string
  archived_at: string | null
  counts: ResearchProjectCounts
  asset_count: number
}

export interface ResearchProjectAsset {
  id: number
  project_id: number
  asset_type: ProjectAssetType
  asset_id: string
  source_scope: string
  metadata: Record<string, unknown>
  added_at: string
  title: string
  subtitle: string
  route: string
  missing: boolean
}

export interface ResearchProject extends ResearchProjectSummary {
  assets: ResearchProjectAsset[]
  sessions: ResearchSession[]
  paper_ids: string[]
}

export interface CreateResearchProjectPayload {
  name: string
  objective?: string
  description?: string
}

export interface UpdateResearchProjectPayload {
  name?: string
  objective?: string
  description?: string
}

export interface AddProjectAssetPayload {
  asset_type: ProjectAssetType
  asset_id: string
  source_scope?: string
  metadata?: Record<string, unknown>
}
