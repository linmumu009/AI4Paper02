import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearSummaryDensityPreference,
  SUMMARY_DENSITY_STORAGE_KEY,
  useSummaryDensity,
} from '../useSummaryDensity'

describe('useSummaryDensity', () => {
  beforeEach(() => {
    clearSummaryDensityPreference()
  })

  it('uses a surface default until the user explicitly chooses a version', () => {
    const card = useSummaryDensity('concise')
    const detail = useSummaryDensity('detailed')

    expect(card.density.value).toBe('concise')
    expect(detail.density.value).toBe('detailed')
    expect(card.hasExplicitPreference.value).toBe(false)
  })

  it('shares and persists an explicit choice across surfaces', () => {
    const card = useSummaryDensity('concise')
    const detail = useSummaryDensity('detailed')

    card.setDensity('detailed')

    expect(detail.density.value).toBe('detailed')
    expect(detail.hasExplicitPreference.value).toBe(true)
    expect(window.localStorage.getItem(SUMMARY_DENSITY_STORAGE_KEY)).toBe('detailed')

    detail.setDensity('concise')
    expect(card.density.value).toBe('concise')
    expect(window.localStorage.getItem(SUMMARY_DENSITY_STORAGE_KEY)).toBe('concise')
  })
})
