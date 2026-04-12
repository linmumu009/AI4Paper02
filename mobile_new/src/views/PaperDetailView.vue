<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import { fetchPaperDetail, addKbPaper, downloadPaperFile } from '@shared/api'
import { fetchKbPaperFiles, processKbPaper, translateKbPaper, retranslateKbPaper, deleteKbPaperDerivative } from '@shared/api/kb-processing'
import {
  fetchUserPaperDetail,
  processUserPaper,
  translateUserPaper,
  retranslateUserPaper,
  fetchUserPaperFiles,
  deleteUserPaperDerivative,
} from '@shared/api/user-papers'
import type { UserPaper } from '@shared/types/user-papers'
import type { PaperDetailResponse } from '@shared/types/paper'
import type { KbPaperFilesResponse } from '@shared/types/kb'
import type { PaperFileType, DownloadFormat } from '@shared/api/download'
import { isAuthenticated } from '@shared/stores/auth'
import { useEngagement } from '@shared/composables/useEngagement'
import { showToast, showDialog } from 'vant'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const route = useRoute()
const engagement = useEngagement()

// Whether this paper comes from "my papers" (user-uploaded)
const isUserPaper = computed(() => route.query.source === 'user-paper')
// For user papers, store the raw UserPaper object for file operations
const userPaperData = ref<UserPaper | null>(null)

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')
const saved = ref(false)
const activeTab = ref<'summary' | 'assets'>('summary')
const lightboxSrc = ref<string | null>(null)
const downloadSheetVisible = ref(false)
const moreSheetVisible = ref(false)

// Scroll-based bottom bar auto-hide
const bottomBarVisible = ref(true)
let lastScrollTop = 0
function onContentScroll(e: Event) {
  const el = e.target as HTMLElement
  const st = el.scrollTop
  if (st > lastScrollTop && st > 60) {
    bottomBarVisible.value = false
  } else {
    bottomBarVisible.value = true
  }
  lastScrollTop = st
}

const summary = computed(() => detail.value?.summary ?? null)
const assets = computed(() => detail.value?.paper_assets ?? null)

const DEFAULT_DOC_TITLE = 'AI4Papers 移动版'

function adaptUserPaperToDetail(up: UserPaper): PaperDetailResponse {
  return {
    summary: up.summary ?? ({} as any),
    paper_assets: up.paper_assets ?? null,
    date: up.created_at?.split('T')[0] ?? '',
    images: [],
    arxiv_url: up.arxiv_pdf_url ?? up.external_url ?? '',
    pdf_url: up.pdf_static_url ?? '',
  }
}

async function loadDetail() {
  loading.value = true
  error.value = ''
  try {
    if (isUserPaper.value) {
      const up = await fetchUserPaperDetail(props.id)
      userPaperData.value = up
      if (!up.summary) {
        error.value = '论文尚未处理，请先触发处理后再查看详情'
        detail.value = null
      } else {
        detail.value = adaptUserPaperToDetail(up)
      }
    } else {
      detail.value = await fetchPaperDetail(props.id)
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  engagement.record('view', 'paper-detail', props.id)
  await loadDetail()
})

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      engagement.record('view', 'paper-detail', newId)
      loadDetail()
    }
  },
)

watch(
  () => summary.value?.short_title,
  (t) => {
    document.title = t ? `${t} · ${DEFAULT_DOC_TITLE}` : DEFAULT_DOC_TITLE
  },
  { immediate: true },
)

function goBack() {
  document.title = DEFAULT_DOC_TITLE
  if (window.history.length > 1) router.back()
  else router.push('/recommend')
}

async function savePaper() {
  if (!summary.value) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  try {
    await addKbPaper(summary.value.paper_id, summary.value)
    saved.value = true
  } catch { /* ignore */ }
}

function openArxiv() {
  const url = isUserPaper.value
    ? (userPaperData.value?.arxiv_pdf_url ?? userPaperData.value?.external_url)
    : detail.value?.arxiv_url
  if (url) window.open(url, '_blank')
}

function openPdf() {
  const url = isUserPaper.value
    ? (userPaperData.value?.pdf_static_url)
    : detail.value?.pdf_url
  if (url) window.open(url, '_blank')
}

function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}

function tierBadgeClass(tier?: number): string {
  switch (tier) {
    case 1: return 'institution-badge institution-badge--t1'
    case 2: return 'institution-badge institution-badge--t2'
    case 3: return 'institution-badge institution-badge--t3'
    default: return 'institution-badge'
  }
}

// ── Structured analysis (assets) accordion ──

const blockMetas: Record<string, { label: string; icon: string; special?: string }> = {
  paper_profile:               { label: '论文档案',   icon: '📋', special: 'profile' },
  background:                  { label: '研究背景',   icon: '🏛️' },
  objective:                   { label: '研究目标',   icon: '🎯' },
  method:                      { label: '方法',       icon: '⚙️' },
  data:                        { label: '数据',       icon: '📊' },
  experiment_or_argumentation: { label: '实验与论证', icon: '🧪' },
  metrics:                     { label: '评价指标',   icon: '📏' },
  results:                     { label: '实验结果',   icon: '📈' },
  evidence_chain:              { label: '证据链',     icon: '🔗' },
  figures_tables_appendix:     { label: '图表与附录', icon: '📑' },
  limitations:                 { label: '局限性',     icon: '⚠️' },
  critical_analysis:           { label: '批判性分析', icon: '🔍', special: 'critical' },
  summary:                     { label: '综合总结',   icon: '💡', special: 'summary' },
  experiment:                  { label: '实验设置',   icon: '🧪' },
}

const subFieldLabels: Record<string, string> = {
  research_questions:                       '研究问题',
  claimed_contributions:                    '作者声称的贡献',
  input:                                    '输入',
  task_or_object:                           '任务/对象',
  architecture_or_paradigm:                '架构/范式',
  key_mechanisms:                           '关键机制',
  training_required:                        '是否训练',
  training_or_optimization:                '训练/优化',
  inference_strategy:                       '推理策略',
  novelty:                                  '创新点',
  datasets_or_materials:                   '数据集/材料',
  data_source:                              '数据来源',
  data_scale:                               '数据规模',
  domain_scope:                             '领域范围',
  design:                                   '实验设计',
  baselines_or_comparators:                '基线/对照',
  variables_or_modules:                     '变量/模块',
  ablation_or_counterfactual:              '消融/反事实',
  argumentation_structure:                 '论证结构',
  metric_names:                             '指标名称',
  evaluation_protocol:                      '评估协议',
  judge_or_annotation_method:              'Judge/标注方法',
  main_findings:                            '主要发现',
  numerical_results:                        '数值结果',
  phenomena:                               '观察现象',
  mechanism_explanations:                  '机制解释',
  claim_to_evidence:                        '结论-证据对应',
  strongly_supported_claims:               '强支持结论',
  weakly_supported_claims:                 '弱支持结论',
  unsupported_or_overextended_claims:      '支持不足/过度外推',
  key_evidence_from_figures_tables_appendix: '图表/附录关键证据',
  scope_boundaries:                         '范围边界',
  threats_to_validity:                      '效度威胁',
  generalization_limits:                    '泛化边界',
  strongest_argument:                       '最强论点',
  weakest_argument:                         '最弱论点',
  substantive_contributions:               '实质性贡献',
  packaging_or_framing_elements:           '包装/叙事成分',
  strong_conclusions:                       '强支持的结论',
  weak_conclusions:                         '弱支持的结论',
  needs_more_evidence:                      '需要更多证据',
  reproduction_or_extension_priorities:    '复现/扩展优先级',
  one_sentence_summary:                     '一句话概括',
  three_takeaways:                          '三条要点',
  literature_review_comment:               '文献综述评述',
  title:                                    '标题',
  authors:                                  '作者',
  affiliations:                             '机构',
  year:                                     '年份',
  publication_status:                       '发表状态',
  paper_type:                               '论文类型',
  research_domain:                          '研究领域',
  problem_gap:                              '问题空白',
  position_in_literature:                  '在文献中的定位',
}

// Default open: method + results to give immediate value without overwhelming
const openSections = ref<Set<string>>(new Set(['method', 'results']))

function toggleSection(key: string) {
  if (openSections.value.has(key)) {
    openSections.value.delete(key)
  } else {
    openSections.value.add(key)
  }
  openSections.value = new Set(openSections.value)
}

const normalizedBlocks = computed(() => {
  const raw = { ...(assets.value?.blocks || {}) } as Record<string, any>
  if (raw.experiment && !raw.experiment_or_argumentation) {
    raw.experiment_or_argumentation = raw.experiment
    delete raw.experiment
  }
  return raw
})

function isEmptyValue(v: unknown): boolean {
  if (v === null || v === undefined) return true
  if (typeof v === 'string') return v.trim() === ''
  if (Array.isArray(v)) return v.length === 0
  return false
}

function blockHasContent(key: string): boolean {
  const block = normalizedBlocks.value[key]
  if (!block || typeof block !== 'object') return false
  return Object.entries(block).some(([, v]) => {
    if (Array.isArray(v)) return v.length > 0
    if (typeof v === 'string') return v.trim() !== ''
    if (v !== null && v !== undefined) return true
    return false
  })
}

const specialCardKeys = new Set(['paper_profile', 'critical_analysis', 'summary'])

const availableKeys = computed(() =>
  Object.keys(blockMetas).filter(key => {
    if (key === 'experiment' && normalizedBlocks.value.experiment_or_argumentation) return false
    return blockHasContent(key)
  }),
)

const topCardKeys = computed(() => availableKeys.value.filter(k => k === 'paper_profile'))
const accordionKeys = computed(() => availableKeys.value.filter(k => !specialCardKeys.has(k)))
const bottomCardKeys = computed(() => availableKeys.value.filter(k => specialCardKeys.has(k) && k !== 'paper_profile'))

function getExtraFields(block: Record<string, unknown>): Array<{ key: string; label: string; value: unknown }> {
  const skip = new Set(['text', 'bullets'])
  return Object.entries(block)
    .filter(([k, v]) => !skip.has(k) && !isEmptyValue(v))
    .map(([k, v]) => ({ key: k, label: subFieldLabels[k] || k, value: v }))
}

const downloadOptions: Array<{ label: string; fileType: PaperFileType; format: DownloadFormat; desc: string }> = [
  { label: 'PDF 原文', fileType: 'pdf', format: 'pdf', desc: '原始论文 PDF' },
  { label: '结构化 Markdown', fileType: 'mineru', format: 'md', desc: '提取后的正文 .md' },
  { label: '中文翻译 Markdown', fileType: 'zh', format: 'md', desc: '中文译文 .md' },
  { label: '双语 Markdown', fileType: 'bilingual', format: 'md', desc: '中英对照 .md' },
  { label: '双语 Word', fileType: 'bilingual', format: 'docx', desc: '中英对照 .docx' },
]

function doDownload(opt: typeof downloadOptions[0]) {
  if (!summary.value) return
  if (isUserPaper.value && userPaperData.value) {
    // For user papers, use static URLs directly
    const urlMap: Record<string, string | null | undefined> = {
      pdf: userPaperData.value.pdf_static_url,
      mineru: userPaperData.value.mineru_static_url,
      zh: userPaperData.value.zh_static_url,
      bilingual: userPaperData.value.bilingual_static_url,
    }
    const url = urlMap[opt.fileType]
    if (url) {
      window.open(url, '_blank')
      showToast('已开始下载')
    } else {
      showToast('该文件尚未生成')
    }
  } else {
    downloadPaperFile(summary.value.paper_id, opt.fileType, 'kb', opt.format)
    showToast('已开始下载')
  }
  downloadSheetVisible.value = false
}

// ── Derivative file management ──
const filesSheetVisible = ref(false)
const filesData = ref<KbPaperFilesResponse | null>(null)
const filesLoading = ref(false)
const filesError = ref('')
const processingAction = ref<string | null>(null)

async function openFilesSheet() {
  if (!summary.value && !isUserPaper.value) return
  const paperId = props.id
  filesSheetVisible.value = true
  filesLoading.value = true
  filesError.value = ''
  try {
    if (isUserPaper.value) {
      const res = await fetchUserPaperFiles(paperId)
      filesData.value = { ...res, process_status: '', process_step: '', translate_progress: 0 } as KbPaperFilesResponse
    } else if (summary.value) {
      filesData.value = await fetchKbPaperFiles(summary.value.paper_id, 'kb')
    }
  } catch {
    filesError.value = '加载失败'
  } finally {
    filesLoading.value = false
  }
}

async function triggerProcess() {
  if (processingAction.value) return
  processingAction.value = 'process'
  try {
    if (isUserPaper.value) {
      await processUserPaper(props.id)
    } else if (summary.value) {
      await processKbPaper(summary.value.paper_id, 'kb')
    }
    showToast('已提交处理任务')
    await openFilesSheet()
  } catch {
    showToast('操作失败')
  } finally {
    processingAction.value = null
  }
}

async function triggerTranslate() {
  if (processingAction.value) return
  processingAction.value = 'translate'
  try {
    if (isUserPaper.value) {
      await translateUserPaper(props.id)
    } else if (summary.value) {
      await translateKbPaper(summary.value.paper_id, 'kb')
    }
    showToast('已提交翻译任务')
    await openFilesSheet()
  } catch {
    showToast('操作失败')
  } finally {
    processingAction.value = null
  }
}

async function triggerRetranslate() {
  if (processingAction.value) return
  processingAction.value = 'retranslate'
  try {
    if (isUserPaper.value) {
      await retranslateUserPaper(props.id)
    } else if (summary.value) {
      await retranslateKbPaper(summary.value.paper_id, 'kb')
    }
    showToast('已提交重新翻译任务')
    await openFilesSheet()
  } catch {
    showToast('操作失败')
  } finally {
    processingAction.value = null
  }
}

async function deleteDerivative(type: 'mineru' | 'zh' | 'bilingual') {
  if (processingAction.value) return
  try {
    await showDialog({ title: '确认删除', message: `将删除"${type === 'mineru' ? 'MinerU结构化' : type === 'zh' ? '中文翻译' : '双语对照'}"文件，此操作不可恢复。`, confirmButtonText: '删除', confirmButtonColor: 'var(--color-tinder-pink)', cancelButtonText: '取消' })
  } catch {
    return
  }
  processingAction.value = `delete_${type}`
  try {
    if (isUserPaper.value) {
      await deleteUserPaperDerivative(props.id, type)
    } else if (summary.value) {
      await deleteKbPaperDerivative(summary.value.paper_id, type, 'kb')
    }
    showToast('已删除')
    await openFilesSheet()
  } catch {
    showToast('删除失败')
  } finally {
    processingAction.value = null
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg min-h-0">
    <!-- Glass header -->
    <PageHeader :glass="true" @back="goBack">
      <template #title>
        <span class="text-[15px] font-semibold text-text-primary truncate">论文详情</span>
      </template>
      <template #right>
        <button
          v-if="summary && !loading"
          type="button"
          class="px-3 py-1.5 rounded-full text-sm font-semibold border-none shrink-0 transition-all"
          :class="saved
            ? 'bg-tinder-green/15 text-tinder-green border border-tinder-green/30'
            : 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'"
          @click="savePaper"
        >
          {{ saved ? '已收藏' : '收藏' }}
        </button>
      </template>
    </PageHeader>

    <!-- Loading / Error full-screen states -->
    <LoadingState v-if="loading" message="加载中..." class="flex-1" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadDetail" />

    <!-- Main content -->
    <div v-else-if="summary" class="flex-1 overflow-y-auto min-h-0 pb-20" @scroll="onContentScroll">

      <!-- ── HERO SECTION ── -->
      <div class="px-5 pt-4 pb-5 border-b border-border/50">
        <!-- Institution + score row -->
        <div class="flex items-center justify-between gap-3 mb-3">
          <span :class="tierBadgeClass(summary.institution_tier)" class="max-w-[70%]">
            {{ summary.institution || '未知机构' }}
            <span v-if="summary.institution_tier && summary.institution_tier <= 3" class="tier-tag-mobile">T{{ summary.institution_tier }}</span>
          </span>
          <div
            v-if="summary.relevance_score != null"
            class="shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-sm font-bold border-2"
            :class="summary.relevance_score >= 0.7
              ? 'border-tag-score-high text-tag-score-high'
              : summary.relevance_score >= 0.4
                ? 'border-tag-score-mid text-tag-score-mid'
                : 'border-tag-score-low text-tag-score-low'"
            :style="{ background: 'var(--color-bg-elevated)' }"
          >
            {{ (summary.relevance_score * 100).toFixed(0) }}
          </div>
        </div>

        <!-- Main title -->
        <h1 class="text-[19px] font-bold text-text-primary leading-snug mb-1.5">
          {{ summary.short_title }}
        </h1>
        <p v-if="summary['📖标题']" class="text-sm text-text-secondary leading-relaxed mb-1">
          {{ summary['📖标题'] }}
        </p>
        <p v-if="summary['🌐来源']" class="text-xs text-text-muted font-mono">{{ summary['🌐来源'] }}</p>

        <!-- Recommendation reason -->
        <div
          v-if="summary['推荐理由']"
          class="mt-3 px-3.5 py-2.5 rounded-xl bg-tinder-blue/8 border border-tinder-blue/20"
        >
          <p class="text-sm text-tinder-blue leading-relaxed">
            <span class="font-semibold">推荐理由：</span>{{ summary['推荐理由'] }}
          </p>
        </div>
      </div>

      <!-- ── TAB BAR (sticky; only shown when paper_assets exists) ── -->
      <div
        v-if="assets?.blocks"
        class="sticky top-0 z-10 flex border-b border-border bg-bg/95 backdrop-blur-sm"
      >
        <button
          type="button"
          class="detail-tab"
          :class="activeTab === 'summary' ? 'detail-tab--active' : ''"
          @click="activeTab = 'summary'"
        >
          AI 摘要
        </button>
        <button
          type="button"
          class="detail-tab"
          :class="activeTab === 'assets' ? 'detail-tab--active' : ''"
          @click="activeTab = 'assets'"
        >
          结构化分析
        </button>
      </div>

      <!-- ── AI SUMMARY TAB ── -->
      <template v-if="activeTab === 'summary'">

        <!-- 文章简介 -->
        <div
          v-if="summary['🛎️文章简介']?.['🔸研究问题'] || summary['🛎️文章简介']?.['🔸主要贡献']"
          class="px-5 py-4 border-b border-border/40"
        >
          <h3 class="section-title">文章简介</h3>
          <div class="space-y-2">
            <p v-if="summary['🛎️文章简介']?.['🔸研究问题']" class="section-body">
              <span class="text-tinder-pink font-medium">研究问题：</span>{{ summary['🛎️文章简介']['🔸研究问题'] }}
            </p>
            <p v-if="summary['🛎️文章简介']?.['🔸主要贡献']" class="section-body">
              <span class="text-tinder-pink font-medium">主要贡献：</span>{{ summary['🛎️文章简介']['🔸主要贡献'] }}
            </p>
          </div>
        </div>

        <!-- 重点思路 -->
        <div v-if="summary['📝重点思路']?.length" class="px-5 py-4 border-b border-border/40">
          <h3 class="section-title">重点思路</h3>
          <div class="space-y-3">
            <div v-for="(item, idx) in summary['📝重点思路']" :key="'m' + idx" class="flex items-start gap-3">
              <span class="shrink-0 w-6 h-6 rounded-full bg-tinder-blue/15 text-tinder-blue flex items-center justify-center text-xs font-bold mt-0.5">
                {{ idx + 1 }}
              </span>
              <p class="section-body leading-relaxed">{{ cleanBullet(item) }}</p>
            </div>
          </div>
        </div>

        <!-- 分析总结 -->
        <div v-if="summary['🔎分析总结']?.length" class="px-5 py-4 border-b border-border/40">
          <h3 class="section-title">分析总结</h3>
          <div class="space-y-2.5">
            <div v-for="(item, idx) in summary['🔎分析总结']" :key="'f' + idx" class="flex items-start gap-2.5">
              <span class="shrink-0 w-2 h-2 rounded-full bg-tinder-gold mt-2" />
              <p class="section-body leading-relaxed">{{ cleanBullet(item) }}</p>
            </div>
          </div>
        </div>

        <!-- 个人观点 + 一句话记忆 -->
        <div v-if="summary['💡个人观点'] || summary['一句话记忆版']" class="px-5 py-4 border-b border-border/40">
          <div v-if="summary['💡个人观点']" :class="{ 'mb-3 pb-3 border-b border-border/40': summary['一句话记忆版'] }">
            <h3 class="section-title">个人观点</h3>
            <p class="section-body italic leading-relaxed">{{ summary['💡个人观点'] }}</p>
          </div>
          <div v-if="summary['一句话记忆版']">
            <p class="text-sm text-text-muted leading-relaxed italic">
              <span class="not-italic font-semibold text-text-secondary">💡 一句话记忆：</span>{{ summary['一句话记忆版'] }}
            </p>
          </div>
        </div>

      </template>

      <!-- ── STRUCTURED ANALYSIS TAB ── -->
      <template v-else-if="activeTab === 'assets' && assets?.blocks">
        <div class="px-4 py-4 space-y-3">

          <!-- paper_profile card (top, collapsible) -->
          <template v-for="key in topCardKeys" :key="key">
            <div class="rounded-xl overflow-hidden border border-border">
              <button
                type="button"
                class="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated text-left border-none border-l-2 border-tinder-pink/30 transition-colors active:bg-bg-hover"
                :class="openSections.has(key) ? 'rounded-t-xl' : 'rounded-xl'"
                @click="toggleSection(key)"
              >
                <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <span>{{ blockMetas[key]?.icon }}</span>
                  {{ blockMetas[key]?.label }}
                </span>
                <svg
                  xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
                  class="text-text-muted transition-transform shrink-0"
                  :class="openSections.has(key) ? 'rotate-180' : ''"
                ><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <div class="accordion-body" :class="openSections.has(key) ? 'is-open' : ''">
                <div>
                  <div class="px-4 py-3 border-l-2 border-tinder-pink/20 bg-bg-card space-y-2.5">
                    <template v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)" :key="field.key">
                      <div>
                        <span class="text-xs text-text-muted block mb-0.5">{{ field.label }}</span>
                        <span v-if="typeof field.value === 'string' || typeof field.value === 'number'" class="text-sm text-text-secondary">{{ field.value }}</span>
                        <div v-else-if="Array.isArray(field.value)" class="flex flex-wrap gap-1 mt-0.5">
                          <span
                            v-for="(item, idx) in (field.value as string[])"
                            :key="idx"
                            class="px-1.5 py-0.5 rounded text-xs bg-bg-elevated border border-border text-text-secondary"
                          >{{ item }}</span>
                        </div>
                      </div>
                    </template>
                    <p v-if="(normalizedBlocks[key] as any)?.text" class="text-sm text-text-secondary leading-relaxed pt-1">
                      {{ (normalizedBlocks[key] as any).text }}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Regular accordion blocks -->
          <template v-for="key in accordionKeys" :key="key">
            <div class="rounded-xl overflow-hidden border border-border">
              <button
                type="button"
                class="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated text-left border-none border-l-2 border-tinder-pink/30 transition-colors active:bg-bg-hover"
                :class="openSections.has(key) ? 'rounded-t-xl' : 'rounded-xl'"
                @click="toggleSection(key)"
              >
                <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <span>{{ blockMetas[key]?.icon }}</span>
                  {{ blockMetas[key]?.label }}
                </span>
                <svg
                  xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
                  class="text-text-muted transition-transform shrink-0"
                  :class="openSections.has(key) ? 'rotate-180' : ''"
                ><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <div class="accordion-body" :class="openSections.has(key) ? 'is-open' : ''">
                <div>
                  <div class="px-4 py-3 border-l-2 border-tinder-pink/20 bg-bg-card space-y-3">
                    <p v-if="(normalizedBlocks[key] as any)?.text" class="text-sm text-text-secondary leading-relaxed">
                      {{ (normalizedBlocks[key] as any).text }}
                    </p>
                    <ul v-if="(normalizedBlocks[key] as any)?.bullets?.length" class="space-y-1.5">
                      <li
                        v-for="(bullet, idx) in (normalizedBlocks[key] as any).bullets"
                        :key="idx"
                        class="text-sm text-text-secondary leading-relaxed pl-3 border-l-2 border-tinder-pink/20"
                      >{{ bullet }}</li>
                    </ul>
                    <template v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)" :key="field.key">
                      <div>
                        <div class="text-xs font-semibold text-text-muted mb-1 uppercase tracking-wide">{{ field.label }}</div>
                        <p v-if="typeof field.value === 'string' || typeof field.value === 'number'" class="text-sm text-text-secondary leading-relaxed pl-2 border-l-2 border-tinder-blue/20">{{ field.value }}</p>
                        <ul v-else-if="Array.isArray(field.value)" class="space-y-1">
                          <li
                            v-for="(item, idx) in (field.value as string[])"
                            :key="idx"
                            class="text-sm text-text-secondary leading-relaxed pl-3 border-l-2 border-tinder-blue/20"
                          >{{ item }}</li>
                        </ul>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Special bottom cards: critical_analysis & summary -->
          <template v-for="key in bottomCardKeys" :key="key">
            <div
              class="rounded-xl overflow-hidden border"
              :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
            >
              <button
                type="button"
                class="w-full flex items-center justify-between px-4 py-3 text-left border-none transition-colors active:opacity-90"
                :class="key === 'critical_analysis'
                  ? (openSections.has(key) ? 'bg-amber-500/10 rounded-t-xl' : 'bg-amber-500/5 rounded-xl')
                  : (openSections.has(key) ? 'bg-tinder-blue/10 rounded-t-xl' : 'bg-tinder-blue/5 rounded-xl')"
                @click="toggleSection(key)"
              >
                <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <span>{{ blockMetas[key]?.icon }}</span>
                  {{ blockMetas[key]?.label }}
                </span>
                <svg
                  xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
                  class="text-text-muted transition-transform shrink-0"
                  :class="openSections.has(key) ? 'rotate-180' : ''"
                ><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <div
                class="accordion-body"
                :class="[
                  openSections.has(key) ? 'is-open' : '',
                  key === 'critical_analysis' ? 'bg-amber-500/5' : 'bg-tinder-blue/5',
                ]"
              >
                <div>
                  <div class="px-4 py-3 space-y-3">
                    <p v-if="(normalizedBlocks[key] as any)?.text" class="text-sm text-text-secondary leading-relaxed">
                      {{ (normalizedBlocks[key] as any).text }}
                    </p>
                    <ul v-if="(normalizedBlocks[key] as any)?.bullets?.length" class="space-y-1.5">
                      <li
                        v-for="(b, idx) in (normalizedBlocks[key] as any).bullets"
                        :key="idx"
                        class="text-sm text-text-secondary pl-3 border-l-2"
                        :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
                      >{{ b }}</li>
                    </ul>
                    <template v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)" :key="field.key">
                      <div>
                        <div class="text-xs font-semibold text-text-muted mb-1 uppercase tracking-wide">{{ field.label }}</div>
                        <p
                          v-if="typeof field.value === 'string'"
                          class="text-sm text-text-secondary leading-relaxed pl-2 border-l-2"
                          :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
                        >{{ field.value }}</p>
                        <ul v-else-if="Array.isArray(field.value)" class="space-y-1">
                          <li
                            v-for="(item, idx) in (field.value as string[])"
                            :key="idx"
                            class="text-sm text-text-secondary pl-3 border-l-2"
                            :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
                          >{{ item }}</li>
                        </ul>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <p v-if="!availableKeys.length" class="text-sm text-text-muted italic text-center py-8">暂无结构化分析数据</p>

        </div>
      </template>

      <!-- ── IMAGES (shared, outside tab content; visible regardless of active tab) ── -->
      <div v-if="detail?.images?.length" class="px-5 py-4 border-t border-border/40">
        <h3 class="section-title mb-3">论文图片</h3>
        <div class="scroll-gallery">
          <div
            v-for="(img, idx) in detail.images"
            :key="idx"
            class="rounded-xl overflow-hidden border border-border bg-bg-elevated cursor-pointer active:opacity-80"
            style="width: 72vw; max-width: 280px;"
            @click="lightboxSrc = img"
          >
            <img
              :src="img"
              class="w-full object-cover"
              loading="lazy"
              :alt="`图 ${idx + 1}`"
              style="max-height: 200px;"
            />
          </div>
        </div>
      </div>

      <!-- Bottom spacer for fixed bar -->
      <div class="h-2" />
    </div>

    <!-- ── FIXED BOTTOM ACTION BAR (auto-hides on scroll down) ── -->
    <div
      v-if="summary && !loading"
      class="shrink-0 fixed bottom-0 left-0 right-0 bg-bg/90 backdrop-blur-md border-t border-border safe-area-bottom px-4 py-3 flex gap-2 z-20 transition-transform duration-300"
      :class="bottomBarVisible ? 'translate-y-0' : 'translate-y-full'"
    >
      <!-- Collect -->
      <button
        type="button"
        class="flex-1 py-3 rounded-2xl text-[14px] font-semibold transition-all"
        :class="saved
          ? 'bg-tinder-green/15 text-tinder-green border border-tinder-green/30'
          : 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white border-none'"
        @click="savePaper"
      >
        {{ saved ? '已收藏' : '收藏' }}
      </button>
      <!-- AI Chat (promoted to primary) -->
      <button
        type="button"
        class="flex-1 py-3 rounded-2xl bg-tinder-purple/10 border border-tinder-purple/30 text-[14px] font-semibold text-tinder-purple active:bg-tinder-purple/20 transition-all"
        @click="router.push({ name: 'chat', query: { paperId: summary.paper_id, title: summary.short_title } })"
      >
        AI 对话
      </button>
      <!-- Read -->
      <button
        type="button"
        class="flex-1 py-3 rounded-2xl bg-tinder-blue/10 border border-tinder-blue/30 text-[14px] font-semibold text-tinder-blue active:bg-tinder-blue/20 transition-all"
        @click="router.push({ name: 'paper-reader', params: { id: summary.paper_id }, query: { mode: 'bilingual', title: summary.short_title || '双语阅读', ...(isUserPaper ? { source: 'user-paper' } : {}) } })"
      >
        阅读
      </button>
      <!-- More -->
      <button
        type="button"
        class="flex-none w-11 py-3 rounded-2xl bg-bg-elevated border border-border text-text-secondary active:bg-bg-hover flex items-center justify-center"
        aria-label="更多操作"
        @click="moreSheetVisible = true; bottomBarVisible = true"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>
        </svg>
      </button>
    </div>

    <!-- More Actions BottomSheet -->
    <BottomSheet :visible="moreSheetVisible" title="更多操作" @close="moreSheetVisible = false">
      <div class="pb-4">
        <!-- ArXiv page -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; openArxiv()"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-blue">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">ArXiv 页面</p>
            <p class="text-[12px] text-text-muted mt-0.5">在 arXiv.org 查看原文</p>
          </div>
        </button>
        <!-- PDF -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; openPdf()"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-pink/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-pink">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">打开 PDF</p>
            <p class="text-[12px] text-text-muted mt-0.5">直接查看论文 PDF 原文</p>
          </div>
        </button>
        <div class="h-px bg-border mx-4 my-1" />
        <!-- Notes -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; router.push({ path: `/notes/${summary!.paper_id}`, query: { title: summary!.short_title } })"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-gold/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-gold">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">写笔记</p>
            <p class="text-[12px] text-text-muted mt-0.5">记录阅读感想与批注</p>
          </div>
        </button>
        <!-- Compare -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; router.push('/compare')"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-blue">
              <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">论文对比</p>
            <p class="text-[12px] text-text-muted mt-0.5">与其他论文进行横向比较</p>
          </div>
        </button>
        <!-- Download -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; downloadSheetVisible = true"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-green/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-green">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">下载文件</p>
            <p class="text-[12px] text-text-muted mt-0.5">PDF、Markdown、双语译文</p>
          </div>
        </button>
        <!-- Derivative files -->
        <button
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="moreSheetVisible = false; openFilesSheet()"
        >
          <div class="w-9 h-9 rounded-xl bg-text-muted/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-text-secondary">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">衍生文件管理</p>
            <p class="text-[12px] text-text-muted mt-0.5">处理、翻译状态与文件管理</p>
          </div>
        </button>
      </div>
    </BottomSheet>

    <!-- Download BottomSheet -->
    <BottomSheet :visible="downloadSheetVisible" title="下载文件" @close="downloadSheetVisible = false">
      <div class="pb-4">
        <button
          v-for="opt in downloadOptions"
          :key="opt.label"
          type="button"
          class="w-full flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover text-left"
          @click="doDownload(opt)"
        >
          <div class="w-9 h-9 rounded-xl bg-tinder-blue/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="text-tinder-blue">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[14px] font-medium text-text-primary">{{ opt.label }}</p>
            <p class="text-[12px] text-text-muted mt-0.5">{{ opt.desc }}</p>
          </div>
        </button>
      </div>
    </BottomSheet>

    <!-- Derivative files management Sheet -->
    <BottomSheet :visible="filesSheetVisible" title="衍生文件管理" @close="filesSheetVisible = false">
      <div class="px-4 pb-6 pt-2">
        <div v-if="filesLoading" class="flex justify-center py-8">
          <div class="w-6 h-6 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
        </div>
        <div v-else-if="filesError" class="py-6 text-center text-[13px] text-tinder-pink">{{ filesError }}</div>
        <div v-else-if="filesData" class="space-y-3">
          <!-- PDF -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">PDF 原文</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full" :class="filesData.exists.pdf ? 'bg-tinder-green/15 text-tinder-green' : 'bg-text-muted/15 text-text-muted'">
                  {{ filesData.exists.pdf ? '存在' : '未找到' }}
                </span>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">原始论文 PDF 文件</p>
          </div>

          <!-- MinerU -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">结构化文本</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                  :class="{
                    'bg-tinder-green/15 text-tinder-green': filesData.exists.mineru,
                    'bg-tinder-blue/15 text-tinder-blue': !filesData.exists.mineru && (filesData.process_status === 'processing' || filesData.process_status === 'pending'),
                    'bg-text-muted/15 text-text-muted': !filesData.exists.mineru && filesData.process_status !== 'processing' && filesData.process_status !== 'pending',
                  }"
                >
                  {{ filesData.exists.mineru ? '已生成' : filesData.process_status === 'processing' ? '处理中' : filesData.process_status === 'pending' ? '等待中' : '未生成' }}
                </span>
              </div>
              <div class="flex items-center gap-1.5">
                <button v-if="!filesData.exists.mineru" type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-blue/10 text-tinder-blue active:bg-tinder-blue/20 disabled:opacity-40" :disabled="!!processingAction" @click="triggerProcess">
                  {{ processingAction === 'process' ? '提交中…' : '触发处理' }}
                </button>
                <button v-if="filesData.exists.mineru" type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-pink/10 text-tinder-pink active:bg-tinder-pink/20 disabled:opacity-40" :disabled="!!processingAction" @click="deleteDerivative('mineru')">
                  删除
                </button>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">MinerU 版面解析后的正文结构</p>
          </div>

          <!-- Chinese translation -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">中文翻译</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                  :class="{
                    'bg-tinder-green/15 text-tinder-green': filesData.exists.zh,
                    'bg-tinder-blue/15 text-tinder-blue': !filesData.exists.zh && (filesData.translate_status === 'processing'),
                    'bg-text-muted/15 text-text-muted': !filesData.exists.zh && filesData.translate_status !== 'processing',
                  }"
                >
                  {{ filesData.exists.zh ? '已生成' : filesData.translate_status === 'processing' ? `翻译中 ${filesData.translate_progress}%` : '未生成' }}
                </span>
              </div>
              <div class="flex items-center gap-1.5">
                <button v-if="!filesData.exists.zh" type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-blue/10 text-tinder-blue active:bg-tinder-blue/20 disabled:opacity-40" :disabled="!!processingAction" @click="triggerTranslate">
                  {{ processingAction === 'translate' ? '提交中…' : '触发翻译' }}
                </button>
                <template v-if="filesData.exists.zh">
                  <button type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-gold/10 text-tinder-gold active:bg-tinder-gold/20 disabled:opacity-40" :disabled="!!processingAction" @click="triggerRetranslate">
                    重新翻译
                  </button>
                  <button type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-pink/10 text-tinder-pink active:bg-tinder-pink/20 disabled:opacity-40" :disabled="!!processingAction" @click="deleteDerivative('zh')">
                    删除
                  </button>
                </template>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">论文中文翻译，用于双语阅读</p>
          </div>

          <!-- Bilingual -->
          <div class="rounded-xl border border-border bg-bg-elevated p-3.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-text-primary">双语对照</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded-full" :class="filesData.exists.bilingual ? 'bg-tinder-green/15 text-tinder-green' : 'bg-text-muted/15 text-text-muted'">
                  {{ filesData.exists.bilingual ? '已生成' : '未生成' }}
                </span>
              </div>
              <div class="flex items-center gap-1.5">
                <button v-if="filesData.exists.bilingual" type="button" class="text-[11px] px-2 py-1 rounded-lg bg-tinder-pink/10 text-tinder-pink active:bg-tinder-pink/20 disabled:opacity-40" :disabled="!!processingAction" @click="deleteDerivative('bilingual')">
                  删除
                </button>
              </div>
            </div>
            <p class="text-[11px] text-text-muted mt-1">中英对照文件，需先完成翻译</p>
          </div>
        </div>
      </div>
    </BottomSheet>

    <!-- Lightbox -->
    <Transition name="fade">
      <div
        v-if="lightboxSrc"
        class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
        @click="lightboxSrc = null"
      >
        <img
          :src="lightboxSrc"
          class="max-w-full max-h-full rounded-xl object-contain"
          @click.stop
        />
        <button
          type="button"
          class="absolute top-safe right-4 w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-white"
          style="top: max(16px, env(safe-area-inset-top, 16px));"
          @click="lightboxSrc = null"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* Tab bar buttons */
.detail-tab {
  flex: 1;
  padding: 0.625rem 0;
  font-size: 0.875rem;
  font-weight: 600;
  border-bottom: 2px solid transparent;
  background: transparent;
  border-left: none;
  border-right: none;
  border-top: none;
  color: var(--color-text-muted);
  transition: color 0.2s, border-color 0.2s;
  cursor: pointer;
}
.detail-tab--active {
  border-bottom-color: var(--color-tinder-pink);
  color: var(--color-tinder-pink);
}

/* Smooth accordion height animation (same technique as AssetsAccordion) */
.accordion-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.25s ease;
  background-color: var(--color-bg-card);
}
.accordion-body.is-open {
  grid-template-rows: 1fr;
}
.accordion-body > div {
  overflow: hidden;
}
</style>
