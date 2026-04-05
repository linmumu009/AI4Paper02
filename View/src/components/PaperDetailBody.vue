<script setup lang="ts">
import { ref } from 'vue'
import SummarySection from './SummarySection.vue'
import AssetsAccordion from './AssetsAccordion.vue'
import type { PaperDetailResponse } from '../types/paper'
import { isAuthenticated } from '../stores/auth'

defineProps<{
  detail: PaperDetailResponse
  effectiveSource?: 'recommendation' | 'user_upload'
}>()

const emit = defineEmits<{
  openPdf: []
  openChat: []
}>()

const activeTab = ref<'summary' | 'assets'>('summary')
</script>

<template>
  <div class="max-w-3xl mx-auto pb-24">
    <div class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6 mb-5">
      <div class="flex flex-wrap items-center gap-2 mb-3">
        <span
          class="px-3 py-1 rounded-full text-xs font-semibold text-white"
          :class="detail.summary.institution_tier === 1
            ? 'bg-gradient-to-r from-[#b8860b] to-[#f5c518]'
            : detail.summary.institution_tier === 2
              ? 'bg-gradient-to-r from-[#4a6fa5] to-[#7bb3d3]'
              : detail.summary.institution_tier === 3
                ? 'bg-gradient-to-r from-[#8b5e3c] to-[#c4956a]'
                : 'bg-brand-gradient'"
        >
          {{ detail.summary.institution || '未知机构' }}
        </span>
        <span
          v-if="detail.summary.institution_tier === 1"
          class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
        >T1 · 顶尖</span>
        <span
          v-else-if="detail.summary.institution_tier === 2"
          class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
        >T2 · 一流</span>
        <span
          v-else-if="detail.summary.institution_tier === 3"
          class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300"
        >T3 · 知名</span>
        <span
          v-if="effectiveSource === 'user_upload'"
          class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-600 border border-amber-500/30"
        >我的上传</span>
        <span class="text-xs text-text-muted">{{ detail.date }}</span>
      </div>

      <h1 class="text-xl sm:text-2xl font-bold text-text-primary leading-snug mb-2">
        {{ detail.summary.short_title }}
      </h1>
      <p class="text-sm text-text-secondary leading-relaxed mb-2">
        {{ detail.summary['📖标题'] }}
      </p>
      <p
        v-if="detail.summary['推荐理由']"
        class="text-sm text-tinder-blue leading-relaxed mb-4 px-3 py-2 rounded-lg bg-tinder-blue/8 border border-tinder-blue/20"
      >
        <span class="font-semibold">推荐理由：</span>{{ detail.summary['推荐理由'] }}
      </p>
      <div v-else class="mb-4"></div>

      <div class="flex flex-wrap gap-2 sm:gap-3">
        <a
          v-if="detail.arxiv_url"
          :href="detail.arxiv_url"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-full bg-bg-elevated border border-border text-sm font-medium text-tinder-blue no-underline hover:bg-bg-hover transition-colors"
        >
          📄 arXiv
        </a>
        <button
          v-if="detail.pdf_url"
          type="button"
          class="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-full border text-sm font-medium cursor-pointer transition-colors bg-bg-elevated border-border text-tinder-pink hover:bg-bg-hover"
          @click="emit('openPdf')"
        >
          📕 PDF
        </button>
        <button
          v-if="isAuthenticated"
          type="button"
          class="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-full border text-sm font-medium cursor-pointer transition-colors bg-bg-elevated border-border text-tinder-blue hover:bg-bg-hover"
          @click="emit('openChat')"
        >
          💬 AI 问答
        </button>
        <span class="self-center text-xs font-mono text-text-muted">{{ detail.summary.paper_id }}</span>
      </div>
    </div>

    <div class="flex gap-1 mb-4 border-b border-border">
      <button
        class="px-4 sm:px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
        :class="activeTab === 'summary'
          ? 'border-tinder-pink text-tinder-pink'
          : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="activeTab = 'summary'"
      >
        论文摘要
      </button>
      <button
        v-if="detail.paper_assets"
        class="px-4 sm:px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
        :class="activeTab === 'assets'
          ? 'border-tinder-pink text-tinder-pink'
          : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="activeTab = 'assets'"
      >
        结构化分析
      </button>
    </div>

    <div v-if="activeTab === 'summary'" class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6">
      <SummarySection :summary="detail.summary" />
    </div>

    <div
      v-if="activeTab === 'assets' && detail.paper_assets"
      class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6"
    >
      <AssetsAccordion :assets="detail.paper_assets" />
    </div>
  </div>
</template>
