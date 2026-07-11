<script setup lang="ts">
import { ref, computed } from 'vue'
import type { IdeaAtom, IdeaSourcePaper } from '../../types/paper'

const props = defineProps<{
  paperId: string
  paperInfo: IdeaSourcePaper | null
  relatedAtoms: IdeaAtom[]
  /** 父组件还在请求论文标题时传 true，卡片头部显示骨架而非 paper_id */
  loading?: boolean
}>()

const expanded = ref(false)

const displayTitle = computed(() => {
  const info = props.paperInfo
  if (!info || !info.title || info.title === props.paperId) return props.paperId
  return info.title
})

const hasMeaningfulTitle = computed(
  () => props.paperInfo && props.paperInfo.title && props.paperInfo.title !== props.paperId,
)

/** 所有关联原子的证据条数（原子级别原文引用） */
const totalEvidenceCount = computed(() =>
  props.relatedAtoms.reduce(
    (acc, atom) => acc + ((atom.evidence as unknown[]) ?? []).length,
    0,
  ),
)

const sourceTypeBadge = computed(() => {
  switch (props.paperInfo?.source_type) {
    case 'kb':
      return { label: 'KB 论文', bgClass: 'badge-kb' }
    case 'user_upload':
      return { label: '上传论文', bgClass: 'badge-upload' }
    case 'pipeline':
      return { label: 'arXiv 推荐', bgClass: 'badge-pipeline' }
    default:
      return null
  }
})

const atomTypeLabel: Record<string, string> = {
  claim: '论断',
  method: '方法',
  setup: '设置',
  limitation: '局限',
  tag: '标签',
}

const atomTypeIcon: Record<string, string> = {
  claim: '💬',
  method: '⚙️',
  setup: '📊',
  limitation: '⚠️',
  tag: '🏷️',
}

// 按类型分组，优先展示 limitation 和 method
const sortedAtomTypes = computed(() => {
  const priority = ['limitation', 'method', 'claim', 'setup', 'tag']
  const groups: Record<string, IdeaAtom[]> = {}
  for (const atom of props.relatedAtoms) {
    if (!groups[atom.atom_type]) groups[atom.atom_type] = []
    groups[atom.atom_type].push(atom)
  }
  return priority.filter((t) => groups[t]?.length).map((t) => ({ type: t, atoms: groups[t] }))
})
</script>

<template>
  <div class="source-paper-card">
    <!-- ── 折叠触发头部 ── -->
    <button
      class="card-header"
      :class="{ 'card-header--expanded': expanded }"
      @click="expanded = !expanded"
    >
      <!-- 论文图标 -->
      <div class="paper-icon">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          class="w-4 h-4"
        >
          <path
            d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
          />
        </svg>
      </div>

      <!-- 标题区 -->
      <div class="card-title-area">
        <!-- 论文标题加载中：显示骨架行 -->
        <span v-if="loading && !paperInfo" class="paper-title-skeleton" />
        <p v-else class="paper-title" :class="{ 'paper-title--id': !hasMeaningfulTitle }">
          {{ displayTitle }}
        </p>
        <div class="paper-meta-row">
          <span class="paper-id-mono">{{ paperId }}</span>
          <span v-if="paperInfo?.institution" class="paper-institution">
            {{ paperInfo.institution }}
          </span>
          <span v-if="loading && !paperInfo" class="paper-loading-hint">标题加载中…</span>
        </div>
      </div>

      <!-- 右侧 badges + 展开箭头 -->
      <div class="card-right-badges">
        <span v-if="sourceTypeBadge" class="source-type-badge" :class="sourceTypeBadge.bgClass">
          {{ sourceTypeBadge.label }}
        </span>
        <span v-if="totalEvidenceCount > 0" class="evidence-count-badge">
          {{ totalEvidenceCount }} 引用
        </span>
        <span v-if="relatedAtoms.length" class="atom-count-badge">
          {{ relatedAtoms.length }} 原子
        </span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          class="expand-chevron"
          :class="{ 'expand-chevron--open': expanded }"
        >
          <path
            fill-rule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clip-rule="evenodd"
          />
        </svg>
      </div>
    </button>

    <!-- ── 展开内容区 ── -->
    <Transition name="card-expand">
      <div v-if="expanded" class="card-expanded-body">
        <!-- 摘要 / 推荐理由 -->
        <div v-if="paperInfo?.abstract" class="paper-abstract-block">
          <p class="section-label-mini">摘要 / 推荐理由</p>
          <p class="paper-abstract-text">{{ paperInfo.abstract }}</p>
        </div>

        <!-- 关联原子列表 -->
        <div v-if="relatedAtoms.length" class="paper-atoms-block">
          <p class="section-label-mini">关联原子（共 {{ relatedAtoms.length }} 条）</p>
          <div
            v-for="group in sortedAtomTypes"
            :key="group.type"
            class="atom-type-group"
          >
            <p class="atom-group-header">
              <span class="atom-icon">{{ atomTypeIcon[group.type] ?? '📄' }}</span>
              <span>{{ atomTypeLabel[group.type] ?? group.type }}</span>
            </p>
            <div class="atom-items">
              <div
                v-for="atom in group.atoms.slice(0, 3)"
                :key="atom.id"
                class="atom-item-block"
              >
                <p class="atom-item-text">
                  {{ atom.content.length > 160 ? atom.content.slice(0, 160) + '…' : atom.content }}
                </p>
                <!-- 原文证据摘录 -->
                <div
                  v-for="(ev, eidx) in ((atom.evidence ?? []) as Array<Record<string, unknown>>).slice(0, 2)"
                  :key="eidx"
                  class="atom-evidence-snippet"
                >
                  <span class="atom-evidence-location">
                    {{ (ev['location'] ?? ev['section'] ?? '未知位置') as string }}
                  </span>
                  <span class="atom-evidence-text">
                    "{{ ((ev['text'] ?? ev['snippet'] ?? '') as string).slice(0, 120) }}"
                  </span>
                </div>
                <p v-if="!(atom.evidence?.length)" class="atom-no-evidence">⚠️ 无原文引用</p>
              </div>
              <p v-if="group.atoms.length > 3" class="atom-more-hint">
                + {{ group.atoms.length - 3 }} 条
              </p>
            </div>
          </div>
        </div>

        <!-- 无原子兜底 -->
        <div v-if="!relatedAtoms.length" class="no-atoms-hint">
          <span>该来源暂无关联原子</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* ── 卡片容器 ── */
.source-paper-card {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-card);
  overflow: hidden;
}

/* ── 折叠头部 ── */
.card-header {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s ease;
}

.card-header:hover {
  background: var(--color-bg-hover, rgba(255, 255, 255, 0.04));
}

.card-header--expanded {
  border-bottom: 1px solid var(--color-border);
}

/* ── 论文图标 ── */
.paper-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  flex-shrink: 0;
  margin-top: 1px;
}

/* ── 标题区 ── */
.card-title-area {
  flex: 1;
  min-width: 0;
}

.paper-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0 0 4px 0;
}

.paper-title--id {
  font-size: 12px;
  font-family: 'Fira Code', 'Courier New', monospace;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.paper-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.paper-id-mono {
  font-size: 11px;
  font-family: 'Fira Code', 'Courier New', monospace;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.paper-institution {
  font-size: 11px;
  color: var(--color-text-muted);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 1px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

/* ── 右侧 badges + 箭头 ── */
.card-right-badges {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  margin-top: 2px;
}

.source-type-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 9999px;
  border: 1px solid transparent;
  white-space: nowrap;
}

.badge-kb {
  background: rgba(99, 179, 237, 0.12);
  color: #63b3ed;
  border-color: rgba(99, 179, 237, 0.25);
}

.badge-upload {
  background: rgba(251, 191, 36, 0.12);
  color: #f6ad55;
  border-color: rgba(251, 191, 36, 0.25);
}

.badge-pipeline {
  background: rgba(167, 139, 250, 0.12);
  color: #a78bfa;
  border-color: rgba(167, 139, 250, 0.25);
}

.atom-count-badge {
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 9999px;
  padding: 2px 7px;
  white-space: nowrap;
}

.expand-chevron {
  width: 16px;
  height: 16px;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.expand-chevron--open {
  transform: rotate(180deg);
}

/* ── 展开内容 ── */
.card-expanded-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-label-mini {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  margin: 0 0 6px 0;
}

/* 摘要块 */
.paper-abstract-block {
  /* container */
}

.paper-abstract-text {
  font-size: 12.5px;
  color: var(--color-text-secondary);
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
}

/* 原子列表块 */
.paper-atoms-block {
  /* container */
}

.atom-type-group {
  margin-bottom: 10px;
}

.atom-group-header {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin: 0 0 5px 0;
}

.atom-icon {
  font-size: 12px;
  line-height: 1;
}

.atom-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 18px;
}

.atom-item-text {
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.55;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 5px 9px;
  margin: 0;
}

.atom-more-hint {
  font-size: 11px;
  color: var(--color-text-muted);
  padding: 2px 9px;
  margin: 0;
  font-style: italic;
}

.no-atoms-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  font-style: italic;
  text-align: center;
  padding: 8px 0;
}

/* ── 标题加载骨架 ── */
.paper-title-skeleton {
  display: block;
  width: 70%;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    rgba(255,255,255,0.05) 25%,
    rgba(255,255,255,0.1) 50%,
    rgba(255,255,255,0.05) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
  margin-bottom: 4px;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.paper-loading-hint {
  font-size: 10px;
  color: var(--color-text-muted);
  font-style: italic;
  opacity: 0.7;
}

/* ── 证据条数 badge ── */
.evidence-count-badge {
  font-size: 10px;
  font-weight: 600;
  color: rgba(99,179,237,0.85);
  background: rgba(99,179,237,0.1);
  border: 1px solid rgba(99,179,237,0.25);
  border-radius: 9999px;
  padding: 2px 7px;
  white-space: nowrap;
}

/* ── 原子块（含证据） ── */
.atom-item-block {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.atom-evidence-snippet {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 4px 0 0 0;
  border-top: 1px solid var(--color-border);
}
.atom-evidence-location {
  font-size: 9.5px;
  color: var(--color-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  padding-top: 1px;
  opacity: 0.7;
}
.atom-evidence-text {
  font-size: 10.5px;
  color: var(--color-text-muted);
  font-style: italic;
  line-height: 1.5;
}

.atom-no-evidence {
  font-size: 9.5px;
  color: rgba(251,191,36,0.7);
  margin: 0;
}

/* ── 展开动画 ── */
.card-expand-enter-active,
.card-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
  transform-origin: top;
}

.card-expand-enter-from,
.card-expand-leave-to {
  opacity: 0;
  transform: scaleY(0.95);
}
</style>
