import { describe, expect, it } from 'vitest'

import {
  formatChinaTimestamp,
  formatScheduleClock,
  formatScheduleDuration,
  getPipelineRuntimeStatus,
  getScheduleStatus,
} from './scheduleStatus'

describe('schedule status presentation', () => {
  it('does not present an empty legacy run as a green success', () => {
    expect(getScheduleStatus({ success: true, exit_code: 0, user_count: 0 })).toEqual({
      label: '无新论文',
      tone: 'neutral',
    })
  })

  it('shows source-empty retries as recoverable work', () => {
    expect(getScheduleStatus({
      success: false,
      exit_code: 4,
      user_count: 0,
      arxiv_count: 0,
      outcome: 'source_empty_retry',
    })).toEqual({ label: '等待重试', tone: 'warning' })
    expect(getPipelineRuntimeStatus({ running: false, exit_code: 4 })).toEqual({
      label: '等待自动重试',
      tone: 'warning',
    })
  })

  it('converts UTC history timestamps to China time', () => {
    expect(formatChinaTimestamp('2026-08-17T22:00:17+00:00')).toBe('2026-08-18 06:00:17')
  })

  it('keeps very short runs visible and formats effective clock values', () => {
    expect(formatScheduleDuration(
      '2026-08-17T22:00:17+00:00',
      '2026-08-17T22:00:20+00:00',
    )).toBe('3 秒')
    expect(formatScheduleClock(9, 15)).toBe('09:15')
  })
})
