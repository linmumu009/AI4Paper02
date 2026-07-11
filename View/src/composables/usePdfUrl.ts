/**
 * usePdfUrl – central PDF URL resolver.
 *
 * Replaces the half-dozen duplicated `buildPdfViewerSrc` / `buildPdfUrl` helper
 * functions scattered across PaperDetail, PaperList, DailyDigest, etc.
 *
 * buildPdfViewerUrl(pdfUrl, paperId?)
 *   → Full iframe src pointing at the local PDF.js viewer with `?file=…&paperId=…`
 *
 * resolvePaperPdfUrl(paperId)
 *   → The raw PDF file URL for an arXiv paper (served via our backend proxy)
 *
 * warmPdfConnection(pdfUrl)
 *   → Fire-and-forget: fetch the first 128 KB of the PDF so the TCP connection
 *     is established and the server/CDN cache is warm before the user clicks PDF.
 */
import { API_ORIGIN } from '../api'

/**
 * Build the viewer iframe src for a given raw PDF URL.
 * Works for:
 *   - `/api/papers/{id}/pdf`  (backend-served local PDF)
 *   - `https://arxiv.org/pdf/...`  (remote arXiv PDF)
 *   - `https://…/static/kb_files/…`  (KB attachment)
 *   - `blob:…`  (Tauri IPC blob)
 */
export function buildPdfViewerUrl(pdfUrl: string, paperId?: string): string {
  const base = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  const file  = encodeURIComponent(pdfUrl)
  const pid   = paperId ? `&paperId=${encodeURIComponent(paperId)}` : ''
  return `${base}?file=${file}${pid}`
}

/**
 * Resolve the raw PDF file URL for an arXiv paper.
 * Returns the backend-proxied endpoint that supports Range streaming.
 */
export function resolvePaperPdfUrl(paperId: string): string {
  return `${API_ORIGIN}/api/papers/${paperId}/pdf`
}

/**
 * Build viewer src for a KB file (static attachment).
 */
export function buildKbPdfViewerUrl(filePath: string, paperId?: string): string {
  const fileUrl = buildKbFileUrl(filePath)
  return buildPdfViewerUrl(fileUrl, paperId)
}

/**
 * Resolve the raw URL for a KB static file (without viewer wrapper).
 */
export function buildKbFileUrl(filePath: string): string {
  const relPath = filePath.replace(/^\/static\/kb_files\//, '')
  return `${API_ORIGIN}/static/kb_files/${relPath}`
}

/**
 * Pre-warm the PDF connection so the server cache and TCP connection are ready
 * before the user actually opens the PDF panel.
 *
 * Issues a single Range request for the first 128 KB (the header / cross-
 * reference table area that PDF.js needs first).  The response goes into the
 * browser's HTTP cache; when PDF.js later requests the same byte range it gets
 * it instantly without a network round-trip.
 *
 * Call this after the paper detail loads, ideally inside requestIdleCallback.
 * Safe to call multiple times — deduplication is handled by the browser cache.
 */
export function warmPdfConnection(pdfUrl: string): void {
  if (!pdfUrl || pdfUrl.startsWith('blob:')) return
  try {
    fetch(pdfUrl, {
      method: 'GET',
      headers: { Range: 'bytes=0-131071' },
      credentials: 'include',
      // 'default' lets the browser cache the partial response; a repeated
      // fetch of the same range will be served from cache.
      cache: 'default',
    }).catch(() => { /* Ignore network errors — this is best-effort */ })
  } catch {
    // Ignore sync errors (e.g. unsupported environment)
  }
}
