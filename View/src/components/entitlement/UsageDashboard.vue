<script setup lang="ts">
import { computed } from 'vue'
import { useEntitlements } from '../../composables/useEntitlements'
import QuotaUsageCard from './QuotaUsageCard.vue'
import GatesBadgeGrid from './GatesBadgeGrid.vue'

const { entitlements, gateAllowed, browseLimit, researchHistoryDays, kbPaperStorage, kbNoteStorage, kbFolderStorage, kbCompareResultStorage } = useEntitlements()

const hasTranslate = computed(() => gateAllowed('translate'))

// Storage fraction helper
function storageFraction(used: number, limit: number | null): number {
  if (!limit) return 0
  return Math.min(1, used / limit)
}

function storageStatus(used: number, limit: number | null, warningThreshold = 5): 'normal' | 'warning' | 'exhausted' {
  if (!limit) return 'normal'
  const remaining = limit - used
  if (remaining <= 0) return 'exhausted'
  if (remaining <= warningThreshold) return 'warning'
  return 'normal'
}

function storageProgressColor(status: string): string {
  if (status === 'exhausted') return 'bg-red-500'
  if (status === 'warning') return 'bg-amber-400'
  return 'bg-tinder-green'
}

function storageBorderClass(status: string): string {
  if (status === 'exhausted') return 'border-red-500/40'
  if (status === 'warning') return 'border-amber-500/30'
  return 'border-border'
}
</script>

<template>
  <div class="space-y-5">

    <!-- Group 1: AI 功能 -->
    <section>
      <h4 class="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-2.5 flex items-center gap-1.5">
        <span>🤖</span> AI 功能
      </h4>
      <div class="grid grid-cols-2 gap-2.5">
        <QuotaUsageCard feature="chat"     label="AI 论文问答" icon="💬" />
        <QuotaUsageCard feature="compare"  label="对比分析"    icon="🔬" />
        <QuotaUsageCard feature="research" label="深度研究"    icon="⚡" />
        <QuotaUsageCard feature="idea_gen" label="灵感生成"    icon="💡" />
        <QuotaUsageCard feature="upload"   label="论文上传"    icon="📤" />
        <QuotaUsageCard v-if="hasTranslate" feature="translate" label="全文翻译" icon="🌐" />
      </div>

      <!-- Browse limit -->
      <div
        v-if="browseLimit !== null"
        class="mt-2.5 flex items-center gap-2 rounded-xl border border-border bg-bg-card p-3"
      >
        <div class="w-7 h-7 rounded-lg bg-tinder-blue/15 text-tinder-blue flex items-center justify-center text-sm shrink-0">
          👁️
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-xs font-semibold text-text-primary leading-tight">每日浏览论文</p>
          <p class="text-[10px] text-text-muted mt-0.5">每日最多 {{ browseLimit }} 篇</p>
        </div>
        <span class="text-[11px] text-text-secondary shrink-0">{{ browseLimit }} 篇/天</span>
      </div>
    </section>

    <!-- Group 2: 知识库存储 -->
    <section v-if="entitlements">
      <h4 class="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-2.5 flex items-center gap-1.5">
        <span>📚</span> 知识库存储
      </h4>
      <div class="grid grid-cols-2 gap-2.5">

        <!-- KB Papers -->
        <div
          class="rounded-xl border p-3.5 bg-bg-card transition-colors"
          :class="storageBorderClass(storageStatus(kbPaperStorage.used, kbPaperStorage.limit, 5))"
        >
          <div class="flex items-center gap-2 mb-2.5">
            <div class="w-7 h-7 rounded-lg bg-tinder-green/15 text-tinder-green flex items-center justify-center text-sm">📄</div>
            <div>
              <p class="text-xs font-semibold text-text-primary">论文收藏</p>
            </div>
          </div>
          <template v-if="kbPaperStorage.limit !== null">
            <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden mb-1.5">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="storageProgressColor(storageStatus(kbPaperStorage.used, kbPaperStorage.limit, 5))"
                :style="`width: ${Math.min(100, storageFraction(kbPaperStorage.used, kbPaperStorage.limit) * 100)}%`"
              />
            </div>
            <div class="flex justify-between text-[11px]">
              <span class="text-text-muted">{{ kbPaperStorage.used }} / {{ kbPaperStorage.limit }}</span>
              <span class="text-text-muted">剩余 {{ kbPaperStorage.remaining }}</span>
            </div>
          </template>
          <template v-else>
            <span class="text-[11px] text-tinder-green">不限篇数</span>
          </template>
        </div>

        <!-- KB Notes -->
        <div
          class="rounded-xl border p-3.5 bg-bg-card transition-colors"
          :class="storageBorderClass(storageStatus(kbNoteStorage.used, kbNoteStorage.limit, 3))"
        >
          <div class="flex items-center gap-2 mb-2.5">
            <div class="w-7 h-7 rounded-lg bg-tinder-purple/15 text-tinder-purple flex items-center justify-center text-sm">📝</div>
            <div>
              <p class="text-xs font-semibold text-text-primary">知识库笔记</p>
            </div>
          </div>
          <template v-if="kbNoteStorage.limit !== null">
            <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden mb-1.5">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="storageProgressColor(storageStatus(kbNoteStorage.used, kbNoteStorage.limit, 3))"
                :style="`width: ${Math.min(100, storageFraction(kbNoteStorage.used, kbNoteStorage.limit) * 100)}%`"
              />
            </div>
            <div class="flex justify-between text-[11px]">
              <span class="text-text-muted">{{ kbNoteStorage.used }} / {{ kbNoteStorage.limit }}</span>
              <span class="text-text-muted">剩余 {{ kbNoteStorage.remaining }}</span>
            </div>
          </template>
          <template v-else>
            <span class="text-[11px] text-tinder-green">不限条数</span>
          </template>
        </div>

        <!-- KB Folders -->
        <div
          class="rounded-xl border p-3.5 bg-bg-card transition-colors"
          :class="storageBorderClass(storageStatus(kbFolderStorage.used, kbFolderStorage.limit, 1))"
        >
          <div class="flex items-center gap-2 mb-2.5">
            <div class="w-7 h-7 rounded-lg bg-tinder-gold/15 text-tinder-gold flex items-center justify-center text-sm">📁</div>
            <div>
              <p class="text-xs font-semibold text-text-primary">文件夹</p>
            </div>
          </div>
          <template v-if="kbFolderStorage.limit !== null">
            <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden mb-1.5">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="storageProgressColor(storageStatus(kbFolderStorage.used, kbFolderStorage.limit, 1))"
                :style="`width: ${Math.min(100, storageFraction(kbFolderStorage.used, kbFolderStorage.limit) * 100)}%`"
              />
            </div>
            <div class="flex justify-between text-[11px]">
              <span class="text-text-muted">{{ kbFolderStorage.used }} / {{ kbFolderStorage.limit }}</span>
              <span class="text-text-muted">剩余 {{ kbFolderStorage.remaining }}</span>
            </div>
          </template>
          <template v-else>
            <span class="text-[11px] text-tinder-green">不限个数</span>
          </template>
        </div>

        <!-- KB Compare Results -->
        <div
          class="rounded-xl border p-3.5 bg-bg-card transition-colors"
          :class="storageBorderClass(storageStatus(kbCompareResultStorage.used, kbCompareResultStorage.limit, 1))"
        >
          <div class="flex items-center gap-2 mb-2.5">
            <div class="w-7 h-7 rounded-lg bg-tinder-blue/15 text-tinder-blue flex items-center justify-center text-sm">🔬</div>
            <div>
              <p class="text-xs font-semibold text-text-primary">保存对比结果</p>
            </div>
          </div>
          <template v-if="kbCompareResultStorage.limit !== null">
            <div class="h-1.5 bg-bg-elevated rounded-full overflow-hidden mb-1.5">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="storageProgressColor(storageStatus(kbCompareResultStorage.used, kbCompareResultStorage.limit, 1))"
                :style="`width: ${Math.min(100, storageFraction(kbCompareResultStorage.used, kbCompareResultStorage.limit) * 100)}%`"
              />
            </div>
            <div class="flex justify-between text-[11px]">
              <span class="text-text-muted">{{ kbCompareResultStorage.used }} / {{ kbCompareResultStorage.limit }}</span>
              <span class="text-text-muted">剩余 {{ kbCompareResultStorage.remaining }}</span>
            </div>
          </template>
          <template v-else>
            <span class="text-[11px] text-tinder-green">不限条数</span>
          </template>
        </div>

      </div>

      <!-- Research history retention -->
      <div
        v-if="researchHistoryDays !== null"
        class="mt-2.5 flex items-center gap-2 rounded-xl border border-border bg-bg-card p-3"
      >
        <div class="w-7 h-7 rounded-lg bg-bg-elevated flex items-center justify-center text-sm shrink-0">🕒</div>
        <div class="flex-1 min-w-0">
          <p class="text-xs font-semibold text-text-primary">研究历史保留</p>
        </div>
        <span class="text-[11px] text-text-secondary shrink-0">{{ researchHistoryDays }} 天</span>
      </div>
    </section>

    <!-- Group 3: 功能权限 -->
    <section>
      <h4 class="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-2.5 flex items-center gap-1.5">
        <span>🔑</span> 功能权限
      </h4>
      <GatesBadgeGrid />
    </section>

  </div>
</template>
