<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import {
  fetchKbTree,
  fetchCompareStream,
  saveCompareResult,
} from '@shared/api'
import { fetchUserPapers } from '@shared/api/user-papers'
import type { KbTree, KbFolder } from '@shared/types/kb'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'CompareView' })

const router = useRouter()
const route = useRoute()

// Phase: 'select' | 'comparing' | 'result'
type Phase = 'select' | 'comparing' | 'result'
const phase = ref<Phase>('select')

// Unified paper type for the picker and selection list
interface PickerPaper {
  paper_id: string
  title: string
  institution: string
  source: 'kb' | 'mypapers'
}

// KB tree for loading KB papers
const kbTree = ref<KbTree | null>(null)

// All merged picker papers (KB + user papers)
const allPickerPapers = ref<PickerPaper[]>([])
const pickerLoading = ref(false)
const pickerLoadError = ref('')

// Selected papers
const selectedPapers = ref<PickerPaper[]>([])

// Paper picker
const pickerVisible = ref(false)
const pickerSearch = ref('')
const pickerSourceTab = ref<'all' | 'kb' | 'mypapers'>('all')

// Compare state
const markdown = ref('')
const compareError = ref('')

// Save result
const saveTitle = ref('')
const savingResult = ref(false)

function kbPaperTitle(paper_data: any): string {
  return paper_data?.short_title || paper_data?.['📖标题'] || ''
}

function getAllKbPapers(tree: KbTree): PickerPaper[] {
  const result: PickerPaper[] = tree.papers.map((p) => ({
    paper_id: p.paper_id,
    title: kbPaperTitle(p.paper_data),
    institution: p.paper_data?.institution || '',
    source: 'kb' as const,
  }))
  function collect(f: KbFolder) {
    f.papers.forEach((p) =>
      result.push({
        paper_id: p.paper_id,
        title: kbPaperTitle(p.paper_data),
        institution: p.paper_data?.institution || '',
        source: 'kb' as const,
      }),
    )
    f.children.forEach(collect)
  }
  tree.folders.forEach(collect)
  return result
}

async function loadAllPickerPapers() {
  pickerLoading.value = true
  pickerLoadError.value = ''
  try {
    const [kbResult, userResult] = await Promise.allSettled([
      fetchKbTree('kb'),
      fetchUserPapers({ limit: 200 }),
    ])

    const merged: PickerPaper[] = []
    const seen = new Set<string>()

    if (kbResult.status === 'fulfilled') {
      kbTree.value = kbResult.value
      for (const p of getAllKbPapers(kbResult.value)) {
        if (!seen.has(p.paper_id)) {
          seen.add(p.paper_id)
          merged.push(p)
        }
      }
    }

    if (userResult.status === 'fulfilled') {
      for (const p of userResult.value.papers) {
        if (!seen.has(p.paper_id)) {
          seen.add(p.paper_id)
          merged.push({
            paper_id: p.paper_id,
            title: p.title || p.paper_id,
            institution: p.institution || '',
            source: 'mypapers' as const,
          })
        }
      }
    }

    if (kbResult.status === 'rejected' && userResult.status === 'rejected') {
      pickerLoadError.value = '加载失败，请重试'
    }

    allPickerPapers.value = merged
  } catch (e: any) {
    pickerLoadError.value = e?.message || '加载失败'
  } finally {
    pickerLoading.value = false
  }
}

onMounted(async () => {
  // If paper IDs passed via query, pre-select them
  const idsParam = route.query.ids as string
  if (idsParam) {
    await loadAllPickerPapers()
    const ids = idsParam.split(',').filter(Boolean)
    selectedPapers.value = ids
      .map((id) => allPickerPapers.value.find((p) => p.paper_id === id))
      .filter((p): p is PickerPaper => !!p)
  }
})

const sourceTabs = [
  { key: 'all' as const, label: '全部' },
  { key: 'kb' as const, label: '知识库' },
  { key: 'mypapers' as const, label: '我的论文' },
]

const filteredPickerPapers = computed(() => {
  const q = pickerSearch.value.trim().toLowerCase()
  const selected = new Set(selectedPapers.value.map((p) => p.paper_id))
  return allPickerPapers.value.filter((p) => {
    if (selected.has(p.paper_id)) return false
    if (pickerSourceTab.value !== 'all' && p.source !== pickerSourceTab.value) return false
    if (!q) return true
    return p.title.toLowerCase().includes(q) || p.institution.toLowerCase().includes(q)
  })
})

async function openPicker() {
  if (allPickerPapers.value.length === 0) await loadAllPickerPapers()
  pickerSearch.value = ''
  pickerVisible.value = true
}

function togglePaper(paper: PickerPaper) {
  const idx = selectedPapers.value.findIndex((p) => p.paper_id === paper.paper_id)
  if (idx >= 0) {
    selectedPapers.value.splice(idx, 1)
  } else {
    if (selectedPapers.value.length >= 5) {
      showToast('最多同时对比 5 篇论文')
      return
    }
    selectedPapers.value.push(paper)
  }
}

function pickPaper(paper: PickerPaper) {
  togglePaper(paper)
  // Only auto-close when reaching max limit
  if (selectedPapers.value.length >= 5) pickerVisible.value = false
}

function removePaper(paperId: string) {
  selectedPapers.value = selectedPapers.value.filter((p) => p.paper_id !== paperId)
}

const canCompare = computed(() => selectedPapers.value.length >= 2)

async function startCompare() {
  if (!canCompare.value) return
  pickerVisible.value = false
  phase.value = 'comparing'
  markdown.value = ''
  compareError.value = ''

  // Auto-generate title
  const titles = selectedPapers.value.map((p) => p.title || p.paper_id)
  saveTitle.value = titles.slice(0, 2).join(' vs ') + (titles.length > 2 ? ` 等${titles.length}篇` : '')

  try {
    const ids = selectedPapers.value.map((p) => p.paper_id)
    const resp = await fetchCompareStream(ids, 'kb')
    if (!resp.ok) {
      compareError.value = '对比请求失败，请重试'
      phase.value = 'select'
      return
    }
    const reader = resp.body?.getReader()
    if (!reader) { compareError.value = '无法读取响应'; phase.value = 'select'; return }
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') continue
          try {
            const obj = JSON.parse(payload)
            if (typeof obj === 'string') {
              markdown.value += obj
            } else {
              if (obj.delta) markdown.value += obj.delta
              if (obj.content) markdown.value = obj.content
              if (obj.error) { compareError.value = obj.error; phase.value = 'select'; return }
            }
          } catch {
            if (payload && payload !== '[DONE]') markdown.value += payload
          }
        }
      }
    }
    // Guard: empty result
    if (!markdown.value.trim()) {
      compareError.value = '对比结果为空，请检查所选论文是否有足够的内容'
      phase.value = 'select'
      return
    }
    phase.value = 'result'
  } catch (e: any) {
    compareError.value = e?.message || '对比失败，请重试'
    phase.value = 'select'
  }
}

async function doSave() {
  if (!saveTitle.value.trim() || !markdown.value || savingResult.value) return
  savingResult.value = true
  try {
    const ids = selectedPapers.value.map((p) => p.paper_id)
    const res = await saveCompareResult(saveTitle.value.trim(), markdown.value, ids)
    showToast('已保存到对比库')
    router.replace(`/compare-result/${res.id}`)
  } catch {
    showToast('保存失败，请重试')
  } finally {
    savingResult.value = false
  }
}

function resetToSelect() {
  phase.value = 'select'
  markdown.value = ''
  compareError.value = ''
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader
      :title="phase === 'comparing' ? '对比生成中…' : phase === 'result' ? '对比结果' : '论文对比'"
      @back="phase === 'select' ? router.back() : resetToSelect()"
    />

    <!-- ── Phase: select ── -->
    <template v-if="phase === 'select'">
      <div class="flex-1 overflow-y-auto pb-28">
        <div class="px-4 py-3 space-y-3">

          <!-- Selected papers -->
          <div>
            <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-2">
              已选 {{ selectedPapers.length }} / 5 篇
            </p>

            <div v-if="selectedPapers.length === 0" class="p-4 rounded-2xl border border-dashed border-border text-center">
              <p class="text-[13px] text-text-muted">选择 2-5 篇论文进行对比</p>
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="paper in selectedPapers"
                :key="paper.paper_id"
                class="flex items-center gap-3 p-3 rounded-2xl bg-bg-elevated border border-border"
              >
                <div class="flex-1 min-w-0">
                  <p class="text-[13px] font-medium text-text-primary line-clamp-2 leading-snug">
                    {{ paper.title || paper.paper_id }}
                  </p>
                  <div class="flex items-center gap-1.5 mt-1 flex-wrap">
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                      :class="paper.source === 'kb' ? 'bg-tinder-green/15 text-tinder-green' : 'bg-tinder-blue/15 text-tinder-blue'"
                    >
                      {{ paper.source === 'kb' ? '知识库' : '我的论文' }}
                    </span>
                    <span v-if="paper.institution" class="text-[11px] text-text-muted">{{ paper.institution }}</span>
                  </div>
                </div>
                <button
                  type="button"
                  class="shrink-0 w-7 h-7 rounded-full bg-tinder-pink/15 flex items-center justify-center text-tinder-pink"
                  @click="removePaper(paper.paper_id)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- Add paper button -->
          <button
            v-if="selectedPapers.length < 5"
            type="button"
            class="w-full flex items-center justify-center gap-2 py-3 rounded-2xl border border-dashed border-border text-text-muted text-[14px] active:bg-bg-hover"
            @click="openPicker"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            添加论文
          </button>

          <p class="text-[12px] text-text-muted text-center">AI 将从多个维度对比所选论文</p>
        </div>
      </div>

      <!-- Bottom CTA -->
      <div
        class="shrink-0 px-4 pt-3 border-t border-border bg-bg-card"
        style="padding-bottom: max(16px, env(safe-area-inset-bottom, 16px));"
      >
        <button type="button" class="btn-primary" :disabled="!canCompare" @click="startCompare">
          {{ canCompare ? '开始对比' : '请至少选择 2 篇论文' }}
        </button>
      </div>
    </template>

    <!-- ── Phase: comparing ── -->
    <template v-else-if="phase === 'comparing'">
      <div class="flex-1 flex flex-col items-center justify-center gap-6 px-8">
        <div class="w-12 h-12 border-2 border-tinder-pink border-t-transparent rounded-full animate-spin" />
        <div class="text-center">
          <p class="text-[15px] font-semibold text-text-primary mb-1">正在对比 {{ selectedPapers.length }} 篇论文</p>
          <p class="text-[13px] text-text-muted">AI 正在分析，请稍等…</p>
        </div>
        <div class="w-full bg-bg-elevated rounded-2xl p-3 max-h-40 overflow-hidden text-[11px] text-text-muted leading-relaxed">
          <div v-if="markdown" class="line-clamp-[6]">{{ markdown.slice(0, 400) }}{{ markdown.length > 400 ? '…' : '' }}</div>
          <div v-else>连接中…</div>
        </div>
      </div>
    </template>

    <!-- ── Phase: result ── -->
    <template v-else-if="phase === 'result'">
      <div v-if="compareError" class="flex-1">
        <ErrorState :message="compareError" @retry="resetToSelect" />
      </div>
      <template v-else>
        <!-- Meta bar -->
        <div class="px-4 py-2 flex items-center gap-3 shrink-0">
          <p class="text-[12px] text-text-muted flex-1">{{ selectedPapers.length }} 篇论文</p>
          <div class="flex items-center gap-2">
            <input
              v-model="saveTitle"
              type="text"
              placeholder="对比标题"
              class="text-[12px] bg-bg-elevated border border-border rounded-lg px-2.5 py-1.5 text-text-primary outline-none w-40"
            />
            <button
              type="button"
              class="shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-medium"
              :class="savingResult ? 'bg-bg-elevated text-text-muted' : 'bg-tinder-green/15 text-tinder-green'"
              :disabled="savingResult"
              @click="doSave"
            >
              {{ savingResult ? '保存中…' : '保存' }}
            </button>
          </div>
        </div>

        <!-- Markdown result -->
        <div class="flex-1 overflow-y-auto px-4 pb-8 pt-2">
          <MarkdownRenderer :content="markdown" />
        </div>
      </template>
    </template>

    <!-- ── Paper picker sheet ── -->
    <BottomSheet
      :visible="pickerVisible"
      title="选择论文"
      height="80dvh"
      @close="pickerVisible = false"
    >
      <!-- Source tabs -->
      <div class="flex gap-1 mx-4 mb-2 mt-1 p-1 bg-bg rounded-xl border border-border">
        <button
          v-for="tab in sourceTabs"
          :key="tab.key"
          type="button"
          class="flex-1 py-1.5 rounded-lg text-[12px] font-medium transition-all"
          :class="pickerSourceTab === tab.key ? 'bg-tinder-blue/15 text-tinder-blue' : 'text-text-muted'"
          @click="pickerSourceTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="px-4 pb-2">
        <SearchBar v-model="pickerSearch" placeholder="搜索论文…" />
      </div>

      <LoadingState v-if="pickerLoading" message="加载中…" />
      <ErrorState v-else-if="pickerLoadError" :message="pickerLoadError" @retry="loadAllPickerPapers" />
      <div v-else-if="filteredPickerPapers.length === 0" class="px-4 py-8 text-center text-[13px] text-text-muted">
        {{ pickerSearch ? '没有匹配结果' : (pickerSourceTab === 'mypapers' ? '我的论文库为空，请先导入论文' : pickerSourceTab === 'kb' ? '知识库为空，请先收藏论文' : '暂无可选论文') }}
      </div>
      <div v-else class="pb-4">
        <div
          v-for="paper in filteredPickerPapers"
          :key="paper.paper_id"
          class="flex items-center gap-3 px-4 py-3 active:bg-bg-hover cursor-pointer"
          @click="pickPaper(paper)"
        >
          <div class="flex-1 min-w-0">
            <p class="text-[13px] font-medium text-text-primary line-clamp-2 leading-snug">
              {{ paper.title || paper.paper_id }}
            </p>
            <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
              <span
                class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                :class="paper.source === 'kb' ? 'bg-tinder-green/15 text-tinder-green' : 'bg-tinder-blue/15 text-tinder-blue'"
              >
                {{ paper.source === 'kb' ? '知识库' : '我的论文' }}
              </span>
              <span v-if="paper.institution" class="text-[11px] text-text-muted">{{ paper.institution }}</span>
            </div>
          </div>
          <div class="shrink-0 w-5 h-5 rounded-full border-2 border-border flex items-center justify-center">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </div>
        </div>
      </div>
    </BottomSheet>
  </div>
</template>
