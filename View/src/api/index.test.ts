import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@shared/api/client', () => ({
  configureTransport: vi.fn(),
  apiClient: {},
  http: { get, post },
}))

vi.mock('@shared/api/transport/tauri', () => ({
  TauriTransport: vi.fn(),
}))

import { fetchPaperDetail, suggestAutoClassifyFolders } from './index'

describe('fetchPaperDetail', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
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

describe('suggestAutoClassifyFolders', () => {
  it('requests a non-mutating AI folder preview with a bounded suggestion count', async () => {
    post.mockResolvedValueOnce({
      data: { ok: true, suggestions: [], analyzed_papers: 5, existing_folders: 2 },
    })

    await suggestAutoClassifyFolders('kb', 6)

    expect(post).toHaveBeenCalledWith('/kb/auto-classify/suggest-folders', {
      scope: 'kb',
      max_suggestions: 6,
    })
  })
})
