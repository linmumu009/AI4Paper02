<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PaperSummary } from '../../types/paper'
import { isAuthenticated } from '../../stores/auth'
import { useWorkspacePaperDetail } from '../../composables/useWorkspacePaperDetail'
import AddToProjectDialog from '../project/AddToProjectDialog.vue'

const props = defineProps<{
  paper: PaperSummary | null
  publicationDate?: string
  collected?: boolean
  bookmarked?: boolean
  collectionActionLabel?: string
  collectionActionTone?: 'primary' | 'danger' | 'neutral'
  projectActionPrimary?: boolean
  sourceScope?: string
}>()

const emit = defineEmits<{
  openDetail: []
  openPdf: []
  collect: []
  toggleBookmark: []
  startResearch: []
}>()

const showProjectDialog = ref(false)

const paperRef = computed(() => props.paper)
const { detail, detailLoading, detailError, summary } = useWorkspacePaperDetail(paperRef)
const title = computed(() => summary.value?.short_title || summary.value?.['📖标题'] || props.paper?.paper_id || '')
const originalTitle = computed(() => {
  const value = summary.value?.['📖标题']
  return value && value !== title.value ? value : ''
})
const authorsLine = computed(() => {
  const authors = summary.value?.authors ?? []
  if (!authors.length) return '作者信息暂缺'
  const visible = authors.slice(0, 3).map(author => author.replace(/\s*\(.*?\)\s*/g, '').trim())
  return authors.length > 3 ? `${visible.join(', ')} et al.` : visible.join(', ')
})
const score = computed(() => {
  const value = summary.value?.relevance_score
  if (value == null) return null
  return Math.round(value <= 1 ? value * 100 : value)
})
const researchQuestion = computed(() => summary.value?.['🛎️文章简介']?.['🔸研究问题'] || '')
const mainContribution = computed(() => summary.value?.['🛎️文章简介']?.['🔸主要贡献'] || '')
const keyThoughts = computed(() => summary.value?.['📝重点思路']?.filter(Boolean).slice(0, 5) ?? [])
const analysisSummary = computed(() => summary.value?.['🔎分析总结']?.filter(Boolean).slice(0, 3) ?? [])
const evidenceItems = computed(() => {
  const evidence = detail.value?.paper_assets?.blocks.evidence_chain
  const results = detail.value?.paper_assets?.blocks.results
  return [
    ...(evidence?.strongly_supported_claims ?? []),
    ...(evidence?.key_evidence_from_figures_tables_appendix ?? []),
    ...(results?.numerical_results ?? []),
  ].filter(Boolean).slice(0, 4)
})

</script>

<template>
  <aside class="paper-inspector" aria-label="选中论文详情">
    <div v-if="!paper" class="paper-inspector__empty">
      <strong>选择一篇论文</strong>
      <p>单击列表行查看摘要、证据和研究操作。</p>
    </div>

    <template v-else>
      <header class="paper-inspector__header">
        <div class="paper-inspector__badges">
          <span v-if="paper.institution">{{ paper.institution }}</span>
          <span v-for="category in paper.categories?.slice(0, 3)" :key="category">{{ category }}</span>
          <strong v-if="score != null">{{ score }}</strong>
        </div>
        <h2>{{ title }}</h2>
        <p v-if="originalTitle" class="paper-inspector__original-title">{{ originalTitle }}</p>
        <p class="paper-inspector__meta">{{ authorsLine }}</p>
        <p class="paper-inspector__meta">arXiv:{{ paper.paper_id }}<span v-if="publicationDate"> · {{ publicationDate }}</span></p>
      </header>

      <div class="paper-inspector__actions">
        <button
          type="button"
          class="paper-inspector__primary"
          :class="{ 'paper-inspector__danger-action': collectionActionTone === 'danger', 'paper-inspector__neutral-action': collectionActionTone === 'neutral' }"
          @click="emit('collect')"
        >
          {{ collectionActionLabel || (collected ? '已收藏到知识库' : '收藏到知识库') }}
        </button>
        <button type="button" @click="emit('startResearch')">开始深度研究</button>
        <button type="button" @click="emit('openPdf')">PDF</button>
        <button type="button" @click="emit('openDetail')">精读</button>
        <button type="button" :class="{ 'paper-inspector__active-action': bookmarked }" @click="emit('toggleBookmark')">
          {{ bookmarked ? '已标记稍后读' : '稍后读' }}
        </button>
        <button
          v-if="isAuthenticated"
          type="button"
          :class="{ 'paper-inspector__project-primary': projectActionPrimary }"
          @click="showProjectDialog = true"
        >加入课题</button>
      </div>

      <div class="paper-inspector__body">
        <section v-if="summary?.['推荐理由'] || summary?.why_recommended" class="paper-inspector__recommendation">
          <h3>推荐理由</h3>
          <p>{{ summary?.why_recommended || summary?.['推荐理由'] }}</p>
        </section>

        <section v-if="summary?.abstract">
          <h3>摘要</h3>
          <p>{{ summary.abstract }}</p>
        </section>

        <section v-if="researchQuestion || mainContribution">
          <h3>文章简介</h3>
          <dl>
            <template v-if="researchQuestion">
              <dt>研究问题</dt>
              <dd>{{ researchQuestion }}</dd>
            </template>
            <template v-if="mainContribution">
              <dt>主要贡献</dt>
              <dd>{{ mainContribution }}</dd>
            </template>
          </dl>
        </section>

        <section v-if="keyThoughts.length">
          <h3>重点思路</h3>
          <ol class="paper-inspector__numbered-list">
            <li v-for="(item, index) in keyThoughts" :key="`${index}-${item}`">
              <span>{{ index + 1 }}</span>
              <p>{{ item }}</p>
            </li>
          </ol>
        </section>

        <section v-if="analysisSummary.length">
          <h3>分析总结</h3>
          <p v-for="(item, index) in analysisSummary" :key="`${index}-${item}`">{{ item }}</p>
        </section>

        <section v-if="summary?.['💡个人观点'] || summary?.['一句话记忆版']">
          <h3>阅读记忆</h3>
          <p>{{ summary?.['一句话记忆版'] || summary?.['💡个人观点'] }}</p>
        </section>

        <section v-if="evidenceItems.length">
          <h3>关键证据</h3>
          <ul>
            <li v-for="item in evidenceItems" :key="item">{{ item }}</li>
          </ul>
        </section>

        <p v-if="detailLoading" class="paper-inspector__status">正在补充结构化证据…</p>
        <p v-else-if="detailError && !summary?.abstract" class="paper-inspector__status">详细证据暂时不可用</p>
      </div>

      <AddToProjectDialog
        v-if="showProjectDialog"
        asset-type="paper"
        :asset-id="paper.paper_id"
        :source-scope="sourceScope || 'digest'"
        :asset-title="title"
        @close="showProjectDialog = false"
      />
    </template>
  </aside>
</template>

<style scoped>
.paper-inspector {
  display: flex;
  width: 100%;
  min-width: 0;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg-card);
  color: var(--color-text-primary);
}

.paper-inspector__empty {
  display: flex;
  height: 100%;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 32px;
  text-align: center;
}

.paper-inspector__empty strong {
  font-size: 14px;
}

.paper-inspector__empty p {
  max-width: 240px;
  margin: 7px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
  line-height: 1.6;
}

.paper-inspector__header {
  flex: 0 0 auto;
  padding: 20px 20px 14px;
  border-bottom: 1px solid var(--color-border);
}

.paper-inspector__badges {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 10px;
}

.paper-inspector__badges span {
  border-radius: 5px;
  padding: 2px 6px;
  background: var(--color-bg-elevated);
  color: var(--color-text-muted);
  font-size: 10px;
}

.paper-inspector__badges strong {
  margin-left: auto;
  color: var(--color-tag-score-high);
  font-size: 16px;
}

.paper-inspector__header h2 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: 18px;
  line-height: 1.38;
}

.paper-inspector__original-title,
.paper-inspector__meta {
  margin: 7px 0 0;
  color: var(--color-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.paper-inspector__original-title {
  color: var(--color-text-secondary);
}

.paper-inspector__actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  flex: 0 0 auto;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border);
}

.paper-inspector__actions button {
  min-height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 140ms ease, color 140ms ease, background-color 140ms ease;
}

.paper-inspector__actions button:hover,
.paper-inspector__actions button:focus-visible {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 45%, var(--color-border));
  color: var(--color-text-primary);
}

.paper-inspector__actions .paper-inspector__primary {
  border-color: transparent;
  background: var(--color-tinder-pink);
  color: white;
}

.paper-inspector__actions .paper-inspector__danger-action {
  border-color: color-mix(in srgb, #ef4444 35%, var(--color-border));
  background: color-mix(in srgb, #ef4444 8%, var(--color-bg-card));
  color: #dc3545;
}

.paper-inspector__actions .paper-inspector__neutral-action {
  border-color: var(--color-border);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
}

.paper-inspector__actions .paper-inspector__project-primary {
  order: -1;
  grid-column: 1 / -1;
  border-color: transparent;
  background: var(--color-tinder-pink);
  color: white;
}

.paper-inspector__actions .paper-inspector__active-action {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 40%, transparent);
  background: color-mix(in srgb, var(--color-tinder-pink) 10%, var(--color-bg-card));
  color: var(--color-tinder-pink);
}

.paper-inspector__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 0 20px 28px;
}

.paper-inspector__body section {
  padding: 17px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 72%, transparent);
}

.paper-inspector__body h3 {
  margin: 0 0 8px;
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 800;
}

.paper-inspector__body p,
.paper-inspector__body li,
.paper-inspector__body dd {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 11.5px;
  line-height: 1.72;
}

.paper-inspector__body p + p {
  margin-top: 7px;
}

.paper-inspector__body dl {
  margin: 0;
}

.paper-inspector__body dt {
  margin: 9px 0 3px;
  color: var(--color-tinder-pink);
  font-size: 10px;
  font-weight: 800;
}

.paper-inspector__body dt:first-child {
  margin-top: 0;
}

.paper-inspector__recommendation {
  margin-top: 14px;
  padding: 12px 13px !important;
  border: 1px solid color-mix(in srgb, var(--color-tinder-blue) 20%, transparent) !important;
  border-radius: 9px;
  background: color-mix(in srgb, var(--color-tinder-blue) 7%, transparent);
}

.paper-inspector__recommendation h3 {
  color: var(--color-tinder-blue);
}

.paper-inspector__numbered-list,
.paper-inspector__body ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.paper-inspector__numbered-list li {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 7px;
  margin-top: 8px;
}

.paper-inspector__numbered-list li > span {
  display: flex;
  width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-tinder-blue) 15%, transparent);
  color: var(--color-tinder-blue);
  font-size: 10px;
  font-weight: 800;
}

.paper-inspector__body ul li {
  position: relative;
  padding-left: 12px;
  margin-top: 7px;
}

.paper-inspector__body ul li::before {
  position: absolute;
  left: 0;
  color: var(--color-tinder-pink);
  content: '•';
}

.paper-inspector__status {
  padding: 14px 0;
  color: var(--color-text-muted) !important;
  font-size: 10.5px !important;
}

@media (max-width: 1279px) {
  .paper-inspector__header {
    padding-top: 48px;
  }
}
</style>
