import { http } from './http'

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)session_id=([^;]*)/)
    if (match) headers['Authorization'] = `Bearer ${decodeURIComponent(match[1])}`
  }
  return headers
}

import type {
  IdeaAtom, IdeaQuestion, IdeaCandidate, IdeaPlan, IdeaFeedback, IdeaExemplar,
  IdeaPromptVersion, IdeaBenchmark,
  IdeaAtomsResponse, IdeaAtomResponse, IdeaQuestionsResponse,
  IdeaCandidatesResponse, IdeaCandidateResponse, IdeaPlanResponse,
  IdeaFeedbackResponse, IdeaExemplarsResponse, IdeaPromptVersionsResponse,
  IdeaBenchmarksResponse, IdeaStatsResponse, IdeaLibraryTreeResponse, IdeaDigestResponse,
} from '../types/idea'

export async function fetchIdeaAtoms(params?: { atom_type?: string; search?: string; limit?: number; offset?: number }): Promise<IdeaAtomsResponse> {
  const { data } = await http.get<IdeaAtomsResponse>('/idea/atoms', { params })
  return data
}

export async function fetchIdeaAtom(atomId: number): Promise<IdeaAtomResponse> {
  const { data } = await http.get<IdeaAtomResponse>(`/idea/atoms/${atomId}`)
  return data
}

export async function updateIdeaAtom(atomId: number, payload: Partial<IdeaAtom>): Promise<IdeaAtomResponse> {
  const { data } = await http.patch<IdeaAtomResponse>(`/idea/atoms/${atomId}`, payload)
  return data
}

export async function deleteIdeaAtom(atomId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/atoms/${atomId}`)
  return data
}

export async function extractIdeaAtoms(paperId: string, dateStr?: string): Promise<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }> {
  const { data } = await http.post<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }>('/idea/atoms/extract', { paper_id: paperId, date_str: dateStr })
  return data
}

export async function fetchIdeaCandidates(params?: { status?: string; search?: string; folder_id?: number | null; limit?: number; offset?: number }): Promise<IdeaCandidatesResponse> {
  const { data } = await http.get<IdeaCandidatesResponse>('/idea/candidates', { params })
  return data
}

export async function fetchIdeaCandidate(candidateId: number): Promise<IdeaCandidateResponse> {
  const { data } = await http.get<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`)
  return data
}

export async function updateIdeaCandidate(candidateId: number, payload: Partial<IdeaCandidate>): Promise<IdeaCandidateResponse> {
  const { data } = await http.patch<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`, payload)
  return data
}

export async function deleteIdeaCandidate(candidateId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/candidates/${candidateId}`)
  return data
}

export async function generateCandidatesForPaper(paperId: string, force = false): Promise<{ ok: boolean; candidates: IdeaCandidate[]; count: number }> {
  const { data } = await http.post<{ ok: boolean; candidates: IdeaCandidate[]; count: number }>('/idea/candidates/generate-for-paper', { paper_id: paperId, force })
  return data
}

export async function generateIdeasStream(payload: {
  question_id?: number
  custom_question?: string
  strategies?: string[]
  reward_id?: number
}): Promise<Response> {
  return fetch('/api/idea/candidates/generate', {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify(payload),
  })
}

export async function reviewIdeaCandidate(
  candidateId: number,
  payload: { action: 'approve' | 'reject' | 'revise'; feedback?: string; scores?: Record<string, number> },
): Promise<IdeaCandidateResponse> {
  const { data } = await http.post<IdeaCandidateResponse>(`/idea/candidates/${candidateId}/review`, payload)
  return data
}

export async function fetchIdeaPlan(candidateId: number): Promise<IdeaPlanResponse> {
  const { data } = await http.get<IdeaPlanResponse>(`/idea/plans/${candidateId}`)
  return data
}

export async function createIdeaPlan(candidateId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.post<IdeaPlanResponse>(`/idea/plans`, { candidate_id: candidateId, ...payload })
  return data
}

export async function fetchGeneratePlanStream(candidateId: number, rewardId?: number): Promise<Response> {
  const body: Record<string, unknown> = { candidate_id: candidateId }
  if (rewardId !== undefined) body.reward_id = rewardId
  return fetch('/api/idea/plans/generate', {
    method: 'POST',
    headers: getAuthHeaders(),
    credentials: 'include',
    body: JSON.stringify(body),
  })
}

export async function updateIdeaPlan(planId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.patch<IdeaPlanResponse>(`/idea/plans/${planId}`, payload)
  return data
}

export async function deleteIdeaPlan(planId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/plans/${planId}`)
  return data
}

export async function createIdeaFeedback(payload: { candidate_id: number; action: string; context?: Record<string, any> }): Promise<IdeaFeedbackResponse> {
  const { data } = await http.post<IdeaFeedbackResponse>('/idea/feedback', payload)
  return data
}

export async function fetchIdeaFeedback(params?: { candidate_id?: number; action?: string; limit?: number }): Promise<IdeaFeedbackResponse> {
  const { data } = await http.get<IdeaFeedbackResponse>('/idea/feedback', { params })
  return data
}

export async function fetchIdeaExemplars(params?: { limit?: number; offset?: number }): Promise<IdeaExemplarsResponse> {
  const { data } = await http.get<IdeaExemplarsResponse>('/idea/exemplars', { params })
  return data
}

export async function fetchIdeaExemplar(exemplarId: number): Promise<{ ok: boolean; exemplar: IdeaExemplar }> {
  const { data } = await http.get<{ ok: boolean; exemplar: IdeaExemplar }>(`/idea/exemplars/${exemplarId}`)
  return data
}

export async function createIdeaExemplar(payload: { candidate_id?: number; pattern?: any; score?: number; notes?: string }): Promise<{ ok: boolean; exemplar: IdeaExemplar }> {
  const { data } = await http.post<{ ok: boolean; exemplar: IdeaExemplar }>('/idea/exemplars', payload)
  return data
}

export async function updateIdeaExemplar(exemplarId: number, payload: Partial<IdeaExemplar>): Promise<{ ok: boolean; exemplar: IdeaExemplar }> {
  const { data } = await http.patch<{ ok: boolean; exemplar: IdeaExemplar }>(`/idea/exemplars/${exemplarId}`, payload)
  return data
}

export async function deleteIdeaExemplar(exemplarId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/exemplars/${exemplarId}`)
  return data
}

export async function fetchIdeaBenchmarks(params?: { limit?: number }): Promise<IdeaBenchmarksResponse> {
  const { data } = await http.get<IdeaBenchmarksResponse>('/idea/benchmarks', { params })
  return data
}

export async function fetchIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean; benchmark: IdeaBenchmark }> {
  const { data } = await http.get<{ ok: boolean; benchmark: IdeaBenchmark }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

export async function createIdeaBenchmark(payload: { name: string; question_ids?: number[] }): Promise<{ ok: boolean; benchmark: IdeaBenchmark }> {
  const { data } = await http.post<{ ok: boolean; benchmark: IdeaBenchmark }>('/idea/benchmarks', payload)
  return data
}

export async function updateIdeaBenchmark(benchmarkId: number, payload: Partial<IdeaBenchmark>): Promise<{ ok: boolean; benchmark: IdeaBenchmark }> {
  const { data } = await http.patch<{ ok: boolean; benchmark: IdeaBenchmark }>(`/idea/benchmarks/${benchmarkId}`, payload)
  return data
}

export async function deleteIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

export async function fetchIdeaPromptVersions(params?: { stage?: string; limit?: number }): Promise<IdeaPromptVersionsResponse> {
  const { data } = await http.get<IdeaPromptVersionsResponse>('/idea/prompt-versions', { params })
  return data
}

export async function fetchIdeaPromptVersion(versionId: number): Promise<{ ok: boolean; version: IdeaPromptVersion }> {
  const { data } = await http.get<{ ok: boolean; version: IdeaPromptVersion }>(`/idea/prompt-versions/${versionId}`)
  return data
}

export async function createIdeaPromptVersion(payload: { stage: string; prompt_text: string; metrics?: any }): Promise<{ ok: boolean; version: IdeaPromptVersion }> {
  const { data } = await http.post<{ ok: boolean; version: IdeaPromptVersion }>('/idea/prompt-versions', payload)
  return data
}

export async function updateIdeaPromptVersion(versionId: number, payload: Partial<IdeaPromptVersion>): Promise<{ ok: boolean; version: IdeaPromptVersion }> {
  const { data } = await http.patch<{ ok: boolean; version: IdeaPromptVersion }>(`/idea/prompt-versions/${versionId}`, payload)
  return data
}

export async function deleteIdeaPromptVersion(versionId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/prompt-versions/${versionId}`)
  return data
}

export async function fetchIdeaStats(): Promise<IdeaStatsResponse> {
  const { data } = await http.get<IdeaStatsResponse>('/idea/stats')
  return data
}

export async function fetchIdeaDigest(date: string): Promise<IdeaDigestResponse> {
  const { data } = await http.get<IdeaDigestResponse>(`/idea/digest/${date}`)
  return data
}
