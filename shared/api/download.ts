import { http } from './http'

export type PaperFileType = 'pdf' | 'mineru' | 'zh' | 'bilingual'
export type DownloadFormat = 'md' | 'docx' | 'pdf'
/** 与 kb.ts 的 KbScope 区分，避免 barrel export 重名；仅用于下载接口 scope 参数 */
export type PaperDownloadScope = 'kb' | 'mypapers'

function triggerDownload(url: string, filename?: string): void {
  const a = document.createElement('a')
  a.href = url
  if (filename) a.download = filename
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/**
 * Download a paper-derived file (pdf / mineru / zh / bilingual).
 * Mobile browser version: opens download URL via anchor tag.
 */
export function downloadPaperFile(
  paperId: string,
  fileType: PaperFileType,
  scope: PaperDownloadScope = 'kb',
  format: DownloadFormat = 'md',
): void {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  const params = new URLSearchParams({
    paper_id: paperId,
    file_type: fileType,
    scope,
    format,
  })
  // Bilingual PDF supports extra theme params from localStorage.
  // useBilingualTheme stores all theme fields as a single JSON object under
  // 'ai4papers-bilingual-theme'. Read from that key so the download reflects
  // the user's current bilingual theme settings.
  if (fileType === 'bilingual' && format === 'pdf') {
    try {
      const raw = localStorage.getItem('ai4papers-bilingual-theme')
      if (raw) {
        const theme = JSON.parse(raw) as {
          hue?: number; saturation?: number; intensity?: number; fontSize?: number
        }
        if (theme.hue != null) params.set('hue', String(theme.hue))
        if (theme.saturation != null) params.set('sat', String(theme.saturation))
        if (theme.intensity != null) params.set('intensity', String(theme.intensity))
        if (theme.fontSize != null) params.set('font_size', String(theme.fontSize))
      }
    } catch {
      // ignore storage parse errors
    }
  }
  triggerDownload(`${base}/download/paper-file?${params.toString()}`)
}

/**
 * Download a note as markdown.
 */
export function downloadNote(noteId: number): void {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  triggerDownload(`${base}/download/note/${noteId}`)
}

/**
 * Download a deep research result.
 */
export function downloadResearchResult(
  sessionId: number,
  format: DownloadFormat = 'md',
): void {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  const params = new URLSearchParams({ format })
  triggerDownload(`${base}/research/${sessionId}/download?${params.toString()}`)
}
