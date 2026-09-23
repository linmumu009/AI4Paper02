import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ReadingTrialEntry from '../ReadingTrialEntry.vue'

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
  it('does not offer reading without a generated document', () => {
    const wrapper = mount(ReadingTrialEntry)
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
})
