/** Map web-app paths from reward hints / legacy links to mobile routes */
export function toMobilePath(webPath: string): string {
  const map: Record<string, string> = {
    '/': '/recommend',
    '/inspiration': '/idea',
    '/my-papers': '/my-papers',
    '/workbench': '/workbench',
    '/community': '/community',
    '/tutorial': '/tutorial',
  }
  if (map[webPath]) return map[webPath]
  if (webPath.startsWith('/papers/')) {
    const id = webPath.replace('/papers/', '')
    return id ? `/paper/${id}` : '/recommend'
  }
  return webPath
}

export const ROUTE_META: Record<string, { title: string; description?: string }> = {
  recommend: { title: '推荐', description: '每日论文与灵感推荐' },
  idea: { title: '灵感', description: '灵感推荐与实验室' },
  'idea-detail': { title: '灵感详情' },
  'idea-lab': { title: '灵感实验室' },
  'idea-atoms': { title: '灵感原子' },
  'idea-exemplars': { title: '范例库' },
  'idea-eval': { title: '评测回放' },
  knowledge: { title: '知识库' },
  profile: { title: '我的' },
  workbench: { title: '工作台' },
  'paper-detail': { title: '论文详情' },
  'note-editor': { title: '笔记' },
  compare: { title: '论文对比' },
  'compare-result': { title: '对比结果' },
  'compare-library': { title: '对比库', description: '查看已保存的论文对比分析结果' },
  research: { title: '深度研究' },
  'research-library': { title: '研究库', description: '查看已保存的深度研究记录' },
  community: { title: '社区' },
  'community-post': { title: '帖子' },
  'idea-generate-settings': { title: '灵感生成设置' },
  'admin-users': { title: '用户管理' },
  'admin-recommend-config': { title: '推荐配置' },
  'admin-idea-system-config': { title: '灵感系统配置' },
  chat: { title: 'AI 对话', description: '与 AI 助手聊论文或自由提问' },
  achievements: { title: '成就与签到', description: '查看连续签到、今日任务和里程碑' },
  subscription: { title: '订阅与用量', description: '查看当前套餐、AI 配额和功能权益' },
  tutorial: { title: '使用教程', description: '了解 AI4Papers 的核心功能与使用方法' },
  'tutorial-chapter': { title: '教程' },
  'my-papers': { title: '我的论文', description: '导入和管理自己上传的论文' },
  login: { title: '登录' },
  register: { title: '注册' },
}

const DEFAULT_TITLE = 'AI4Papers 移动版'
const DEFAULT_DESC =
  '免费的 AI 论文推荐与阅读工具。随时随地浏览每日 arXiv 论文精选与中文摘要。'

export function applyPageMeta(routeName: string | symbol | undefined | null) {
  const name = typeof routeName === 'string' ? routeName : ''
  const meta = name ? ROUTE_META[name] : undefined
  document.title = meta?.title ? `${meta.title} · ${DEFAULT_TITLE}` : DEFAULT_TITLE
  let descEl = document.querySelector('meta[name="description"]')
  if (!descEl) {
    descEl = document.createElement('meta')
    descEl.setAttribute('name', 'description')
    document.head.appendChild(descEl)
  }
  descEl.setAttribute('content', meta?.description ?? DEFAULT_DESC)
}
