import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResearchStreamContent from './ResearchStreamContent.vue'

describe('ResearchStreamContent', () => {
  it('emits the paper ID when a generated report citation is clicked', async () => {
    const wrapper = mount(ResearchStreamContent, {
      props: { streamText: '该结论由 2607.08716 支持。', isRunning: false, paperIds: ['2607.08716'] },
    })

    await wrapper.find('[data-research-paper-id="2607.08716"]').trigger('click')
    expect(wrapper.emitted('openPaper')).toEqual([['2607.08716']])
  })
})
