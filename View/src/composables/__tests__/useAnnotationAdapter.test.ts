import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  fetchAnnotations: vi.fn(),
  createAnnotation: vi.fn(),
}))

import { createAnnotation, fetchAnnotations } from '../../api'
import { useAnnotationAdapter } from '../useAnnotationAdapter'

function dispatchViewerMessage(source: MessageEventSource | null, data: unknown) {
  window.dispatchEvent(new MessageEvent('message', {
    data,
    origin: window.location.origin,
    source,
  }))
}

describe('useAnnotationAdapter', () => {
  beforeEach(() => {
    vi.mocked(fetchAnnotations).mockResolvedValue({ paper_id: 'paper-1', annotations: [] })
  })

  it('ignores messages not sent by the mounted PDF viewer', async () => {
    const iframe = document.createElement('iframe')
    iframe.src = '/static/pdfjs/web/viewer.html'
    document.body.appendChild(iframe)
    const adapter = useAnnotationAdapter()
    adapter.attachAnnotationAdapter()

    dispatchViewerMessage(window, {
      type: 'pdfviewer:addHighlight',
      paperId: 'paper-1',
      highlight: { page: 1, rects: [] },
    })
    await Promise.resolve()

    expect(createAnnotation).not.toHaveBeenCalled()
    adapter.detachAnnotationAdapter()
  })

  it('accepts messages from the mounted same-origin PDF viewer', async () => {
    const iframe = document.createElement('iframe')
    iframe.src = '/static/pdfjs/web/viewer.html'
    document.body.appendChild(iframe)
    const adapter = useAnnotationAdapter()
    adapter.attachAnnotationAdapter()

    dispatchViewerMessage(iframe.contentWindow, {
      type: 'pdfviewer:addHighlight',
      paperId: 'paper-1',
      highlight: {
        page: 2,
        text: 'important',
        color: '#ffff00',
        rects: [{ x: 1, y: 2, w: 3, h: 4 }],
      },
    })

    await vi.waitFor(() => {
      expect(createAnnotation).toHaveBeenCalledWith(
        'paper-1',
        {
          page: 2,
          type: 'highlight',
          content: 'important',
          color: '#ffff00',
          position_data: JSON.stringify([{ x: 1, y: 2, w: 3, h: 4 }]),
        },
        'kb',
      )
    })
    adapter.detachAnnotationAdapter()
  })
})
