import { http } from './http'
import type {
  DatesResponse, PapersResponse, PaperDetailResponse,
  DigestResponse, PipelineStatusResponse,
} from '../types/paper'

export async function fetchDates(): Promise<DatesResponse> {
  const { data } = await http.get<DatesResponse>('/dates')
  return data
}

export async function fetchPapers(
  date: string,
  search?: string,
  institution?: string,
): Promise<PapersResponse> {
  const { data } = await http.get<PapersResponse>('/papers', {
    params: { date, search: search || undefined, institution: institution || undefined },
  })
  return data
}

const paperDetailRequests = new Map<string, Promise<PaperDetailResponse>>()

export function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const existing = paperDetailRequests.get(paperId)
  if (existing) return existing

  const request = http
    .get<PaperDetailResponse>(`/papers/${paperId}`)
    .then(({ data }) => data)
  paperDetailRequests.set(paperId, request)
  request.then(
    () => {
      if (paperDetailRequests.get(paperId) === request) paperDetailRequests.delete(paperId)
    },
    () => {
      if (paperDetailRequests.get(paperId) === request) paperDetailRequests.delete(paperId)
    },
  )
  return request
}

export async function fetchDigest(date: string): Promise<DigestResponse> {
  const { data } = await http.get<DigestResponse>(`/digest/${date}`)
  return data
}

export async function fetchPipelineStatus(date: string): Promise<PipelineStatusResponse> {
  const { data } = await http.get<PipelineStatusResponse>('/pipeline/status', { params: { date } })
  return data
}
