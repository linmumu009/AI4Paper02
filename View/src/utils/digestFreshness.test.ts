import { describe, expect, it } from 'vitest'

import { getDigestContextLabel, toLocalDateKey } from './digestFreshness'

describe('digest freshness labels', () => {
  it('calls a genuinely current digest today papers', () => {
    expect(getDigestContextLabel('2026-08-18', '2026-08-18', '2026-08-18')).toBe('今日论文')
  })

  it('calls an older latest digest the latest edition instead of today', () => {
    expect(getDigestContextLabel('2026-08-14', '2026-08-14', '2026-08-18')).toBe('最新一期')
  })

  it('keeps the newest published fallback labeled as the latest edition', () => {
    expect(getDigestContextLabel(
      '2026-08-14',
      '2026-08-18',
      '2026-08-18',
      true,
    )).toBe('最新一期')
  })

  it('distinguishes a selected historical digest', () => {
    expect(getDigestContextLabel('2026-08-13', '2026-08-14', '2026-08-18')).toBe('历史日报')
  })

  it('formats dates from local calendar fields without UTC drift', () => {
    expect(toLocalDateKey(new Date(2026, 7, 8, 23, 30))).toBe('2026-08-08')
  })
})
