<script setup lang="ts">
import { computed, ref } from 'vue'
import SummarySection from './SummarySection.vue'
import AssetsAccordion from './AssetsAccordion.vue'
import ResearchMemoryPanel from './ResearchMemoryPanel.vue'
import AddToProjectDialog from './project/AddToProjectDialog.vue'
import type { PaperDetailResponse, PaperImage } from '../types/paper'
import { isAuthenticated } from '../stores/auth'

const props = defineProps<{
  detail: PaperDetailResponse
  effectiveSource?: 'recommendation' | 'user_upload'
}>()

const emit = defineEmits<{
  openPdf: []
  openChat: []
}>()

const activeTab = ref<'summary' | 'images' | 'assets' | 'memory'>('summary')
const selectedImage = ref<PaperImage | null>(null)
const paperImages = computed(() => props.detail.images || [])
const paperId = computed(() => props.detail.summary.paper_id || '')
const showProjectDialog = ref(false)
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
        <button
          v-if="isAuthenticated && paperId"
          type="button"
          class="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-full border text-sm font-medium cursor-pointer transition-colors bg-bg-elevated border-border text-tinder-green hover:bg-bg-hover"
          @click="showProjectDialog = true"
        >
          🗂️ 加入课题
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
        v-if="paperImages.length"
        class="px-4 sm:px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
        :class="activeTab === 'images'
          ? 'border-tinder-pink text-tinder-pink'
          : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="activeTab = 'images'"
      >
        论文图表
        <span class="ml-1 text-xs text-text-muted">{{ paperImages.length }}</span>
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
      <button
        v-if="isAuthenticated && paperId"
        class="px-4 sm:px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
        :class="activeTab === 'memory'
          ? 'border-tinder-blue text-tinder-blue'
          : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="activeTab = 'memory'"
      >
        研究记忆
      </button>
    </div>

    <div v-if="activeTab === 'summary'" class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6">
      <SummarySection :summary="detail.summary" />
    </div>

    <div
      v-if="activeTab === 'images' && paperImages.length"
      class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6"
    >
      <div class="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 class="text-base font-bold text-text-primary mb-1">论文图表</h2>
          <p class="text-sm text-text-muted">来自后端 MinerU/select_image 产物，可用于快速浏览图表证据。</p>
        </div>
        <span class="shrink-0 text-xs px-2 py-1 rounded-full bg-bg-elevated border border-border text-text-muted">
          {{ paperImages.length }} 张
        </span>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          v-for="image in paperImages"
          :key="image.filename"
          type="button"
          class="group overflow-hidden rounded-xl border border-border bg-bg-elevated p-0 text-left cursor-zoom-in transition-colors hover:border-tinder-blue/60"
          @click="selectedImage = image"
        >
          <img
            :src="image.url"
            :alt="image.caption || image.filename"
            loading="lazy"
            class="w-full h-44 object-contain bg-bg-card transition-transform group-hover:scale-[1.02]"
          />
          <div class="px-3 py-2 border-t border-border">
            <p class="text-xs text-text-muted font-mono truncate">{{ image.filename }}</p>
          </div>
        </button>
      </div>
    </div>

    <div
      v-if="activeTab === 'assets' && detail.paper_assets"
      class="bg-bg-card rounded-2xl border border-border p-4 sm:p-6"
    >
      <AssetsAccordion :assets="detail.paper_assets" />
    </div>

    <div
      v-if="activeTab === 'memory' && isAuthenticated && paperId"
      class="bg-bg-card rounded-2xl border border-border overflow-hidden"
      style="min-height: 320px"
    >
      <ResearchMemoryPanel :paper-id="paperId" />
    </div>

    <div
      v-if="selectedImage"
      class="fixed inset-0 z-[1000] bg-black/75 flex items-center justify-center p-4"
      @click.self="selectedImage = null"
    >
      <div class="max-w-5xl max-h-[90vh] w-full rounded-2xl bg-bg-card border border-border overflow-hidden shadow-2xl">
        <div class="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
          <p class="text-sm text-text-secondary font-mono truncate">{{ selectedImage.filename }}</p>
          <button
            type="button"
            class="shrink-0 px-3 py-1.5 rounded-full border border-border bg-bg-elevated text-sm text-text-secondary cursor-pointer hover:bg-bg-hover"
            @click="selectedImage = null"
          >
            关闭
          </button>
        </div>
        <div class="max-h-[calc(90vh-54px)] overflow-auto bg-bg-elevated">
          <img
            :src="selectedImage.url"
            :alt="selectedImage.caption || selectedImage.filename"
            class="w-full h-auto object-contain"
          />
        </div>
      </div>
    </div>
    <AddToProjectDialog
      v-if="showProjectDialog"
      asset-type="paper"
      :asset-id="paperId"
      :source-scope="paperId.startsWith('up_') ? 'mypapers' : 'kb'"
      :asset-title="detail.summary.short_title || detail.summary['📖标题']"
      @close="showProjectDialog = false"
    />
  </div>
</template>
