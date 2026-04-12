<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import PaperListItem from '@/components/PaperListItem.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import {
  fetchKbTree,
  generateIdeasStream,
  fetchIdeaStats,
} from '@shared/api'
import type { KbTree, KbFolder, KbPaper } from '@shared/types/kb'
import { showToast } from 'vant'

defineOptions({ name: 'WorkbenchView' })

const router = useRouter()

const kbTree = ref<KbTree | null>(null)
const kbLoading = ref(false)
const pickerVisible = ref(false)
const pickerSearch = ref('')
const selectedPapers = ref<KbPaper[]>([])

const atomCount = ref(0)
const candidateCount = ref(0)
const statsLoaded = ref(false)

const generating = ref(false)
const generateLog = ref('')
const generateDone = ref(false)
const generatingVisible = ref(false)

type Strategy = 'synthesis' | 'gap' | 'transfer' | 'augmentation'
const selectedStrategy = ref<Strategy>('synthesis')
const strategies: { key: Strategy; label: string; desc: string }[] = [
  { key: 'synthesis', label: '综合创新', desc: '融合多篇论文的方法，生成全新研究方向' },
  { key: 'gap', label: '空白探索', desc: '识别现有研究未解决的问题，提出解决方案' },
  { key: 'transfer', label: '跨域迁移', desc: '将一个领域的方法迁移到另一个领域' },
  { key: 'augmentation', label: '扩展增强', desc: '在现有研究基础上提出改进和增强方案' },
]

async function loadKb() {
  if (kbTree.value) return
  kbLoading.value = true
  try {
    kbTree.value = await fetchKbTree('kb')
  } finally {
    kbLoading.value = false
  }
}

async function loadStats() {
  try {
    const stats = await fetchIdeaStats()
    atomCount.value = stats.atom_count
    candidateCount.value = stats.candidate_count
    statsLoaded.value = true
  } catch { /* best-effort */ }
}

onMounted(loadStats)

function getAllKbPapers(): KbPaper[] {
  if (!kbTree.value) return []
  const result: KbPaper[] = [...kbTree.value.papers]
  function collect(f: KbFolder) { result.push(...f.papers); f.children.forEach(collect) }
  kbTree.value.folders.forEach(collect)
  return result
}

const filteredPickerPapers = computed(() => {
  const q = pickerSearch.value.trim().toLowerCase()
  const selected = new Set(selectedPapers.value.map((p) => p.paper_id))
  return getAllKbPapers().filter((p) => {
    if (selected.has(p.paper_id)) return false
    if (!q) return true
    const title = (p.paper_data?.short_title || p.paper_data?.['📖标题'] || '').toLowerCase()
    return title.includes(q)
  })
})

async function openPicker() {
  await loadKb()
  pickerSearch.value = ''
  pickerVisible.value = true
}

function togglePaper(paper: KbPaper) {
  const idx = selectedPapers.value.findIndex((p) => p.paper_id === paper.paper_id)
  if (idx >= 0) selectedPapers.value.splice(idx, 1)
  else {
    if (selectedPapers.value.length >= 5) { showToast('最多选 5 篇'); return }
    selectedPapers.value.push(paper)
  }
}

async function doGenerate() {
  if (generating.value) return
  generating.value = true
  generateDone.value = false
  generateLog.value = '正在连接…'
  generatingVisible.value = true
  try {
    const resp = await generateIdeasStream({
      strategies: [selectedStrategy.value],
    })
    if (!resp.ok) { generateLog.value = '生成失败，请重试'; return }
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) return
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
            if (obj.log) generateLog.value = obj.log
            if (obj.message) generateLog.value = obj.message
          } catch { /* ignore */ }
        }
      }
    }
    generateLog.value = '生成完成！前往灵感库查看新灵感'
    generateDone.value = true
    await loadStats()
  } catch (e: any) {
    generateLog.value = `出错了：${e?.message || '未知错误'}`
  } finally {
    generating.value = false
  }
}


</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-y-auto">
    <PageHeader title="灵感工作台" @back="router.back()" />

    <div class="px-4 pb-8 space-y-5">

      <!-- Stats row -->
      <div v-if="statsLoaded" class="grid grid-cols-2 gap-3">
        <div class="card-section text-center">
          <p class="text-[22px] font-bold text-tinder-blue">{{ atomCount }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">知识原子</p>
        </div>
        <div class="card-section text-center">
          <p class="text-[22px] font-bold text-tinder-gold">{{ candidateCount }}</p>
          <p class="text-[11px] text-text-muted mt-0.5">灵感候选</p>
        </div>
      </div>

      <!-- No atoms hint -->
      <div v-if="statsLoaded && atomCount === 0" class="p-4 rounded-2xl bg-tinder-pink/10 border border-tinder-pink/20">
        <p class="text-[13px] text-tinder-pink font-medium mb-1">知识原子为空</p>
        <p class="text-[12px] text-text-secondary leading-relaxed">先去推荐页收藏论文到知识库，系统会自动提取知识原子，之后才能生成灵感。</p>
        <button type="button" class="btn-text mt-2" @click="router.push('/recommend')">去看今日推荐 →</button>
      </div>

      <!-- Strategy selector -->
      <div>
        <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-3">生成策略</p>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="s in strategies"
            :key="s.key"
            type="button"
            class="p-3 rounded-2xl border text-left transition-all"
            :class="selectedStrategy === s.key
              ? 'border-tinder-pink bg-tinder-pink/10'
              : 'border-border bg-bg-elevated'"
            @click="selectedStrategy = s.key"
          >
            <p class="text-[13px] font-semibold text-text-primary mb-1">{{ s.label }}</p>
            <p class="text-[11px] text-text-muted leading-relaxed line-clamp-2">{{ s.desc }}</p>
          </button>
        </div>
      </div>

      <!-- Optional paper scope -->
      <div>
        <div class="flex items-center justify-between mb-2">
          <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider">论文范围（选填）</p>
          <span class="text-[11px] text-text-muted">{{ selectedPapers.length === 0 ? '全部知识库' : `已选 ${selectedPapers.length} 篇` }}</span>
        </div>
        <div v-if="selectedPapers.length > 0" class="space-y-2 mb-2">
          <div
            v-for="paper in selectedPapers"
            :key="paper.paper_id"
            class="flex items-center gap-2 p-2.5 rounded-xl bg-bg-elevated border border-border"
          >
            <p class="text-[12px] text-text-primary flex-1 line-clamp-1">{{ paper.paper_data?.short_title || paper.paper_id }}</p>
            <button type="button" class="text-tinder-pink" @click="togglePaper(paper)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>
        <button
          type="button"
          class="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-dashed border-border text-text-muted text-[13px] active:bg-bg-hover"
          @click="openPicker"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          添加特定论文
        </button>
      </div>

      <!-- Generate button -->
      <button
        type="button"
        class="btn-primary"
        :disabled="generating || atomCount === 0"
        @click="doGenerate"
      >
        {{ generating ? '生成中…' : '🧪 生成新灵感' }}
      </button>

      <!-- Navigate to idea list -->
      <button
        type="button"
        class="btn-ghost w-full"
        @click="router.push('/idea')"
      >
        查看全部灵感 ({{ candidateCount }})
      </button>
    </div>

    <!-- Picker sheet -->
    <BottomSheet :visible="pickerVisible" title="选择论文" height="80dvh" @close="pickerVisible = false">
      <div class="px-4 pb-2 pt-1">
        <SearchBar v-model="pickerSearch" placeholder="搜索…" />
      </div>
      <LoadingState v-if="kbLoading" message="加载中…" />
      <div v-else-if="filteredPickerPapers.length === 0" class="px-4 py-8 text-center text-[13px] text-text-muted">
        {{ pickerSearch ? '没有匹配' : '知识库为空' }}
      </div>
      <div v-else class="pb-4">
        <PaperListItem
          v-for="paper in filteredPickerPapers"
          :key="paper.paper_id"
          :paper="paper"
          @click="togglePaper(paper)"
        />
      </div>
    </BottomSheet>

    <!-- Generate progress sheet -->
    <BottomSheet :visible="generatingVisible" title="生成灵感" @close="!generating && (generatingVisible = false)">
      <div class="px-5 py-6 flex flex-col items-center gap-4 min-h-[160px]">
        <div v-if="generating" class="w-8 h-8 border-2 border-tinder-pink border-t-transparent rounded-full animate-spin" />
        <svg v-else-if="generateDone" class="text-tinder-green" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
        </svg>
        <p class="text-[14px] text-text-secondary text-center leading-relaxed">{{ generateLog }}</p>
        <div v-if="!generating" class="flex gap-3 w-full">
          <button type="button" class="btn-ghost flex-1" @click="generatingVisible = false">关闭</button>
          <button v-if="generateDone" type="button" class="btn-primary flex-1" @click="generatingVisible = false; router.push('/idea')">
            查看灵感
          </button>
        </div>
      </div>
    </BottomSheet>
  </div>
</template>
