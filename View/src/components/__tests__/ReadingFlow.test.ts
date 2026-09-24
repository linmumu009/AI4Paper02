import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ReadingTrialViewer from '../ReadingTrialViewer.vue'

vi.mock('../../api', () => ({ IS_TAURI: false, tauriFetchText: vi.fn() }))
vi.mock('../ReadingExcerptMenu.vue', () => ({ default: { name: 'ReadingExcerptMenu', template: '<button class="test-excerpt" @click="$emit(\'saved\', {id: 7, title: \'论文笔记\'})">保存测试摘录</button>', emits: ['saved'] } }))
vi.mock('../ReadingNotesPanel.vue', () => ({ default: { name: 'ReadingNotesPanel', template: '<aside class="test-notes">并排笔记</aside>' } }))

describe('reading without navigation', () => {
  it('restores the same paper position after remount', async () => {
    sessionStorage.clear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => '# 阅读位置\n\n正文。' }))
    vi.stubGlobal('CSS', { escape: (text: string) => text })
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length })
    const props = { url: '/resume.md', mode: 'zh' as const, paperId: 'resume', scope: 'mypapers' as const }
    const first = mount(ReadingTrialViewer, { props })
    await flushPromises()
    frames.splice(0).forEach(callback => callback(0))
    const body = first.find('.markdown-viewer-body')
    ;(body.element as HTMLElement).scrollTop = 650
    await body.trigger('scroll')
    first.unmount()
    const second = mount(ReadingTrialViewer, { props })
    await flushPromises()
    frames.splice(0).forEach(callback => callback(0))
    expect((second.find('.markdown-viewer-body').element as HTMLElement).scrollTop).toBe(650)
    second.unmount()
    sessionStorage.clear()
    vi.unstubAllGlobals()
  })
  it('saves quietly and opens notes only on request, keeping the same reader mounted', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, text: async () => '# 摘要\n\n需要继续阅读的正文内容。' })
    vi.stubGlobal('fetch', fetch)
    vi.stubGlobal('CSS', { escape: (text: string) => text })
    Range.prototype.getBoundingClientRect = () => new DOMRect(100, 100, 200, 20)
    const wrapper = mount(ReadingTrialViewer, { props: { url: '/paper.md', mode: 'zh', paperId: 'paper', scope: 'mypapers' }, attachTo: document.body })
    await flushPromises()
    const body = wrapper.find('.markdown-viewer-body').element as HTMLElement
    body.scrollTop = 150
    const range = document.createRange()
    range.selectNodeContents(body.querySelector('p')!)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    await wrapper.find('.markdown-viewer-body').trigger('mouseup')
    await wrapper.find('.test-excerpt').trigger('click')
    expect(wrapper.find('.test-notes').exists()).toBe(false)
    expect(body.scrollTop).toBe(150)
    expect(wrapper.find('.saved-notice').text()).toContain('已存入')
    await wrapper.find('.saved-notice button').trigger('click')
    expect(wrapper.find('.test-notes').exists()).toBe(true)
    expect(wrapper.find('.markdown-viewer-body').element).toBe(body)
    expect(fetch).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    vi.unstubAllGlobals()
  })
})
