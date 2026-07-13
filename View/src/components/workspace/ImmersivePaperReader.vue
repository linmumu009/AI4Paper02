<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkspacePaperDetail } from '../../composables/useWorkspacePaperDetail'
import { isAuthenticated } from '../../stores/auth'
import type { PaperDetailResponse, PaperSummary } from '../../types/paper'
import AddToProjectDialog from '../project/AddToProjectDialog.vue'
import ImmersiveWorkspaceShell from './ImmersiveWorkspaceShell.vue'
import arrowLeftIcon from '../../assets/heroicons/arrow-left.svg'
import arrowRightIcon from '../../assets/heroicons/arrow-right.svg'
import beakerIcon from '../../assets/heroicons/beaker.svg'
import bookOpenIcon from '../../assets/heroicons/book-open.svg'
import bookmarkIcon from '../../assets/heroicons/bookmark.svg'
import checkIcon from '../../assets/heroicons/check-circle.svg'
import documentIcon from '../../assets/heroicons/document-text.svg'
import heartIcon from '../../assets/heroicons/heart.svg'
import scaleIcon from '../../assets/heroicons/scale.svg'
import squaresIcon from '../../assets/heroicons/squares-2x2.svg'
import xMarkIcon from '../../assets/heroicons/x-mark.svg'
const props = withDefaults(defineProps<{
  paper: PaperSummary
  relatedPapers: PaperSummary[]
  publicationDate?: string
  position: number
  total: number
  collected?: boolean
  bookmarked?: boolean
  canGoPrevious?: boolean
  canGoNext?: boolean
  returnMode?: 'card' | 'list'
  returnLabel?: string
  decisionMode?: 'digest' | 'knowledge' | 'mypapers' | 'project' | 'research'
  sourceScope?: string
  canCompare?: boolean
  showCollectionAction?: boolean
  showBookmarkAction?: boolean
  detailOverride?: PaperDetailResponse | null
  projectContext?: {
    name: string
    objective?: string
    paperCount?: number
  } | null
  researchContext?: {
    question?: string
    paperCount?: number
  } | null
}>(), {
  decisionMode: 'digest',
  sourceScope: 'digest',
  canCompare: true,
  showCollectionAction: true,
  showBookmarkAction: true,
})

const emit = defineEmits<{
  previous: []
  next: []
  skip: []
  compare: []
  collect: []
  openPdf: []
  openDetail: []
  toggleBookmark: []
  startResearch: []
  selectRelated: [paperId: string]
  exit: []
  login: []
}>()

const showProjectDialog = ref(false)
const contextOpen = ref(false)
const contextTab = ref<'outline' | 'project' | 'related'>(['project', 'research'].includes(props.decisionMode) ? 'project' : 'outline')
const readingProgress = ref(0)
const paperRef = computed(() => props.paper)
const detailOverrideRef = computed(() => props.detailOverride)
const { detail, detailLoading, detailError, summary } = useWorkspacePaperDetail(paperRef, detailOverrideRef)

const title = computed(() => summary.value?.short_title || summary.value?.['📖标题'] || props.paper.paper_id)
const originalTitle = computed(() => {
  const value = summary.value?.['📖标题']
  return value && value !== title.value ? value : ''
})
function textItems(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(textItems)
  if (typeof value === 'string') {
    const item = value.trim()
    return item ? [item] : []
  }
  if (typeof value === 'number' && Number.isFinite(value)) return [String(value)]
  return []
}

const authorsLine = computed(() => {
  const authors = textItems(summary.value?.authors)
  if (!authors.length) return '作者信息暂缺'
  const visible = authors.slice(0, 4).map(author => author.replace(/\s*\(.*?\)\s*/g, '').trim())
  return authors.length > 4 ? `${visible.join(', ')} et al.` : visible.join(', ')
})
const score = computed(() => {
  const value = summary.value?.relevance_score
  if (value == null) return null
  return Math.round(value <= 1 ? value * 100 : value)
})
const researchQuestion = computed(() => summary.value?.['🛎️文章简介']?.['🔸研究问题'] || '')
const mainContribution = computed(() => summary.value?.['🛎️文章简介']?.['🔸主要贡献'] || '')
const recommendation = computed(() => summary.value?.why_recommended || summary.value?.['推荐理由'] || mainContribution.value)
const keyThoughts = computed(() => textItems(summary.value?.['📝重点思路']).slice(0, 5))
const analysisSummary = computed(() => textItems(summary.value?.['🔎分析总结']).slice(0, 3))
const assetBlocks = computed(() => detail.value?.paper_assets?.blocks)

function uniqueItems(...groups: unknown[]): string[] {
  return [...new Set(groups.flatMap(textItems))]
}

type ReadingGroupTone = 'neutral' | 'claim' | 'evidence' | 'inference' | 'warning'
type ReadingGroup = {
  key: string
  label: string
  hint?: string
  tone: ReadingGroupTone
  items: string[]
}

function readingGroup(
  key: string,
  label: string,
  values: unknown[],
  tone: ReadingGroupTone = 'neutral',
  hint = '',
): ReadingGroup {
  return { key, label, hint, tone, items: uniqueItems(...values) }
}

function populatedGroups(groups: ReadingGroup[]): ReadingGroup[] {
  return groups.filter(group => group.items.length > 0)
}

function withLegacyFallback(groups: ReadingGroup[], label: string, ...fallbackValues: unknown[]): ReadingGroup[] {
  if (groups.some(group => group.items.length > 0)) return populatedGroups(groups)
  return populatedGroups([readingGroup('legacy', label, fallbackValues)])
}

const objectiveGroups = computed(() => populatedGroups([
  readingGroup('questions', '研究问题', [researchQuestion.value, assetBlocks.value?.objective?.research_questions]),
  readingGroup(
    'contributions',
    '作者声称的贡献',
    [mainContribution.value, assetBlocks.value?.objective?.claimed_contributions],
    'claim',
    '这是作者对新增工作的主张，仍需结合结果与证据核验。',
  ),
  readingGroup('reading-clues', '阅读线索', [keyThoughts.value.slice(0, 3)]),
]))
const methodGroups = computed(() => withLegacyFallback([
  readingGroup('architecture', '架构或范式', [assetBlocks.value?.method?.architecture_or_paradigm]),
  readingGroup('mechanisms', '关键机制', [assetBlocks.value?.method?.key_mechanisms]),
  readingGroup('training', '训练与优化', [assetBlocks.value?.method?.training_required, assetBlocks.value?.method?.training_or_optimization]),
  readingGroup('inference', '推理策略', [assetBlocks.value?.method?.inference_strategy]),
  readingGroup('novelty', '方法创新点', [assetBlocks.value?.method?.novelty], 'claim', '创新性属于论文定位，应与基线和消融结果对照阅读。'),
], '方法概述', assetBlocks.value?.method?.text, assetBlocks.value?.method?.bullets))
const evaluationGroups = computed(() => withLegacyFallback([
  readingGroup('datasets', '数据集或研究材料', [assetBlocks.value?.data?.datasets_or_materials]),
  readingGroup('data-context', '数据来源、规模与范围', [assetBlocks.value?.data?.data_source, assetBlocks.value?.data?.data_scale, assetBlocks.value?.data?.domain_scope]),
  readingGroup('design', '实验或论证设计', [assetBlocks.value?.experiment_or_argumentation?.design, assetBlocks.value?.experiment_or_argumentation?.argumentation_structure]),
  readingGroup('baselines', '基线与对照', [assetBlocks.value?.experiment_or_argumentation?.baselines_or_comparators]),
  readingGroup('variables', '变量与模块', [assetBlocks.value?.experiment_or_argumentation?.variables_or_modules]),
  readingGroup('ablation', '消融与反事实', [assetBlocks.value?.experiment_or_argumentation?.ablation_or_counterfactual]),
  readingGroup('metrics', '评价指标', [assetBlocks.value?.metrics?.metric_names]),
  readingGroup('protocol', '评估协议', [assetBlocks.value?.metrics?.evaluation_protocol, assetBlocks.value?.metrics?.judge_or_annotation_method]),
], '评估概述', assetBlocks.value?.data?.text, assetBlocks.value?.experiment?.text, assetBlocks.value?.metrics?.text))
const resultGroups = computed(() => withLegacyFallback([
  readingGroup('numbers', '数值证据', [assetBlocks.value?.results?.numerical_results], 'evidence', '优先核对指标、比较对象与原文表格。'),
  readingGroup('findings', '主要发现', [assetBlocks.value?.results?.main_findings]),
  readingGroup('phenomena', '观察到的现象', [assetBlocks.value?.results?.phenomena]),
  readingGroup('mechanism-explanations', '机制解释', [assetBlocks.value?.results?.mechanism_explanations], 'inference', '作者解释或分析推断，不等同于已验证的因果机制。'),
  readingGroup('supported-claims', '证据支持较强的结论', [assetBlocks.value?.evidence_chain?.strongly_supported_claims], 'evidence'),
  readingGroup('source-evidence', '关键图表与附录证据', [assetBlocks.value?.evidence_chain?.key_evidence_from_figures_tables_appendix], 'evidence'),
], '结果概述', assetBlocks.value?.results?.text, assetBlocks.value?.results?.bullets))
const limitationGroups = computed(() => populatedGroups([
  readingGroup('scope', '适用范围', [assetBlocks.value?.limitations?.scope_boundaries]),
  readingGroup('validity', '有效性威胁', [assetBlocks.value?.limitations?.threats_to_validity], 'warning'),
  readingGroup('generalization', '外推限制', [assetBlocks.value?.limitations?.generalization_limits], 'warning'),
  readingGroup('weak-evidence', '证据支持较弱', [assetBlocks.value?.evidence_chain?.weakly_supported_claims], 'warning'),
  readingGroup('unsupported', '未充分支持或可能过度外推', [assetBlocks.value?.evidence_chain?.unsupported_or_overextended_claims], 'warning'),
  readingGroup('needs-evidence', '仍需补充的证据', [assetBlocks.value?.critical_analysis?.weakest_argument, assetBlocks.value?.critical_analysis?.needs_more_evidence], 'warning'),
]))
const analysisGroups = computed(() => populatedGroups([
  readingGroup('editor-summary', '编辑分析', [analysisSummary.value]),
  readingGroup('strongest-argument', '最有力的论证', [assetBlocks.value?.critical_analysis?.strongest_argument], 'evidence'),
  readingGroup('substantive', '实质性贡献', [assetBlocks.value?.critical_analysis?.substantive_contributions]),
  readingGroup('framing', '包装与表述成分', [assetBlocks.value?.critical_analysis?.packaging_or_framing_elements], 'inference'),
]))
const verificationPriorities = computed(() => uniqueItems(assetBlocks.value?.critical_analysis?.reproduction_or_extension_priorities))
const readingPercent = computed(() => Math.round(readingProgress.value * 100))
const readingSections = computed(() => [
  { id: 'reader-overview', label: '导读', visible: Boolean(recommendation.value || summary.value?.abstract) },
  { id: 'reader-objective', label: '研究问题与贡献', visible: objectiveGroups.value.length > 0 },
  { id: 'reader-method', label: '方法与机制', visible: methodGroups.value.length > 0 },
  { id: 'reader-evaluation', label: '数据与评估', visible: evaluationGroups.value.length > 0 },
  { id: 'reader-results', label: '结果与证据', visible: resultGroups.value.length > 0 },
  { id: 'reader-limitations', label: '局限性与边界', visible: limitationGroups.value.length > 0 },
  { id: 'reader-analysis', label: '分析总结', visible: analysisGroups.value.length > 0 },
  { id: 'reader-resources', label: '继续核验', visible: true },
].filter(section => section.visible))

const relatedTitle = (paper: PaperSummary) => paper.short_title || paper['📖标题'] || paper.paper_id
const relatedAuthors = (paper: PaperSummary) => textItems(paper.authors).slice(0, 2).join(', ')
const relatedCategories = (paper: PaperSummary) => textItems(paper.categories).slice(0, 2).join(' · ')
const resolvedReturnLabel = computed(() => props.returnLabel || (props.returnMode === 'card' ? '返回卡片模式' : '返回列表模式'))
const isKnowledgeDecision = computed(() => props.decisionMode === 'knowledge')
const isMyPapersDecision = computed(() => props.decisionMode === 'mypapers')
const isProjectDecision = computed(() => props.decisionMode === 'project')
const isResearchDecision = computed(() => props.decisionMode === 'research')
const isSequentialDecision = computed(() => isMyPapersDecision.value || isProjectDecision.value || isResearchDecision.value)

function openContext(tab: 'outline' | 'project' | 'related' = contextTab.value) {
  contextTab.value = tab
  contextOpen.value = true
}

function selectRelatedPaper(paperId: string) {
  emit('selectRelated', paperId)
  contextOpen.value = false
}

function scrollToSection(sectionId: string) {
  document.getElementById(sectionId)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  if (typeof window !== 'undefined' && window.innerWidth < 1280) contextOpen.value = false
}
</script>

<template>
  <ImmersiveWorkspaceShell
    class="immersive-reader"
    :context-open="contextOpen"
    context-label="论文研究上下文"
    aria-label="沉浸论文阅读"
    @close-context="contextOpen = false"
    @document-scroll="readingProgress = $event"
  >
    <template #rail>
      <button type="button" class="immersive-reader__rail-button immersive-reader__rail-button--active" :aria-label="resolvedReturnLabel" :title="resolvedReturnLabel" @click="emit('exit')">
        <img :src="bookOpenIcon" alt="">
        <span class="immersive-reader__rail-label">返回</span>
      </button>
      <button
        type="button"
        class="immersive-reader__rail-button immersive-reader__context-trigger"
        aria-label="打开研究上下文"
        title="研究上下文"
        :aria-expanded="contextOpen"
        @click="openContext()"
      >
        <img :src="squaresIcon" alt="">
        <span class="immersive-reader__rail-label">上下文</span>
      </button>
    </template>

    <div class="immersive-reader__document-inner">
        <div
          class="immersive-reader__progress"
          role="progressbar"
          aria-label="论文阅读进度"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="readingPercent"
        >
          <span :style="{ width: `${readingPercent}%` }" />
        </div>
        <div class="immersive-reader__document-topline">
          <p>推荐论文 · {{ paper.categories?.[0] || '今日精选' }}</p>
          <div class="immersive-reader__pager" aria-label="论文导航">
            <button type="button" :disabled="!canGoPrevious" aria-label="上一篇论文" title="上一篇论文" @click="emit('previous')"><img :src="arrowLeftIcon" alt=""></button>
            <span>{{ Math.min(position, total) }} / {{ total }}</span>
            <button type="button" :disabled="!canGoNext" aria-label="下一篇论文" title="下一篇论文" @click="emit('next')"><img :src="arrowRightIcon" alt=""></button>
          </div>
        </div>

        <header class="immersive-reader__header">
          <div class="immersive-reader__title-row">
            <div>
              <h1>{{ title }}</h1>
              <p v-if="originalTitle" class="immersive-reader__original-title">{{ originalTitle }}</p>
            </div>
            <div v-if="score != null" class="immersive-reader__score" :aria-label="`相关度 ${score}`">
              <strong>{{ score }}</strong>
              <span>推荐指数</span>
            </div>
          </div>
          <p class="immersive-reader__meta">arXiv: {{ paper.paper_id }}<span v-if="publicationDate"> · {{ publicationDate }}</span></p>
          <p class="immersive-reader__meta">{{ authorsLine }}</p>
          <p v-if="paper.institution" class="immersive-reader__meta">{{ paper.institution }}</p>
          <div class="immersive-reader__inline-actions">
            <button type="button" @click="emit('openPdf')"><img :src="documentIcon" alt="">查看 PDF</button>
            <button type="button" @click="emit('openDetail')"><img :src="bookOpenIcon" alt="">进入精读</button>
            <button v-if="showBookmarkAction" type="button" :class="{ 'is-active': bookmarked }" @click="emit('toggleBookmark')">
              <img :src="bookmarkIcon" alt="">{{ bookmarked ? '已标记稍后读' : '稍后读' }}
            </button>
          </div>
        </header>

        <section
          v-if="recommendation || summary?.abstract"
          id="reader-overview"
          class="immersive-reader__section immersive-reader__overview"
        >
          <div v-if="recommendation" class="immersive-reader__recommendation">
            <h2>推荐理由</h2>
            <p>{{ recommendation }}</p>
          </div>
          <div v-if="summary?.abstract" class="immersive-reader__reading-block">
            <h2>摘要导读</h2>
            <p>{{ summary.abstract }}</p>
          </div>
        </section>

        <section v-if="objectiveGroups.length" id="reader-objective" class="immersive-reader__section">
          <div class="immersive-reader__section-heading">
            <h2>研究问题与贡献</h2>
            <span>论文要解决什么，以及新增了什么</span>
          </div>
          <div class="immersive-reader__groups">
            <article v-for="group in objectiveGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section v-if="methodGroups.length" id="reader-method" class="immersive-reader__section">
          <div class="immersive-reader__section-heading">
            <h2>方法与机制</h2>
            <span>架构、关键机制与优化方式</span>
          </div>
          <div class="immersive-reader__groups">
            <article v-for="group in methodGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section v-if="evaluationGroups.length" id="reader-evaluation" class="immersive-reader__section">
          <div class="immersive-reader__section-heading">
            <h2>数据与评估</h2>
            <span>数据集、基线和评价协议</span>
          </div>
          <div class="immersive-reader__groups">
            <article v-for="group in evaluationGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section v-if="resultGroups.length" id="reader-results" class="immersive-reader__section">
          <div class="immersive-reader__section-heading">
            <h2>结果与证据</h2>
            <span>优先展示数值结果和强支持结论</span>
          </div>
          <div class="immersive-reader__groups">
            <article v-for="group in resultGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section v-if="limitationGroups.length" id="reader-limitations" class="immersive-reader__section immersive-reader__limitations">
          <div class="immersive-reader__section-heading">
            <h2>局限性与适用边界</h2>
            <span>阅读结论时需要保留的条件</span>
          </div>
          <div class="immersive-reader__groups">
            <article v-for="group in limitationGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section v-if="analysisGroups.length" id="reader-analysis" class="immersive-reader__section immersive-reader__analysis">
          <div class="immersive-reader__section-heading"><h2>分析总结</h2><span>区分编辑判断、强论证与表述包装</span></div>
          <div class="immersive-reader__groups">
            <article v-for="group in analysisGroups" :key="group.key" class="immersive-reader__group" :class="`is-${group.tone}`">
              <div class="immersive-reader__group-heading"><h3>{{ group.label }}</h3><p v-if="group.hint">{{ group.hint }}</p></div>
              <ul><li v-for="item in group.items" :key="item">{{ item }}</li></ul>
            </article>
          </div>
        </section>

        <section id="reader-resources" class="immersive-reader__section immersive-reader__resources">
          <div class="immersive-reader__section-heading">
            <h2>继续核验</h2>
            <span>回到原文确认关键证据</span>
          </div>
          <p>结构化解读用于快速定位问题，重要结论仍建议结合论文原文、图表和附录核验。</p>
          <div v-if="verificationPriorities.length" class="immersive-reader__verification-priorities">
            <h3>优先复现或扩展</h3>
            <ul><li v-for="item in verificationPriorities" :key="item">{{ item }}</li></ul>
          </div>
          <div class="immersive-reader__resource-actions">
            <button type="button" @click="emit('openPdf')"><img :src="documentIcon" alt="">打开论文 PDF</button>
            <button type="button" @click="emit('openDetail')"><img :src="bookOpenIcon" alt="">查看完整解析</button>
          </div>
        </section>

        <p v-if="detailLoading" class="immersive-reader__status">正在补充结构化证据…</p>
        <p v-else-if="detailError" class="immersive-reader__status">{{ detailError }}</p>
    </div>

    <template #context>
      <div class="immersive-reader__context">
        <div class="immersive-reader__context-tabs" role="tablist" aria-label="研究上下文分类">
          <button
            type="button"
            role="tab"
            :aria-selected="contextTab === 'outline'"
            :class="{ 'is-active': contextTab === 'outline' }"
            @click="contextTab = 'outline'"
          >目录</button>
          <button
            type="button"
            role="tab"
            :aria-selected="contextTab === 'project'"
            :class="{ 'is-active': contextTab === 'project' }"
            @click="contextTab = 'project'"
          >{{ isResearchDecision ? '研究' : '课题' }}</button>
          <button
            type="button"
            role="tab"
            :aria-selected="contextTab === 'related'"
            :class="{ 'is-active': contextTab === 'related' }"
            @click="contextTab = 'related'"
          >相关论文 <span>{{ relatedPapers.length }}</span></button>
        </div>

        <section v-if="contextTab === 'outline'" class="immersive-reader__outline" role="tabpanel">
          <div class="immersive-reader__context-heading">
            <h2>阅读目录</h2>
            <span>{{ readingPercent }}%</span>
          </div>
          <button
            v-for="(section, index) in readingSections"
            :key="section.id"
            type="button"
            class="immersive-reader__outline-link"
            @click="scrollToSection(section.id)"
          >
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <strong>{{ section.label }}</strong>
          </button>
        </section>

        <section v-else-if="contextTab === 'project'" role="tabpanel">
          <div class="immersive-reader__context-heading">
            <h2>{{ researchContext ? '当前研究' : projectContext ? '当前课题' : '研究课题' }}</h2>
            <span>{{ researchContext ? `${researchContext.paperCount || 0} 篇论文` : projectContext ? `${projectContext.paperCount || 0} 篇论文` : isAuthenticated ? '当前论文' : '登录后启用' }}</span>
          </div>
          <template v-if="researchContext">
            <p class="immersive-reader__context-title">{{ researchContext.question || '深度研究证据集' }}</p>
            <p class="immersive-reader__context-copy">当前论文来自本次研究资料。返回报告后仍会保留原来的阅读位置和研究状态。</p>
          </template>
          <template v-else-if="projectContext">
            <p class="immersive-reader__context-title">{{ projectContext.name }}</p>
            <p class="immersive-reader__context-copy">{{ projectContext.objective || '围绕课题目标继续核验证据。' }}</p>
          </template>
          <template v-else-if="isAuthenticated">
            <p class="immersive-reader__context-title">把这篇论文加入正在推进的研究课题</p>
            <button type="button" class="immersive-reader__context-primary" @click="showProjectDialog = true">加入课题</button>
          </template>
          <template v-else>
            <p class="immersive-reader__context-copy">登录后可以保存论文、建立课题并持续追踪研究脉络。</p>
            <button type="button" class="immersive-reader__context-primary" @click="emit('login')">登录并使用</button>
          </template>
        </section>

        <section v-else role="tabpanel">
          <div class="immersive-reader__context-heading">
            <h2>相关论文</h2>
            <span>{{ relatedPapers.length }} 篇</span>
          </div>
          <button
            v-for="related in relatedPapers"
            :key="related.paper_id"
            type="button"
            class="immersive-reader__related-paper"
            @click="selectRelatedPaper(related.paper_id)"
          >
            <strong>{{ relatedTitle(related) }}</strong>
            <span>{{ relatedAuthors(related) || related.institution || related.paper_id }}</span>
            <small>{{ relatedCategories(related) || '相关研究' }}</small>
          </button>
          <p v-if="relatedPapers.length === 0" class="immersive-reader__context-copy">当前筛选结果中暂无相关论文。</p>
        </section>
      </div>
    </template>

    <template #dock>
      <div class="immersive-reader__dock" :class="{ 'immersive-reader__dock--three': !showCollectionAction }">
        <button type="button" :disabled="isSequentialDecision && !canGoNext" @click="emit('skip')">
          <span class="immersive-reader__dock-icon"><img :src="isKnowledgeDecision ? checkIcon : isSequentialDecision ? arrowRightIcon : xMarkIcon" alt=""></span>
          <span class="immersive-reader__dock-copy"><strong>{{ isKnowledgeDecision ? '标为已读' : isResearchDecision ? '下一引用' : isProjectDecision ? '下一证据' : isMyPapersDecision ? '下一篇' : '跳过' }}</strong><small>{{ isKnowledgeDecision ? '完成本次阅读' : isResearchDecision ? '继续核验研究资料' : isProjectDecision ? '继续核验课题论文' : isMyPapersDecision ? '继续浏览论文' : '不感兴趣' }}</small></span>
        </button>
        <button type="button" :disabled="canCompare === false" @click="emit('compare')">
          <span class="immersive-reader__dock-icon immersive-reader__dock-icon--blue"><img :src="scaleIcon" alt=""></span>
          <span class="immersive-reader__dock-copy"><strong>{{ isResearchDecision ? '原文' : '对比' }}</strong><small>{{ isResearchDecision ? '打开 PDF 核验' : '与相关文章比较' }}</small></span>
        </button>
        <button v-if="showCollectionAction" type="button" :class="{ 'is-active': collected }" @click="emit('collect')">
          <span class="immersive-reader__dock-icon immersive-reader__dock-icon--green"><img :src="heartIcon" alt=""></span>
          <span class="immersive-reader__dock-copy"><strong>{{ isKnowledgeDecision ? '移出知识库' : collected ? '已收藏' : '收藏' }}</strong><small>{{ isKnowledgeDecision ? '保留笔记' : '加入知识库' }}</small></span>
        </button>
        <button type="button" class="immersive-reader__dock-primary" @click="emit('startResearch')">
          <span class="immersive-reader__dock-icon"><img :src="beakerIcon" alt=""></span>
          <span class="immersive-reader__dock-copy"><strong>{{ isResearchDecision ? '返回报告' : '深度研究' }}</strong><small>{{ isResearchDecision ? '继续查看研究结论' : '深入追踪这条线索' }}</small></span>
        </button>
      </div>
    </template>
  </ImmersiveWorkspaceShell>

  <AddToProjectDialog
    v-if="showProjectDialog"
    asset-type="paper"
    :asset-id="paper.paper_id"
    :source-scope="sourceScope || 'digest'"
    :asset-title="title"
    @close="showProjectDialog = false"
  />
</template>

<style scoped>
.immersive-reader {
  color: var(--color-text-primary);
}

.immersive-reader__rail-button {
  display: flex;
  min-height: 54px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 3px;
  padding: 6px 2px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  cursor: pointer;
}

.immersive-reader__rail-button img {
  width: 23px;
  height: 23px;
}

.immersive-reader__rail-label {
  font-size: 9px;
  font-weight: 700;
}

.immersive-reader__context-trigger {
  display: none;
}

.immersive-reader__rail-button:hover,
.immersive-reader__rail-button:focus-visible,
.immersive-reader__rail-button--active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 22%, transparent);
  background: color-mix(in srgb, var(--color-tinder-pink) 8%, transparent);
  color: var(--color-tinder-pink);
}

.immersive-reader__document-inner {
  width: min(100%, 920px);
  margin: 0 auto;
  padding: 24px 40px 62px;
}

.immersive-reader__progress {
  position: sticky;
  z-index: 3;
  top: 0;
  width: 100%;
  height: 3px;
  margin: -24px 0 21px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-border) 70%, transparent);
}

.immersive-reader__progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--color-tinder-pink), var(--color-tinder-blue));
  transition: width 120ms linear;
}

.immersive-reader__document-topline,
.immersive-reader__title-row,
.immersive-reader__section-heading,
.immersive-reader__context-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.immersive-reader__document-topline {
  margin-bottom: 24px;
}

.immersive-reader__document-topline > p {
  margin: 0;
  color: var(--color-tinder-pink);
  font-size: 12px;
  font-weight: 800;
}

.immersive-reader__pager {
  display: flex;
  align-items: center;
  gap: 8px;
}

.immersive-reader__pager button,
.immersive-reader__inline-actions button {
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.immersive-reader__pager button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.immersive-reader__pager button {
  display: inline-flex;
  min-width: 30px;
  align-items: center;
  justify-content: center;
}

.immersive-reader__pager button img {
  width: 14px;
  height: 14px;
}

.immersive-reader__pager span {
  min-width: 52px;
  color: var(--color-text-muted);
  font-size: 12px;
  text-align: center;
}

.immersive-reader__title-row {
  align-items: flex-start;
}

.immersive-reader__header h1 {
  margin: 0;
  font-size: clamp(24px, 2.2vw, 34px);
  font-weight: 800;
  line-height: 1.24;
  letter-spacing: -0.035em;
}

.immersive-reader__original-title,
.immersive-reader__meta {
  margin: 8px 0 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.65;
}

.immersive-reader__original-title {
  color: var(--color-text-secondary);
}

.immersive-reader__score {
  display: flex;
  width: 56px;
  height: 56px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  border: 1px solid color-mix(in srgb, var(--color-tag-score-high) 38%, transparent);
  border-radius: 50%;
  color: var(--color-tag-score-high);
}

.immersive-reader__score strong {
  font-size: 18px;
  line-height: 1;
}

.immersive-reader__score span {
  margin-top: 3px;
  font-size: 10px;
}

.immersive-reader__inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 14px;
}

.immersive-reader__inline-actions button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.immersive-reader__inline-actions button img {
  width: 13px;
  height: 13px;
}

.immersive-reader__inline-actions button:hover,
.immersive-reader__inline-actions button:focus-visible,
.immersive-reader__inline-actions .is-active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 38%, var(--color-border));
  color: var(--color-tinder-pink);
}

.immersive-reader__recommendation {
  margin-top: 0;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-pink) 16%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-tinder-pink) 7%, transparent);
}

.immersive-reader__recommendation h2,
.immersive-reader__section h2,
.immersive-reader__context h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
}

.immersive-reader__recommendation h2 {
  color: var(--color-tinder-pink);
}

.immersive-reader__recommendation p,
.immersive-reader__section p,
.immersive-reader__section li {
  margin: 9px 0 0;
  color: var(--color-text-secondary);
  font-size: 15px;
  line-height: 1.85;
}

.immersive-reader__section {
  scroll-margin-top: 18px;
  padding: 26px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 72%, transparent);
}

.immersive-reader__overview {
  padding-top: 20px;
}

.immersive-reader__reading-block {
  margin-top: 22px;
}

.immersive-reader__reading-block h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
}

.immersive-reader__reading-block p {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
  font-size: 15px;
  line-height: 1.9;
}

.immersive-reader__section ul {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.immersive-reader__section li {
  position: relative;
  padding-left: 16px;
}

.immersive-reader__section li::before {
  position: absolute;
  left: 0;
  color: var(--color-tinder-pink);
  content: '•';
}

.immersive-reader__groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.immersive-reader__group {
  min-width: 0;
  padding: 16px 17px;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-bg-card) 92%, transparent);
}

.immersive-reader__group.is-claim {
  border-color: color-mix(in srgb, #d99a00 28%, var(--color-border));
  background: color-mix(in srgb, #f2b705 5%, var(--color-bg-card));
}

.immersive-reader__group.is-evidence {
  border-color: color-mix(in srgb, var(--color-tinder-blue) 26%, var(--color-border));
  background: color-mix(in srgb, var(--color-tinder-blue) 4%, var(--color-bg-card));
}

.immersive-reader__group.is-inference {
  border-color: color-mix(in srgb, #8657d9 24%, var(--color-border));
  background: color-mix(in srgb, #8657d9 4%, var(--color-bg-card));
}

.immersive-reader__group.is-warning {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 24%, var(--color-border));
}

.immersive-reader__group-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.immersive-reader__group-heading h3,
.immersive-reader__verification-priorities h3 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.5;
}

.immersive-reader__group-heading p {
  max-width: 62%;
  margin: 0;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.6;
  text-align: right;
}

.immersive-reader__group ul {
  margin-top: 9px;
}

.immersive-reader__group li {
  margin-top: 7px;
  font-size: 15px;
  line-height: 1.8;
}

.immersive-reader__verification-priorities {
  margin-top: 13px;
  padding: 12px 14px;
  border-left: 3px solid color-mix(in srgb, var(--color-tinder-blue) 55%, transparent);
  background: color-mix(in srgb, var(--color-tinder-blue) 4%, transparent);
}

.immersive-reader__numbered-list {
  display: grid;
  gap: 9px;
  counter-reset: objective;
}

.immersive-reader__numbered-list li {
  padding: 11px 13px 11px 42px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: var(--color-bg);
  counter-increment: objective;
}

.immersive-reader__numbered-list li::before {
  top: 10px;
  left: 13px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-tinder-pink) 10%, transparent);
  color: var(--color-tinder-pink);
  content: counter(objective);
  font-size: 9px;
  font-weight: 800;
  line-height: 20px;
  text-align: center;
}

.immersive-reader__section-heading span {
  color: var(--color-text-muted);
  font-size: 12px;
}

.immersive-reader__evidence-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.immersive-reader__evidence-list article {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-blue) 20%, var(--color-border));
  border-radius: 9px;
  background: color-mix(in srgb, var(--color-tinder-blue) 4%, var(--color-bg));
}

.immersive-reader__evidence-list article > span {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-tinder-blue) 11%, transparent);
  color: var(--color-tinder-blue);
  font-size: 9px;
  font-weight: 800;
}

.immersive-reader__evidence-list p {
  margin: 1px 0 0;
  color: var(--color-text-secondary);
  font-size: 11px;
  line-height: 1.7;
}

.immersive-reader__limitations {
  margin-top: 4px;
  padding-inline: 16px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-pink) 18%, var(--color-border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-tinder-pink) 4%, transparent);
}

.immersive-reader__analysis p {
  padding-left: 14px;
  border-left: 2px solid color-mix(in srgb, var(--color-tinder-blue) 34%, transparent);
}

.immersive-reader__resources > p {
  max-width: 680px;
}

.immersive-reader__resource-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.immersive-reader__resource-actions button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.immersive-reader__resource-actions button:hover,
.immersive-reader__resource-actions button:focus-visible {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 34%, var(--color-border));
  color: var(--color-tinder-pink);
}

.immersive-reader__resource-actions img {
  width: 14px;
  height: 14px;
}

.immersive-reader__status {
  margin: 16px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
}

.immersive-reader__context section {
  padding: 20px 18px;
  border-bottom: 1px solid var(--color-border);
}

.immersive-reader__context-tabs {
  position: sticky;
  z-index: 1;
  top: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  padding: 14px;
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-card) 96%, transparent);
  backdrop-filter: blur(10px);
}

.immersive-reader__outline-link {
  display: grid;
  width: 100%;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 10px 0;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 65%, transparent);
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.immersive-reader__outline-link > span {
  color: var(--color-tinder-blue);
  font-size: 11px;
  font-weight: 800;
}

.immersive-reader__outline-link strong {
  font-size: 13px;
  line-height: 1.5;
}

.immersive-reader__outline-link:hover,
.immersive-reader__outline-link:focus-visible {
  color: var(--color-tinder-pink);
}

.immersive-reader__context-tabs button {
  min-height: 34px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.immersive-reader__context-tabs button span {
  margin-left: 3px;
  color: var(--color-tinder-blue);
}

.immersive-reader__context-tabs button:hover,
.immersive-reader__context-tabs button:focus-visible,
.immersive-reader__context-tabs button.is-active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 24%, var(--color-border));
  background: color-mix(in srgb, var(--color-tinder-pink) 8%, transparent);
  color: var(--color-tinder-pink);
}

.immersive-reader__context-heading span {
  color: var(--color-text-muted);
  font-size: 11px;
}

.immersive-reader__context-title,
.immersive-reader__context-copy {
  margin: 12px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.immersive-reader__context-primary {
  width: 100%;
  min-height: 34px;
  margin-top: 13px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-pink) 28%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-tinder-pink) 8%, transparent);
  color: var(--color-tinder-pink);
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.immersive-reader__related-paper {
  display: block;
  width: 100%;
  padding: 13px 0;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 65%, transparent);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.immersive-reader__related-paper strong,
.immersive-reader__related-paper span,
.immersive-reader__related-paper small {
  display: block;
}

.immersive-reader__related-paper strong {
  font-size: 14px;
  line-height: 1.5;
}

.immersive-reader__related-paper span,
.immersive-reader__related-paper small {
  margin-top: 4px;
  color: var(--color-text-muted);
  font-size: 12px;
  line-height: 1.55;
}

.immersive-reader__related-paper small {
  color: var(--color-tinder-blue);
}

.immersive-reader__dock {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(3, minmax(112px, 1fr)) minmax(160px, 1.35fr);
  gap: 12px;
}

.immersive-reader__dock--three {
  grid-template-columns: repeat(2, minmax(112px, 1fr)) minmax(160px, 1.35fr);
}

.immersive-reader__dock button {
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.immersive-reader__dock button:hover,
.immersive-reader__dock button:focus-visible,
.immersive-reader__dock button.is-active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 35%, var(--color-border));
  color: var(--color-tinder-pink);
}

.immersive-reader__dock button:disabled {
  cursor: not-allowed;
  opacity: .42;
}

.immersive-reader__dock-icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--color-tinder-pink) 38%, transparent);
  border-radius: 50%;
  color: var(--color-tinder-pink);
}

.immersive-reader__dock-icon--blue {
  border-color: color-mix(in srgb, var(--color-tinder-blue) 40%, transparent);
  color: var(--color-tinder-blue);
}

.immersive-reader__dock-icon--green {
  border-color: color-mix(in srgb, var(--color-tag-score-high) 42%, transparent);
  color: var(--color-tag-score-high);
}

.immersive-reader__dock-icon img {
  width: 18px;
  height: 18px;
}

.immersive-reader__dock-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.immersive-reader__dock-copy strong {
  font-size: 13px;
}

.immersive-reader__dock-copy small {
  color: var(--color-text-muted);
  font-size: 10px;
  white-space: nowrap;
}

.immersive-reader__dock .immersive-reader__dock-primary {
  border-color: transparent;
  background: var(--color-tinder-pink);
  color: white;
}

.immersive-reader__dock .immersive-reader__dock-primary .immersive-reader__dock-icon {
  border-color: color-mix(in srgb, white 64%, transparent);
}

.immersive-reader__dock .immersive-reader__dock-primary small {
  color: color-mix(in srgb, white 82%, transparent);
}


:global(.dark) .immersive-reader__rail-button img,
:global(.dark) .immersive-reader__pager img,
:global(.dark) .immersive-reader__inline-actions img,
:global(.dark) .immersive-reader__resource-actions img,
:global(.dark) .immersive-reader__dock img {
  filter: invert(1);
}
@media (max-width: 1279px) {
  .immersive-reader__context-trigger {
    display: flex;
  }

  .immersive-reader__context-tabs {
    padding-right: 52px;
  }
}

@media (max-width: 767px) {
  .immersive-reader__rail-button {
    min-height: 36px;
    flex: 1 1 0;
    flex-direction: row;
    gap: 5px;
    padding: 4px 7px;
  }

  .immersive-reader__rail-button small {
    display: none;
  }

  .immersive-reader__document-inner {
    padding: 18px 18px 44px;
  }

  .immersive-reader__document-topline {
    align-items: flex-start;
    flex-direction: column;
    margin-bottom: 18px;
  }

  .immersive-reader__title-row {
    gap: 12px;
  }

  .immersive-reader__header h1 {
    font-size: 23px;
  }

  .immersive-reader__groups {
    grid-template-columns: minmax(0, 1fr);
  }

  .immersive-reader__group-heading {
    flex-direction: column;
    gap: 4px;
  }

  .immersive-reader__group-heading p {
    max-width: none;
    text-align: left;
  }

  .immersive-reader__dock {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 4px;
  }

  .immersive-reader__dock--three {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .immersive-reader__dock button {
    min-height: 56px;
    padding: 4px;
  }

  .immersive-reader__dock-copy small {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .immersive-reader__progress span {
    transition: none;
  }
}
</style>
