import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api', () => ({
  fetchPdfCleanupStatus: vi.fn(),
  runPdfCleanup: vi.fn(),
  savePdfCleanupConfig: vi.fn(),
}))

import {
  fetchPdfCleanupStatus,
  runPdfCleanup,
  savePdfCleanupConfig,
} from '../../../api'
import AdminPdfCleanupPanel from '../AdminPdfCleanupPanel.vue'

const statusResponse = {
  ok: true,
  auto_enabled: false,
  retention_days: 14,
  auto_hour: 3,
  auto_minute: 0,
  scheduler_alive: true,
  last_run_at: null,
  last_result: null,
}

describe('AdminPdfCleanupPanel', () => {
  beforeEach(() => {
    vi.mocked(fetchPdfCleanupStatus).mockResolvedValue(statusResponse)
    vi.mocked(savePdfCleanupConfig).mockResolvedValue({ ok: true, message: 'saved' })
  })

  it('loads scheduler status when mounted', async () => {
    const wrapper = mount(AdminPdfCleanupPanel)
    await flushPromises()

    expect(fetchPdfCleanupStatus).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('调度线程状态')
    expect(wrapper.text()).toContain('运行中')
  })

  it('runs a dry-run preview and renders normalized results', async () => {
    vi.mocked(runPdfCleanup).mockResolvedValue({
      ok: true,
      dry_run: true,
      retention_days: 14,
      scanned: 5,
      deletable: 2,
      deleted: 0,
      skipped_saved: 1,
      skipped_recent: 2,
      freed_bytes: 4096,
      freed_mb: 0,
      errors: [],
      started_at: '2026-07-11T00:00:00Z',
      finished_at: '2026-07-11T00:00:01Z',
    })
    const wrapper = mount(AdminPdfCleanupPanel)
    await flushPromises()

    const previewButton = wrapper.findAll('button')
      .find(button => button.text().includes('预览清理'))
    expect(previewButton).toBeDefined()
    await previewButton!.trigger('click')
    await flushPromises()

    expect(runPdfCleanup).toHaveBeenCalledWith(true, undefined)
    expect(wrapper.text()).toContain('预览完成')
    expect(wrapper.text()).toContain('4.0 KB')
  })
})
