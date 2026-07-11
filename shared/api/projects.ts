import { http } from './http'
import type {
  AddProjectAssetPayload,
  CreateResearchProjectPayload,
  ResearchProject,
  ResearchProjectAsset,
  ResearchProjectSummary,
  UpdateResearchProjectPayload,
} from '../types/project'

export async function fetchResearchProjects(includeArchived = false): Promise<ResearchProjectSummary[]> {
  const { data } = await http.get<{ projects: ResearchProjectSummary[] }>('/projects', {
    params: { include_archived: includeArchived || undefined },
  })
  return data.projects
}

export async function createResearchProject(
  payload: CreateResearchProjectPayload,
): Promise<ResearchProjectSummary> {
  const { data } = await http.post<ResearchProjectSummary>('/projects', payload)
  return data
}

export async function fetchResearchProject(projectId: number): Promise<ResearchProject> {
  const { data } = await http.get<ResearchProject>(`/projects/${projectId}`)
  return data
}

export async function updateResearchProject(
  projectId: number,
  payload: UpdateResearchProjectPayload,
): Promise<ResearchProjectSummary> {
  const { data } = await http.patch<ResearchProjectSummary>(`/projects/${projectId}`, payload)
  return data
}

export async function archiveResearchProject(projectId: number): Promise<void> {
  await http.post(`/projects/${projectId}/archive`)
}

export async function restoreResearchProject(projectId: number): Promise<void> {
  await http.post(`/projects/${projectId}/restore`)
}

export async function deleteResearchProject(projectId: number): Promise<void> {
  await http.delete(`/projects/${projectId}`)
}

export async function addResearchProjectAsset(
  projectId: number,
  payload: AddProjectAssetPayload,
): Promise<ResearchProjectAsset> {
  const { data } = await http.post<ResearchProjectAsset>(`/projects/${projectId}/assets`, payload)
  return data
}

export async function removeResearchProjectAsset(
  projectId: number,
  assetType: string,
  assetId: string,
  sourceScope = '',
): Promise<void> {
  await http.delete(`/projects/${projectId}/assets/${assetType}/${encodeURIComponent(assetId)}`, {
    params: { source_scope: sourceScope || undefined },
  })
}
