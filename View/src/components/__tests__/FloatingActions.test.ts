import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  route: {
    name: 'paper-detail' as string,
    query: {} as Record<string, string>,
  },
  router: {
    back: vi.fn(),
    push: vi.fn(),
  },
  isOpen: { value: false },
  isPageInPanelView: { value: false },
  requestDigestReset: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))

vi.mock('../../composables/useGlobalChat', () => ({
  useGlobalChat: () => ({
    isOpen: mocks.isOpen,
    chatDrawerWidthPx: { value: 480 },
    open: vi.fn(),
    close: vi.fn(),
    isPageInPanelView: mocks.isPageInPanelView,
    requestDigestReset: mocks.requestDigestReset,
  }),
}))

vi.mock('../../stores/auth', () => ({
  isAuthenticated: false,
}))

import FloatingActions from '../FloatingActions.vue'

describe('FloatingActions recommendation return', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.route.name = 'paper-detail'
    mocks.route.query = {}
    mocks.isOpen.value = false
    mocks.isPageInPanelView.value = false
  })

  it('restores the exact recommendation card when detail was opened from the digest', async () => {
    mocks.route.query = { from: 'digest' }

    const wrapper = mount(FloatingActions)
    await wrapper.get('button').trigger('click')

    expect(mocks.router.back).toHaveBeenCalledOnce()
    expect(mocks.router.push).not.toHaveBeenCalled()
  })

  it('opens the digest normally when a detail page has no digest history', async () => {
    const wrapper = mount(FloatingActions)
    await wrapper.get('button').trigger('click')

    expect(mocks.router.push).toHaveBeenCalledWith({ name: 'digest' })
    expect(mocks.router.back).not.toHaveBeenCalled()
  })

  it('asks the digest page to close its current panel instead of navigating', async () => {
    mocks.route.name = 'digest'
    mocks.isPageInPanelView.value = true

    const wrapper = mount(FloatingActions)
    await wrapper.get('button').trigger('click')

    expect(mocks.requestDigestReset).toHaveBeenCalledOnce()
    expect(mocks.router.back).not.toHaveBeenCalled()
    expect(mocks.router.push).not.toHaveBeenCalled()
  })
})
