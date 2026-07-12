<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchUserPaperDetail } from '../../api'
import type { PaperDetailResponse, PaperSummary, UserPaper } from '../../types/paper'
import ImmersivePaperReader from './ImmersivePaperReader.vue'

const props = defineProps<{
  paper: UserPaper
  relatedPapers: UserPaper[]
  position: number
  total: number
  canGoPrevious?: boolean
  canGoNext?: boolean
  returnLabel?: string
  decisionMode?: 'mypapers' | 'research'
  researchContext?: {
    question?: string
    paperCount?: number
  } | null
}>()

const emit = defineEmits<{
  exit: []
  previous: []
  next: []
  openPdf: [paper: UserPaper]
  openDetail: [paperId: string]
  compare: [paperIds: string[]]
  research: [paperIds: string[], paperTitles: Record<string, string>]
  selectRelated: [paperId: string]
}>()

const userPaperCache = new Map<string, UserPaper>()
const loadedPaper = ref<UserPaper | null>(null)
let loadVersion = 0

function toSummary(paper: UserPaper): PaperSummary {
  const base = paper.summary
  return {
    institution: base?.institution || paper.institution || '',
    short_title: base?.short_title || paper.title || paper.paper_id,
    '📖标题': base?.['📖标题'] || paper.title || paper.paper_id,
    '🌐来源': base?.['🌐来源'] || (paper.source_type === 'arxiv' ? 'arXiv' : '我的论文'),
    paper_id: paper.paper_id,
    '推荐理由': base?.['推荐理由'],
    '🛎️文章简介': base?.['🛎️文章简介'] || { '🔸研究问题': '', '🔸主要贡献': '' },
    '📝重点思路': base?.['📝重点思路'] || [],
    '🔎分析总结': base?.['🔎分析总结'] || [],
    '💡个人观点': base?.['💡个人观点'] || '',
    relevance_score: base?.relevance_score,
    abstract: base?.abstract || paper.abstract || '',
    categories: base?.categories || [],
    authors: base?.authors?.length ? base.authors : paper.authors,
    images: base?.images,
    image_count: base?.image_count,
  }
}

const effectivePaper = computed(() => loadedPaper.value ?? props.paper)
const summary = computed(() => toSummary(effectivePaper.value))
const relatedSummaries = computed(() => props.relatedPapers.map(toSummary))
const detailOverride = computed<PaperDetailResponse>(() => ({
  summary: summary.value,
  paper_assets: effectivePaper.value.paper_assets ?? null,
  date: effectivePaper.value.created_at?.slice(0, 10) || '',
  images: summary.value.images || [],
  arxiv_url: effectivePaper.value.external_url || '',
  pdf_url: effectivePaper.value.pdf_static_url || effectivePaper.value.arxiv_pdf_url || '',
}))
const title = computed(() => summary.value.short_title || summary.value['📖标题'] || summary.value.paper_id)

watch(
  () => props.paper.paper_id,
  async (paperId) => {
    const version = ++loadVersion
    loadedPaper.value = userPaperCache.get(paperId) ?? props.paper
    if (props.paper.process_status !== 'completed') return
    try {
      const paper = await fetchUserPaperDetail(paperId)
      if (version !== loadVersion) return
      userPaperCache.set(paperId, paper)
      loadedPaper.value = paper
    } catch {
      // The list payload still provides enough metadata for a graceful reading fallback.
    }
  },
  { immediate: true },
)

function comparePaper() {
  const related = props.relatedPapers[0]
  if (related) emit('compare', [props.paper.paper_id, related.paper_id])
}

function startResearch() {
  emit('research', [props.paper.paper_id], { [props.paper.paper_id]: title.value })
}

function handleKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('exit')
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp' || event.key === 'k' || event.key === 'K') {
    event.preventDefault()
    emit('previous')
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown' || event.key === 'j' || event.key === 'J') {
    event.preventDefault()
    emit('next')
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <ImmersivePaperReader
    :paper="summary"
    :related-papers="relatedSummaries"
    :detail-override="detailOverride"
    :publication-date="detailOverride.date"
    :position="position"
    :total="total"
    :can-go-previous="canGoPrevious"
    :can-go-next="canGoNext"
    :can-compare="relatedPapers.length > 0"
    :show-collection-action="false"
    :show-bookmark-action="false"
    :return-label="returnLabel || '返回我的论文'"
    :decision-mode="decisionMode || 'mypapers'"
    :research-context="researchContext"
    source-scope="mypapers"
    @exit="emit('exit')"
    @previous="emit('previous')"
    @next="emit('next')"
    @skip="emit('next')"
    @compare="decisionMode === 'research' ? emit('openPdf', effectivePaper) : comparePaper()"
    @open-pdf="emit('openPdf', effectivePaper)"
    @open-detail="emit('openDetail', paper.paper_id)"
    @start-research="decisionMode === 'research' ? emit('exit') : startResearch()"
    @select-related="emit('selectRelated', $event)"
  />
</template>
