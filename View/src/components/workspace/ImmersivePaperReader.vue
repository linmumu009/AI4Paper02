<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkspacePaperDetail } from '../../composables/useWorkspacePaperDetail'
import { isAuthenticated } from '../../stores/auth'
import type { PaperSummary } from '../../types/paper'
import AddToProjectDialog from '../project/AddToProjectDialog.vue'
import arrowLeftIcon from '../../assets/heroicons/arrow-left.svg'
import arrowRightIcon from '../../assets/heroicons/arrow-right.svg'
import beakerIcon from '../../assets/heroicons/beaker.svg'
import bookOpenIcon from '../../assets/heroicons/book-open.svg'
import bookmarkIcon from '../../assets/heroicons/bookmark.svg'
import chartIcon from '../../assets/heroicons/chart-bar-square.svg'
import documentIcon from '../../assets/heroicons/document-text.svg'
import heartIcon from '../../assets/heroicons/heart.svg'
import scaleIcon from '../../assets/heroicons/scale.svg'
import squaresIcon from '../../assets/heroicons/squares-2x2.svg'
import xMarkIcon from '../../assets/heroicons/x-mark.svg'
const props = defineProps<{
  paper: PaperSummary
  relatedPapers: PaperSummary[]
  publicationDate?: string
  position: number
  total: number
  collected?: boolean
  bookmarked?: boolean
  canGoPrevious?: boolean
  canGoNext?: boolean
}>()

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
  changeMode: [mode: 'card' | 'list']
  login: []
}>()

const showProjectDialog = ref(false)
const paperRef = computed(() => props.paper)
const { detail, detailLoading, detailError, summary } = useWorkspacePaperDetail(paperRef)

const title = computed(() => summary.value?.short_title || summary.value?.['📖标题'] || props.paper.paper_id)
const originalTitle = computed(() => {
  const value = summary.value?.['📖标题']
  return value && value !== title.value ? value : ''
})
const authorsLine = computed(() => {
  const authors = summary.value?.authors ?? []
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
const keyThoughts = computed(() => summary.value?.['📝重点思路']?.filter(Boolean).slice(0, 5) ?? [])
const analysisSummary = computed(() => summary.value?.['🔎分析总结']?.filter(Boolean).slice(0, 3) ?? [])

const evidenceCards = computed(() => {
  const blocks = detail.value?.paper_assets?.blocks
  const result = blocks?.results?.numerical_results?.[0]
    || blocks?.results?.main_findings?.[0]
    || analysisSummary.value[0]
  const method = blocks?.method?.key_mechanisms?.[0]
    || blocks?.method?.novelty?.[0]
    || keyThoughts.value[0]
  const boundary = blocks?.limitations?.threats_to_validity?.[0]
    || blocks?.limitations?.generalization_limits?.[0]
    || mainContribution.value
  return [
    { label: '关键结果', value: result },
    { label: '方法证据', value: method },
    { label: '可信边界', value: boundary },
  ].filter(card => Boolean(card.value))
})

const relatedTitle = (paper: PaperSummary) => paper.short_title || paper['📖标题'] || paper.paper_id
</script>

<template>
  <section class="immersive-reader" aria-label="沉浸论文阅读">
    <nav class="immersive-reader__rail" aria-label="沉浸阅读快捷入口">
      <button type="button" class="immersive-reader__rail-button immersive-reader__rail-button--active" aria-label="返回论文列表" title="返回论文列表" @click="emit('changeMode', 'list')">
        <img :src="bookOpenIcon" alt="">
        <span class="sr-only">返回论文列表</span>
      </button>
      <button type="button" class="immersive-reader__rail-button" :class="{ 'immersive-reader__rail-button--marked': collected }" :aria-label="collected ? '已收藏到知识库' : '收藏到知识库'" title="收藏到知识库" @click="emit('collect')">
        <img :src="bookmarkIcon" alt="">
        <span class="sr-only">收藏到知识库</span>
      </button>
      <button type="button" class="immersive-reader__rail-button" aria-label="与相关文章对比" title="与相关文章对比" @click="emit('compare')">
        <img :src="squaresIcon" alt="">
        <span class="sr-only">与相关文章对比</span>
      </button>
      <button type="button" class="immersive-reader__rail-button" aria-label="开始深度研究" title="开始深度研究" @click="emit('startResearch')">
        <img :src="chartIcon" alt="">
        <span class="sr-only">开始深度研究</span>
      </button>
    </nav>

    <main class="immersive-reader__document">
      <div class="immersive-reader__document-inner">
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
            <button type="button" :class="{ 'is-active': bookmarked }" @click="emit('toggleBookmark')">
              <img :src="bookmarkIcon" alt="">{{ bookmarked ? '已标记稍后读' : '稍后读' }}
            </button>
          </div>
        </header>

        <section v-if="recommendation" class="immersive-reader__recommendation">
          <h2>推荐理由</h2>
          <p>{{ recommendation }}</p>
        </section>

        <section v-if="summary?.abstract" class="immersive-reader__section">
          <h2>摘要</h2>
          <p>{{ summary.abstract }}</p>
        </section>

        <section v-if="researchQuestion || mainContribution" class="immersive-reader__section">
          <h2>关键思路</h2>
          <ul>
            <li v-if="researchQuestion">{{ researchQuestion }}</li>
            <li v-if="mainContribution">{{ mainContribution }}</li>
            <li v-for="item in keyThoughts.slice(0, 3)" :key="item">{{ item }}</li>
          </ul>
        </section>

        <section v-if="evidenceCards.length" class="immersive-reader__section">
          <div class="immersive-reader__section-heading">
            <h2>核心证据</h2>
            <span>来自结构化论文证据</span>
          </div>
          <div class="immersive-reader__evidence-grid">
            <article v-for="card in evidenceCards" :key="card.label">
              <h3>{{ card.label }}</h3>
              <p>{{ card.value }}</p>
            </article>
          </div>
        </section>

        <section v-if="analysisSummary.length" class="immersive-reader__section immersive-reader__analysis">
          <h2>分析总结</h2>
          <p v-for="item in analysisSummary" :key="item">{{ item }}</p>
        </section>

        <p v-if="detailLoading" class="immersive-reader__status">正在补充结构化证据…</p>
        <p v-else-if="detailError" class="immersive-reader__status">{{ detailError }}</p>
      </div>
    </main>

    <aside class="immersive-reader__context" aria-label="论文研究上下文">
      <section>
        <div class="immersive-reader__context-heading">
          <h2>研究课题</h2>
          <span>{{ isAuthenticated ? '当前论文' : '登录后启用' }}</span>
        </div>
        <template v-if="isAuthenticated">
          <p class="immersive-reader__context-title">把这篇论文加入正在推进的研究课题</p>
          <button type="button" class="immersive-reader__context-primary" @click="showProjectDialog = true">加入课题</button>
        </template>
        <template v-else>
          <p class="immersive-reader__context-copy">登录后可以保存论文、建立课题并持续追踪研究脉络。</p>
          <button type="button" class="immersive-reader__context-primary" @click="emit('login')">登录并使用</button>
        </template>
      </section>

      <section>
        <div class="immersive-reader__context-heading">
          <h2>相关论文</h2>
          <span>{{ relatedPapers.length }} 篇</span>
        </div>
        <button
          v-for="related in relatedPapers"
          :key="related.paper_id"
          type="button"
          class="immersive-reader__related-paper"
          @click="emit('selectRelated', related.paper_id)"
        >
          <strong>{{ relatedTitle(related) }}</strong>
          <span>{{ related.authors?.slice(0, 2).join(', ') || related.institution || related.paper_id }}</span>
          <small>{{ related.categories?.slice(0, 2).join(' · ') || '相关研究' }}</small>
        </button>
        <p v-if="relatedPapers.length === 0" class="immersive-reader__context-copy">当前筛选结果中暂无相关论文。</p>
      </section>
    </aside>

    <footer class="immersive-reader__dock" aria-label="论文决策操作">
      <button type="button" @click="emit('skip')">
        <span class="immersive-reader__dock-icon"><img :src="xMarkIcon" alt=""></span>
        <span class="immersive-reader__dock-copy"><strong>跳过</strong><small>不感兴趣</small></span>
      </button>
      <button type="button" @click="emit('compare')">
        <span class="immersive-reader__dock-icon immersive-reader__dock-icon--blue"><img :src="scaleIcon" alt=""></span>
        <span class="immersive-reader__dock-copy"><strong>对比</strong><small>与相关文章比较</small></span>
      </button>
      <button type="button" :class="{ 'is-active': collected }" @click="emit('collect')">
        <span class="immersive-reader__dock-icon immersive-reader__dock-icon--green"><img :src="heartIcon" alt=""></span>
        <span class="immersive-reader__dock-copy"><strong>{{ collected ? '已收藏' : '收藏' }}</strong><small>加入知识库</small></span>
      </button>
      <button type="button" class="immersive-reader__dock-primary" @click="emit('startResearch')">
        <span class="immersive-reader__dock-icon"><img :src="beakerIcon" alt=""></span>
        <span class="immersive-reader__dock-copy"><strong>深度研究</strong><small>深入追踪这条线索</small></span>
      </button>
    </footer>

    <AddToProjectDialog
      v-if="showProjectDialog"
      asset-type="paper"
      :asset-id="paper.paper_id"
      source-scope="digest"
      :asset-title="title"
      @close="showProjectDialog = false"
    />
  </section>
</template>

<style scoped>
.immersive-reader {
  position: relative;
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-columns: 68px minmax(0, 1fr) 336px;
  padding-bottom: 88px;
  overflow: hidden;
  background: var(--color-bg);
  color: var(--color-text-primary);
}

.immersive-reader__rail {
  display: flex;
  min-height: 0;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 16px 7px;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-card);
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

.immersive-reader__rail-button:hover,
.immersive-reader__rail-button:focus-visible,
.immersive-reader__rail-button--active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 22%, transparent);
  background: color-mix(in srgb, var(--color-tinder-pink) 8%, transparent);
  color: var(--color-tinder-pink);
}

.immersive-reader__rail-button--marked {
  color: var(--color-tag-score-high);
}

.immersive-reader__document,
.immersive-reader__context {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.immersive-reader__document {
  background: var(--color-bg-card);
}

.immersive-reader__document-inner {
  width: min(100%, 1000px);
  margin: 0 auto;
  padding: 24px 40px 62px;
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
  font-size: 10px;
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
  font-size: 10px;
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
  font-size: 10px;
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
  font-size: 11px;
  line-height: 1.55;
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
  font-size: 8px;
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
  margin-top: 20px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--color-tinder-pink) 16%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-tinder-pink) 7%, transparent);
}

.immersive-reader__recommendation h2,
.immersive-reader__section h2,
.immersive-reader__context h2 {
  margin: 0;
  font-size: 13px;
  font-weight: 800;
}

.immersive-reader__recommendation h2 {
  color: var(--color-tinder-pink);
}

.immersive-reader__recommendation p,
.immersive-reader__section p,
.immersive-reader__section li {
  margin: 7px 0 0;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.8;
}

.immersive-reader__section {
  padding: 22px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 72%, transparent);
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

.immersive-reader__section-heading span {
  color: var(--color-text-muted);
  font-size: 9px;
}

.immersive-reader__evidence-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.immersive-reader__evidence-grid article {
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: var(--color-bg);
}

.immersive-reader__evidence-grid h3 {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 9px;
  font-weight: 700;
}

.immersive-reader__evidence-grid p {
  display: -webkit-box;
  margin-top: 7px;
  overflow: hidden;
  color: var(--color-tinder-blue);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.immersive-reader__analysis p {
  padding-left: 14px;
  border-left: 2px solid color-mix(in srgb, var(--color-tinder-blue) 34%, transparent);
}

.immersive-reader__status {
  margin: 16px 0 0;
  color: var(--color-text-muted);
  font-size: 10px;
}

.immersive-reader__context {
  border-left: 1px solid var(--color-border);
  background: var(--color-bg-card);
}

.immersive-reader__context section {
  padding: 20px 18px;
  border-bottom: 1px solid var(--color-border);
}

.immersive-reader__context-heading span {
  color: var(--color-text-muted);
  font-size: 9px;
}

.immersive-reader__context-title,
.immersive-reader__context-copy {
  margin: 12px 0 0;
  color: var(--color-text-secondary);
  font-size: 11px;
  line-height: 1.65;
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
  font-size: 10px;
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
  font-size: 11px;
  line-height: 1.45;
}

.immersive-reader__related-paper span,
.immersive-reader__related-paper small {
  margin-top: 4px;
  color: var(--color-text-muted);
  font-size: 9px;
  line-height: 1.45;
}

.immersive-reader__related-paper small {
  color: var(--color-tinder-blue);
}

.immersive-reader__dock {
  position: absolute;
  z-index: 5;
  right: 100px;
  bottom: 0;
  left: 100px;
  display: grid;
  grid-template-columns: repeat(3, minmax(112px, 1fr)) minmax(160px, 1.35fr);
  gap: 12px;
  padding: 10px 72px;
  border-top: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-card) 95%, transparent);
  box-shadow: 0 -8px 22px color-mix(in srgb, #000 7%, transparent);
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
  font-size: 11px;
}

.immersive-reader__dock-copy small {
  color: var(--color-text-muted);
  font-size: 8px;
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


:global(.dark) .immersive-reader__rail img,
:global(.dark) .immersive-reader__pager img,
:global(.dark) .immersive-reader__inline-actions img,
:global(.dark) .immersive-reader__dock img {
  filter: invert(1);
}
@media (max-width: 1279px) {
  .immersive-reader {
    grid-template-columns: 58px minmax(0, 1fr);
  }

  .immersive-reader__context {
    display: none;
  }

  .immersive-reader__dock {
    right: 24px;
    left: 82px;
    padding-inline: 34px;
  }
}

@media (max-width: 767px) {
  .immersive-reader {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 48px minmax(0, 1fr);
    padding-bottom: 72px;
  }

  .immersive-reader__rail {
    flex-direction: row;
    gap: 4px;
    padding: 5px 8px;
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }

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

  .immersive-reader__evidence-grid {
    grid-template-columns: 1fr;
  }

  .immersive-reader__dock {
    right: 0;
    left: 0;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 4px;
    padding: 7px;
  }

  .immersive-reader__dock button {
    min-height: 56px;
    padding: 4px;
  }

  .immersive-reader__dock-copy small {
    display: none;
  }
}
</style>
