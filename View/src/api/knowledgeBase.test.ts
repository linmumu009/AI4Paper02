import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@shared/api/client', () => ({
  apiClient: { stream: vi.fn() },
  http: {
    get,
    post,
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { addKbPaper, fetchKbTree, fetchPaperResourceStatus } from './knowledgeBase'

describe('knowledge-base scope boundary', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('maps the inspiration UI scope to the persisted idea_library scope', async () => {
    get.mockResolvedValueOnce({ data: { folders: [], papers: [] } })

    await fetchKbTree('inspiration')

    expect(get).toHaveBeenCalledWith('/kb/tree', {
      params: { scope: 'idea_library' },
    })
  })

  it('uses idea_library when saving an inspiration candidate', async () => {
    post.mockResolvedValueOnce({ data: { paper_id: 'idea_12' } })

    await addKbPaper(
      'idea_12',
      { paper_id: 'idea_12', title: '新灵感' } as any,
      null,
      'inspiration',
    )

    expect(post).toHaveBeenCalledWith('/kb/papers', expect.objectContaining({
      paper_id: 'idea_12',
      scope: 'idea_library',
    }))
  })

  it('requests resource status with the backend scope name', async () => {
    get.mockResolvedValueOnce({ data: { paper_id: 'idea_12' } })

    await fetchPaperResourceStatus('idea_12', 'inspiration')

    expect(get).toHaveBeenCalledWith('/kb/papers/idea_12/resource-status', {
      params: { scope: 'idea_library' },
    })
  })
})
