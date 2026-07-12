import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResearchWorkspace from './ResearchWorkspace.vue'

describe('ResearchWorkspace', () => {
  it('frames the real research panel with corpus and execution plan', () => {
    const wrapper = mount(ResearchWorkspace, {
      props: {
        paperIds: ['2607.08716', '2607.08421'],
        paperTitles: {
          '2607.08716': '长期记忆扩展',
          '2607.08421': '循环记忆机制',
        },
        projectId: 9,
        scope: 'kb',
      },
      global: { stubs: { ResearchPanel: { template: '<div data-testid="research-panel" />' } } },
    })

    expect(wrapper.find('.research-workspace').exists()).toBe(true)
    expect(wrapper.text()).toContain('长期记忆扩展')
    expect(wrapper.text()).toContain('R1')
    expect(wrapper.text()).toContain('全文精读')
    expect(wrapper.text()).toContain('结果将归入课题 #9')
    expect(wrapper.find('[data-testid="research-panel"]').exists()).toBe(true)
  })

  it('forwards research panel actions to the page', async () => {
    const wrapper = mount(ResearchWorkspace, {
      props: { paperIds: ['a'], paperTitles: { a: '论文 A' } },
      global: {
        stubs: {
          ResearchPanel: {
            emits: ['close', 'removePaper', 'saveToLibrary'],
            template: '<div><button class="close" @click="$emit(\'close\')"/><button class="remove" @click="$emit(\'removePaper\', \'a\')"/><button class="save" @click="$emit(\'saveToLibrary\', 7)"/></div>',
          },
        },
      },
    })
    await wrapper.find('.close').trigger('click')
    await wrapper.find('.remove').trigger('click')
    await wrapper.find('.save').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('removePaper')).toEqual([['a']])
    expect(wrapper.emitted('saveToLibrary')).toEqual([[7]])
  })
})
