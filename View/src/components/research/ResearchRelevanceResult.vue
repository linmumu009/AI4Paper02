<script setup lang="ts">
import type { ResearchRankingItem } from '../../types/paper'

const props = defineProps<{
  rankings: ResearchRankingItem[]
  selectedIds: string[]
  isRunning: boolean
  progressMsg?: string
  totalPapers: number
  titleFor: (paperId: string) => string
}>()

const highRelevance = () => props.rankings.filter(r => r.level === 'high')
const mediumRelevance = () => props.rankings.filter(r => r.level === 'medium')
const lowRelevance = () => props.rankings.filter(r => r.level === 'low')
</script>

<template>
  <div class="space-y-4">
    <!-- Running placeholder -->
    <div v-if="isRunning && rankings.length === 0" class="flex items-center gap-2.5 text-sm text-text-muted py-2">
      <svg class="animate-spin shrink-0" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      <span>{{ progressMsg || `正在评估 ${totalPapers} 篇论文的相关性…` }}</span>
    </div>

    <!-- Selected summary -->
    <div v-if="selectedIds.length > 0"
      class="flex items-center gap-2 px-3 py-2 rounded-lg bg-accent-primary/6 border border-accent-primary/15"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
        class="text-accent-primary shrink-0">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
      <span class="text-xs text-text-secondary">
        已选 <strong class="text-accent-primary">{{ selectedIds.length }}</strong> 篇进入下一轮分析
      </span>
    </div>

    <!-- High relevance group -->
    <div v-if="highRelevance().length > 0" class="space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-green-500">高相关 · {{ highRelevance().length }}</span>
        <div class="flex-1 h-px bg-green-500/15"></div>
      </div>
      <div class="space-y-1.5">
        <div
          v-for="item in highRelevance()"
          :key="item.paper_id"
          class="group rounded-lg overflow-hidden border border-green-500/15 bg-green-500/4 hover:bg-green-500/8 transition-colors"
        >
          <div class="flex items-stretch">
            <!-- Score bar on left -->
            <div class="w-1 shrink-0 bg-green-500/30 relative">
              <div
                class="absolute bottom-0 left-0 right-0 bg-green-500 transition-all duration-700"
                :style="{ height: Math.round(item.score * 100) + '%' }"
              />
            </div>
            <div class="flex-1 min-w-0 px-3 py-2">
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono font-bold text-green-500 tabular-nums shrink-0">
                  {{ Math.round(item.score * 100) }}%
                </span>
                <span class="text-xs font-medium text-text-primary truncate flex-1">
                  {{ titleFor(item.paper_id) }}
                </span>
                <span
                  v-if="selectedIds.includes(item.paper_id)"
                  class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-accent-primary/15 text-accent-primary font-semibold border border-accent-primary/20"
                >选入</span>
              </div>
              <p class="text-xs text-text-muted mt-0.5 leading-relaxed">{{ item.reason }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Medium relevance group -->
    <div v-if="mediumRelevance().length > 0" class="space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-yellow-500">中相关 · {{ mediumRelevance().length }}</span>
        <div class="flex-1 h-px bg-yellow-500/15"></div>
      </div>
      <div class="space-y-1.5">
        <div
          v-for="item in mediumRelevance()"
          :key="item.paper_id"
          class="group rounded-lg overflow-hidden border border-yellow-500/15 bg-yellow-500/4 hover:bg-yellow-500/8 transition-colors"
        >
          <div class="flex items-stretch">
            <div class="w-1 shrink-0 bg-yellow-500/25 relative">
              <div
                class="absolute bottom-0 left-0 right-0 bg-yellow-500 transition-all duration-700"
                :style="{ height: Math.round(item.score * 100) + '%' }"
              />
            </div>
            <div class="flex-1 min-w-0 px-3 py-2">
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono font-bold text-yellow-500 tabular-nums shrink-0">
                  {{ Math.round(item.score * 100) }}%
                </span>
                <span class="text-xs font-medium text-text-primary truncate flex-1">
                  {{ titleFor(item.paper_id) }}
                </span>
                <span
                  v-if="selectedIds.includes(item.paper_id)"
                  class="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-accent-primary/15 text-accent-primary font-semibold border border-accent-primary/20"
                >选入</span>
              </div>
              <p class="text-xs text-text-muted mt-0.5 leading-relaxed">{{ item.reason }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Low relevance group (collapsed / pills) -->
    <div v-if="lowRelevance().length > 0">
      <div class="flex items-center gap-2 mb-2">
        <span class="text-[10px] font-semibold uppercase tracking-wider text-text-muted">低相关 · {{ lowRelevance().length }} · 已排除</span>
        <div class="flex-1 h-px bg-border"></div>
      </div>
      <div class="flex flex-wrap gap-1">
        <span
          v-for="item in lowRelevance()"
          :key="item.paper_id"
          class="text-[11px] px-2 py-0.5 rounded-full border border-border text-text-muted opacity-50"
          :title="item.reason"
        >{{ titleFor(item.paper_id) }}</span>
      </div>
    </div>
  </div>
</template>
