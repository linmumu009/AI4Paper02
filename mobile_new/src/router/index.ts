import { createRouter, createWebHistory } from 'vue-router'
import { ensureAuthInitialized, isAuthenticated, isAdmin } from '@shared/stores/auth'
import { trackPageView } from '@shared/composables/useAnalytics'
import { applyPageMeta } from '@/utils/seo'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/recommend',
    },

    // ── Tab: 推荐 ──────────────────────────────────────────
    {
      path: '/recommend',
      name: 'recommend',
      component: () => import('../views/RecommendView.vue'),
      meta: { tab: 'recommend' },
    },

    // ── Tab: 灵感 ──────────────────────────────────────────
    {
      path: '/idea',
      name: 'idea',
      component: () => import('../views/IdeaView.vue'),
      meta: { tab: 'idea', requiresAuth: true },
    },
    {
      path: '/idea/candidates/:id',
      name: 'idea-detail',
      component: () => import('../views/IdeaDetailView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: '/idea/lab',
      name: 'idea-lab',
      component: () => import('../views/IdeaLabView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/atoms',
      name: 'idea-atoms',
      component: () => import('../views/AtomBrowserView.vue'),
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

    // ── Tab: 知识库 ────────────────────────────────────────
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('../views/KnowledgeView.vue'),
      meta: { tab: 'knowledge', requiresAuth: true },
    },

    // ── Tab: 我的 ──────────────────────────────────────────
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfileView.vue'),
      meta: { tab: 'profile' },
    },

    // ── 工作台 ─────────────────────────────────────────────
    {
      path: '/workbench',
      name: 'workbench',
      component: () => import('../views/WorkbenchView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 论文 & 笔记 ────────────────────────────────────────
    {
      path: '/paper/:id',
      name: 'paper-detail',
      component: () => import('../views/PaperDetailView.vue'),
      props: true,
    },
    {
      path: '/paper/:id/read',
      name: 'paper-reader',
      component: () => import('../views/PaperReaderView.vue'),
      props: true,
    },
    {
      path: '/notes/:id',
      name: 'note-editor',
      component: () => import('../views/NoteEditorView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },

    // ── 对比 ───────────────────────────────────────────────
    {
      path: '/compare',
      name: 'compare',
      component: () => import('../views/CompareView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/compare-result/:id',
      name: 'compare-result',
      component: () => import('../views/CompareResultView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: '/compare-library',
      name: 'compare-library',
      component: () => import('../views/CompareLibraryView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 深度研究 ───────────────────────────────────────────
    {
      path: '/research',
      name: 'research',
      component: () => import('../views/ResearchView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/research-library',
      name: 'research-library',
      component: () => import('../views/ResearchLibraryView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 社区 ───────────────────────────────────────────────
    {
      path: '/community',
      name: 'community',
      component: () => import('../views/CommunityView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/community/post/:id',
      name: 'community-post',
      component: () => import('../views/CommunityPostView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },

    // ── 设置 ───────────────────────────────────────────────
    {
      path: '/settings',
      name: 'advanced-settings',
      component: () => import('../views/AdvancedSettingsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings/llm-presets',
      name: 'llm-presets',
      component: () => import('../views/LlmPresetsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings/prompt-presets',
      name: 'prompt-presets',
      component: () => import('../views/PromptPresetsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings/feature/:feature',
      name: 'feature-settings',
      component: () => import('../views/FeatureSettingsView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: '/settings/idea-generate',
      name: 'idea-generate-settings',
      component: () => import('../views/IdeaGenerateSettingsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/knowledge/auto-classify',
      name: 'auto-classify-settings',
      component: () => import('../views/AutoClassifySettingsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/announcements',
      name: 'announcements',
      component: () => import('../views/AnnouncementsView.vue'),
    },

    // ── 管理员 ─────────────────────────────────────────────
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/AdminDashboardView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsersView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/redeem-keys',
      name: 'admin-redeem-keys',
      component: () => import('../views/AdminRedeemKeysView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/analytics',
      name: 'admin-analytics',
      component: () => import('../views/AdminAnalyticsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/llm-configs',
      name: 'admin-llm-configs',
      component: () => import('../views/AdminLlmConfigsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/prompt-configs',
      name: 'admin-prompt-configs',
      component: () => import('../views/AdminPromptConfigsView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/data-tracking',
      name: 'admin-data-tracking',
      component: () => import('../views/AdminDataTrackingView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/recommend-config',
      name: 'admin-recommend-config',
      component: () => import('../views/AdminRecommendConfigView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/idea-system-config',
      name: 'admin-idea-system-config',
      component: () => import('../views/AdminIdeaSystemConfigView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },

    // ── AI 对话 ────────────────────────────────────────────
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 成就 ───────────────────────────────────────────────
    {
      path: '/achievements',
      name: 'achievements',
      component: () => import('../views/AchievementsView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 订阅与用量 ─────────────────────────────────────────
    {
      path: '/subscription',
      name: 'subscription',
      component: () => import('../views/SubscriptionView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 教程 ───────────────────────────────────────────────
    {
      path: '/tutorial',
      name: 'tutorial',
      component: () => import('../views/TutorialView.vue'),
    },
    {
      path: '/tutorial/:chapter',
      name: 'tutorial-chapter',
      component: () => import('../views/TutorialChapterView.vue'),
      props: true,
    },

    // ── 我的论文 ───────────────────────────────────────────
    {
      path: '/my-papers',
      name: 'my-papers',
      component: () => import('../views/MyPapersView.vue'),
      meta: { requiresAuth: true },
    },

    // ── 认证 ───────────────────────────────────────────────
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  await ensureAuthInitialized()
  if (!to.meta.requiresAuth) return true
  if (!isAuthenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !isAdmin.value) {
    return { path: '/profile' }
  }
  return true
})

router.afterEach((to) => {
  applyPageMeta(to.name as string | undefined)
  if (to.name) {
    trackPageView(String(to.name), { path: to.path })
  }
})

export default router
