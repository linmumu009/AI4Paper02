<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import UserBar from '../components/UserBar.vue'

// ---------------------------------------------------------------------------
// Navigation structure — 3 chapters, 9 sections
// ---------------------------------------------------------------------------
interface Section {
  id: string
  label: string
}
interface Chapter {
  id: string
  label: string
  color: string
  sections: Section[]
}

const chapters: Chapter[] = [
  {
    id: 'ch-start',
    label: '快速入门',
    color: 'text-tinder-pink',
    sections: [
      { id: 'start',  label: '注册与每日浏览' },
      { id: 'config', label: '配置 AI 模型' },
    ],
  },
  {
    id: 'ch-deep',
    label: '深度指南',
    color: 'text-tinder-blue',
    sections: [
      { id: 'kb',        label: '知识库管理' },
      { id: 'reading',   label: '阅读与笔记' },
      { id: 'compare',   label: '论文对比分析' },
      { id: 'ai',        label: 'AI 问答 & 深度研究' },
      { id: 'workbench', label: '灵感工作台' },
    ],
  },
  {
    id: 'ch-expand',
    label: '扩展与交流',
    color: 'text-tinder-green',
    sections: [
      { id: 'mypapers',  label: '导入论文与翻译' },
      { id: 'community', label: '社区与订阅' },
    ],
  },
]

const allSectionIds = chapters.flatMap(c => c.sections.map(s => s.id))

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const showSidebar     = ref(false)
const activeSection   = ref('start')
const readingProgress = ref(0)
const contentRef      = ref<HTMLElement | null>(null)
const expandConfig    = ref(false)
const activeAiTab     = ref<'chat' | 'research'>('chat')

let observer:      IntersectionObserver | null = null
let animObserver:  IntersectionObserver | null = null
let mediaQuery:    MediaQueryList | null = null

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function scrollTo(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  if (window.innerWidth < 768) showSidebar.value = false
}

function onContentScroll() {
  const el = contentRef.value
  if (!el) return
  const total = el.scrollHeight - el.clientHeight
  readingProgress.value = total > 0 ? Math.min(100, (el.scrollTop / total) * 100) : 0
}

function initScrollSpy() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) activeSection.value = entry.target.id
      }
    },
    { root: contentRef.value, rootMargin: '-15% 0px -70% 0px', threshold: 0 },
  )
  allSectionIds.forEach(id => {
    const el = document.getElementById(id)
    if (el) observer!.observe(el)
  })
}

function initFadeObserver() {
  if (animObserver) animObserver.disconnect()
  animObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('tut-visible')
          animObserver?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.06 },
  )
  document.querySelectorAll('.tut-fade').forEach(el => animObserver!.observe(el))
}

function onMediaChange(e: MediaQueryListEvent | MediaQueryList) {
  showSidebar.value = (e as MediaQueryListEvent).matches ?? (e as MediaQueryList).matches
}

onMounted(() => {
  mediaQuery = window.matchMedia('(min-width: 768px)')
  showSidebar.value = mediaQuery.matches
  mediaQuery.addEventListener('change', onMediaChange as EventListener)
  contentRef.value?.addEventListener('scroll', onContentScroll, { passive: true })
  initScrollSpy()
  setTimeout(initFadeObserver, 120)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  animObserver?.disconnect()
  contentRef.value?.removeEventListener('scroll', onContentScroll)
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
      <!-- Reading progress bar -->
      <div class="h-0.5 bg-border w-full shrink-0 overflow-hidden">
        <div
          class="h-full bg-brand-gradient transition-all duration-200 ease-out"
          :style="{ width: `${readingProgress}%` }"
        />
      </div>

      <div class="shrink-0 px-4 py-3 border-b border-border">
        <h2 class="text-sm font-bold text-text-primary">使用教程</h2>
        <p class="text-xs text-text-muted mt-0.5">AI4Papers 完整功能指南</p>
      </div>

      <nav class="flex-1 overflow-y-auto py-2">
        <div v-for="chapter in chapters" :key="chapter.id" class="mb-1">
          <div
            class="px-3 pt-2.5 pb-1 text-[11px] font-bold tracking-widest uppercase select-none transition-colors"
            :class="activeChapterId() === chapter.id ? chapter.color : 'text-text-muted'"
          >
            {{ chapter.label }}
          </div>
          <button
            v-for="section in chapter.sections"
            :key="section.id"
            class="w-full text-left pl-5 pr-3 py-1.5 text-xs transition-colors flex items-center gap-2 bg-transparent border-none cursor-pointer rounded-none"
            :class="activeSection === section.id
              ? 'text-tinder-pink font-semibold bg-bg-hover'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'"
            @click="scrollTo(section.id)"
          >
            <span
              class="w-1 h-3 rounded-full shrink-0 transition-colors"
              :class="activeSection === section.id ? 'bg-tinder-pink' : 'bg-transparent'"
            />
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
      class="fixed top-[calc(var(--navbar-h)+1rem)] left-0 z-20 bg-bg-card border border-border border-l-0 rounded-r-lg px-1.5 py-2 text-text-muted hover:text-text-primary transition-colors md:hidden cursor-pointer"
      @click="showSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>

    <!-- ===================== Main content ===================== -->
    <div ref="contentRef" class="flex-1 h-full overflow-y-auto min-w-0">

      <!-- ============================================================ -->
      <!-- HERO                                                          -->
      <!-- ============================================================ -->
      <div class="relative overflow-hidden border-b border-border bg-bg-card">
        <!-- Ambient glow -->
        <div
          class="absolute inset-0 pointer-events-none"
          style="background: radial-gradient(ellipse 70% 60% at 15% 50%, rgba(253,38,122,0.08) 0%, transparent 70%), radial-gradient(ellipse 60% 50% at 85% 50%, rgba(14,165,233,0.07) 0%, transparent 70%);"
        />
        <div class="relative max-w-3xl mx-auto px-5 sm:px-8 py-12 sm:py-16">
          <!-- Badge -->
          <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-tinder-pink/10 border border-tinder-pink/20 mb-5">
            <span class="w-1.5 h-1.5 rounded-full bg-tinder-pink" />
            <span class="text-xs font-semibold text-tinder-pink tracking-wide">使用教程 · 完整版</span>
          </div>

          <h1 class="text-2xl sm:text-3xl font-bold text-text-primary leading-tight mb-3">
            用 AI 让每天的论文阅读<br>
            <span class="gradient-text">真正高效起来</span>
          </h1>
          <p class="text-sm sm:text-base text-text-secondary leading-relaxed mb-8 max-w-xl">
            AI4Papers 每天自动从 arXiv 筛选高质量 AI/ML 论文，配合中文摘要、知识库、论文对比与灵感生成，帮你把「浏览论文」变成真正的研究工作流。
          </p>

          <!-- Stats anchors -->
          <div class="flex flex-wrap gap-6 sm:gap-10 mb-8">
            <div v-for="stat in [
              { value: '300+', label: '每日智能筛选论文' },
              { value: '10+', label: '覆盖 arXiv 分类' },
              { value: '5 分钟', label: '完成第一次浏览' },
            ]" :key="stat.label" class="flex flex-col gap-0.5">
              <span class="text-2xl font-black gradient-text leading-none">{{ stat.value }}</span>
              <span class="text-sm text-text-muted">{{ stat.label }}</span>
            </div>
          </div>

          <!-- CTAs -->
          <div class="flex flex-wrap items-center gap-3">
            <button
              class="px-5 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity shadow-lg"
              style="box-shadow: 0 4px 20px rgba(253,38,122,0.25);"
              @click="scrollTo('start')"
            >
              5 分钟快速上手 →
            </button>
            <button
              class="px-5 py-2.5 rounded-full border border-border text-sm text-text-secondary hover:text-text-primary hover:border-border-light transition-colors cursor-pointer bg-transparent"
              @click="scrollTo('kb')"
            >
              直接看深度指南
            </button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- FEATURE OVERVIEW                                              -->
      <!-- ============================================================ -->
      <div class="border-b border-border bg-bg">
        <div class="max-w-3xl mx-auto px-5 sm:px-8 py-10">
          <div class="mb-6">
            <h2 class="text-base font-bold text-text-primary">六大核心功能</h2>
            <p class="text-sm text-text-muted mt-0.5">点击卡片跳转到对应章节</p>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <button
              v-for="feat in [
                { icon: '🗞️', name: '每日论文发现',   desc: 'AI 精选 arXiv 新论文，刷卡决定收藏或跳过', target: 'start',     accent: 'hover:border-tinder-pink/40 hover:bg-tinder-pink/5' },
                { icon: '📚', name: '知识库管理',      desc: '文件夹分类收藏，构建个人研究档案',           target: 'kb',        accent: 'hover:border-tinder-blue/40 hover:bg-tinder-blue/5' },
                { icon: '📄', name: '深度阅读 & 笔记', desc: '双屏分栏，中文摘要 + 原文 PDF 并排对照',    target: 'reading',   accent: 'hover:border-tinder-blue/40 hover:bg-tinder-blue/5' },
                { icon: '⚖️', name: '论文对比分析',    desc: 'AI 横向对比 2–8 篇文献方法与结果',         target: 'compare',   accent: 'hover:border-tinder-purple/40 hover:bg-tinder-purple/5' },
                { icon: '💡', name: 'AI 灵感生成',     desc: '从论文中提炼研究方向，生成完整提案',        target: 'workbench', accent: 'hover:border-tinder-purple/40 hover:bg-tinder-purple/5' },
                { icon: '🌐', name: '导入与翻译',      desc: '上传任意 PDF，自动生成中文全文翻译',        target: 'mypapers',  accent: 'hover:border-tinder-green/40 hover:bg-tinder-green/5' },
              ]"
              :key="feat.name"
              class="text-left p-4 rounded-xl border border-border bg-bg-elevated transition-all duration-200 cursor-pointer"
              :class="feat.accent"
              @click="scrollTo(feat.target)"
            >
              <div class="text-2xl mb-2.5 leading-none">{{ feat.icon }}</div>
              <div class="text-sm font-semibold text-text-primary mb-1">{{ feat.name }}</div>
              <div class="text-xs text-text-muted leading-relaxed">{{ feat.desc }}</div>
            </button>
          </div>
        </div>
      </div>

      <!-- ============================================================ -->
      <!-- CONTENT BODY                                                  -->
      <!-- ============================================================ -->
      <div class="max-w-3xl mx-auto px-5 sm:px-8 py-10 space-y-16">

        <!-- ============================================================ -->
        <!-- CHAPTER 1: 快速入门                                           -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div class="w-7 h-7 rounded-lg bg-brand-gradient flex items-center justify-center text-xs font-black text-white shrink-0">1</div>
            <div>
              <div class="text-xs font-bold text-tinder-pink tracking-widest uppercase">快速入门</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">三步开始你的第一次浏览</h2>
            </div>
          </div>

          <!-- Section: start -->
          <section id="start" class="tut-fade mb-10 scroll-mt-6">
            <!-- Summary callout -->
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 mb-6">
              <svg class="w-4 h-4 text-tinder-pink shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <span class="text-sm font-semibold text-tinder-pink">核心路径：注册免费账号 → 打开「发现」页 → 收藏感兴趣的论文</span>
            </div>

            <!-- 3-step timeline -->
            <div>
              <div
                v-for="(step, i) in [
                  {
                    num: '01',
                    title: '注册免费账号',
                    body: '注册完全免费，无需信用卡。免费账号已包含每日论文推荐、知识库收藏、阅读笔记等全部核心体验；AI 问答、论文对比、灵感生成等高级功能有每日或每月配额。',
                    tip: '点击右上角「登录」→「注册」，30 秒完成',
                    lineColor: 'border-tinder-pink',
                    numBg: 'bg-tinder-pink/10 border-tinder-pink text-tinder-pink',
                  },
                  {
                    num: '02',
                    title: '打开「发现」，浏览今日推荐论文',
                    body: '点击顶部导航「发现」进入每日推荐页。AI 从数百篇 arXiv 新论文中筛选高质量研究，每张卡片包含 AI 评分、结构化中文摘要和结果图摘要，帮你在 30 秒内判断是否值得精读。',
                    tip: '右滑或点击 ❤ 收藏；左滑或 ✕ 跳过；★ 展开完整分析',
                    lineColor: 'border-tinder-green',
                    numBg: 'bg-tinder-green/10 border-tinder-green text-tinder-green',
                  },
                  {
                    num: '03',
                    title: '把感兴趣的论文存入知识库',
                    body: '收藏后，论文进入左侧侧边栏「知识库」Tab。点击任意论文可进入详情页查看完整 AI 分析，或打开原文 PDF 精读，或直接开始 AI 问答。',
                    tip: '先在侧边栏点击目标文件夹，再点 ❤，论文直接进入该分类',
                    lineColor: 'border-tinder-blue',
                    numBg: 'bg-tinder-blue/10 border-tinder-blue text-tinder-blue',
                  },
                ]"
                :key="step.num"
                class="flex gap-4"
              >
                <!-- Timeline spine -->
                <div class="flex flex-col items-center shrink-0">
                  <div
                    class="w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs font-black"
                    :class="step.numBg"
                  >{{ step.num }}</div>
                  <div v-if="i < 2" class="w-px flex-1 bg-border mt-2 mb-2 min-h-[20px]" />
                </div>
                <!-- Content -->
                <div class="pb-7 flex-1 min-w-0">
                  <h3 class="text-base font-bold text-text-primary mb-2">{{ step.title }}</h3>
                  <p class="text-sm text-text-secondary leading-relaxed mb-3">{{ step.body }}</p>
                  <div class="flex items-start gap-2 px-3 py-2 rounded-lg bg-bg-elevated border border-border">
                    <svg class="w-3.5 h-3.5 text-text-muted shrink-0 mt-px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    <span class="text-xs text-text-muted leading-relaxed">{{ step.tip }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Discover page action bar reference -->
            <div class="rounded-xl border border-border bg-bg-card overflow-hidden">
              <div class="px-4 py-2.5 border-b border-border">
                <span class="text-sm font-semibold text-text-primary">发现页底部操作栏一览</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border">
                <div
                  v-for="action in [
                    { icon: '↩',  label: '撤回',   desc: '返回上一张重新决策',   cls: 'text-text-secondary' },
                    { icon: '✕',  label: '跳过',   desc: '不感兴趣，进入下一张', cls: 'text-text-muted' },
                    { icon: '❤',  label: '收藏',   desc: '加入知识库',            cls: 'text-tinder-green' },
                    { icon: '★',  label: '展开详情', desc: '右侧面板查看完整分析', cls: 'text-tinder-gold' },
                  ]"
                  :key="action.label"
                  class="px-4 py-3 flex items-center gap-2.5"
                >
                  <span class="text-lg leading-none" :class="action.cls">{{ action.icon }}</span>
                  <div>
                    <div class="text-sm font-semibold text-text-primary">{{ action.label }}</div>
                    <div class="text-xs text-text-muted mt-0.5 leading-relaxed">{{ action.desc }}</div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- Section: config -->
          <section id="config" class="tut-fade scroll-mt-6">
            <!-- Summary callout -->
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-gold/10 border border-tinder-gold/20 mb-5">
              <svg class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>
              <span class="text-sm font-semibold text-tinder-gold">AI 功能前置：提供自己的 LLM API Key，即可解锁 AI 问答、对比分析、灵感生成全部 AI 能力</span>
            </div>

            <div class="rounded-xl border border-border bg-bg-card overflow-hidden">
              <div class="px-5 py-4 border-b border-border">
                <h3 class="text-base font-bold text-text-primary">一次配置，所有 AI 功能共享</h3>
                <p class="text-sm text-text-muted mt-1 leading-relaxed">
                  平台支持 OpenAI、阿里云通义或任意 OpenAI 兼容接口。你的 API Key 存储在你自己的账号内，仅在你发起请求时调用。
                </p>
              </div>
              <div class="p-5">
                <!-- Steps -->
                <div class="space-y-3 mb-5">
                  <div
                    v-for="(step, i) in [
                      { title: '进入高级设置', body: '点击侧边栏底部用户名 → 展开菜单 → 选择「高级设置」，进入「模型预设」标签页。' },
                      { title: '新建模型预设', body: '点击「新建预设」，填写 Base URL、API Key 和 Model Name，保存。推荐新手使用 gpt-4o-mini（成本低、速度快）或阿里云的 qwen-turbo。' },
                      { title: '为各功能选择预设', body: '在高级设置的「AI 问答 / 对比分析 / 灵感涌现 / 灵感生成」各子页，在「使用模型预设」下拉框中选择刚创建的预设，保存即可。' },
                    ]"
                    :key="i"
                    class="flex items-start gap-3"
                  >
                    <div class="w-6 h-6 rounded-full bg-tinder-gold/20 text-tinder-gold font-bold flex items-center justify-center shrink-0 text-xs">{{ i + 1 }}</div>
                    <div>
                      <div class="text-sm font-semibold text-text-primary mb-0.5">{{ step.title }}</div>
                      <div class="text-sm text-text-secondary leading-relaxed">{{ step.body }}</div>
                    </div>
                  </div>
                </div>

                <!-- Expandable: field reference -->
                <button
                  class="w-full flex items-center justify-between px-3 py-2.5 rounded-lg border border-border bg-bg-elevated text-xs text-text-secondary hover:text-text-primary transition-colors cursor-pointer mb-1"
                  @click="expandConfig = !expandConfig"
                >
                  <span class="font-medium">查看填写示例（Base URL · API Key · Model）</span>
                  <svg class="w-4 h-4 transition-transform shrink-0" :class="expandConfig ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                <div v-if="expandConfig" class="rounded-lg border border-border bg-bg-elevated p-3.5 space-y-3 mb-4">
                  <div
                    v-for="row in [
                      { label: 'Base URL', value: 'https://api.openai.com/v1',   hint: '阿里云通义：https://dashscope.aliyuncs.com/compatible-mode/v1' },
                      { label: 'API Key',  value: 'sk-xxxxxxxx...',              hint: '从你的模型服务商控制台获取，妥善保管' },
                      { label: 'Model',    value: 'gpt-4o-mini',                 hint: '阿里云推荐：qwen-turbo 或 qwen-plus' },
                    ]"
                    :key="row.label"
                    class="flex items-start gap-3"
                  >
                    <span class="w-20 shrink-0 text-xs text-text-muted pt-0.5">{{ row.label }}</span>
                    <div>
                      <code class="text-xs bg-bg-card border border-border px-2 py-0.5 rounded font-mono text-text-secondary">{{ row.value }}</code>
                      <div class="text-[11px] text-text-muted mt-0.5">{{ row.hint }}</div>
                    </div>
                  </div>
                </div>

                <!-- Feature → config path table -->
                <div class="rounded-lg border border-border-light bg-bg-elevated overflow-hidden">
                  <div class="grid grid-cols-2 text-xs font-semibold text-text-muted border-b border-border">
                    <span class="px-3 py-1.5">功能</span>
                    <span class="px-3 py-1.5 border-l border-border">配置位置</span>
                  </div>
                  <div class="divide-y divide-border/50">
                    <div
                      v-for="row in [
                        ['AI 问答',       '高级设置 → AI 问答'],
                        ['论文对比',      '高级设置 → 对比分析'],
                        ['灵感涌现（灵感页）', '高级设置 → 灵感涌现'],
                        ['灵感生成（工作台）', '高级设置 → 灵感生成'],
                      ]"
                      :key="row[0]"
                      class="grid grid-cols-2"
                    >
                      <span class="px-3 py-2 text-sm text-text-secondary">{{ row[0] }}</span>
                      <span class="px-3 py-2 text-xs text-text-muted font-mono border-l border-border/50">{{ row[1] }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- CHAPTER 2: 深度指南                                           -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div
              class="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black text-white shrink-0"
              style="background: linear-gradient(135deg, #0ea5e9, #6366f1);"
            >2</div>
            <div>
              <div class="text-xs font-bold text-tinder-blue tracking-widest uppercase">深度指南</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">让每篇论文产生更大研究价值</h2>
            </div>
          </div>

          <!-- Section: kb -->
          <section id="kb" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-blue/10 border border-tinder-blue/20 mb-5">
              <svg class="w-4 h-4 text-tinder-blue shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              <span class="text-sm font-semibold text-tinder-blue">知识库：用文件夹分类管理精选文献，构建个人研究档案</span>
            </div>

            <!-- Two-column: steps + visual mockup -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-semibold text-text-primary mb-3">如何组织你的知识库</div>
                <div class="space-y-3">
                  <div
                    v-for="(item, i) in [
                      '在侧边栏「知识库」Tab 顶部点击「新建」，创建文件夹（如「LLM 方向」「RAG 方法」）',
                      '浏览发现页时先在侧边栏点击目标文件夹，再点 ❤，论文直接进入该分类',
                      '右键点击任意论文，弹出快捷菜单：新建笔记、加入对比清单、深度研究、移动文件夹',
                    ]"
                    :key="i"
                    class="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed"
                  >
                    <span class="w-5 h-5 rounded-full bg-tinder-blue/15 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">{{ i + 1 }}</span>
                    {{ item }}
                  </div>
                </div>
              </div>

              <!-- Sidebar mockup -->
              <div class="rounded-xl border border-border bg-bg-elevated p-4 flex flex-col gap-2">
                <div class="text-xs font-bold text-text-muted uppercase tracking-wider mb-1.5">侧边栏 · 知识库 Tab 示意</div>
                <div class="space-y-1 text-sm flex-1">
                  <div class="flex items-center gap-1.5 text-text-primary font-semibold">
                    <svg class="w-3.5 h-3.5 text-tinder-gold" viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    LLM 方向 <span class="text-text-muted font-normal ml-1">12 篇</span>
                  </div>
                  <div class="flex items-center gap-1.5 text-text-secondary pl-5">
                    <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
                    Attention is All You Need
                  </div>
                  <div class="flex items-center gap-1.5 text-text-secondary pl-5">
                    <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
                    GPT-4 Technical Report
                  </div>
                  <div class="flex items-center gap-1.5 text-text-primary font-semibold mt-1">
                    <svg class="w-3.5 h-3.5 text-tinder-blue" viewBox="0 0 24 24" fill="currentColor"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    RAG 方法 <span class="text-text-muted font-normal ml-1">7 篇</span>
                  </div>
                </div>
                <div class="pt-3 border-t border-border">
                  <div class="text-xs text-text-muted mb-1.5">右键菜单快捷操作</div>
                  <div class="grid grid-cols-1 gap-1">
                    <div
                      v-for="item in ['📝 新建笔记', '⚖️ 加入对比清单', '🔍 深度研究', '📁 移动到文件夹']"
                      :key="item"
                      class="text-xs text-text-secondary px-2 py-1 rounded bg-bg-card border border-border"
                    >{{ item }}</div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- Section: reading -->
          <section id="reading" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-blue/10 border border-tinder-blue/20 mb-5">
              <svg class="w-4 h-4 text-tinder-blue shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
              <span class="text-sm font-semibold text-tinder-blue">深度阅读：中文摘要 + 原文 PDF 并排，笔记 2 秒自动保存</span>
            </div>

            <!-- Three panel cards -->
            <div class="grid grid-cols-3 gap-3 mb-4">
              <div
                v-for="panel in [
                  { icon: '📄', title: '论文详情', sub: 'AI 结构化中文分析', items: ['研究背景与问题', '方法与模型架构', '实验结果与图表', 'AI 评分与关键亮点'], border: 'border-tinder-pink/25 bg-tinder-pink/5' },
                  { icon: '📕', title: '原文 PDF', sub: '内嵌阅读，无需下载', items: ['全文页面阅读', '与中文摘要并排', '拖动分割线调宽', '支持页码跳转'], border: 'border-tinder-blue/25 bg-tinder-blue/5' },
                  { icon: '📝', title: '阅读笔记', sub: '富文本，自动保存', items: ['H1–H3 标题层级', '有序 / 无序列表', '引用块 / 代码块', '2 秒自动保存'], border: 'border-tinder-green/25 bg-tinder-green/5' },
                ]"
                :key="panel.title"
                class="rounded-xl border p-3.5"
                :class="panel.border"
              >
                <div class="text-xl mb-2 leading-none">{{ panel.icon }}</div>
                <div class="text-sm font-bold text-text-primary mb-0.5">{{ panel.title }}</div>
                <div class="text-xs text-text-muted mb-2.5">{{ panel.sub }}</div>
                <ul class="space-y-1">
                  <li
                    v-for="item in panel.items"
                    :key="item"
                    class="text-xs text-text-secondary flex items-center gap-1.5"
                  >
                    <span class="w-1 h-1 rounded-full bg-text-muted/50 shrink-0" />{{ item }}
                  </li>
                </ul>
              </div>
            </div>

            <!-- How to split -->
            <div class="rounded-xl border border-border bg-bg-card p-4">
              <div class="text-sm font-semibold text-text-primary mb-3">如何开启双屏分栏阅读</div>
              <div class="flex flex-wrap items-center gap-2 text-sm">
                <span class="px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary">点击论文 → 进入详情页</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary">顶部工具栏点击「分栏」图标</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary">拖动中间分割线调整比例</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1.5 rounded-lg bg-tinder-blue/10 border border-tinder-blue/25 text-tinder-blue font-medium">右侧 Tab 切换 PDF / 笔记</span>
              </div>
            </div>
          </section>

          <!-- Section: compare -->
          <section id="compare" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-purple/10 border border-tinder-purple/20 mb-5">
              <svg class="w-4 h-4 text-tinder-purple shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
              <span class="text-sm font-semibold text-tinder-purple">论文对比：选 2–8 篇，AI 生成方法、数据集、结果的横向比较报告</span>
            </div>

            <!-- Prerequisite -->
            <div class="flex items-center gap-2.5 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5 text-sm">
              <svg class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span class="text-text-secondary flex-1"><span class="font-semibold text-tinder-gold">前置条件：</span>需先在「高级设置 → 对比分析」中配置模型预设</span>
              <button class="text-tinder-gold hover:underline cursor-pointer bg-transparent border-none whitespace-nowrap text-sm" @click="scrollTo('config')">去配置 ›</button>
            </div>

            <!-- Pipeline flow -->
            <div class="rounded-xl border border-border bg-bg-card p-5 mb-4">
              <div class="text-sm font-semibold text-text-primary mb-4">操作流程</div>
              <div class="flex items-start">
                <template
                  v-for="(step, i) in [
                    { icon: '⊞', label: '选 2–8 篇', detail: '右键论文 →\n「加入对比清单」' },
                    { icon: '▶', label: '开始对比', detail: '侧边栏底部点击\n「开始对比」' },
                    { icon: '📊', label: '查看报告', detail: 'AI 生成横向\n对比报告' },
                    { icon: '🗂', label: '保存历史', detail: '对比库 Tab\n随时可查' },
                  ]"
                  :key="step.label"
                >
                    <div class="flex-1 flex flex-col items-center text-center px-1">
                    <div class="w-10 h-10 rounded-full bg-tinder-purple/10 border border-tinder-purple/20 flex items-center justify-center text-lg mb-2">{{ step.icon }}</div>
                    <div class="text-xs font-semibold text-text-primary">{{ step.label }}</div>
                    <div class="text-[11px] text-text-muted mt-0.5 leading-relaxed whitespace-pre-line">{{ step.detail }}</div>
                  </div>
                  <div v-if="i < 3" class="flex items-center mt-5 shrink-0 w-4">
                    <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                  </div>
                </template>
              </div>
            </div>

            <div class="rounded-xl border border-tinder-purple/20 bg-tinder-purple/5 p-3.5 text-sm text-text-secondary leading-relaxed">
              <span class="font-semibold text-tinder-purple">小技巧：</span>知识库中的 arXiv 论文与「我的论文」（上传的 PDF）可混合选入对比，非常适合横向评测同一问题下的不同方法。
            </div>
          </section>

          <!-- Section: ai -->
          <section id="ai" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-blue/10 border border-tinder-blue/20 mb-5">
              <svg class="w-4 h-4 text-tinder-blue shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span class="text-sm font-semibold text-tinder-blue">AI 问答 & 深度研究：遇到任何问题，随时向 AI 提问</span>
            </div>

            <!-- Prerequisite -->
            <div class="flex items-center gap-2.5 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5 text-sm">
              <svg class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span class="text-text-secondary flex-1"><span class="font-semibold text-tinder-gold">前置条件：</span>需先在「高级设置 → AI 问答」中配置模型预设</span>
              <button class="text-tinder-gold hover:underline cursor-pointer bg-transparent border-none whitespace-nowrap text-sm" @click="scrollTo('config')">去配置 ›</button>
            </div>

            <!-- Tab switcher -->
            <div class="flex gap-2 mb-4">
              <button
                v-for="tab in [{ id: 'chat', label: '💬 AI 问答' }, { id: 'research', label: '🔍 深度研究' }]"
                :key="tab.id"
                class="px-4 py-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer border"
                :class="activeAiTab === tab.id
                  ? 'bg-tinder-blue/15 border-tinder-blue/30 text-tinder-blue'
                  : 'bg-transparent border-border text-text-muted hover:text-text-secondary'"
                @click="activeAiTab = (tab.id as 'chat' | 'research')"
              >
                {{ tab.label }}
              </button>
            </div>

            <!-- AI Chat panel -->
            <div v-if="activeAiTab === 'chat'">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div class="rounded-xl border border-tinder-blue/25 bg-tinder-blue/5 p-4">
                  <div class="text-sm font-bold text-tinder-blue mb-2">内嵌论文问答</div>
                  <p class="text-sm text-text-secondary leading-relaxed mb-3">在论文详情页顶部工具栏点击「💬 AI 问答」，在右侧面板输入问题，AI 基于当前论文全文内容作答，支持多轮追问。</p>
                  <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-card border border-border text-text-muted leading-relaxed">
                    最适合：深入理解某篇论文的技术细节、方法推导或实验设计
                  </div>
                </div>
                <div class="rounded-xl border border-tinder-pink/25 bg-tinder-pink/5 p-4">
                  <div class="text-sm font-bold text-tinder-pink mb-2">全局 AI 聊天</div>
                  <p class="text-sm text-text-secondary leading-relaxed mb-3">点击页面右下角「💬」悬浮按钮，聊天抽屉从右侧滑出，不遮挡当前页面，可随时切换论文上下文或进行通用学术问答。</p>
                  <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-card border border-border text-text-muted leading-relaxed">
                    最适合：跨论文综合提问、学术写作辅助、概念解释
                  </div>
                </div>
              </div>
            </div>

            <!-- Deep Research panel -->
            <div v-if="activeAiTab === 'research'">
              <div class="rounded-xl border border-border bg-bg-card p-4 mb-4">
                <div class="text-sm font-semibold text-text-primary mb-3">AI 问答 vs 深度研究 Q&A — 什么时候用哪个？</div>
                <div class="grid grid-cols-2 gap-3">
                  <div class="rounded-lg border border-border bg-bg-elevated p-3">
                    <div class="text-sm font-semibold text-text-primary mb-2">AI 问答</div>
                    <ul class="space-y-1.5 text-xs text-text-muted leading-relaxed">
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>针对单篇论文</li>
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>实时对话，快速提问</li>
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>适合局部理解与翻译</li>
                    </ul>
                  </div>
                  <div class="rounded-lg border border-sky-500/30 bg-sky-500/10 p-3">
                    <div class="text-sm font-semibold text-sky-400 mb-2">深度研究 Q&A</div>
                    <ul class="space-y-1.5 text-xs text-text-secondary leading-relaxed">
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>支持 1–20 篇同时</li>
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>跨文献深度检索推理</li>
                      <li class="flex items-start gap-1.5"><span class="mt-0.5">·</span>适合文献综述与多轮分析</li>
                    </ul>
                  </div>
                </div>
              </div>
              <div class="space-y-2.5">
                <div
                  v-for="(step, i) in [
                    '在侧边栏右键论文 → 选「🔍 深度研究」，对单篇发起研究；或点击工具栏「批量」按钮，勾选 1–20 篇后点击「深度研究」',
                    '主区打开「深度研究 Q&A」面板，在输入框提问，AI 对所选论文全文进行深度检索与推理，支持多轮追问和历史记录查阅',
                  ]"
                  :key="i"
                  class="flex items-start gap-2.5 p-3.5 rounded-xl border border-border bg-bg-elevated text-sm text-text-secondary leading-relaxed"
                >
                  <span class="w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">{{ i + 1 }}</span>
                  {{ step }}
                </div>
              </div>
            </div>
          </section>

          <!-- Section: workbench -->
          <section id="workbench" class="tut-fade scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-purple/10 border border-tinder-purple/20 mb-5">
              <svg class="w-4 h-4 text-tinder-purple shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
              <span class="text-sm font-semibold text-tinder-purple">灵感工作台：从论文日报到完整研究方向提案，一站完成</span>
            </div>

            <!-- Prerequisite -->
            <div class="flex items-center gap-2.5 p-3 rounded-xl border border-tinder-gold/30 bg-tinder-gold/5 mb-5 text-sm">
              <svg class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span class="text-text-secondary flex-1"><span class="font-semibold text-tinder-gold">前置条件：</span>在高级设置 → 灵感涌现 / 灵感生成 中配置模型预设</span>
              <button class="text-tinder-gold hover:underline cursor-pointer bg-transparent border-none whitespace-nowrap text-sm" @click="scrollTo('config')">去配置 ›</button>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="flex items-center gap-2 mb-2.5">
                  <div class="w-7 h-7 rounded-lg bg-bg-elevated border border-border flex items-center justify-center text-sm">🗞️</div>
                  <span class="text-sm font-bold text-text-primary">灵感页（每日刷卡）</span>
                </div>
                <ul class="space-y-2 text-sm text-text-secondary leading-relaxed">
                  <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span>AI 每天从精选论文中提炼研究灵感候选，刷卡挑选感兴趣的方向</li>
                  <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span>切换到「论文灵感」Tab，选中知识库中某篇论文，AI 单独为它生成灵感候选列表</li>
                </ul>
              </div>
              <div class="rounded-xl border border-tinder-purple/25 bg-tinder-purple/5 p-4">
                <div class="flex items-center gap-2 mb-2.5">
                  <div class="w-7 h-7 rounded-lg bg-tinder-purple/20 border border-tinder-purple/20 flex items-center justify-center text-sm">🔬</div>
                  <span class="text-sm font-bold text-tinder-purple">灵感工作台（深度生成）</span>
                </div>
                <ul class="space-y-2 text-sm text-text-secondary leading-relaxed">
                  <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span><span><span class="font-medium text-text-primary">工作台：</span>选多篇论文，AI 组合生成包含问题定义、方法路线的完整研究方向提案</span></li>
                  <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span><span><span class="font-medium text-text-primary">原子库：</span>管理从论文提炼的研究原子（方法、问题、数据集），是灵感生成的原材料</span></li>
                  <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span><span><span class="font-medium text-text-primary">范例库：</span>收藏研究范例，作为灵感生成的质量参考标准</span></li>
                </ul>
              </div>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- CHAPTER 3: 扩展与交流                                         -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div class="w-7 h-7 rounded-lg bg-tinder-green flex items-center justify-center text-xs font-black text-white shrink-0">3</div>
            <div>
              <div class="text-xs font-bold text-tinder-green tracking-widest uppercase">扩展与交流</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">把平台外的论文带进来，与研究者交流</h2>
            </div>
          </div>

          <!-- Section: mypapers -->
          <section id="mypapers" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-green/10 border border-tinder-green/20 mb-5">
              <svg class="w-4 h-4 text-tinder-green shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              <span class="text-sm font-semibold text-tinder-green">我的论文：上传任意 PDF，享受 AI 摘要、笔记、对比与中文全文翻译</span>
            </div>

            <!-- Three import methods -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              <div
                v-for="method in [
                  { title: 'PDF 上传',  desc: '上传本地 PDF，约 1.5–3 分钟后自动生成中文摘要',    cls: 'border-tinder-pink/25 bg-tinder-pink/5',   title_cls: 'text-tinder-pink' },
                  { title: 'arXiv 导入', desc: '输入 arXiv ID（如 2401.00001），自动抓取论文信息', cls: 'border-tinder-blue/25 bg-tinder-blue/5',   title_cls: 'text-tinder-blue' },
                  { title: '手动录入',  desc: '手动填写标题、作者、摘要等，适合非 arXiv 来源',   cls: 'border-tinder-gold/25 bg-tinder-gold/5',  title_cls: 'text-tinder-gold' },
                ]"
                :key="method.title"
                class="rounded-xl border p-3.5"
                :class="method.cls"
              >
                <div class="text-sm font-bold mb-1.5" :class="method.title_cls">{{ method.title }}</div>
                <p class="text-sm text-text-secondary leading-relaxed">{{ method.desc }}</p>
              </div>
            </div>

            <!-- Processing pipeline -->
            <div class="rounded-xl border border-border bg-bg-card p-4 mb-4">
              <div class="text-sm font-semibold text-text-primary mb-3">上传后的自动处理流水线</div>
              <div class="flex flex-wrap items-center gap-1.5 text-sm mb-2.5">
                <span class="px-2.5 py-1 rounded-lg bg-tinder-pink/10 border border-tinder-pink/20 text-tinder-pink font-medium">PDF 上传</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1 rounded-lg bg-bg-elevated border border-border text-text-secondary">MinerU 结构化解析</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1 rounded-lg bg-bg-elevated border border-border text-text-secondary">AI 摘要生成</span>
                <svg class="w-3 h-3 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                <span class="px-2.5 py-1 rounded-lg bg-tinder-green/10 border border-tinder-green/20 text-tinder-green font-medium">处理完成</span>
              </div>
              <p class="text-xs text-text-muted leading-relaxed">全程约 1.5–3 分钟，可在侧边栏实时查看进度状态。处理完成后即可加入对比清单、进行 AI 问答。</p>
            </div>

            <!-- Translation flow -->
            <div class="rounded-xl border border-tinder-green/25 bg-tinder-green/5 p-4">
              <div class="text-sm font-bold text-tinder-green mb-3">生成中文全文翻译（处理完成后可用）</div>
              <div class="space-y-2.5">
                <div
                  v-for="(step, i) in [
                    '处理完成后，点击侧边栏论文左侧的展开箭头，出现子链接列表（原 PDF、MinerU 解析等）',
                    '点击「生成中文翻译与对照」，翻译由服务端处理，无需你单独配置，进度环实时显示翻译进度',
                    '翻译完成后，子链接新增「中文翻译」和「中英对照」，支持分栏与原 PDF 并排阅读对照',
                  ]"
                  :key="i"
                  class="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed"
                >
                  <span class="w-5 h-5 rounded-full bg-tinder-green/20 text-tinder-green font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">{{ i + 1 }}</span>
                  {{ step }}
                </div>
              </div>
            </div>
          </section>

          <!-- Section: community (+ subscription) -->
          <section id="community" class="tut-fade scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-green/10 border border-tinder-green/20 mb-5">
              <svg class="w-4 h-4 text-tinder-green shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              <span class="text-sm font-semibold text-tinder-green">社区与个人中心：与研究者交流，管理账号与订阅权益</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2.5">社区互动</div>
                <p class="text-sm text-text-secondary leading-relaxed mb-3">通过侧边栏底部用户名菜单中的「社区」入口访问。帖子和回复均支持 Markdown，4 种分类覆盖不同交流场景。</p>
                <div class="flex flex-wrap gap-1.5">
                  <span
                    v-for="cat in ['❓ 提问', '💬 讨论', '📢 分享', '🆘 求助']"
                    :key="cat"
                    class="px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-xs text-text-secondary"
                  >{{ cat }}</span>
                </div>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2.5">个人中心 & 高级设置</div>
                <div class="space-y-2 text-sm text-text-secondary leading-relaxed">
                  <div class="flex items-start gap-2">
                    <span class="w-1.5 h-1.5 rounded-full bg-text-muted mt-1.5 shrink-0" />
                    <span><span class="font-medium text-text-primary">个人中心：</span>修改用户名、密码，查看订阅状态，输入兑换码，查看平台公告</span>
                  </div>
                  <div class="flex items-start gap-2">
                    <span class="w-1.5 h-1.5 rounded-full bg-tinder-gold mt-1.5 shrink-0" />
                    <span><span class="font-medium text-text-primary">高级设置：</span>模型预设（AI 功能必配）、提示词预设、各功能独立参数、推荐过滤条件</span>
                  </div>
                  <div class="flex items-start gap-2">
                    <span class="w-1.5 h-1.5 rounded-full bg-text-muted mt-1.5 shrink-0" />
                    <span>两处均从侧边栏底部用户名菜单进入</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Subscription table -->
            <div class="rounded-xl border border-border-light bg-bg-card overflow-hidden">
              <div class="px-4 py-3 border-b border-border flex items-center justify-between">
                <span class="text-sm font-bold text-text-primary">订阅等级对比</span>
                <span class="text-xs text-tinder-green font-medium">免费账号已覆盖全部核心功能</span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-xs min-w-[400px]">
                  <thead>
                    <tr class="border-b border-border bg-bg-elevated/50">
                      <th class="text-left px-4 py-2.5 text-text-muted font-semibold">功能</th>
                      <th class="text-center px-3 py-2.5 text-text-muted font-semibold">免费</th>
                      <th class="text-center px-3 py-2.5">
                        <span class="font-bold" style="background: linear-gradient(135deg, #f59e0b, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro</span>
                      </th>
                      <th class="text-center px-3 py-2.5">
                        <span class="font-bold" style="background: linear-gradient(135deg, #fd267a, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro+</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-border/50">
                    <tr
                      v-for="row in [
                        { feat: '每日推荐论文',   free: '3 篇',       pro: '9 篇',        proplus: '不限',         hl: false },
                        { feat: 'AI 问答',        free: '10 条/天',   pro: '无限',        proplus: '无限',         hl: true  },
                        { feat: '对比分析',       free: '3次·2篇/月', pro: '30次·5篇/月', proplus: '100次·8篇/月', hl: false },
                        { feat: '深度研究',       free: '2 次/月',    pro: '15 次/月',    proplus: '50 次/月',     hl: false },
                        { feat: '灵感生成',       free: '3 次/月',    pro: '30 次/月',    proplus: '100 次/月',    hl: false },
                        { feat: '全文翻译',       free: '2 次/月',    pro: '15 次/月',    proplus: '28 次/月',     hl: false },
                        { feat: 'DOCX/PDF 导出',  free: '2 次/月',    pro: '15 次/月',    proplus: '28 次/月',     hl: false },
                        { feat: '知识库上限',     free: '20 篇',      pro: '100 篇',      proplus: '500 篇',       hl: false },
                        { feat: '论文上传',       free: '2 篇/月',    pro: '30 篇/月',    proplus: '100 篇/月',    hl: false },
                      ]"
                      :key="row.feat"
                      class="hover:bg-bg-elevated/30 transition-colors"
                    >
                      <td class="px-4 py-2.5 text-text-secondary">{{ row.feat }}</td>
                      <td class="px-3 py-2.5 text-center text-text-muted">{{ row.free }}</td>
                      <td class="px-3 py-2.5 text-center text-text-secondary">{{ row.pro }}</td>
                      <td class="px-3 py-2.5 text-center font-medium text-tinder-green">{{ row.proplus }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="px-4 py-3 border-t border-border bg-bg-elevated/40 text-xs text-text-muted leading-relaxed">
                通过侧边栏底部用户名 → 个人中心 → 订阅，输入兑换码或查看订阅方式
              </div>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- FOOTER                                                        -->
        <!-- ============================================================ -->
        <div class="text-center py-8 border-t border-border">
          <div class="text-3xl mb-4">🎉</div>
          <h3 class="text-base font-bold text-text-primary mb-2">教程阅读完毕！</h3>
          <p class="text-sm text-text-secondary mb-7 max-w-sm mx-auto leading-relaxed">
            现在你已经了解了 AI4Papers 的全部功能。
            开始用它让你的研究工作流真正高效起来吧。
          </p>
          <div class="flex flex-wrap items-center justify-center gap-3">
            <router-link
              to="/"
              class="px-5 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold hover:opacity-90 transition-opacity no-underline"
              style="box-shadow: 0 4px 20px rgba(253,38,122,0.2);"
            >
              开始浏览今日推荐 →
            </router-link>
            <router-link
              to="/community"
              class="px-5 py-2.5 rounded-full border border-border text-sm text-text-secondary hover:text-text-primary hover:border-border-light transition-colors no-underline"
            >
              去社区提问
            </router-link>
            <button
              class="px-5 py-2.5 rounded-full border border-border text-sm text-text-muted hover:text-text-secondary transition-colors cursor-pointer bg-transparent"
              @click="scrollTo('start')"
            >
              从头再读一遍
            </button>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style>
.tut-fade {
  opacity: 0;
  transform: translateY(18px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.tut-fade.tut-visible {
  opacity: 1;
  transform: translateY(0);
}
</style>
