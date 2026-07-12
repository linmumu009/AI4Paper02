import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { fetchPaperDetail, fetchUserPaperDetail } from '../../../api'
import type { UserPaper } from '../../../types/paper'
import UserPaperImmersiveReader from '../UserPaperImmersiveReader.vue'

vi.mock('../../../api', () => ({
  fetchPaperDetail: vi.fn(),
  fetchUserPaperDetail: vi.fn(),
  fetchResearchProjects: vi.fn().mockResolvedValue([]),
  addResearchProjectAsset: vi.fn(),
}))

function userPaper(id: string, title: string): UserPaper {
  return {
    id: Number(id.replace(/\D/g, '')) || 1,
    paper_id: id,
    user_id: 1,
    source_type: 'pdf',
    source_ref: `${title}.pdf`,
    title,
    authors: ['测试作者'],
    abstract: '上传论文摘要',
    institution: '个人文献库',
    year: 2026,
    pdf_path: `${id}.pdf`,
    pdf_static_url: `/static/${id}.pdf`,
    external_url: '',
    summary_json: '{}',
    paper_assets_json: '{}',
    process_status: 'completed',
    process_step: 'done',
    process_error: '',
    process_started_at: null,
    process_finished_at: null,
    summary: {
      institution: '个人文献库', short_title: title, '📖标题': `${title} Original`, '🌐来源': '我的论文', paper_id: id,
      '🛎️文章简介': { '🔸研究问题': '如何分析上传论文？', '🔸主要贡献': '复用结构化证据。' },
      '📝重点思路': ['保持来源上下文'], '🔎分析总结': ['适配器不重复请求普通详情'], '💡个人观点': '',
      authors: ['测试作者'], categories: ['cs.AI'], abstract: '上传论文摘要',
    },
    paper_assets: {
      paper_id: id, title, url: '', year: 2026,
      blocks: {
        method: { text: '', bullets: [], key_mechanisms: ['读取用户论文资产。'] },
        results: { text: '', bullets: [], main_findings: ['成功复用沉浸阅读器。'] },
      },
    },
    created_at: '2026-07-12T08:00:00Z',
    updated_at: '2026-07-12T08:00:00Z',
  }
}

describe('UserPaperImmersiveReader', () => {
  it('adapts uploaded paper detail without calling the regular paper endpoint', async () => {
    const paper = userPaper('up_1', '上传论文一')
    const related = userPaper('up_2', '上传论文二')
    vi.mocked(fetchUserPaperDetail).mockResolvedValue(paper)

    const wrapper = mount(UserPaperImmersiveReader, {
      props: {
        paper,
        relatedPapers: [related],
        position: 1,
        total: 2,
        canGoNext: true,
      },
    })
    await flushPromises()

    expect(fetchUserPaperDetail).toHaveBeenCalledWith('up_1')
    expect(fetchPaperDetail).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('上传论文一')
    expect(wrapper.text()).toContain('读取用户论文资产。')
    expect(wrapper.text()).toContain('下一篇')
    expect(wrapper.text()).not.toContain('加入知识库')

    const buttons = wrapper.findAll('button')
    await buttons.find(button => button.text().includes('继续浏览论文'))?.trigger('click')
    await buttons.find(button => button.text().includes('与相关文章比较'))?.trigger('click')
    await buttons.find(button => button.text().includes('打开论文 PDF'))?.trigger('click')

    expect(wrapper.emitted('next')).toHaveLength(1)
    expect(wrapper.emitted('compare')).toEqual([[['up_1', 'up_2']]])
    const openedPaper = wrapper.emitted('openPdf')?.[0]?.[0] as UserPaper | undefined
    expect(openedPaper?.paper_id).toBe('up_1')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('exit')).toHaveLength(1)
  })
})
