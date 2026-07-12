import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchPaperDetail } from '../../../api'
import { clearWorkspacePaperDetailCache } from '../../../composables/useWorkspacePaperDetail'
import type { KbPaper, KbTree, PaperDetailResponse, PaperSummary } from '../../../types/paper'
import KnowledgeWorkspace from '../KnowledgeWorkspace.vue'

vi.mock('../../../api', () => ({
  fetchPaperDetail: vi.fn(),
  fetchResearchProjects: vi.fn().mockResolvedValue([]),
  addResearchProjectAsset: vi.fn(),
}))

function summary(id: string, title: string, score: number): PaperSummary {
  return {
    institution: 'Test Lab', short_title: title, '📖标题': title, '🌐来源': 'arXiv', paper_id: id,
    '🛎️文章简介': { '🔸研究问题': '如何保持长期状态？', '🔸主要贡献': '提出结构化记忆更新。' },
    '📝重点思路': ['主动更新记忆'], '🔎分析总结': ['长期任务稳定提升'], '💡个人观点': '',
    authors: ['Yifan Wu'], relevance_score: score,
  }
}

function kbPaper(id: string, title: string, score: number, folderId: number | null): KbPaper {
  return {
    id: Number(id.replace(/\D/g, '')) || 1, paper_id: id, folder_id: folderId,
    paper_data: summary(id, title, score), created_at: `2026-07-${id.endsWith('2') ? '11' : '12'}T08:00:00Z`,
    note_count: id.endsWith('2') ? 2 : 0, read_status: id.endsWith('2') ? 'reading' : 'unread',
  }
}

const rootPaper = kbPaper('paper-1', '主动记忆干预', .98, null)
const folderPaper = kbPaper('paper-2', '长期智能体评测', .94, 7)
const tree: KbTree = {
  papers: [rootPaper],
  folders: [{ id: 7, name: '长期记忆', parent_id: null, children: [], papers: [folderPaper], created_at: '2026-07-01', updated_at: '2026-07-12' }],
}

const detail: PaperDetailResponse = {
  summary: rootPaper.paper_data, paper_assets: null, date: '2026-07-12', images: [], arxiv_url: '', pdf_url: '',
}

describe('KnowledgeWorkspace', () => {
  beforeEach(() => {
    clearWorkspacePaperDetailCache()
    vi.mocked(fetchPaperDetail).mockImplementation(async (paperId) => ({
      ...detail,
      summary: paperId === folderPaper.paper_id ? folderPaper.paper_data : rootPaper.paper_data,
    }))
  })

  it('renders all papers and narrows to the active folder', async () => {
    const wrapper = mount(KnowledgeWorkspace, { props: { kbTree: tree, activeFolderId: null } })
    await flushPromises()
    expect(wrapper.text()).toContain('主动记忆干预')
    expect(wrapper.text()).toContain('长期智能体评测')
    expect(wrapper.text()).toContain('2 篇论文')

    await wrapper.setProps({ activeFolderId: 7 })
    expect(wrapper.text()).not.toContain('主动记忆干预')
    expect(wrapper.text()).toContain('长期智能体评测')
    expect(wrapper.text()).toContain('长期记忆')
  })

  it('emits batch compare, research and read-status actions', async () => {
    const wrapper = mount(KnowledgeWorkspace, { props: { kbTree: tree, activeFolderId: null } })
    const checkboxes = wrapper.findAll<HTMLInputElement>('.knowledge-workspace__paper-cell>input')
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)

    const batchButtons = wrapper.findAll('.knowledge-workspace__batchbar button')
    await batchButtons.find(button => button.text().includes('加入对比'))?.trigger('click')
    await batchButtons.find(button => button.text().includes('深度研究'))?.trigger('click')
    await wrapper.find('.knowledge-workspace__status').trigger('click')

    expect(wrapper.emitted('compare')).toEqual([[['paper-1', 'paper-2']]])
    expect(wrapper.emitted('research')?.[0]?.[0]).toEqual(['paper-1', 'paper-2'])
    expect(wrapper.emitted('updateReadStatus')?.[0]).toEqual([rootPaper, 'reading'])
  })

  it('opens knowledge papers in the shared immersive reader and restores the library on exit', async () => {
    const wrapper = mount(KnowledgeWorkspace, { props: { kbTree: tree, activeFolderId: null } })
    await wrapper.findAll('.knowledge-workspace__row')[0].trigger('dblclick')
    await flushPromises()

    expect(wrapper.find('[aria-label="沉浸论文阅读"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="返回知识库"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('标为已读')
    expect(wrapper.text()).toContain('移出知识库')

    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text().includes('查看完整解析'))?.trigger('click')
    expect(wrapper.emitted('openPaper')).toEqual([[rootPaper.paper_id]])

    await buttons.find(button => button.text().includes('完成本次阅读'))?.trigger('click')
    expect(wrapper.emitted('updateReadStatus')?.at(-1)).toEqual([rootPaper, 'read'])
    expect(wrapper.text()).toContain('2 / 2')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('.knowledge-workspace__rows').exists()).toBe(true)
    expect(wrapper.find('[aria-label="沉浸论文阅读"]').exists()).toBe(false)
  })
})
