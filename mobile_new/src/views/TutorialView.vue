<script setup lang="ts">
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()

const chapters = [
  {
    id: 'getting-started',
    number: 1,
    title: '快速入门',
    emoji: '🚀',
    color: 'from-tinder-pink/20 to-tinder-pink/5',
    border: 'border-tinder-pink/30',
    titleColor: 'text-tinder-pink',
    sections: ['注册与每日浏览', '配置 AI 模型'],
    desc: '5 分钟上手，完成账号注册和 AI 模型配置',
  },
  {
    id: 'deep-guide',
    number: 2,
    title: '深度指南',
    emoji: '📚',
    color: 'from-tinder-blue/20 to-tinder-blue/5',
    border: 'border-tinder-blue/30',
    titleColor: 'text-tinder-blue',
    sections: ['知识库管理', '阅读与笔记', '论文对比', 'AI 问答与深度研究', '灵感工作台'],
    desc: '掌握知识库、对比、AI 问答和灵感生成等核心功能',
  },
  {
    id: 'advanced',
    number: 3,
    title: '扩展与交流',
    emoji: '🌐',
    color: 'from-tinder-green/20 to-tinder-green/5',
    border: 'border-tinder-green/30',
    titleColor: 'text-tinder-green',
    sections: ['导入论文与翻译', '社区与订阅'],
    desc: '上传自有论文、中文翻译和社区互动',
  },
]
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="使用教程" @back="router.back()" />

    <div class="flex-1 overflow-y-auto min-h-0 pb-6">

      <!-- Hero -->
      <div class="px-5 pt-5 pb-6">
        <div class="w-14 h-14 rounded-3xl bg-gradient-to-br from-tinder-pink to-tinder-purple flex items-center justify-center text-[26px] mb-4">
          🎓
        </div>
        <h1 class="text-[22px] font-extrabold text-text-primary leading-tight mb-2">
          欢迎使用 AI4Papers
        </h1>
        <p class="text-[14px] text-text-secondary leading-relaxed">
          你的 AI 论文推荐与研究助手。通过本教程，快速掌握每日推荐、知识库管理、AI 问答和灵感生成等核心能力。
        </p>
      </div>

      <!-- Chapter cards -->
      <div class="px-4 space-y-3">
        <button
          v-for="chapter in chapters"
          :key="chapter.id"
          type="button"
          class="w-full text-left rounded-2xl border bg-gradient-to-br p-4 active:opacity-80 transition-opacity"
          :class="[chapter.color, chapter.border]"
          @click="router.push(`/tutorial/${chapter.id}`)"
        >
          <div class="flex items-start gap-3">
            <span class="text-[28px] shrink-0">{{ chapter.emoji }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-[10px] font-semibold text-text-muted">第 {{ chapter.number }} 章</span>
                <h2 class="text-[16px] font-bold" :class="chapter.titleColor">{{ chapter.title }}</h2>
              </div>
              <p class="text-[12px] text-text-muted mb-2.5 leading-relaxed">{{ chapter.desc }}</p>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="s in chapter.sections"
                  :key="s"
                  class="text-[11px] text-text-secondary bg-bg-elevated/70 px-2 py-0.5 rounded-full"
                >
                  {{ s }}
                </span>
              </div>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="text-text-muted shrink-0 mt-1"><polyline points="9 18 15 12 9 6"/></svg>
          </div>
        </button>
      </div>

      <!-- Footer tip -->
      <div class="mx-4 mt-5 px-4 py-3.5 rounded-2xl bg-tinder-blue/8 border border-tinder-blue/20">
        <p class="text-[12px] text-tinder-blue leading-relaxed">
          💡 <span class="font-semibold">小提示：</span>每天浏览、收藏、提问可完成今日任务，连续签到解锁里程碑奖励。
        </p>
      </div>

    </div>
  </div>
</template>
