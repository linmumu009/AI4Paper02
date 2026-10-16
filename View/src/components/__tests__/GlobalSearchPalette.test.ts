import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, type Ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GlobalSearchPalette from '../GlobalSearchPalette.vue'
import { useGlobalSearch } from '../../composables/useGlobalSearch'
import { isAuthenticated } from '../../stores/auth'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), push: vi.fn() }))
vi.mock('../../api/globalSearch', () => ({ fetchGlobalSearch: mocks.fetch }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('../../composables/useGlobalChat', () => ({ useGlobalChat: () => ({ open: vi.fn() }) }))
vi.mock('../../utils/recentPapers', () => ({ getRecentPapers: () => [] }))
vi.mock('../../composables/useGlobalSearch', async () => {
  const { ref } = await import('vue')
  const isOpen = ref(false)
  return { useGlobalSearch: () => ({ isOpen, open: () => { isOpen.value = true }, close: () => { isOpen.value = false } }) }
})
vi.mock('../../stores/auth', async () => {
  const { ref } = await import('vue')
  return { isAuthenticated: ref(false) }
})

const paper = {
  type: 'paper', id: '2610.18861', title: 'Hybrid Reasoning Agents',
  subtitle: 'arXiv:2610.18861 · First Author', route: '/papers/2610.18861',
  score: 180, updated_at: '', collection_status: 'uncollected',
}
const authState = isAuthenticated as Ref<boolean>

async function openPalette() {
  const wrapper = mount(GlobalSearchPalette, { global: { stubs: { Teleport: true } } })
  useGlobalSearch().open()
  await nextTick()
  return wrapper
}

describe('global paper search', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    vi.resetAllMocks()
    authState.value = false
    useGlobalSearch().close()
    mocks.fetch.mockResolvedValue({ results: [paper], total: 1 })
  })
  afterEach(() => vi.useRealTimers())

  it('lets guests find uncollected papers and open them with the keyboard', async () => {
    const wrapper = await openPalette()
    await wrapper.find('input').setValue('2610.18861')
    await vi.advanceTimersByTimeAsync(220)
    await flushPromises()
    expect(mocks.fetch).toHaveBeenCalledWith('2610.18861', 30, 'all')
    expect(wrapper.text()).toContain('Hybrid Reasoning Agents')
    expect(wrapper.find('[role="option"]').text()).toContain('未收藏')
    await wrapper.find('input').trigger('keydown', { key: 'Enter' })
    expect(mocks.push).toHaveBeenCalledWith('/papers/2610.18861')
    expect(useGlobalSearch().isOpen.value).toBe(false)
    wrapper.unmount()
  })

  it('shows ownership badges and requests a server-side scope filter', async () => {
    authState.value = true
    mocks.fetch.mockResolvedValue({ results: [
      { ...paper, collection_status: 'collected' },
      { ...paper, type: 'user_paper', id: 'up_1', collection_status: 'uploaded' },
    ] })
    const wrapper = await openPalette()
    await wrapper.find('input').setValue('Hybrid')
    await vi.advanceTimersByTimeAsync(220)
    await flushPromises()
    expect(wrapper.text()).toContain('已收藏')
    expect(wrapper.text()).toContain('我的上传')
    await wrapper.findAll('button').find(button => button.text() === '未收藏论文')!.trigger('click')
    await vi.advanceTimersByTimeAsync(220)
    expect(mocks.fetch).toHaveBeenLastCalledWith('Hybrid', 30, 'uncollected')
    wrapper.unmount()
  })

  it('does not show an old response after the query changes or the palette closes', async () => {
    let resolveOld!: (value: unknown) => void
    mocks.fetch.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    const wrapper = await openPalette()
    await wrapper.find('input').setValue('old')
    await vi.advanceTimersByTimeAsync(220)
    await wrapper.find('input').setValue('new')
    resolveOld({ results: [{ ...paper, title: 'Stale result' }] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Stale result')
    useGlobalSearch().close()
    await nextTick()
    await vi.advanceTimersByTimeAsync(220)
    expect(mocks.fetch).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
