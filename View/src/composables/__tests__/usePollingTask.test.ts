import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPollingTask } from '../usePollingTask'

describe('createPollingTask', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('runs on schedule and stops when the callback returns false', async () => {
    vi.useFakeTimers()
    const callback = vi.fn()
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(false)
    const task = createPollingTask(callback, { intervalMs: 1000 })

    task.start()
    await vi.advanceTimersByTimeAsync(1000)
    expect(callback).toHaveBeenCalledTimes(1)
    expect(task.active.value).toBe(true)

    await vi.advanceTimersByTimeAsync(1000)
    expect(callback).toHaveBeenCalledTimes(2)
    expect(task.active.value).toBe(false)
  })

  it('does not overlap slow polling requests', async () => {
    vi.useFakeTimers()
    let resolveRequest: (() => void) | undefined
    const callback = vi.fn(() => new Promise<void>((resolve) => { resolveRequest = resolve }))
    const task = createPollingTask(callback, { intervalMs: 1000 })

    task.start(true)
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(5000)
    expect(callback).toHaveBeenCalledTimes(1)

    resolveRequest?.()
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(1000)
    expect(callback).toHaveBeenCalledTimes(2)
    task.stop()
  })

  it('cancels pending work when stopped', async () => {
    vi.useFakeTimers()
    const callback = vi.fn()
    const task = createPollingTask(callback, { intervalMs: 1000 })
    task.start()
    task.stop()

    await vi.advanceTimersByTimeAsync(2000)
    expect(callback).not.toHaveBeenCalled()
  })
})
