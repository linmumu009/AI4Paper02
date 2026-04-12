import { createRouter, createWebHistory, createWebHashHistory } from 'vue-router'
import { ensureAuthInitialized, isAdmin, isAuthenticated } from '../stores/auth'

// In Tauri the frontend is served from a custom protocol (tauri://localhost).
// WebHashHistory avoids 404s on hard refresh and works without a server-side
// SPA fallback.  In regular browser mode keep WebHistory for clean URLs.
const isTauri = typeof import.meta.env.VITE_API_BASE === 'string'
  && import.meta.env.VITE_API_BASE !== ''

// SEO: per-route meta (title + description)
const ROUTE_META: Record<string, { title: string; description: string }> = {
  'digest': {
    title: 'AI4Papers - 每日 arXiv 论文推荐 | 免费 AI 论文日报 · 中文摘要',
    description: '免费的 AI 论文推荐工具，每日自动筛选 arXiv 最新 AI/ML 论文，LLM 智能评分 + 顶级机构过滤 + 中文摘要 + 结果图摘要，10 分钟掌握前沿研究。',
  },
  'inspiration': {
    title: '灵感库 - AI4Papers 论文灵感生成工具',
    description: '从精选论文中激发研究灵感。AI 辅助浏览候选论文、对比分析、生成创新研究想法。免费的科研灵感工具。',
  },
  'workbench': {
    title: '灵感工作台 - AI4Papers 研究灵感生成',
    description: '基于知识库中的精选论文，AI 辅助生成新的研究想法与创意方案。免费的 AI 科研灵感生成工具。',
  },
  'login': {
    title: '登录 - AI4Papers 免费论文推荐工具',
    description: '登录 AI4Papers，解锁知识库、论文对比、灵感生成等高级功能。免费注册，免费使用。',
  },
  'register': {
    title: '注册 - AI4Papers 免费论文推荐工具',
    description: '注册 AI4Papers 账号，开始每日 arXiv 论文智能推荐之旅。完全免费，所有功能均可免费使用。',
  },
  'profile': {
    title: '个人中心 - AI4Papers',
    description: '管理您的 AI4Papers 账号信息、公告和订阅。',
  },
  'advanced-settings': {
    title: '高级设置 - AI4Papers',
    description: '管理 AI4Papers 的模型预设、提示词预设及各功能参数配置。',
  },
  'my-papers': {
    title: '我的论文 - AI4Papers',
    description: '上传或导入你自己的论文，支持 PDF 上传、arXiv 导入和手动录入，统一管理个人论文库。',
  },
  'community': {
    title: '社区 - AI4Papers',
    description: '与其他研究者交流讨论，提问、分享和探索最新的 AI 论文与研究想法。',
  },
  'tutorial': {
    title: '使用教程 - AI4Papers',
    description: 'AI4Papers 使用教程，了解如何使用每日论文推荐、知识库、论文对比、灵感生成等功能。',
  },
  'community-post': {
    title: '帖子详情 - AI4Papers 社区',
    description: '查看社区帖子详情与回复。',
  },
  'announcement-detail': {
    title: '公告详情 - AI4Papers',
    description: '查看 AI4Papers 平台公告详情。',
  },
}

const DEFAULT_TITLE = 'AI4Papers - 免费 AI 论文推荐工具 | arXiv 每日论文 · 中文摘要 · 论文阅读助手'
const DEFAULT_DESC  = 'AI4Papers 是免费的 AI 论文推荐工具和论文阅读助手，每日自动筛选 arXiv 最新论文，LLM 智能评分 + 中文摘要 + 结果图摘要 + 知识库 + 论文对比 + 灵感生成。'

/** 更新 <title> 和 <meta name="description"> */
export function setPageMeta(title: string, description?: string) {
  document.title = title
  let el = document.querySelector<HTMLMetaElement>('meta[name="description"]')
  if (!el) {
    el = document.createElement('meta')
    el.name = 'description'
    document.head.appendChild(el)
  }
  el.content = description || DEFAULT_DESC
}

const router = createRouter({
  history: isTauri ? createWebHashHistory() : createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'digest',
      component: () => import('../views/DailyDigest.vue'),
    },
    {
      path: '/inspiration',
      name: 'inspiration',
      component: () => import('../views/PaperList.vue'),
    },
    // ---------------------------------------------------------------------------
    // Idea Generation v2 routes (灵感生成)
    // ---------------------------------------------------------------------------
    {
      path: '/workbench',
      name: 'workbench',
      component: () => import('../views/WorkbenchView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea',
      redirect: '/workbench',
    },
    {
      path: '/idea/candidates/:id',
      name: 'idea-detail',
      component: () => import('../views/IdeaDetailView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/atoms',
      name: 'idea-atoms',
      component: () => import('../views/AtomBrowser.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/exemplars',
      name: 'idea-exemplars',
      component: () => import('../views/ExemplarView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/eval',
      name: 'idea-eval',
      component: () => import('../views/EvalReplayView.vue'),
      meta: { requiresAuth: true },
    },
    // ---------------------------------------------------------------------------
    {
      path: '/my-papers',
      name: 'my-papers',
      redirect: '/?tab=mypapers',
    },
    {
      path: '/community',
      name: 'community',
      component: () => import('../views/CommunityView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tutorial',
      name: 'tutorial',
      component: () => import('../views/TutorialView.vue'),
    },
    {
      path: '/community/post/:id',
      name: 'community-post',
      component: () => import('../views/CommunityPostView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/announcements/:id',
      name: 'announcement-detail',
      component: () => import('../views/AnnouncementDetail.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/papers/:id',
      name: 'paper-detail',
      component: () => import('../views/PaperDetail.vue'),
      props: true,
    },
    {
      path: '/notes/:id',
      name: 'note-editor',
      component: () => import('../views/NoteEditor.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/Register.vue'),
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfileSettings.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/advanced-settings',
      name: 'advanced-settings',
      component: () => import('../views/ProfileSettings.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      redirect: '/admin/users',
    },
    {
      path: '/admin/user',
      redirect: '/admin/users',
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsers.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

// SEO: update document title and meta description on every navigation
// + Analytics: track page views
import { trackPageView } from '../composables/useAnalytics'

router.afterEach((to) => {
  // paper-detail pages handle their own title in the component
  if (to.name === 'paper-detail') return
  const m = ROUTE_META[to.name as string]
  setPageMeta(m?.title || DEFAULT_TITLE, m?.description)

  // Track page view for analytics
  trackPageView(String(to.name || to.path))
})

router.beforeEach(async (to) => {
  // 确保认证状态已初始化
  await ensureAuthInitialized()
  
  // 检查是否需要管理员权限
  if (to.meta.requiresAdmin) {
    // 先检查是否已登录
    if (!isAuthenticated.value) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }
    // 再检查是否有管理员权限
    if (!isAdmin.value) {
      return { path: '/' }
    }
  }
  
  // 检查是否需要登录
  if (to.meta.requiresAuth) {
    if (!isAuthenticated.value) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }
  }
  
  return true
})

export default router
