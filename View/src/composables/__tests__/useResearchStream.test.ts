import { describe, expect, it, vi } from 'vitest'
import { useResearchStream } from '../useResearchStream'

describe('useResearchStream', () => {
  it('surfaces non-2xx response details', async () => {
    const response = new Response(JSON.stringify({ detail: '本月额度已用完' }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' },
    })
    const { consumeStream } = useResearchStream()

    await expect(consumeStream(response, async () => {}, () => false))
      .rejects.toThrow('请求失败 (429): 本月额度已用完')
  })

  it('parses valid SSE events', async () => {
    const response = new Response(
      'data: {"type":"progress","round":1,"message":"分析中"}\n\n',
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
    )
    const onEvent = vi.fn(async () => {})
    const { consumeStream } = useResearchStream()

    await consumeStream(response, onEvent, () => false)

    expect(onEvent).toHaveBeenCalledOnce()
    expect(onEvent).toHaveBeenCalledWith({
      type: 'progress',
      round: 1,
      message: '分析中',
    })
  })
})
