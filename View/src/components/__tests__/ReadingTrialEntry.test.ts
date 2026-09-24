import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ReadingTrialEntry from '../ReadingTrialEntry.vue'
import { readReadingSession, readingSessionKey } from '../../utils/readingSession'

vi.mock('../../api', () => ({ API_ORIGIN: '', IS_TAURI: false }))

describe('parallel reading entry', () => {
  it('opens the copied reader, switches to the original, and returns to the paper', async () => {
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
    HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
    const wrapper = mount(ReadingTrialEntry, {
      props: { mineruUrl: '/static/source.md', zhUrl: '/static/chinese.md', bilingualUrl: '/static/both.md' },
      global: { stubs: { Teleport: true, MarkdownViewer: { template: '<div data-reader="original" />' }, ReadingTrialViewer: { props: ['url', 'mode'], template: '<div data-reader="trial">{{ mode }} {{ url }}</div>' } } },
    })
    await wrapper.find('.trial-launch').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-reader="trial"]').text()).toContain('bilingual /static/both.md')
    await wrapper.find('[aria-label="阅读内容"]').setValue('zh')
    expect(wrapper.find('[data-reader="trial"]').text()).toContain('zh /static/chinese.md')
    await wrapper.find('[aria-label="阅读版本"]').setValue('original')
    expect(wrapper.find('[data-reader="original"]').exists()).toBe(true)
    expect(wrapper.find('[data-reader="trial"]').exists()).toBe(false)
    await wrapper.find('.trial-close').trigger('click')
    expect(wrapper.find('dialog').exists()).toBe(false)
    wrapper.unmount()
  })
  it('restores an open paper after remount and clears the session on explicit close', async () => {
    sessionStorage.clear()
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
    HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
    const global = { stubs: { Teleport: true, MarkdownViewer: true, ReadingTrialViewer: true } }
    const original = mount(ReadingTrialEntry, { props: { paperId: 'reload-paper', scope: 'mypapers', zhUrl: '/zh.md', bilingualUrl: '/both.md' }, global })
    await original.find('.trial-launch').trigger('click')
    await original.find('[aria-label="阅读内容"]').setValue('zh')
    const session = readReadingSession()!
    expect(session.paperId).toBe('reload-paper')
    expect(session.mode).toBe('zh')
    original.unmount()
    const restored = mount(ReadingTrialEntry, { props: { ...session, resume: session }, global })
    await flushPromises()
    expect(restored.find('dialog').attributes('open')).toBeDefined()
    expect((restored.find('[aria-label="阅读内容"]').element as HTMLSelectElement).value).toBe('zh')
    await restored.find('.trial-close').trigger('click')
    expect(sessionStorage.getItem(readingSessionKey)).toBeNull()
    restored.unmount()
  })
  it('does not offer reading without a generated document', () => {
    const wrapper = mount(ReadingTrialEntry)
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
})
