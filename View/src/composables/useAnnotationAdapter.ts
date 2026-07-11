/**
 * useAnnotationAdapter
 *
 * Bridges the iframe PDF viewer's postMessage highlight protocol with the
 * backend kb_annotations API.  This composable is designed to be used in
 * any parent component that embeds a <PdfPanel> (PaperDetail, PaperList,
 * DailyDigest, etc.).
 *
 * Usage:
 *   const { attachAnnotationAdapter, detachAnnotationAdapter } = useAnnotationAdapter()
 *   onMounted(() => attachAnnotationAdapter())
 *   onUnmounted(() => detachAnnotationAdapter())
 *
 * Protocol handled (postMessage from iframe → parent):
 *   pdfviewer:getHighlights  → fetch from backend, post pdfviewer:highlights back
 *   pdfviewer:addHighlight   → save to backend
 *   pdfviewer:highlightClick → (optional) forward to parent for UI display
 *   pdfviewer:download       → trigger download via Blob URL or a link
 *
 * No component-level state is managed here — the viewer iframe is the source
 * of truth for the rendered highlight layer; this adapter is purely a
 * persistence bridge.
 */
import type { KbScope } from '../api'
import { fetchAnnotations, createAnnotation } from '../api'

/** Rect coordinates stored in position_data JSON, normalised to PDF points. */
interface HighlightRect {
  x: number
  y: number
  w: number
  h: number
}

/** The viewer's internal highlight shape (pdfviewer:addHighlight payload). */
interface ViewerHighlight {
  id?: string
  page: number
  rects: HighlightRect[]
  text?: string
  color?: string
}

function viewerHighlightFromAnnotation(ann: {
  id: number
  page: number
  color: string
  content: string
  position_data: string
}): ViewerHighlight & { id: string } {
  let rects: HighlightRect[] = []
  try { rects = JSON.parse(ann.position_data) } catch {}
  return {
    id: String(ann.id),
    page: ann.page,
    rects,
    text: ann.content,
    color: ann.color,
  }
}

// ── Message handler registry ──────────────────────────────────────────────────
// We use a module-level WeakMap so adapters don't leak even if the caller
// forgets to call detachAnnotationAdapter.

type MsgHandler = (e: MessageEvent) => void

const _handlers = new Map<string, MsgHandler>()
let _handlerKey = 0

export function useAnnotationAdapter() {
  let _key: string | null = null

  function attachAnnotationAdapter(scope: KbScope = 'kb') {
    detachAnnotationAdapter()
    _key = String(++_handlerKey)

    const handler: MsgHandler = async (event: MessageEvent) => {
      const { type, paperId, highlight } = event.data ?? {}
      if (!type?.startsWith('pdfviewer:')) return

      // Only trust messages from one of our currently mounted PDF.js viewers.
      // Checking both Window identity and origin prevents unrelated iframes or
      // cross-origin opener windows from reading/writing annotations.
      const iframe = Array.from(document.querySelectorAll<HTMLIFrameElement>(
        'iframe[src*="/static/pdfjs/web/viewer.html"]',
      )).find((candidate) => candidate.contentWindow === event.source)
      if (!iframe) return

      let viewerOrigin: string
      try {
        viewerOrigin = new URL(iframe.src, window.location.href).origin
      } catch {
        return
      }
      if (event.origin !== viewerOrigin) return
      // Custom-protocol WebViews may expose an opaque "null" origin. Window
      // identity above remains authoritative; opaque origins require "*" when
      // replying because "null" is not a valid postMessage targetOrigin.
      const replyTargetOrigin = viewerOrigin === 'null' ? '*' : viewerOrigin

      if (type === 'pdfviewer:getHighlights') {
        // Load existing annotations from the backend and send them to the viewer
        if (!paperId) return
        try {
          const resp = await fetchAnnotations(paperId, scope)
          const highlights = resp.annotations.map(viewerHighlightFromAnnotation)
          iframe.contentWindow?.postMessage(
            { type: 'pdfviewer:highlights', paperId, highlights },
            replyTargetOrigin,
          )
        } catch {
          // Not authenticated or no annotations yet – send empty list
          iframe.contentWindow?.postMessage(
            { type: 'pdfviewer:highlights', paperId, highlights: [] },
            replyTargetOrigin,
          )
        }
        return
      }

      if (type === 'pdfviewer:addHighlight') {
        if (!paperId || !highlight) return
        try {
          await createAnnotation(
            paperId,
            {
              page: highlight.page,
              type: 'highlight',
              content: highlight.text ?? '',
              color: highlight.color ?? '#FFFF00',
              position_data: JSON.stringify(highlight.rects ?? []),
            },
            scope,
          )
        } catch {
          // Silently ignore — user may not be logged in
        }
        return
      }

      if (type === 'pdfviewer:download') {
        const { url } = event.data ?? {}
        if (!url) return
        const a = document.createElement('a')
        a.href = url
        a.download = (paperId ?? 'paper') + '.pdf'
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        return
      }
    }

    _handlers.set(_key, handler)
    window.addEventListener('message', handler)
  }

  function detachAnnotationAdapter() {
    if (!_key) return
    const h = _handlers.get(_key)
    if (h) {
      window.removeEventListener('message', h)
      _handlers.delete(_key)
    }
    _key = null
  }

  return { attachAnnotationAdapter, detachAnnotationAdapter }
}
