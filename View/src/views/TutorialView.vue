<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import UserBar from '../components/UserBar.vue'

// ---------------------------------------------------------------------------
// Navigation structure — 5 main lines + cross tools + start
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
    id: 'ch-main',
    label: '五大主线工作流',
    color: 'text-tinder-pink',
    sections: [
      { id: 'recommend-to-kb',     label: '论文推荐 ➔ 知识库' },
      { id: 'idea-to-workbench',   label: '灵感卡片 ➔ 灵感工作台' },
      { id: 'compare-to-library',  label: '对比分析 ➔ 对比库' },
      { id: 'research-to-library', label: '深度研究 ➔ 研究库' },
      { id: 'mypapers',            label: '外部论文 ➔ 我的论文库' },
    ],
  },
  {
    id: 'ch-enhance',
    label: '贯穿全流程的增强能力',
    color: 'text-tinder-blue',
    sections: [
      { id: 'notes',     label: '阅读笔记' },
      { id: 'ai-chat',   label: 'AI 问答' },
      { id: 'translate', label: '翻译与中英对照' },
      { id: 'config',    label: '模型配置 (AI 前置)' },
    ],
  },
  {
    id: 'ch-start',
    label: '新手必读',
    color: 'text-tinder-green',
    sections: [
      { id: 'start', label: '5 分钟快速上手' },
    ],
  },
]

const allSectionIds = chapters.flatMap(c => c.sections.map(s => s.id))

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const showSidebar     = ref(false)
const activeSection   = ref('recommend-to-kb')
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
    <button v-if="showSidebar" type="button" class="fixed inset-0 bg-black/50 z-20 md:hidden" aria-label="关闭教程导航" @click="showSidebar = false" />

    <!-- ===================== Sidebar ===================== -->
    <aside
      id="tutorial-navigation"
      class="w-[80vw] max-w-[340px] md:w-[var(--sidebar-w)] shrink-0 bg-bg-sidebar border-r border-border flex flex-col z-30 transition-transform duration-200 md:relative md:translate-x-0"
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
            class="px-3 pt-2.5 pb-1 text-[10.5px] font-semibold tracking-widest uppercase select-none transition-colors"
            :class="activeChapterId() === chapter.id ? chapter.color : 'text-text-muted'"
          >
            {{ chapter.label }}
          </div>
          <button
            v-for="section in chapter.sections"
            :key="section.id"
            class="w-full text-left px-3 py-2.5 text-[15px] transition-colors flex items-center gap-2.5 bg-transparent border-none cursor-pointer rounded-lg"
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
      type="button"
      aria-label="打开教程导航"
      aria-controls="tutorial-navigation"
      :aria-expanded="showSidebar"
      class="fixed top-[calc(var(--navbar-h)+1rem)] left-0 z-20 bg-bg-card border border-border border-l-0 rounded-r-lg px-1.5 py-2 text-text-muted hover:text-text-primary transition-colors md:hidden cursor-pointer"
      @click="showSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>

    <!-- ===================== Main content ===================== -->
    <div ref="contentRef" class="flex-1 h-full overflow-y-auto min-w-0">

      <!-- ============================================================ -->
      <!-- HERO                                                          -->
      <!-- ============================================================ -->
      <div class="relative overflow-hidden border-b border-border bg-bg-card">
        <div
          class="absolute inset-0 pointer-events-none"
          style="background: radial-gradient(ellipse 70% 60% at 15% 50%, rgba(253,38,122,0.08) 0%, transparent 70%), radial-gradient(ellipse 60% 50% at 85% 50%, rgba(14,165,233,0.07) 0%, transparent 70%);"
        />
        <div class="relative max-w-3xl mx-auto px-5 sm:px-8 py-12 sm:py-16">
          <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-tinder-pink/10 border border-tinder-pink/20 mb-5">
            <span class="w-1.5 h-1.5 rounded-full bg-tinder-pink" />
            <span class="text-xs font-semibold text-tinder-pink tracking-wide">使用教程 · 完整版</span>
          </div>

          <h1 class="text-2xl sm:text-3xl font-bold text-text-primary leading-tight mb-3">
            AI4Papers 不是单点工具，<br>
            <span class="gradient-text">而是一套从发现论文到沉淀研究资产的工作流</span>
          </h1>
          <p class="text-sm sm:text-base text-text-secondary leading-relaxed mb-8 max-w-xl">
            在这里，你的所有动作都会产生长期复利：发现的好论文进入知识库，知识库的论文提炼出研究灵感，多篇文献沉淀为对比报告，最终生成你的专属研究体系。
          </p>

          <div class="flex flex-wrap items-center gap-3">
            <button
              class="px-5 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity shadow-lg"
              style="box-shadow: 0 4px 20px rgba(253,38,122,0.25);"
              @click="scrollTo('recommend-to-kb')"
            >
              了解五大工作流 →
            </button>
            <button
              class="px-5 py-2.5 rounded-full border border-border text-sm text-text-secondary hover:text-text-primary hover:border-border-light transition-colors cursor-pointer bg-transparent"
              @click="scrollTo('start')"
            >
              跳过，直接看 5 分钟上手
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
            <h2 class="text-base font-bold text-text-primary">五大主线工作流</h2>
            <p class="text-sm text-text-muted mt-0.5">点击卡片跳转到对应章节</p>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <button
              v-for="feat in [
                { icon: '🗞️', name: '论文推荐 ➔ 知识库',     desc: '发现值得读的论文，并沉淀到自己的收藏体系', target: 'recommend-to-kb',     accent: 'hover:border-tinder-pink/40 hover:bg-tinder-pink/5' },
                { icon: '💡', name: '灵感卡片 ➔ 灵感工作台',   desc: '把论文启发变成可筛选、可生成的研究方向', target: 'idea-to-workbench',   accent: 'hover:border-tinder-purple/40 hover:bg-tinder-purple/5' },
                { icon: '⚖️', name: '对比分析 ➔ 对比库',      desc: '把多篇论文的差异沉淀为可复用的结构化报告', target: 'compare-to-library',  accent: 'hover:border-tinder-blue/40 hover:bg-tinder-blue/5' },
                { icon: '🔍', name: '深度研究 ➔ 研究库',      desc: '围绕具体问题做跨论文深度问答与研究记录保存', target: 'research-to-library', accent: 'hover:border-sky-500/40 hover:bg-sky-500/5' },
                { icon: '🌐', name: '外部论文 ➔ 我的论文库',   desc: '把站外的本地文献导入进来，接入整个 AI 工作流', target: 'mypapers',            accent: 'hover:border-tinder-green/40 hover:bg-tinder-green/5' },
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
        <!-- CHAPTER 1: 五大主线工作流                                       -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div class="w-7 h-7 rounded-lg bg-brand-gradient flex items-center justify-center text-xs font-black text-white shrink-0">1</div>
            <div>
              <div class="text-xs font-bold text-tinder-pink tracking-widest uppercase">五大主线工作流</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">把论文变成你的研究资产</h2>
            </div>
          </div>

          <!-- Line 1: Recommend to KB -->
          <section id="recommend-to-kb" class="tut-fade mb-12 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 mb-5">
              <span class="text-xl shrink-0 leading-none">🗞️</span>
              <span class="text-sm font-semibold text-tinder-pink">1. 论文推荐 ➔ 知识库：发现值得读的论文，并沉淀到自己的收藏体系</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">如何进入</div>
                <p class="text-sm text-text-secondary leading-relaxed">顶部导航点击 <span class="font-medium text-text-primary">「发现」</span> 浏览每日最新推荐。</p>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">产出结果</div>
                <p class="text-sm text-text-secondary leading-relaxed">在左侧侧边栏的 <span class="font-medium text-text-primary">「知识库」</span> 中，沉淀出按文件夹分类整理的个人文献档案。</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
              <div class="space-y-3">
                <div class="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed">
                  <span class="w-5 h-5 rounded-full bg-tinder-pink/15 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">1</span>
                  浏览每日论文卡片，查看 AI 评分与摘要
                </div>
                <div class="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed">
                  <span class="w-5 h-5 rounded-full bg-tinder-pink/15 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">2</span>
                  点击卡片底部 ❤ 按钮（或右滑卡片），论文将自动加入侧边栏的知识库
                </div>
                <div class="flex items-start gap-2.5 text-sm text-text-secondary leading-relaxed">
                  <span class="w-5 h-5 rounded-full bg-tinder-pink/15 text-tinder-pink font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">3</span>
                  在知识库中创建自定义文件夹（如「RAG 方法」），分类管理收藏的文献
                </div>
              </div>
            </div>
          </section>

          <!-- Line 2: Idea to Workbench -->
          <section id="idea-to-workbench" class="tut-fade mb-12 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-purple/10 border border-tinder-purple/20 mb-5">
              <span class="text-xl shrink-0 leading-none">💡</span>
              <span class="text-sm font-semibold text-tinder-purple">2. 灵感卡片 ➔ 灵感工作台：把论文启发变成可筛选、可生成的研究方向</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">如何进入</div>
                <p class="text-sm text-text-secondary leading-relaxed">顶部导航点击 <span class="font-medium text-text-primary">「灵感库」</span>。</p>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">产出结果</div>
                <p class="text-sm text-text-secondary leading-relaxed">提取研究原子，生成包含创新方法和痛点定义的研究方案提案。</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
              <ul class="space-y-2 text-sm text-text-secondary leading-relaxed">
                <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span> <span class="font-medium text-text-primary">每日刷卡：</span>在灵感页，AI 每天为你推荐可能的研究方向，感兴趣就保存</li>
                <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span> <span class="font-medium text-text-primary">从指定论文生成：</span>侧边栏切换到「论文灵感」，选中某篇知识库论文，直接提炼它的衍生研究灵感</li>
                <li class="flex items-start gap-1.5"><span class="text-tinder-purple mt-0.5">›</span> <span class="font-medium text-text-primary">灵感工作台：</span>进入灵感工作台深度组合多篇论文的原子（方法、问题、数据集），产出完整研究提案</li>
              </ul>
            </div>
          </section>

          <!-- Line 3: Compare to Library -->
          <section id="compare-to-library" class="tut-fade mb-12 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-blue/10 border border-tinder-blue/20 mb-5">
              <span class="text-xl shrink-0 leading-none">⚖️</span>
              <span class="text-sm font-semibold text-tinder-blue">3. 对比分析 ➔ 对比库：把多篇论文的差异沉淀为可复用的结构化报告</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">如何进入</div>
                <p class="text-sm text-text-secondary leading-relaxed">侧边栏右键知识库或我的论文 ➔ <span class="font-medium text-text-primary">「加入对比清单」</span> ➔ 底部点击 <span class="font-medium text-text-primary">「开始对比」</span>。</p>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">产出结果</div>
                <p class="text-sm text-text-secondary leading-relaxed">在侧边栏的 <span class="font-medium text-text-primary">「对比库」</span> 中查阅和保存横向对比报告。</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
               <div class="text-sm text-text-secondary leading-relaxed mb-3">
                 AI 将对你选中的 2–8 篇论文进行方法、数据集、结果的深度横向比较。你可以混选知识库（arXiv）和我的论文库（PDF）的文献。
               </div>
               <div class="flex flex-wrap items-center gap-2 text-sm text-text-muted">
                  <span class="px-2 py-1 rounded bg-bg-card border border-border">多模型比较</span>
                  <span class="px-2 py-1 rounded bg-bg-card border border-border">优缺点分析</span>
                  <span class="px-2 py-1 rounded bg-bg-card border border-border">自动提取对比表格</span>
               </div>
            </div>
          </section>

          <!-- Line 4: Research to Library -->
          <section id="research-to-library" class="tut-fade mb-12 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-sky-500/10 border border-sky-500/20 mb-5">
              <span class="text-xl shrink-0 leading-none">🔍</span>
              <span class="text-sm font-semibold text-sky-500">4. 深度研究 ➔ 研究库：围绕具体问题做跨论文深度问答与研究记录保存</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">如何进入</div>
                <p class="text-sm text-text-secondary leading-relaxed">侧边栏勾选 1–20 篇文献，点击底部 <span class="font-medium text-text-primary">「深度研究」</span>，或直接在详情页发起。</p>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">产出结果</div>
                <p class="text-sm text-text-secondary leading-relaxed">多轮深度的 Q&A 会话记录，保存在侧边栏的 <span class="font-medium text-text-primary">「深度研究」</span>（研究库）Tab 中。</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-border bg-bg-elevated p-4 text-sm text-text-secondary leading-relaxed">
              不同于单篇论文的轻量问答，深度研究支持针对数十篇论文组成的文献集合，抛出一个宏大问题（如“这几篇论文处理幻觉问题的方式有何演进？”），AI 会深度检索引文内容并进行推理，生成带有引用来源的长篇解答，且支持连续追问。
            </div>
          </section>

          <!-- Line 5: My Papers -->
          <section id="mypapers" class="tut-fade mb-10 scroll-mt-6">
            <div class="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-tinder-green/10 border border-tinder-green/20 mb-5">
              <span class="text-xl shrink-0 leading-none">🌐</span>
              <span class="text-sm font-semibold text-tinder-green">5. 外部论文 ➔ 我的论文库：把站外的本地文献导入进来，接入整个 AI 工作流</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">如何进入</div>
                <p class="text-sm text-text-secondary leading-relaxed">顶部导航点击 <span class="font-medium text-text-primary">「我的论文」</span>。</p>
              </div>
              <div class="rounded-xl border border-border bg-bg-card p-4">
                <div class="text-sm font-bold text-text-primary mb-2">产出结果</div>
                <p class="text-sm text-text-secondary leading-relaxed">本地 PDF 经过解析，拥有了和系统自带 arXiv 论文一样的摘要、可翻译、可对比、可问答能力。</p>
              </div>
            </div>

            <div class="mt-4 rounded-xl border border-border bg-bg-elevated p-4">
               <p class="text-sm text-text-secondary leading-relaxed mb-2">支持的导入方式：</p>
               <ul class="space-y-1.5 text-sm text-text-secondary">
                 <li><span class="font-medium text-text-primary">PDF 上传：</span>上传本地 PDF，系统使用 MinerU 解析，1.5-3 分钟后生成摘要</li>
                 <li><span class="font-medium text-text-primary">arXiv ID 导入：</span>一键抓取任意未被推荐抓取的 arXiv 论文</li>
                 <li><span class="font-medium text-text-primary">手动录入：</span>为实体书籍或不公开文献创建元数据记录</li>
               </ul>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- CHAPTER 2: 贯穿全流程的增强能力                                 -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div class="w-7 h-7 rounded-lg bg-tinder-blue flex items-center justify-center text-xs font-black text-white shrink-0">2</div>
            <div>
              <div class="text-xs font-bold text-tinder-blue tracking-widest uppercase">贯穿全流程的增强能力</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">在任何主线节点随时调用</h2>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Notes -->
            <section id="notes" class="tut-fade scroll-mt-6 rounded-xl border border-border bg-bg-card p-4">
              <div class="flex items-center gap-2 mb-2.5">
                <span class="text-lg leading-none">📝</span>
                <span class="text-sm font-bold text-text-primary">阅读笔记</span>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-3">
                在阅读论文详情或 PDF 时，右侧边栏切换到「笔记」Tab。支持富文本（Markdown）编辑，2秒自动保存。
              </p>
              <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-muted">
                在哪出现：知识库、我的论文库、论文阅读页
              </div>
            </section>

            <!-- AI Chat -->
            <section id="ai-chat" class="tut-fade scroll-mt-6 rounded-xl border border-border bg-bg-card p-4">
              <div class="flex items-center gap-2 mb-2.5">
                <span class="text-lg leading-none">💬</span>
                <span class="text-sm font-bold text-text-primary">AI 问答</span>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-3">
                针对单篇论文的实时问答面板（顶部工具栏开启），或点击右下角悬浮按钮打开全局问答抽屉，随时向 AI 请教。
              </p>
              <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-muted">
                在哪出现：全站右下角、论文阅读页工具栏
              </div>
            </section>

            <!-- Translate -->
            <section id="translate" class="tut-fade scroll-mt-6 rounded-xl border border-border bg-bg-card p-4">
              <div class="flex items-center gap-2 mb-2.5">
                <span class="text-lg leading-none">🌐</span>
                <span class="text-sm font-bold text-text-primary">翻译与中英对照</span>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-3">
                在侧边栏论文子链接中点击「生成中文翻译」。完成后可在阅读页开启双屏分栏，左侧英文原文 PDF，右侧中文翻译对照。
              </p>
              <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-muted">
                在哪出现：知识库和我的论文的 PDF 阅读模式中
              </div>
            </section>

            <!-- Config -->
            <section id="config" class="tut-fade scroll-mt-6 rounded-xl border border-border bg-bg-card p-4">
              <div class="flex items-center gap-2 mb-2.5">
                <span class="text-lg leading-none">⚙️</span>
                <span class="text-sm font-bold text-text-primary">模型配置 (AI 前置)</span>
              </div>
              <p class="text-sm text-text-secondary leading-relaxed mb-4">
                AI4Papers 的所有高级 AI 功能（深度研究、对比分析等）均支持并推荐使用自带 API Key。
              </p>

              <div class="space-y-4 mb-4">
                <div>
                  <div class="text-sm font-bold text-text-primary mb-2">为什么需要自带 Key？</div>
                  <ul class="space-y-2 text-sm text-text-secondary leading-relaxed">
                    <li class="flex items-start gap-1.5"><span class="text-tinder-blue mt-0.5">⚡️</span> <div><span class="font-medium text-text-primary">打破额度限制：</span>高级功能对 Token 消耗极大，自带 Key 可彻底解除系统基础额度束缚。</div></li>
                    <li class="flex items-start gap-1.5"><span class="text-tinder-blue mt-0.5">🧠</span> <div><span class="font-medium text-text-primary">自由选择模型：</span>兼容 OpenAI 格式，随时切换 gpt-4o、qwen-max 或 deepseek-chat 等最适合当前任务的“大脑”。</div></li>
                    <li class="flex items-start gap-1.5"><span class="text-tinder-blue mt-0.5">💰</span> <div><span class="font-medium text-text-primary">成本完全透明：</span>直连大模型服务商，不赚差价，用多少花多少。</div></li>
                  </ul>
                </div>

                <div class="rounded-xl border border-border bg-bg-elevated p-3">
                  <div class="text-sm font-bold text-text-primary mb-2">具体配置步骤：</div>
                  <div class="space-y-3">
                    <div class="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                      <span class="w-5 h-5 rounded-full bg-tinder-blue/15 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">1</span>
                      <div><span class="font-medium text-text-primary">新建预设：</span>点击左下角用户名 ➔ <span class="font-medium text-text-primary">「高级设置」</span> ➔ <span class="font-medium text-text-primary">「模型预设」</span>，点击新建。</div>
                    </div>
                    <div class="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                      <span class="w-5 h-5 rounded-full bg-tinder-blue/15 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">2</span>
                      <div><span class="font-medium text-text-primary">填写参数：</span>填入模型名称（如 <code>qwen-max</code>）、API URL（如阿里云的 <code>https://dashscope.aliyuncs.com/compatible-mode/v1</code>）以及 API Key（<code>sk-...</code>）。</div>
                    </div>
                    <div class="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                      <span class="w-5 h-5 rounded-full bg-tinder-blue/15 text-tinder-blue font-bold flex items-center justify-center shrink-0 text-xs mt-0.5">3</span>
                      <div><span class="font-medium text-text-primary">绑定功能：</span>回到高级设置或个人中心，在对比分析、深度研究等功能的设置中，把默认模型切换为你刚建好的预设。</div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="text-xs px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-muted inline-block">
                在哪出现：用户名下拉菜单 ➔ 高级设置
              </div>
            </section>
          </div>
        </div>

        <!-- ============================================================ -->
        <!-- CHAPTER 3: 新手必读                                           -->
        <!-- ============================================================ -->
        <div>
          <div class="flex items-center gap-3 mb-7">
            <div class="w-7 h-7 rounded-lg bg-tinder-green flex items-center justify-center text-xs font-black text-white shrink-0">3</div>
            <div>
              <div class="text-xs font-bold text-tinder-green tracking-widest uppercase">新手必读</div>
              <h2 class="text-lg font-bold text-text-primary leading-tight">5 分钟快速开始</h2>
            </div>
          </div>

          <section id="start" class="tut-fade scroll-mt-6">
            <div class="rounded-xl border border-border bg-bg-card p-6">
               <div class="text-base font-bold text-text-primary mb-4">第一天，你只需要做三件事：</div>
               <div class="space-y-6">
                 <div class="flex items-start gap-4">
                   <div class="w-8 h-8 rounded-full bg-tinder-pink/10 border border-tinder-pink flex items-center justify-center text-tinder-pink font-bold shrink-0">1</div>
                   <div>
                     <div class="text-sm font-bold text-text-primary mb-1">注册账号</div>
                     <div class="text-sm text-text-secondary leading-relaxed">系统已经为你准备好了完全免费的基础额度，足以体验论文推荐、收藏和摘要等核心功能。</div>
                   </div>
                 </div>
                 <div class="flex items-start gap-4">
                   <div class="w-8 h-8 rounded-full bg-tinder-blue/10 border border-tinder-blue flex items-center justify-center text-tinder-blue font-bold shrink-0">2</div>
                   <div>
                     <div class="text-sm font-bold text-text-primary mb-1">刷一次今日推荐</div>
                     <div class="text-sm text-text-secondary leading-relaxed">进入顶部「发现」，左右滑动翻看 AI 精选的学术论文。把觉得有用的点 ❤ 收藏进你的知识库。</div>
                   </div>
                 </div>
                 <div class="flex items-start gap-4">
                   <div class="w-8 h-8 rounded-full bg-tinder-green/10 border border-tinder-green flex items-center justify-center text-tinder-green font-bold shrink-0">3</div>
                   <div>
                     <div class="text-sm font-bold text-text-primary mb-1">填入 API Key 解锁完全体（可选但强烈建议）</div>
                     <div class="text-sm text-text-secondary leading-relaxed">进入「高级设置」，配置任意兼容的 API Key（如阿里云通义或 OpenAI），开启「深度研究」「对比分析」和「灵感工作台」的无限可能。</div>
                   </div>
                 </div>
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
            现在你已经掌握了 AI4Papers 的工作流。<br/>开始让你的研究效率飞跃吧。
          </p>
          <div class="flex flex-wrap items-center justify-center gap-3">
            <router-link
              to="/"
              class="px-5 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold hover:opacity-90 transition-opacity no-underline"
              style="box-shadow: 0 4px 20px rgba(253,38,122,0.2);"
            >
              去推荐页发现论文 →
            </router-link>
            <router-link
              to="/knowledge"
              class="px-5 py-2.5 rounded-full border border-border text-sm text-text-secondary hover:text-text-primary hover:border-border-light transition-colors no-underline"
            >
              打开知识库
            </router-link>
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
