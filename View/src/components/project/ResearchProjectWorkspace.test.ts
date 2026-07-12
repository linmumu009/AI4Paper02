import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { PaperDetailResponse, PaperSummary, ResearchProject } from '../../types/paper'
import ResearchProjectWorkspace from './ResearchProjectWorkspace.vue'

const candidate: PaperSummary = {
  institution: 'Meta AI', short_title: '长期记忆增强智能体', '📖标题': 'Long-Horizon Agents', '🌐来源': 'arXiv', paper_id: 'candidate',
  '推荐理由': '与长期记忆课题高度相关。', '🛎️文章简介': { '🔸研究问题': '如何保持状态？', '🔸主要贡献': '提出记忆增强方法。' },
  '📝重点思路': [], '🔎分析总结': [], '💡个人观点': '',
}

const project: ResearchProject = {
  id: 1, user_id: 1, legacy_folder_id: 2, name: '长期记忆智能体', objective: '如何在长期任务中主动更新关键记忆？',
  description: '', status: 'active', created_at: '2026-07-01', updated_at: '2026-07-12', archived_at: null,
  counts: { paper: 1 }, asset_count: 1, paper_ids: ['paper-1'], sessions: [],
  assets: [{ id: 1, project_id: 1, asset_type: 'paper', asset_id: 'paper-1', source_scope: 'kb', metadata: {}, added_at: '2026-07-12', title: '主动记忆干预', subtitle: 'Meta AI', route: '/papers/paper-1', missing: false }],
}

const detail: PaperDetailResponse = {
  summary: { ...candidate, paper_id: 'paper-1', short_title: '主动记忆干预', authors: ['Yifan Wu'] },
  paper_assets: { paper_id: 'paper-1', title: '主动记忆干预', url: '', year: 2026, blocks: {
    method: { text: '主动更新结构化记忆。', bullets: [] },
    results: { text: '', bullets: [], main_findings: ['在长期任务上稳定提升。'] },
  } },
  date: '2026-07-12', images: [], arxiv_url: '', pdf_url: '',
}

describe('ResearchProjectWorkspace', () => {
  it('renders real project evidence and candidate papers', () => {
    const wrapper = mount(ResearchProjectWorkspace, { props: { project, projects: [project], paperDetails: { 'paper-1': detail }, candidates: [candidate] } })
    expect(wrapper.text()).toContain('如何在长期任务中主动更新关键记忆？')
    expect(wrapper.text()).toContain('在长期任务上稳定提升。')
    expect(wrapper.text()).toContain('长期记忆增强智能体')
  })

  it('emits candidate, tab and prompted research actions', async () => {
    const wrapper = mount(ResearchProjectWorkspace, { props: { project, candidates: [candidate] } })
    await wrapper.findAll('.project-workspace__candidate>button')[1].trigger('click')
    await wrapper.findAll('.project-workspace__tabs button').find(button => button.text() === '论文对比')?.trigger('click')
    await wrapper.find('.project-workspace__composer textarea').setValue('验证记忆干预的边界条件')
    await wrapper.find('.project-workspace__composer').trigger('submit')

    expect(wrapper.emitted('addCandidate')).toEqual([[candidate]])
    expect(wrapper.emitted('update:activeTab')).toContainEqual(['compare'])
    expect(wrapper.emitted('startResearch')).toContainEqual(['验证记忆干预的边界条件'])
  })

  it('opens project evidence in the shared immersive reader and restores the project with Escape', async () => {
    const wrapper = mount(ResearchProjectWorkspace, { props: { project, projects: [project], paperDetails: { 'paper-1': detail } } })

    await wrapper.find('.project-workspace__evidence-row').trigger('click')

    expect(wrapper.find('[aria-label="沉浸论文阅读"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="返回研究项目"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前课题')
    expect(wrapper.text()).toContain('长期记忆智能体')
    expect(wrapper.text()).toContain('下一证据')
    expect(wrapper.text()).not.toContain('加入课题')

    const pdfButton = wrapper.findAll('button').find(button => button.text().includes('打开论文 PDF'))
    const detailButton = wrapper.findAll('button').find(button => button.text().includes('查看完整解析'))
    await pdfButton?.trigger('click')
    await detailButton?.trigger('click')
    expect(wrapper.emitted('openPaperPdf')).toEqual([['paper-1']])
    expect(wrapper.emitted('openAsset')).toEqual([[project.assets[0]]])

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[aria-label="沉浸论文阅读"]').exists()).toBe(false)
    expect(wrapper.find('.project-workspace').exists()).toBe(true)
    wrapper.unmount()
  })

  it('falls back to the original asset route when structured paper detail is unavailable', async () => {
    const wrapper = mount(ResearchProjectWorkspace, { props: { project, paperDetails: {} } })
    await wrapper.find('.project-workspace__evidence-row').trigger('click')
    expect(wrapper.emitted('openAsset')).toEqual([[project.assets[0]]])
    expect(wrapper.find('[aria-label="沉浸论文阅读"]').exists()).toBe(false)
  })
})
