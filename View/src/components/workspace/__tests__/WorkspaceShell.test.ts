import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResearchWorkspaceShell from '../ResearchWorkspaceShell.vue'
import WorkspaceModeSwitch from '../WorkspaceModeSwitch.vue'

describe('WorkspaceModeSwitch', () => {
  it('renders only enabled presentations and emits the selected mode', async () => {
    const wrapper = mount(WorkspaceModeSwitch, {
      props: {
        modelValue: 'card',
        modes: ['card', 'list'],
      },
    })

    const buttons = wrapper.findAll('[role="radio"]')
    expect(buttons.map(button => button.text())).toEqual(['卡片', '列表'])
    expect(buttons[0]?.attributes('aria-checked')).toBe('true')

    await buttons[1]?.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['list']])
  })

  it('supports arrow-key navigation between modes', async () => {
    const wrapper = mount(WorkspaceModeSwitch, {
      attachTo: document.body,
      props: {
        modelValue: 'list',
        modes: ['card', 'list', 'immersive'],
      },
    })

    const buttons = wrapper.findAll<HTMLButtonElement>('[role="radio"]')
    await buttons[1]?.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['immersive'])
    wrapper.unmount()
  })
})

describe('ResearchWorkspaceShell', () => {
  it('exposes the active presentation and keeps toolbar/content in stable regions', () => {
    const wrapper = mount(ResearchWorkspaceShell, {
      props: { mode: 'list', showToolbar: true },
      slots: {
        toolbar: '<div data-test="toolbar">filters</div>',
        default: '<div data-test="content">papers</div>',
      },
    })

    expect(wrapper.attributes('data-workspace-mode')).toBe('list')
    expect(wrapper.find('[data-test="toolbar"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
  })

  it('removes the toolbar region when the workspace has no controls', () => {
    const wrapper = mount(ResearchWorkspaceShell, {
      props: { mode: 'card', showToolbar: false },
      slots: { toolbar: 'filters', default: 'empty state' },
    })

    expect(wrapper.find('header').exists()).toBe(false)
    expect(wrapper.text()).toContain('empty state')
  })
})
