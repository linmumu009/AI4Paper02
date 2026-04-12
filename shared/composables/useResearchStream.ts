import type { ResearchSseEvent } from '../types/research'

export function useResearchStream() {
  async function consumeStream(
    response: Response,
    onEvent: (evt: ResearchSseEvent) => Promise<void>,
    shouldAbort: () => boolean,
  ): Promise<void> {
    if (!response.body) throw new Error('No response body')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      if (shouldAbort()) break

      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          const evt = JSON.parse(raw) as ResearchSseEvent
          await onEvent(evt)
        } catch {
          // ignore malformed SSE events
        }
      }
    }
  }

  return { consumeStream }
}
