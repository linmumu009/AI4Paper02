<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import UserBar from '../components/UserBar.vue'

// ---------------------------------------------------------------------------
// Two-level navigation structure  (5 chapters, 11 sections)
// ---------------------------------------------------------------------------
interface Section {
  id: string
  label: string
}
interface Chapter {
  id: string
  label: string
  subtitle: string
  color: string
  sections: Section[]
}

const chapters: Chapter[] = [
  {
    id: 'ch-start',
    label: '一、快速入门',
    subtitle: 'Getting Started',
    color: 'text-tinder-pink',
    sections: [
      { id: 'intro',    label: '平台能为你做什么？' },
      { id: 'discover', label: '每日发现：刷卡浏览论文' },
    ],
  },
  {
    id: 'ch-config',
    label: '二、准备工作',
    subtitle: 'Setup',
    color: 'text-tinder-gold',
    sections: [
      { id: 'config', label: '模型配置：解锁 AI 功能' },
    ],
  },
  {
    id: 'ch-read',
    label: '三、沉浸阅读',
    subtitle: 'Deep Reading & Management',
    color: 'text-tinder-blue',
    sections: [
      { id: 'kb',      label: '知识库：管理专属文献' },
      { id: 'detail',  label: '深度阅读与笔记' },
      { id: 'compare', label: '论文对比' },
    ],
  },
  {
    id: 'ch-ai',
    label: '四、AI 与灵感',
    subtitle: 'AI Inspiration',
    color: 'text-tinder-purple',
    sections: [
      { id: 'ai',        label: 'AI 问答' },
      { id: 'workbench', label: '灵感工作台' },
    ],
  },
  {
    id: 'ch-expand',
    label: '五、扩展与交流',
    subtitle: 'Expand & Connect',
    color: 'text-tinder-green',
    sections: [
      { id: 'mypapers',  label: '导入论文与翻译' },
      { id: 'community', label: '社区互动' },
      { id: 'profile',   label: '个人中心与订阅' },
    ],
  },
]

const allSectionIds = chapters.flatMap(c => c.sections.map(s => s.id))

// ---------------------------------------------------------------------------
// Sidebar & scroll state
// ---------------------------------------------------------------------------
const showSidebar = ref(false)
const activeSection = ref('intro')
const contentRef = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

function scrollTo(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  if (window.innerWidth < 768) showSidebar.value = false
}

function initObserver() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) activeSection.value = entry.target.id
      }
    },
    { root: contentRef.value, rootMargin: '-15% 0px -70% 0px', threshold: 0 },
  )
  allSectionIds.forEach((id) => {
    const el = document.getElementById(id)
    if (el) observer!.observe(el)
  })
}

let mediaQuery: MediaQueryList | null = null
function onMediaChange(e: MediaQueryListEvent | MediaQueryList) {
  showSidebar.value = (e as MediaQueryListEvent).matches ?? (e as MediaQueryList).matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(min-width: 768px)')
  showSidebar.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange as EventListener)
  initObserver()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  mediaQuery?.removeEventListener('change', onMediaChange as EventListener)
})

function activeChapterId(): string {
  for (const ch of chapters) {
    if (ch.sections.some(s => s.id === activeSection.value)) return ch.id
  }
  return ''
}
</script>

<template>
  <div class="h-full flex overflow-hidden relative">

    <!-- Mobile overlay -->
    <div v-if="showSidebar" class="fixed inset-0 bg-black/50 z-20 md:hidden" @click="showSidebar = false" />

    <!-- ===================== Sidebar ===================== -->
    <aside
      class="w-60 shrink-0 bg-bg-sidebar border-r border-border flex flex-col z-30 transition-transform duration-200 md:relative md:translate-x-0"
      :class="showSidebar ? 'fixed inset-y-0 left-0 translate-x-0' : 'fixed inset-y-0 left-0 -translate-x-full'"
    >
      <div class="shrink-0 px-4 py-4 border-b border-border">
        <h2 class="text-sm font-semibold text-text-primary">使用教程</h2>
        <p class="text-[11px] text-text-muted mt-0.5">AI4Papers 功能指南</p>
      </div>

      <nav class="flex-1 overflow-y-auto py-2">
        <div v-for="chapter in chapters" :key="chapter.id" class="mb-1">
          <div
            class="px-3 pt-2.5 pb-1 text-[10px] font-bold tracking-wider uppercase select-none"
            :class="activeChapterId() === chapter.id ? chapter.color : 'text-text-muted'"
          >
            {{ chapter.label }}
          </div>
          <button
            v-for="section in chapter.sections"
            :key="section.id"
            class="w-full text-left pl-5 pr-3 py-1.5 text-xs transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer"
            :class="activeSection === section.id
              ? 'text-tinder-pink font-semibold bg-bg-hover'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'"
            @click="scrollTo(section.id)"
          >
            <span class="w-1 h-3 rounded-full shrink-0 transition-colors" :class="activeSection === section.id ? 'bg-tinder-pink' : 'bg-transparent'" />
            {{ section.label }}
          </button>
        </div>
      </nav>

      <div class="shrink-0 border-t border-border">
        <UserBar />
      </div>
    </aside>

    <!-- Mobile toggle -->
    <button
      v-if="!showSidebar"
      class="fixed top-[72px] left-0 z-20 bg-bg-card border border-border border-l-0 rounded-r-lg px-1.5 py-2 text-text-muted hover:text-text-primary transition-colors md:hidden"
      @click="showSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>

    <!-- ===================== Main content ===================== -->
    <div ref="contentRef" class="flex-1 h-full overflow-y-auto min-w-0">
      <div class="max-w-3xl mx-auto px-4 sm:px-6 py-8">

        <!-- =========================================================== -->
        <!-- CHAPTER 1: 快速入门                                          -->
        <!-- =========================================================== -->
        <div class="mb-3">
          <span class="text-xs font-bold text-tinder-pink tracking-widest uppercase">Chapter 1</span>
          <h1 class="text-xl font-bold text-text-primary mt-1">快速入门</h1>
          <p class="text-sm text-text-muted mt-1">5 分钟了解 AI4Papers 并完成第一次论文浏览</p>
        </div>
        <div class="w-full h-px bg-border mb-6" />

        <!-- 1.1 平台简介 -->
        <section id="intro" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white" style="background: linear-gradient(135deg, #fd267a, #ff6036);">1</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">平台能为你做什么？</h2>
                <p class="text-xs text-text-muted mt-0.5">花 3 分钟了解核心价值</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                <span class="font-semibold text-text-primary">AI4Papers</span> 是专为 AI/ML 研究者设计的论文发现与研究助手。它解决了一个核心痛点：<span class="text-tinder-pink font-medium">每天 arXiv 新增数百篇论文，你根本看不完</span>。
              </p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
                <div class="rounded-xl p-3.5 border border-border-light bg-bg-elevated">
                  <div class="flex items-center gap-2 mb-2">
                    <div class="w-6 h-6 rounded-md bg-tinder-pink/20 flex items-center justify-center shrink-0">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    </div>
                    <span class="text-xs font-semibold text-text-primary">AI 智能筛选</span>
                  </div>
                  <p class="text-xs text-text-secondary leading-relaxed">LLM 对每篇论文评分，只推送高质量研究成果，过滤低水平论文。</p>
                </div>
                <div class="rounded-xl p-3.5 border border-border-light bg-bg-elevated">
                  <div class="flex items-center gap-2 mb-2">
                    <div class="w-6 h-6 rounded-md bg-tinder-blue/20 flex items-center justify-center shrink-0">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-tinder-blue" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                    </div>
                    <span class="text-xs font-semibold text-text-primary">中文摘要</span>
                  </div>
                  <p class="text-xs text-text-secondary leading-relaxed">AI 生成结构化中文摘要，含研究问题、方法、结果，快速判断是否精读。</p>
                </div>
                <div class="rounded-xl p-3.5 border border-border-light bg-bg-elevated">
                  <div class="flex items-center gap-2 mb-2">
                    <div class="w-6 h-6 rounded-md bg-tinder-green/20 flex items-center justify-center shrink-0">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-tinder-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <span class="text-xs font-semibold text-text-primary">知识库 + 对比</span>
                  </div>
                  <p class="text-xs text-text-secondary leading-relaxed">收藏论文进知识库，文件夹分类管理，支持多篇横向对比分析。</p>
                </div>
                <div class="rounded-xl p-3.5 border border-border-light bg-bg-elevated">
                  <div class="flex items-center gap-2 mb-2">
                    <div class="w-6 h-6 rounded-md bg-tinder-purple/20 flex items-center justify-center shrink-0">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-tinder-purple" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
                    </div>
                    <span class="text-xs font-semibold text-text-primary">AI 灵感生成</span>
                  </div>
                  <p class="text-xs text-text-secondary leading-relaxed">AI 从收藏论文中提炼灵感候选，工作台组合生成完整研究方向提案。</p>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：AI4Papers 主界面概览</p>
              </div>
              <div class="rounded-xl border border-tinder-pink/20 bg-tinder-pink/5 p-4">
                <div class="text-xs font-bold text-tinder-pink mb-3">60 秒上手路径</div>
                <ol class="space-y-2.5">
                  <li class="flex items-start gap-3 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-tinder-pink/20 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-[10px]">1</span>
                    <span><span class="font-medium text-text-primary">注册免费账号</span>，无需付费即可使用全部核心功能。</span>
                  </li>
                  <li class="flex items-start gap-3 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-tinder-pink/20 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-[10px]">2</span>
                    <span>前往顶部导航「<span class="font-medium text-text-primary">发现</span>」，开始浏览今日推荐论文。</span>
                  </li>
                  <li class="flex items-start gap-3 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-tinder-pink/20 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-[10px]">3</span>
                    <span>如需使用 <span class="font-medium text-text-primary">AI 问答、对比、灵感</span> 等功能，先完成「第二章：准备工作」中的模型配置。</span>
                  </li>
                </ol>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('discover')">
                下一节：每日发现 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 1.2 每日发现 -->
        <section id="discover" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white" style="background: linear-gradient(135deg, #fd267a, #ff6036);">2</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">每日发现：刷卡浏览论文</h2>
                <p class="text-xs text-text-muted mt-0.5">掌握四个核心操作</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                「发现」页的界面仿照 Tinder 卡片设计。每张卡片是一篇经 AI 精选的论文，你只需决定：<span class="text-tinder-green font-medium">感兴趣</span>还是<span class="text-text-muted font-medium">跳过</span>。
              </p>
              <div class="mb-5">
                <div class="text-xs font-semibold text-text-primary mb-3">底部操作栏，从左到右：</div>
                <div class="grid grid-cols-2 gap-2.5">
                  <div class="rounded-xl p-3 border border-border bg-bg-elevated flex items-start gap-2.5">
                    <div class="w-7 h-7 rounded-full bg-bg-card border border-border flex items-center justify-center shrink-0 text-sm">↩</div>
                    <div><div class="text-xs font-semibold text-text-primary">撤回</div><div class="text-xs text-text-muted mt-0.5">返回上一张，重新决策</div></div>
                  </div>
                  <div class="rounded-xl p-3 border border-border bg-bg-elevated flex items-start gap-2.5">
                    <div class="w-7 h-7 rounded-full bg-bg-card border border-border flex items-center justify-center shrink-0 text-sm text-text-muted">✕</div>
                    <div><div class="text-xs font-semibold text-text-primary">跳过</div><div class="text-xs text-text-muted mt-0.5">不感兴趣，进入下一张</div></div>
                  </div>
                  <div class="rounded-xl p-3 border border-tinder-green/30 bg-tinder-green/5 flex items-start gap-2.5">
                    <div class="w-7 h-7 rounded-full bg-tinder-green/20 flex items-center justify-center shrink-0 text-sm">❤</div>
                    <div><div class="text-xs font-semibold text-tinder-green">收藏</div><div class="text-xs text-text-muted mt-0.5">加入知识库，进入下一张</div></div>
                  </div>
                  <div class="rounded-xl p-3 border border-tinder-gold/30 bg-tinder-gold/5 flex items-start gap-2.5">
                    <div class="w-7 h-7 rounded-full bg-tinder-gold/20 flex items-center justify-center shrink-0 text-sm">★</div>
                    <div><div class="text-xs font-semibold text-tinder-gold">详情</div><div class="text-xs text-text-muted mt-0.5">在右侧展开完整分析</div></div>
                  </div>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：发现页刷卡界面与底部操作栏</p>
              </div>
              <div class="rounded-xl border border-tinder-blue/20 bg-tinder-blue/5 p-4">
                <div class="text-xs font-bold text-tinder-blue mb-2.5">使用技巧</div>
                <ul class="space-y-2 text-xs text-text-secondary">
                  <li class="flex items-start gap-2"><span class="text-tinder-blue shrink-0 mt-0.5">›</span> 点击卡片顶部<span class="font-medium text-text-primary mx-1">日期下拉</span>，可回看任意历史日期的推荐。</li>
                  <li class="flex items-start gap-2"><span class="text-tinder-blue shrink-0 mt-0.5">›</span> 收藏时如已在侧边栏选中某文件夹，论文会直接进入该文件夹。</li>
                  <li class="flex items-start gap-2"><span class="text-tinder-blue shrink-0 mt-0.5">›</span> 免费账号每日可查看 <span class="font-medium text-text-primary">3 篇</span>推荐，Pro 15 篇，Pro+ 无限制。</li>
                </ul>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('config')">
                下一节：模型配置 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>


        <!-- =========================================================== -->
        <!-- CHAPTER 2: 准备工作                                          -->
        <!-- =========================================================== -->
        <div class="mb-3 mt-4">
          <span class="text-xs font-bold text-tinder-gold tracking-widest uppercase">Chapter 2</span>
          <h1 class="text-xl font-bold text-text-primary mt-1">准备工作</h1>
          <p class="text-sm text-text-muted mt-1">使用 AI 功能前，需先完成一次性的模型配置</p>
        </div>
        <div class="w-full h-px bg-border mb-6" />

        <!-- 2.1 模型配置 -->
        <section id="config" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-gold">3</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">模型配置：解锁 AI 功能的第一步</h2>
                <p class="text-xs text-text-muted mt-0.5">配置一次，所有 AI 功能均可使用</p>
              </div>
            </div>
            <div class="p-5">
              <!-- Why needed -->
              <div class="rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 p-4 mb-5">
                <div class="text-xs font-bold text-tinder-gold mb-2">为什么需要配置？</div>
                <p class="text-xs text-text-secondary leading-relaxed">以下功能均需要调用大模型（LLM）：AI 问答、论文对比、灵感生成、灵感工作台。平台不内置统一的 API Key，你需要提供自己的大模型服务凭证（支持 OpenAI / 阿里云通义 / 任意 OpenAI 兼容接口）。</p>
              </div>

              <!-- Steps -->
              <div class="text-xs font-semibold text-text-primary mb-3">配置步骤</div>
              <div class="space-y-3 mb-5">
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-gold/20 text-tinder-gold font-bold flex items-center justify-center shrink-0 text-[11px]">1</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    点击侧边栏底部的用户名展开菜单，选择「<span class="font-medium text-text-primary">高级设置</span>」。
                  </div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-gold/20 text-tinder-gold font-bold flex items-center justify-center shrink-0 text-[11px]">2</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    进入「<span class="font-medium text-text-primary">模型预设</span>」页面，点击「新建预设」，填写：
                    <div class="mt-2 space-y-1">
                      <div class="flex items-center gap-2"><span class="w-16 shrink-0 text-text-muted">Base URL</span><span class="font-mono text-[11px] bg-bg-card border border-border px-1.5 py-0.5 rounded text-text-secondary">https://api.openai.com/v1</span></div>
                      <div class="flex items-center gap-2"><span class="w-16 shrink-0 text-text-muted">API Key</span><span class="font-mono text-[11px] bg-bg-card border border-border px-1.5 py-0.5 rounded text-text-secondary">sk-...</span></div>
                      <div class="flex items-center gap-2"><span class="w-16 shrink-0 text-text-muted">Model</span><span class="font-mono text-[11px] bg-bg-card border border-border px-1.5 py-0.5 rounded text-text-secondary">gpt-4o-mini</span></div>
                    </div>
                  </div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-gold/20 text-tinder-gold font-bold flex items-center justify-center shrink-0 text-[11px]">3</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    保存预设后，前往各功能的独立配置页（<span class="font-medium text-text-primary">AI 问答 / 对比分析 / 灵感涌现 / 灵感生成</span>），在「使用模型预设」中选择刚创建的预设。
                  </div>
                </div>
              </div>

              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：高级设置 - 模型预设配置页</p>
              </div>

              <!-- Feature to preset mapping -->
              <div class="rounded-xl border border-border-light bg-bg-elevated overflow-hidden">
                <div class="px-4 py-2.5 border-b border-border">
                  <div class="text-xs font-semibold text-text-primary">各功能的配置位置</div>
                </div>
                <div class="divide-y divide-border">
                  <div v-for="item in [
                    { feature: 'AI 问答', path: '高级设置 → AI 问答', color: 'text-tinder-blue' },
                    { feature: '论文对比', path: '高级设置 → 对比分析', color: 'text-tinder-purple' },
                    { feature: '灵感涌现（灵感页）', path: '高级设置 → 灵感涌现', color: 'text-tinder-purple' },
                    { feature: '灵感生成（工作台）', path: '高级设置 → 灵感生成', color: 'text-tinder-purple' },
                  ]" :key="item.feature" class="flex items-center px-4 py-2 gap-3">
                    <span class="text-xs w-36 shrink-0" :class="item.color">{{ item.feature }}</span>
                    <span class="text-xs text-text-muted">{{ item.path }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('kb')">
                下一节：知识库管理 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>


        <!-- =========================================================== -->
        <!-- CHAPTER 3: 沉浸阅读                                          -->
        <!-- =========================================================== -->
        <div class="mb-3 mt-4">
          <span class="text-xs font-bold text-tinder-blue tracking-widest uppercase">Chapter 3</span>
          <h1 class="text-xl font-bold text-text-primary mt-1">沉浸阅读</h1>
          <p class="text-sm text-text-muted mt-1">整理知识库，深读、做笔记、多篇横向对比</p>
        </div>
        <div class="w-full h-px bg-border mb-6" />

        <!-- 3.1 知识库 -->
        <section id="kb" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-blue">4</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">知识库：管理你的专属文献</h2>
                <p class="text-xs text-text-muted mt-0.5">文件夹分类整理，构建个人研究档案</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                每次点击 ❤ 收藏，论文就进入左侧侧边栏的「<span class="font-medium text-text-primary">知识库</span>」Tab。知识库支持多级文件夹，按项目、主题或时间线分类管理。
              </p>
              <div class="space-y-3 mb-5">
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-blue/20 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-[11px]">1</div>
                  <div class="text-xs text-text-secondary leading-relaxed">在侧边栏「知识库」Tab 顶部点击 <span class="font-medium text-text-primary">「新建」</span> 按钮，创建文件夹（如「LLM 方向」）。</div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-blue/20 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-[11px]">2</div>
                  <div class="text-xs text-text-secondary leading-relaxed">浏览发现页时，<span class="font-medium text-text-primary">先在侧边栏点击目标文件夹</span>，再点击 ❤，论文直接进入该文件夹。</div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-blue/20 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-[11px]">3</div>
                  <div class="text-xs text-text-secondary leading-relaxed"><span class="font-medium text-text-primary">右键点击</span>侧边栏中的任意论文，弹出菜单可进行：新建笔记、加入对比清单、移动到其他文件夹、移出知识库等操作。</div>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：知识库侧边栏与右键菜单</p>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('detail')">
                下一节：深度阅读与笔记 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 3.2 深度阅读与笔记 -->
        <section id="detail" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-blue">5</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">深度阅读与笔记：双屏分栏体验</h2>
                <p class="text-xs text-text-muted mt-0.5">中文摘要 + PDF 并排对照，顺手记笔记</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                点击知识库中的论文后进入详情页。支持<span class="font-medium text-text-primary">单栏</span>和<span class="font-medium text-text-primary">左右分栏</span>两种模式，可同时展示多个内容面板。
              </p>
              <div class="grid grid-cols-3 gap-2.5 mb-5">
                <div class="rounded-xl p-3 border border-border bg-bg-elevated text-center">
                  <div class="text-xl mb-1.5">📄</div>
                  <div class="text-xs font-semibold text-text-primary">论文详情</div>
                  <div class="text-[11px] text-text-muted mt-1 leading-relaxed">AI 中文分析，含背景、方法、结果、图片</div>
                </div>
                <div class="rounded-xl p-3 border border-border bg-bg-elevated text-center">
                  <div class="text-xl mb-1.5">📕</div>
                  <div class="text-xs font-semibold text-text-primary">原文 PDF</div>
                  <div class="text-[11px] text-text-muted mt-1 leading-relaxed">内嵌阅读器，无需下载，可与中文摘要并排</div>
                </div>
                <div class="rounded-xl p-3 border border-border bg-bg-elevated text-center">
                  <div class="text-xl mb-1.5">📝</div>
                  <div class="text-xs font-semibold text-text-primary">阅读笔记</div>
                  <div class="text-[11px] text-text-muted mt-1 leading-relaxed">富文本编辑，2 秒自动保存</div>
                </div>
              </div>
              <div class="rounded-xl border border-border-light bg-bg-elevated p-4 mb-5">
                <div class="text-xs font-semibold text-text-primary mb-3">如何开启分栏阅读</div>
                <ol class="space-y-2">
                  <li class="flex items-start gap-2.5 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">1</span>
                    顶部<span class="font-medium text-text-primary mx-1">面板工具栏</span>点击「分栏」图标进入双屏模式。
                  </li>
                  <li class="flex items-start gap-2.5 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">2</span>
                    拖动<span class="font-medium text-text-primary mx-1">中间分割线</span>调整左右宽度比例。
                  </li>
                  <li class="flex items-start gap-2.5 text-xs text-text-secondary">
                    <span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">3</span>
                    点击右侧面板标签切换 PDF / 笔记。
                  </li>
                </ol>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：左侧中文摘要 + 右侧 PDF 分栏阅读</p>
              </div>
              <div class="rounded-xl border border-tinder-gold/20 bg-tinder-gold/5 p-4">
                <div class="text-xs font-bold text-tinder-gold mb-2.5">笔记编辑器支持</div>
                <div class="flex flex-wrap gap-1.5">
                  <span v-for="tool in ['H1–H3 标题','粗体 / 斜体','有序 / 无序列表','引用块','代码块','插入图片','插入链接','撤销 / 重做']" :key="tool" class="px-2 py-0.5 text-[11px] bg-bg-card rounded border border-border text-text-secondary">{{ tool }}</span>
                </div>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('compare')">
                下一节：论文对比 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 3.3 论文对比 -->
        <section id="compare" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-blue">6</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">论文对比：横向评测多篇文献</h2>
                <p class="text-xs text-text-muted mt-0.5">AI 生成结构化横向对比报告</p>
              </div>
            </div>
            <div class="p-5">
              <!-- Prerequisite notice -->
              <div class="flex items-center gap-3 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p class="text-xs text-text-secondary flex-1">
                  <span class="font-semibold text-tinder-gold">前置条件：</span>需先在「高级设置 → 对比分析」中配置模型预设。
                </p>
                <button class="text-xs text-tinder-gold hover:underline bg-transparent border-none cursor-pointer shrink-0 whitespace-nowrap" @click="scrollTo('config')">查看配置 ›</button>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                选择 2–5 篇论文，AI 生成涵盖方法、数据集、结果、局限性的<span class="font-medium text-text-primary">横向对比报告</span>。知识库论文和自己上传的论文均可混合选入对比。
              </p>
              <div class="space-y-3 mb-5">
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-purple/20 text-tinder-purple font-bold flex items-center justify-center shrink-0 text-[11px]">1</div>
                  <div class="text-xs text-text-secondary leading-relaxed"><span class="font-medium text-text-primary">右键</span>点击侧边栏中的论文，选择「<span class="text-tinder-purple font-medium">加入对比清单</span>」，重复操作选 2–5 篇。</div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-purple/20 text-tinder-purple font-bold flex items-center justify-center shrink-0 text-[11px]">2</div>
                  <div class="text-xs text-text-secondary leading-relaxed">侧边栏底部出现已选列表，确认后点击「<span class="text-tinder-purple font-medium">开始对比</span>」。</div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-purple/20 text-tinder-purple font-bold flex items-center justify-center shrink-0 text-[11px]">3</div>
                  <div class="text-xs text-text-secondary leading-relaxed">AI 分析完成后，报告展示在主区。历史对比结果保存在「<span class="text-tinder-purple font-medium">对比库</span>」Tab，随时可查。</div>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：对比清单选择与 AI 对比报告</p>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('ai')">
                下一节：AI 问答 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>


        <!-- =========================================================== -->
        <!-- CHAPTER 4: AI 与灵感                                         -->
        <!-- =========================================================== -->
        <div class="mb-3 mt-4">
          <span class="text-xs font-bold text-tinder-purple tracking-widest uppercase">Chapter 4</span>
          <h1 class="text-xl font-bold text-text-primary mt-1">AI 与灵感</h1>
          <p class="text-sm text-text-muted mt-1">从论文阅读到 AI 辅助的研究方向生成</p>
        </div>
        <div class="w-full h-px bg-border mb-6" />

        <!-- 4.1 AI 问答 -->
        <section id="ai" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-purple">7</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">AI 问答：随叫随到的论文助手</h2>
                <p class="text-xs text-text-muted mt-0.5">两种入口，随时向 AI 提问</p>
              </div>
            </div>
            <div class="p-5">
              <!-- Prerequisite notice -->
              <div class="flex items-center gap-3 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p class="text-xs text-text-secondary flex-1">
                  <span class="font-semibold text-tinder-gold">前置条件：</span>需先在「高级设置 → AI 问答」中配置模型预设。
                </p>
                <button class="text-xs text-tinder-gold hover:underline bg-transparent border-none cursor-pointer shrink-0 whitespace-nowrap" @click="scrollTo('config')">查看配置 ›</button>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                遇到看不懂的方法或想追问某个结论？AI 助手了解当前论文的全部内容，可以帮你解答任何疑问。
              </p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
                <div class="rounded-xl border border-tinder-blue/20 bg-tinder-blue/5 p-4">
                  <div class="text-xs font-semibold text-tinder-blue mb-2">内嵌论文问答</div>
                  <p class="text-xs text-text-secondary leading-relaxed mb-2">在论文详情页工具栏点击「💬 AI 问答」，在右侧面板输入问题，AI 基于当前论文内容回答。</p>
                  <div class="text-[11px] text-text-muted">适合：深入理解某篇论文的技术细节</div>
                </div>
                <div class="rounded-xl border border-tinder-pink/20 bg-tinder-pink/5 p-4">
                  <div class="text-xs font-semibold text-tinder-pink mb-2">全局 AI 聊天</div>
                  <p class="text-xs text-text-secondary leading-relaxed mb-2">点击右下角「💬」悬浮按钮，聊天抽屉从右侧滑出，不遮挡当前页面，支持自由切换论文上下文。</p>
                  <div class="text-[11px] text-text-muted">适合：跨论文综合提问或通用学术问答</div>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：全局 AI 聊天抽屉与内嵌问答面板</p>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('workbench')">
                下一节：灵感工作台 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 4.2 灵感工作台 -->
        <section id="workbench" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-purple">8</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">灵感工作台：让 AI 帮你构思研究方向</h2>
                <p class="text-xs text-text-muted mt-0.5">从论文日报到完整研究提案</p>
              </div>
            </div>
            <div class="p-5">
              <!-- Prerequisite notice -->
              <div class="flex items-center gap-3 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p class="text-xs text-text-secondary flex-1">
                  <span class="font-semibold text-tinder-gold">前置条件：</span>需先在「高级设置 → 灵感涌现 / 灵感生成」中配置模型预设。
                </p>
                <button class="text-xs text-tinder-gold hover:underline bg-transparent border-none cursor-pointer shrink-0 whitespace-nowrap" @click="scrollTo('config')">查看配置 ›</button>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                灵感模块分两层：顶部导航「<span class="font-medium text-text-primary">灵感</span>」提供每日刷卡；「<span class="font-medium text-text-primary">工作台</span>」提供深度方向生成与管理。
              </p>
              <div class="space-y-3 mb-5">
                <div class="rounded-xl border border-border bg-bg-elevated p-4">
                  <div class="text-xs font-semibold text-text-primary mb-2">灵感页（每日刷卡）</div>
                  <ul class="space-y-1.5 text-xs text-text-secondary">
                    <li class="flex items-start gap-2"><span class="text-tinder-purple shrink-0 mt-0.5">›</span> AI 每天从精选论文中提炼研究灵感候选，刷卡筛选喜欢的。</li>
                    <li class="flex items-start gap-2"><span class="text-tinder-purple shrink-0 mt-0.5">›</span> 切换到「<span class="font-medium text-text-primary">论文灵感</span>」Tab，选中知识库一篇论文，AI 为它单独生成灵感候选列表。</li>
                  </ul>
                </div>
                <div class="rounded-xl border border-tinder-purple/20 bg-tinder-purple/5 p-4">
                  <div class="text-xs font-semibold text-tinder-purple mb-2">灵感工作台（深度生成）</div>
                  <ul class="space-y-1.5 text-xs text-text-secondary">
                    <li class="flex items-start gap-2"><span class="text-tinder-purple shrink-0 mt-0.5">›</span> <span class="font-medium text-text-primary">灵感工作台</span>：选多篇论文，AI 组合生成包含问题定义、方法路线的完整研究方向提案。</li>
                    <li class="flex items-start gap-2"><span class="text-tinder-purple shrink-0 mt-0.5">›</span> <span class="font-medium text-text-primary">原子库</span>：管理从论文提炼的研究原子（方法、问题、数据集等），是灵感生成的基础素材。</li>
                    <li class="flex items-start gap-2"><span class="text-tinder-purple shrink-0 mt-0.5">›</span> <span class="font-medium text-text-primary">范例库</span>：收藏研究范例，作为灵感生成的风格参考。</li>
                  </ul>
                </div>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：灵感工作台与研究提案生成</p>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('mypapers')">
                下一节：导入论文与翻译 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>


        <!-- =========================================================== -->
        <!-- CHAPTER 5: 扩展与交流                                        -->
        <!-- =========================================================== -->
        <div class="mb-3 mt-4">
          <span class="text-xs font-bold text-tinder-green tracking-widest uppercase">Chapter 5</span>
          <h1 class="text-xl font-bold text-text-primary mt-1">扩展与交流</h1>
          <p class="text-sm text-text-muted mt-1">导入任意 PDF 并生成中文全文翻译，与研究者交流，个性化配置</p>
        </div>
        <div class="w-full h-px bg-border mb-6" />

        <!-- 5.1 导入论文与翻译 -->
        <section id="mypapers" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-green">9</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">导入论文与翻译：从上传到中文全文</h2>
                <p class="text-xs text-text-muted mt-0.5">上传任意 PDF，享受 AI 摘要与全文中文翻译</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                「我的论文」功能让你把平台外的论文带入平台，享受与推荐论文<span class="font-medium text-text-primary">完全相同</span>的 AI 分析体验（中文摘要、笔记、对比、AI 问答），还可额外生成<span class="font-medium text-text-primary">中文翻译</span>和<span class="font-medium text-text-primary">中英对照</span> Markdown。
              </p>

              <!-- Import methods -->
              <div class="text-xs font-semibold text-text-primary mb-3">三种导入方式</div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                <div class="rounded-xl border border-tinder-pink/20 bg-tinder-pink/5 p-3.5">
                  <div class="text-xs font-bold text-tinder-pink mb-1.5">PDF 上传</div>
                  <p class="text-xs text-text-secondary leading-relaxed">上传本地 PDF，平台自动提取内容并生成中文摘要（约 1.5–3 分钟）。</p>
                </div>
                <div class="rounded-xl border border-tinder-blue/20 bg-tinder-blue/5 p-3.5">
                  <div class="text-xs font-bold text-tinder-blue mb-1.5">arXiv 导入</div>
                  <p class="text-xs text-text-secondary leading-relaxed">输入 arXiv ID（如 <code class="text-[10px] bg-bg-card border border-border px-1 py-0.5 rounded">2401.00001</code>），自动抓取论文信息。</p>
                </div>
                <div class="rounded-xl border border-tinder-gold/20 bg-tinder-gold/5 p-3.5">
                  <div class="text-xs font-bold text-tinder-gold mb-1.5">手动录入</div>
                  <p class="text-xs text-text-secondary leading-relaxed">手动填写标题、作者、摘要等，适合非 arXiv 来源。</p>
                </div>
              </div>

              <!-- Processing pipeline -->
              <div class="text-xs font-semibold text-text-primary mb-3">上传后的处理流水线</div>
              <div class="rounded-xl border border-border bg-bg-elevated p-4 mb-5">
                <div class="flex items-center gap-2 flex-wrap text-xs text-text-secondary">
                  <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-card border border-border">
                    <span class="text-tinder-pink font-medium">PDF 上传</span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                  <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-card border border-border">
                    <span class="font-medium text-text-primary">MinerU 解析</span>
                    <span class="text-text-muted">（结构化 MD）</span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                  <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-bg-card border border-border">
                    <span class="font-medium text-text-primary">AI 摘要生成</span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                  <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-tinder-green/10 border border-tinder-green/30">
                    <span class="text-tinder-green font-medium">处理完成</span>
                  </div>
                </div>
                <p class="text-xs text-text-muted mt-3">整个过程约 1.5–3 分钟，可在侧边栏查看处理进度。处理完成后才可加入对比清单和进行 AI 问答。</p>
              </div>

              <!-- Translation -->
              <div class="text-xs font-semibold text-text-primary mb-3">生成中文翻译（处理完成后可用）</div>
              <div class="space-y-3 mb-5">
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-green/20 text-tinder-green font-bold flex items-center justify-center shrink-0 text-[11px]">1</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    处理完成后，在侧边栏点击论文左侧的展开箭头，会出现子链接列表（原 PDF、MinerU 解析等）。
                  </div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-green/20 text-tinder-green font-bold flex items-center justify-center shrink-0 text-[11px]">2</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    点击「<span class="text-tinder-green font-medium">生成中文翻译与对照</span>」，平台开始翻译（翻译服务由服务端配置，无需用户单独设置）。进度环会实时显示翻译进度。
                  </div>
                </div>
                <div class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-elevated">
                  <div class="w-6 h-6 rounded-full bg-tinder-green/20 text-tinder-green font-bold flex items-center justify-center shrink-0 text-[11px]">3</div>
                  <div class="text-xs text-text-secondary leading-relaxed">
                    翻译完成后，子链接列表新增「<span class="font-medium text-text-primary">中文翻译</span>」和「<span class="font-medium text-text-primary">中英对照</span>」。点击可在主区打开，支持分栏与原 PDF 并排阅读。
                  </div>
                </div>
              </div>

              <!-- Screenshot placeholder -->
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2 mb-5">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：侧边栏子链接列表 + 中文翻译与对照视图</p>
              </div>

              <!-- Lifecycle table -->
              <div class="rounded-xl border border-border-light bg-bg-elevated overflow-hidden">
                <div class="px-4 py-2.5 border-b border-border">
                  <div class="text-xs font-semibold text-text-primary">各阶段可用功能</div>
                </div>
                <div class="divide-y divide-border text-xs">
                  <div class="grid grid-cols-3 gap-2 px-4 py-2 bg-bg-elevated/60">
                    <span class="text-text-muted font-semibold">阶段</span>
                    <span class="text-text-muted font-semibold col-span-2">可用功能</span>
                  </div>
                  <div v-for="row in [
                    { stage: '处理中', features: '查看进度、重新处理', muted: true },
                    { stage: '处理完成', features: '论文详情、PDF 阅读、笔记、AI 问答、加入对比清单', muted: false },
                    { stage: 'MinerU 解析完成', features: '额外可查看原始解析 Markdown，并触发翻译', muted: false },
                    { stage: '翻译完成', features: '额外可查看中文翻译、中英对照（支持分栏阅读）', muted: false },
                  ]" :key="row.stage" class="grid grid-cols-3 gap-2 px-4 py-2.5">
                    <span class="text-text-secondary font-medium">{{ row.stage }}</span>
                    <span class="col-span-2" :class="row.muted ? 'text-text-muted' : 'text-text-secondary'">{{ row.features }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('community')">
                下一节：社区互动 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 5.2 社区互动 -->
        <section id="community" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-green">10</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">社区互动：与研究者交流</h2>
                <p class="text-xs text-text-muted mt-0.5">提问、讨论、分享，所有帖子支持 Markdown</p>
              </div>
            </div>
            <div class="p-5">
              <p class="text-sm text-text-secondary leading-relaxed mb-5">
                社区是研究者的公开交流空间。通过侧边栏底部用户菜单中的「<span class="font-medium text-text-primary">社区</span>」入口访问。
              </p>
              <div class="flex flex-wrap gap-2 mb-5">
                <span v-for="cat in ['❓ 提问','💬 讨论','📢 分享','🆘 求助']" :key="cat" class="px-2.5 py-1 bg-bg-elevated rounded-full border border-border text-xs text-text-secondary">{{ cat }}</span>
              </div>
              <div class="rounded-xl border border-border-light bg-bg-elevated p-4 mb-5">
                <div class="text-xs font-semibold text-text-primary mb-2.5">发帖步骤</div>
                <ol class="space-y-2 text-xs text-text-secondary">
                  <li class="flex items-start gap-2.5"><span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">1</span> 进入社区页面，点击「发帖」按钮。</li>
                  <li class="flex items-start gap-2.5"><span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">2</span> 选择分类，填写标题和正文（支持 Markdown）。</li>
                  <li class="flex items-start gap-2.5"><span class="w-5 h-5 rounded-full bg-bg-card border border-border font-bold flex items-center justify-center shrink-0 text-[10px] text-text-muted">3</span> 提交后可在帖子详情页查看回复。</li>
                </ol>
              </div>
              <div class="aspect-video bg-bg-elevated rounded-xl border border-dashed border-border flex flex-col items-center justify-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-text-muted/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                <p class="text-xs text-text-muted/60">截图：社区页面与发帖界面</p>
              </div>
            </div>
            <div class="px-5 py-3 border-t border-border flex justify-end">
              <button class="text-xs text-text-muted hover:text-tinder-pink transition-colors flex items-center gap-1 bg-transparent border-none cursor-pointer" @click="scrollTo('profile')">
                下一节：个人中心与订阅 <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>
        </section>

        <!-- 5.3 个人中心与订阅 -->
        <section id="profile" class="mb-8 scroll-mt-6">
          <div class="bg-bg-card rounded-2xl border border-border overflow-hidden">
            <div class="px-5 py-4 border-b border-border flex items-center gap-3">
              <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-sm font-bold text-white bg-tinder-green">11</div>
              <div>
                <h2 class="text-sm font-bold text-text-primary">个人中心与订阅</h2>
                <p class="text-xs text-text-muted mt-0.5">账号管理与订阅等级说明</p>
              </div>
            </div>
            <div class="p-5">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                <div class="rounded-xl p-4 border border-border bg-bg-elevated">
                  <div class="text-xs font-semibold text-text-primary mb-3">个人中心 (/profile)</div>
                  <ul class="space-y-1.5 text-xs text-text-secondary">
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>修改用户名 / 昵称</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>修改账号密码</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>查看订阅状态与等级</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>输入兑换码</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>查看平台公告</li>
                  </ul>
                </div>
                <div class="rounded-xl p-4 border border-border bg-bg-elevated">
                  <div class="text-xs font-semibold text-text-primary mb-3">高级设置 (/advanced-settings)</div>
                  <ul class="space-y-1.5 text-xs text-text-secondary">
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-tinder-gold shrink-0"/>模型预设（AI 功能必配）</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>提示词预设</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>各功能独立 LLM 配置</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>推荐论文过滤条件</li>
                    <li class="flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-text-muted shrink-0"/>MinerU Token（PDF 解析）</li>
                  </ul>
                </div>
              </div>

              <!-- Subscription tiers -->
              <div class="text-xs font-semibold text-text-primary mb-3">订阅等级说明</div>
              <div class="rounded-xl border border-border-light bg-bg-elevated overflow-hidden mb-5">
                <div class="divide-y divide-border text-xs">
                  <div class="grid grid-cols-3 gap-2 px-4 py-2 bg-bg-elevated/60">
                    <span class="text-text-muted font-semibold">等级</span>
                    <span class="text-text-muted font-semibold">每日推荐上限</span>
                    <span class="text-text-muted font-semibold">备注</span>
                  </div>
                  <div class="grid grid-cols-3 gap-2 px-4 py-2.5">
                    <span class="text-text-secondary font-medium">免费</span>
                    <span class="text-text-secondary">3 篇</span>
                    <span class="text-text-muted">注册即可使用全部功能</span>
                  </div>
                  <div class="grid grid-cols-3 gap-2 px-4 py-2.5">
                    <span class="font-bold" style="background: linear-gradient(135deg, #f59e0b, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro</span>
                    <span class="text-text-secondary">15 篇</span>
                    <span class="text-text-muted">灵感候选数量同样扩大</span>
                  </div>
                  <div class="grid grid-cols-3 gap-2 px-4 py-2.5">
                    <span class="font-bold" style="background: linear-gradient(135deg, #fd267a, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro+</span>
                    <span class="text-text-secondary">无限制</span>
                    <span class="text-text-muted">全量访问每日推荐</span>
                  </div>
                </div>
              </div>

              <p class="text-xs text-text-muted">通过侧边栏底部用户名 → 个人中心 → 兑换码，或联系平台获取升级方式。</p>
            </div>
          </div>
        </section>

        <!-- Footer -->
        <div class="text-center py-6 border-t border-border mt-2">
          <p class="text-sm font-medium text-text-primary mb-1.5">教程阅读完毕！</p>
          <p class="text-xs text-text-muted">
            如有问题，欢迎前往
            <router-link to="/community" class="text-tinder-pink hover:underline">社区</router-link>
            提问，或
            <button class="text-tinder-pink hover:underline bg-transparent border-none cursor-pointer text-xs p-0" @click="scrollTo('intro')">从头重新阅读</button>。
          </p>
        </div>

      </div>
    </div>
  </div>
</template>
