<script setup lang="ts">
import { computed } from 'vue'
import type { PaperSummary } from '../../types/paper'

const props = defineProps<{
  paper: PaperSummary
  index: number
  active: boolean
  selected: boolean
  collected: boolean
  bookmarked: boolean
  publicationDate?: string
}>()

const emit = defineEmits<{
  select: []
  open: []
  toggleSelection: []
  collect: []
  toggleBookmark: []
}>()

const displayTitle = computed(
  () => props.paper.short_title || props.paper['📖标题'] || props.paper.paper_id,
)
const originalTitle = computed(() => {
  const title = props.paper['📖标题']
  return title && title !== displayTitle.value ? title : ''
})
const authorsLine = computed(() => {
  const authors = props.paper.authors ?? []
  if (!authors.length) return '作者未知'
  const visible = authors.slice(0, 2).map(author => author.replace(/\s*\(.*?\)\s*/g, '').trim())
  return authors.length > 2 ? `${visible.join(', ')} et al.` : visible.join(', ')
})
const firstAuthor = computed(() => {
  const author = props.paper.authors?.[0]
  return author ? author.replace(/\s*\(.*?\)\s*/g, '').trim() : '—'
})
const normalizedScore = computed(() => {
  const score = props.paper.relevance_score
  if (score == null) return null
  return Math.round(score <= 1 ? score * 100 : score)
})
const tier = computed(() => {
  const value = props.paper.institution_tier
  return typeof value === 'number' && value >= 1 && value <= 4
    ? value
    : props.paper.is_large_institution ? 3 : 4
})

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    emit('open')
  }
  if (event.key === ' ') {
    event.preventDefault()
    emit('select')
  }
}
</script>

<template>
  <article
    class="workspace-paper-row"
    :class="{
      'workspace-paper-row--active': active,
      'workspace-paper-row--selected': selected,
    }"
    role="option"
    :aria-selected="active"
    :tabindex="active ? 0 : -1"
    @click="emit('select')"
    @dblclick="emit('open')"
    @keydown="handleKeydown"
  >
    <div class="workspace-paper-row__selection" @click.stop>
      <input
        type="checkbox"
        :checked="selected"
        :aria-label="`选择论文：${displayTitle}`"
        @change="emit('toggleSelection')"
      >
    </div>

    <div class="workspace-paper-row__paper">
      <div class="workspace-paper-row__eyebrow">
        <span class="workspace-paper-row__index">{{ index + 1 }}</span>
        <span class="workspace-paper-row__tier">T{{ tier }}</span>
        <span v-if="paper.institution" class="workspace-paper-row__institution">{{ paper.institution }}</span>
        <span v-for="category in paper.categories?.slice(0, 2)" :key="category" class="workspace-paper-row__category">
          {{ category }}
        </span>
      </div>
      <p class="workspace-paper-row__title">{{ displayTitle }}</p>
      <p v-if="originalTitle" class="workspace-paper-row__original-title">{{ originalTitle }}</p>
      <p class="workspace-paper-row__authors">{{ authorsLine }}</p>
    </div>

    <div class="workspace-paper-row__score" :aria-label="normalizedScore == null ? '暂无相关度' : `相关度 ${normalizedScore}`">
      <strong v-if="normalizedScore != null">{{ normalizedScore }}</strong>
      <span v-else>—</span>
      <small>相关度</small>
    </div>

    <div class="workspace-paper-row__author" :title="authorsLine">
      <span>{{ firstAuthor }}</span>
      <small>作者</small>
    </div>

    <time class="workspace-paper-row__date" :datetime="publicationDate || ''">
      <span>{{ publicationDate || '—' }}</span>
      <small>日期</small>
    </time>

    <div class="workspace-paper-row__actions" @click.stop>
      <button
        type="button"
        :class="{ 'workspace-paper-row__action--active': collected }"
        :aria-label="collected ? `已收藏：${displayTitle}` : `收藏到知识库：${displayTitle}`"
        @click="emit('collect')"
      >
        {{ collected ? '已收藏' : '收藏' }}
      </button>
      <button
        type="button"
        :class="{ 'workspace-paper-row__action--active': bookmarked }"
        :aria-label="bookmarked ? `取消稍后读：${displayTitle}` : `稍后读：${displayTitle}`"
        @click="emit('toggleBookmark')"
      >
        {{ bookmarked ? '已标记' : '稍后读' }}
      </button>
    </div>
  </article>
</template>

<style scoped>
.workspace-paper-row {
  display: grid;
  grid-template-columns: 32px minmax(260px, 1fr) 76px 112px 92px 124px;
  min-height: 94px;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 72%, transparent);
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background-color 140ms ease, box-shadow 140ms ease;
}

.workspace-paper-row:last-child {
  border-bottom: 0;
}

.workspace-paper-row:hover {
  background: color-mix(in srgb, var(--color-bg-hover) 72%, var(--color-bg-card));
}

.workspace-paper-row:focus-visible {
  position: relative;
  z-index: 1;
  outline: 2px solid color-mix(in srgb, var(--color-tinder-pink) 64%, white);
  outline-offset: -2px;
}

.workspace-paper-row--active {
  background: color-mix(in srgb, var(--color-tinder-pink) 7%, var(--color-bg-card));
  box-shadow: inset 3px 0 0 var(--color-tinder-pink);
}

.workspace-paper-row--selected {
  background: color-mix(in srgb, var(--color-tinder-pink) 11%, var(--color-bg-card));
}

.workspace-paper-row__selection {
  display: flex;
  justify-content: center;
}

.workspace-paper-row__selection input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-tinder-pink);
  cursor: pointer;
}

.workspace-paper-row__paper {
  min-width: 0;
}

.workspace-paper-row__eyebrow {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  margin-bottom: 4px;
  color: var(--color-text-muted);
  font-size: 10px;
}

.workspace-paper-row__index {
  min-width: 18px;
  font-variant-numeric: tabular-nums;
}

.workspace-paper-row__tier,
.workspace-paper-row__category {
  border-radius: 4px;
  padding: 1px 5px;
  background: color-mix(in srgb, var(--color-tinder-blue) 11%, transparent);
  color: var(--color-tinder-blue);
  font-weight: 700;
}

.workspace-paper-row__category {
  background: var(--color-bg-elevated);
  color: var(--color-text-muted);
  font-weight: 500;
}

.workspace-paper-row__institution {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-paper-row__title,
.workspace-paper-row__original-title,
.workspace-paper-row__authors {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-paper-row__title {
  color: var(--color-text-primary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}

.workspace-paper-row__original-title,
.workspace-paper-row__authors {
  margin-top: 2px;
  color: var(--color-text-muted);
  font-size: 10.5px;
  line-height: 1.3;
}

.workspace-paper-row__score,
.workspace-paper-row__author,
.workspace-paper-row__date {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  color: var(--color-text-secondary);
  font-size: 11px;
}

.workspace-paper-row__score strong {
  color: var(--color-tag-score-high);
  font-size: 15px;
  font-variant-numeric: tabular-nums;
}

.workspace-paper-row__author span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-paper-row__date span {
  font-variant-numeric: tabular-nums;
}

.workspace-paper-row__score small,
.workspace-paper-row__author small,
.workspace-paper-row__date small {
  color: var(--color-text-muted);
  font-size: 9px;
}

.workspace-paper-row__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.workspace-paper-row__actions button {
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-muted);
  font: inherit;
  font-size: 10px;
  cursor: pointer;
}

.workspace-paper-row__actions button:hover,
.workspace-paper-row__actions button:focus-visible {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 45%, var(--color-border));
  color: var(--color-text-primary);
}

.workspace-paper-row__actions .workspace-paper-row__action--active {
  border-color: color-mix(in srgb, var(--color-tinder-pink) 35%, transparent);
  background: color-mix(in srgb, var(--color-tinder-pink) 10%, transparent);
  color: var(--color-tinder-pink);
}

@media (max-width: 1599px) {
  .workspace-paper-row {
    grid-template-columns: 30px minmax(200px, 1fr) 58px 76px 82px 96px;
  }
}

@media (max-width: 1199px) {
  .workspace-paper-row {
    grid-template-columns: 28px minmax(0, 1fr) 58px 102px;
  }

  .workspace-paper-row__author,
  .workspace-paper-row__date {
    display: none;
  }
}

@media (max-width: 767px) {
  .workspace-paper-row {
    grid-template-columns: 26px minmax(0, 1fr) 46px;
    min-height: 82px;
    gap: 8px;
    padding: 10px;
  }

  .workspace-paper-row__actions {
    display: none;
  }

  .workspace-paper-row__score {
    align-items: flex-end;
  }

  .workspace-paper-row__original-title,
  .workspace-paper-row__category {
    display: none;
  }
}
</style>
