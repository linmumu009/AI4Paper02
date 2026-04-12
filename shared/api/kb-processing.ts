import { http } from './http'
import type { KbPaperProcessStatusResponse, KbPaperTranslateStatusResponse, KbPaperFilesResponse } from '../types/kb'
import type { KbScope } from './kb'

export function kbPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '等待处理...',
    starting: '初始化...',
    pdf_attach: '查找/复制 PDF...',
    pdf_mineru: 'MinerU 版面解析中...',
    pdf_extract: '提取文本（PyMuPDF）...',
    done: '处理完成',
    '': '',
  }
  return labels[step] ?? step
}

export async function processKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/kb/papers/${paperId}/process`, null, { params: { scope } })
  return data
}

export async function fetchKbPaperProcessStatus(paperId: string, scope: KbScope = 'kb'): Promise<KbPaperProcessStatusResponse> {
  const { data } = await http.get<KbPaperProcessStatusResponse>(`/kb/papers/${paperId}/process-status`, { params: { scope } })
  return data
}

export async function translateKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/kb/papers/${paperId}/translate`, null, { params: { scope } })
  return data
}

export async function retranslateKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/kb/papers/${paperId}/retranslate`, null, { params: { scope } })
  return data
}

export async function fetchKbPaperTranslateStatus(paperId: string, scope: KbScope = 'kb'): Promise<KbPaperTranslateStatusResponse> {
  const { data } = await http.get<KbPaperTranslateStatusResponse>(`/kb/papers/${paperId}/translate-status`, { params: { scope } })
  return data
}

export async function fetchKbPaperFiles(paperId: string, scope: KbScope = 'kb'): Promise<KbPaperFilesResponse> {
  const { data } = await http.get<KbPaperFilesResponse>(`/kb/papers/${paperId}/files`, { params: { scope } })
  return data
}

export async function deleteKbPaperDerivative(paperId: string, derivativeType: 'mineru' | 'zh' | 'bilingual', scope: KbScope = 'kb'): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/kb/papers/${paperId}/derivatives/${derivativeType}`, { params: { scope } })
  return data
}
