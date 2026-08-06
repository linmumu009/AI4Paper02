import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@shared/api/client', () => ({
  configureTransport: vi.fn(),
  apiClient: {},
  http: { get },
}))

vi.mock('@shared/api/transport/tauri', () => ({
  TauriTransport: vi.fn(),
}))

import { fetchPaperDetail } from './index'

describe('fetchPaperDetail', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('shares one network call between concurrent consumers, then releases it', async () => {
    let resolveRequest!: (value: { data: any }) => void
    get.mockReturnValueOnce(new Promise(resolve => {
      resolveRequest = resolve
    }))

    const first = fetchPaperDetail('2608.00001')
    const second = fetchPaperDetail('2608.00001')

    expect(second).toBe(first)
    expect(get).toHaveBeenCalledOnce()

    resolveRequest({ data: { summary: { paper_id: '2608.00001' } } })
    await Promise.all([first, second])

    get.mockResolvedValueOnce({ data: { summary: { paper_id: '2608.00001' } } })
    await fetchPaperDetail('2608.00001')
    expect(get).toHaveBeenCalledTimes(2)
  })
})
