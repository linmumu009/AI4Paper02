<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'

const props = defineProps<{ chapter: string }>()
const router = useRouter()

interface Section {
  title: string
  content: string[]
  bullets?: string[]
  tip?: string
}

interface ChapterData {
  title: string
  emoji: string
  color: string
  prev?: string
  next?: string
  sections: Section[]
}

const allChapters: Record<string, ChapterData> = {
  'getting-started': {
    title: '快速入门',
    emoji: '🚀',
    color: 'text-tinder-pink',
    next: 'deep-guide',
    sections: [
      {
        title: '注册与每日浏览',
        content: [
          'AI4Papers 每天为你精选最新 arXiv 论文，并用 AI 生成中文摘要、推荐理由和核心思路。',
          '注册账号后，在「推荐」页面即可看到每日个性化论文推送。',
        ],
        bullets: [
          '右滑卡片可将论文加入知识库',
          '左滑可跳过当前论文',
          '点击卡片进入论文详情查看完整解析',
          '在设置中选择感兴趣的研究领域',
        ],
        tip: '每日浏览、收藏、AI 提问三项任务完成后可获得签到积分，连续积累解锁里程碑奖励。',
      },
      {
        title: '配置 AI 模型',
        content: [
          'AI4Papers 支持接入多种大语言模型，你可以在「高级设置」中添加自己的 API Key，或使用系统默认模型。',
          'Pro 用户可以创建多个模型预设，针对不同功能（问答、深度研究、灵感生成）分别配置最优模型。',
        ],
        bullets: [
          '进入「我的」→「编辑资料」可访问高级设置',
          '支持 OpenAI、Claude、DeepSeek 等主流模型',
          '每个功能模块可独立绑定不同的模型预设',
          '配置完成后无需重新登录即时生效',
        ],
      },
    ],
  },
  'deep-guide': {
    title: '深度指南',
    emoji: '📚',
    color: 'text-tinder-blue',
    prev: 'getting-started',
    next: 'advanced',
    sections: [
      {
        title: '知识库管理',
        content: [
          '知识库是你的论文收藏夹，支持文件夹分类整理。收藏的论文会保存 AI 解析结果，方便随时回顾。',
        ],
        bullets: [
          '在推荐页右滑或在详情页点击「收藏」添加论文',
          '支持创建多个文件夹分类管理',
          '长按论文卡片可移动到其他文件夹',
          '点击论文可进入详情查看完整 AI 解析',
        ],
        tip: 'Pro 用户最多可收藏 200 篇论文，Free 用户 20 篇。',
      },
      {
        title: '阅读与笔记',
        content: [
          '在论文详情页可打开 PDF 原文阅读，同时用 AI 辅助理解。笔记支持 Markdown 格式，可与论文关联保存。',
        ],
        bullets: [
          '点击「打开 PDF」在浏览器中阅读原文',
          '点击「笔记」创建或编辑与该论文关联的笔记',
          '笔记支持 Markdown 格式排版',
          '所有笔记可在知识库的笔记分类中统一查看',
        ],
      },
      {
        title: '论文对比',
        content: [
          '对比功能可以让 AI 对 2-8 篇论文进行横向比较，分析方法异同、优劣势，生成结构化对比报告。',
        ],
        bullets: [
          '在论文详情页点击「对比」进入对比页',
          '可添加多篇论文（Pro 用户最多 8 篇）',
          '选择对比维度：方法、实验、结论等',
          '对比结果可保存到知识库',
        ],
        tip: '通过连续签到奖励可获得扩展对比名额券，临时解锁更多对比篇数。',
      },
      {
        title: 'AI 问答与深度研究',
        content: [
          '论文问答功能可以针对单篇论文与 AI 对话，深入理解方法与实验。通用助手支持自由问答。',
          '深度研究功能会跨多篇论文进行系统性分析，自动检索关联文献并给出综合报告。',
        ],
        bullets: [
          '在论文详情页点击「AI 对话」进入问答界面',
          '切换「通用助手」模式可自由提问',
          '深度研究在底部导航「研究」页面进入',
          '研究报告支持导出（Pro+ 用户）',
        ],
      },
      {
        title: '灵感工作台',
        content: [
          '灵感功能基于你的知识库生成研究思路，推荐潜在的研究方向、方法创新点和实验设计。',
        ],
        bullets: [
          '在底部导航「灵感」页面查看每日推荐',
          '「灵感实验室」可手动触发生成新灵感',
          '「原子库」展示从知识库提炼的核心概念',
          '「范例库」收录优质灵感案例供参考',
        ],
        tip: '知识库内容越丰富，灵感生成质量越高。建议收藏 10 篇以上相关论文再使用。',
      },
    ],
  },
  'advanced': {
    title: '扩展与交流',
    emoji: '🌐',
    color: 'text-tinder-green',
    prev: 'deep-guide',
    sections: [
      {
        title: '导入论文与翻译',
        content: [
          '除了每日推荐，你还可以上传自己的论文（PDF 文件、arXiv ID 或手动录入）。上传后系统会自动解析并生成 AI 摘要。',
        ],
        bullets: [
          '支持三种导入方式：PDF 上传 / arXiv ID / 手动录入',
          '上传 PDF 后系统自动提取文本（MinerU 处理）',
          '处理完成后可使用 AI 翻译生成中文版本',
          '导入的论文可加入知识库参与对比和问答',
        ],
        tip: '中文翻译功能需要 Pro 账号，翻译后生成完整中文版 PDF。',
      },
      {
        title: '社区与订阅',
        content: [
          '社区是和其他研究者交流的地方，可以发布论文笔记、研究心得和讨论帖子。',
          '订阅 Pro 或 Pro+ 可解锁更多 AI 配额、更高知识库容量和高级功能。',
        ],
        bullets: [
          '在「社区」页面查看和发布帖子',
          '帖子支持 Markdown 格式',
          '在「我的」→「订阅与配额」查看用量详情',
          '使用兑换码可激活订阅',
        ],
      },
    ],
  },
}

const chapterData = computed(() => allChapters[props.chapter] ?? null)
const chapterList = ['getting-started', 'deep-guide', 'advanced']
const chapterIdx = computed(() => chapterList.indexOf(props.chapter))
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader @back="router.push('/tutorial')">
      <template #title>
        <span v-if="chapterData" class="text-[15px] font-semibold" :class="chapterData.color">
          {{ chapterData.emoji }} {{ chapterData.title }}
        </span>
      </template>
    </PageHeader>

    <!-- Not found -->
    <div v-if="!chapterData" class="flex-1 flex flex-col items-center justify-center gap-3 px-8">
      <p class="text-text-muted text-[14px]">找不到此章节</p>
      <button type="button" class="text-tinder-blue text-[14px]" @click="router.push('/tutorial')">返回教程首页</button>
    </div>

    <div v-else class="flex-1 overflow-y-auto min-h-0 pb-6">

      <!-- Chapter header -->
      <div class="px-5 pt-5 pb-4 border-b border-border/50">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[11px] text-text-muted">第 {{ chapterIdx + 1 }} 章，共 3 章</span>
        </div>
        <h1 class="text-[20px] font-extrabold text-text-primary">{{ chapterData.title }}</h1>
        <p class="text-[13px] text-text-muted mt-1">共 {{ chapterData.sections.length }} 节</p>
      </div>

      <!-- Sections -->
      <div class="px-4 py-4 space-y-5">
        <div
          v-for="(section, idx) in chapterData.sections"
          :key="section.title"
          class="card-section"
        >
          <!-- Section header -->
          <div class="flex items-center gap-2.5 mb-3">
            <div class="w-7 h-7 rounded-full bg-tinder-blue/15 text-tinder-blue flex items-center justify-center text-[12px] font-bold shrink-0">
              {{ idx + 1 }}
            </div>
            <h2 class="text-[15px] font-bold text-text-primary">{{ section.title }}</h2>
          </div>

          <!-- Content paragraphs -->
          <div class="space-y-2 mb-3">
            <p v-for="(para, pi) in section.content" :key="pi" class="text-[13px] text-text-secondary leading-relaxed">
              {{ para }}
            </p>
          </div>

          <!-- Bullet list -->
          <ul v-if="section.bullets?.length" class="space-y-2 mb-3">
            <li
              v-for="(bullet, bi) in section.bullets"
              :key="bi"
              class="flex items-start gap-2.5"
            >
              <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-blue mt-2" />
              <span class="text-[13px] text-text-secondary leading-relaxed">{{ bullet }}</span>
            </li>
          </ul>

          <!-- Tip box -->
          <div v-if="section.tip" class="px-3.5 py-2.5 rounded-xl bg-tinder-gold/8 border border-tinder-gold/25">
            <p class="text-[12px] text-tinder-gold leading-relaxed">
              <span class="font-semibold">💡 提示：</span>{{ section.tip }}
            </p>
          </div>
        </div>
      </div>

    </div>

    <!-- Bottom navigation -->
    <div class="shrink-0 fixed bottom-0 left-0 right-0 bg-bg/95 backdrop-blur-md border-t border-border safe-area-bottom px-4 py-3 flex gap-2 z-20">
      <button
        v-if="chapterData.prev"
        type="button"
        class="flex-1 py-2.5 rounded-xl bg-bg-elevated border border-border text-[13px] font-medium text-text-secondary active:bg-bg-hover flex items-center justify-center gap-1.5"
        @click="router.push(`/tutorial/${chapterData.prev}`)"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        上一章
      </button>
      <button
        type="button"
        class="py-2.5 rounded-xl bg-bg-elevated border border-border text-[13px] font-medium text-text-muted active:bg-bg-hover px-4"
        @click="router.push('/tutorial')"
      >
        目录
      </button>
      <button
        v-if="chapterData.next"
        type="button"
        class="flex-1 py-2.5 rounded-xl bg-tinder-blue/10 border border-tinder-blue/30 text-[13px] font-medium text-tinder-blue active:bg-tinder-blue/20 flex items-center justify-center gap-1.5"
        @click="router.push(`/tutorial/${chapterData.next}`)"
      >
        下一章
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <div v-else class="flex-1" />
    </div>
  </div>
</template>
