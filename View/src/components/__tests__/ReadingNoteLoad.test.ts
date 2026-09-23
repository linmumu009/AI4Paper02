import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import NoteEditor from '../../views/NoteEditor.vue'

const api = vi.hoisted(() => ({ updateNote: vi.fn() }))
vi.mock('../../api', () => ({
  fetchNoteDetail: vi.fn().mockResolvedValue({ id: 10, title: '我的研究摘录', content: '<blockquote><p><a href="/reading-source/paper#anchor">论文摘录</a></p></blockquote><p>返回原文</p>' }),
  updateNote: api.updateNote,
  deleteNote: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }), onBeforeRouteLeave: vi.fn() }))
vi.mock('../project/AddToProjectDialog.vue', () => ({ default: { template: '<div />' } }))

describe('loading a note containing reading excerpts', () => {
  it('retains its title and source link without saving on load', async () => {
    const wrapper = mount(NoteEditor, { props: { id: '10', embedded: true } })
    await flushPromises()
    expect((wrapper.find('input[placeholder="笔记标题..."]').element as HTMLInputElement).value).toBe('我的研究摘录')
    expect(wrapper.find('a[href="/reading-source/paper#anchor"]').exists()).toBe(true)
    expect(api.updateNote).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
