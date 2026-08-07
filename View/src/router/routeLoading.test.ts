import { describe, expect, it } from 'vitest'

import { shouldShowRouteLoading } from './routeLoading'

describe('shouldShowRouteLoading', () => {
  it('does not cover the page when only digest query state changes', () => {
    expect(shouldShowRouteLoading(
      { name: 'digest', path: '/' },
      { name: 'digest', path: '/' },
    )).toBe(false)
  })

  it('shows loading when navigating to a different page', () => {
    expect(shouldShowRouteLoading(
      { name: 'paper-detail', path: '/papers/2608.02438' },
      { name: 'digest', path: '/' },
    )).toBe(true)
  })

  it('shows loading when route params change the path', () => {
    expect(shouldShowRouteLoading(
      { name: 'paper-detail', path: '/papers/2608.02442' },
      { name: 'paper-detail', path: '/papers/2608.02438' },
    )).toBe(true)
  })

  it('shows loading during the initial navigation', () => {
    expect(shouldShowRouteLoading(
      { name: 'digest', path: '/' },
      { name: undefined, path: '/' },
    )).toBe(true)
  })
})
