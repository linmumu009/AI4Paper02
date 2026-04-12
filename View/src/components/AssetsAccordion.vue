<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PaperAssets } from '../types/paper'

const props = defineProps<{
  assets: PaperAssets
}>()

// ---------------------------------------------------------------------------
// Block metadata — all 13 new keys + legacy "experiment" alias
// ---------------------------------------------------------------------------
interface BlockMeta {
  label: string
  icon: string
  special?: 'profile' | 'critical' | 'summary'
}

const blockMetas: Record<string, BlockMeta> = {
  paper_profile:              { label: '论文档案',     icon: '📋', special: 'profile' },
  background:                 { label: '研究背景',     icon: '🏛️' },
  objective:                  { label: '研究目标',     icon: '🎯' },
  method:                     { label: '方法',         icon: '⚙️' },
  data:                       { label: '数据',         icon: '📊' },
  experiment_or_argumentation:{ label: '实验与论证',   icon: '🧪' },
  metrics:                    { label: '评价指标',     icon: '📏' },
  results:                    { label: '实验结果',     icon: '📈' },
  evidence_chain:             { label: '证据链',       icon: '🔗' },
  figures_tables_appendix:    { label: '图表与附录',   icon: '📑' },
  limitations:                { label: '局限性',       icon: '⚠️' },
  critical_analysis:          { label: '批判性分析',   icon: '🔍', special: 'critical' },
  summary:                    { label: '综合总结',     icon: '💡', special: 'summary' },
  // Legacy alias — only shown when new key is absent
  experiment:                 { label: '实验设置',     icon: '🧪' },
}

// Sub-field labels for better display
const subFieldLabels: Record<string, string> = {
  research_questions:                      '研究问题',
  claimed_contributions:                   '作者声称的贡献',
  input:                                   '输入',
  task_or_object:                          '任务/对象',
  architecture_or_paradigm:               '架构/范式',
  key_mechanisms:                          '关键机制',
  training_required:                       '是否训练',
  training_or_optimization:               '训练/优化',
  inference_strategy:                      '推理策略',
  novelty:                                 '创新点',
  datasets_or_materials:                  '数据集/材料',
  data_source:                             '数据来源',
  data_scale:                              '数据规模',
  domain_scope:                            '领域范围',
  design:                                  '实验设计',
  baselines_or_comparators:               '基线/对照',
  variables_or_modules:                    '变量/模块',
  ablation_or_counterfactual:             '消融/反事实',
  argumentation_structure:                '论证结构',
  metric_names:                            '指标名称',
  evaluation_protocol:                     '评估协议',
  judge_or_annotation_method:             'Judge/标注方法',
  main_findings:                           '主要发现',
  numerical_results:                       '数值结果',
  phenomena:                              '观察现象',
  mechanism_explanations:                 '机制解释',
  claim_to_evidence:                       '结论-证据对应',
  strongly_supported_claims:              '强支持结论',
  weakly_supported_claims:                '弱支持结论',
  unsupported_or_overextended_claims:     '支持不足/过度外推',
  key_evidence_from_figures_tables_appendix: '图表/附录关键证据',
  scope_boundaries:                        '范围边界',
  threats_to_validity:                     '效度威胁',
  generalization_limits:                   '泛化边界',
  strongest_argument:                      '最强论点',
  weakest_argument:                        '最弱论点',
  substantive_contributions:              '实质性贡献',
  packaging_or_framing_elements:          '包装/叙事成分',
  strong_conclusions:                      '强支持的结论',
  weak_conclusions:                        '弱支持的结论',
  needs_more_evidence:                     '需要更多证据',
  reproduction_or_extension_priorities:   '复现/扩展优先级',
  one_sentence_summary:                    '一句话概括',
  three_takeaways:                         '三条要点',
  literature_review_comment:              '文献综述评述',
  // paper_profile sub-fields
  title:                                   '标题',
  authors:                                 '作者',
  affiliations:                            '机构',
  year:                                    '年份',
  publication_status:                      '发表状态',
  paper_type:                              '论文类型',
  research_domain:                         '研究领域',
  problem_gap:                             '问题空白',
  position_in_literature:                 '在文献中的定位',
}

// ---------------------------------------------------------------------------
// Compute which blocks actually have data (handling legacy key remap)
// ---------------------------------------------------------------------------
const normalizedBlocks = computed(() => {
  const raw = { ...(props.assets.blocks || {}) } as Record<string, any>
  // Remap legacy experiment → experiment_or_argumentation if new key absent
  if (raw.experiment && !raw.experiment_or_argumentation) {
    raw.experiment_or_argumentation = raw.experiment
    delete raw.experiment
  }
  return raw
})

function blockHasContent(key: string): boolean {
  const block = normalizedBlocks.value[key]
  if (!block || typeof block !== 'object') return false
  // Check any field for non-empty content
  return Object.entries(block).some(([k, v]) => {
    if (k === 'text') return typeof v === 'string' && v.trim() !== ''
    if (Array.isArray(v)) return v.length > 0
    if (typeof v === 'string') return v.trim() !== ''
    if (v !== null && v !== undefined) return true
    return false
  })
}

const availableKeys = computed(() =>
  Object.keys(blockMetas).filter(key => {
    // Skip legacy "experiment" if it was remapped
    if (key === 'experiment' && normalizedBlocks.value.experiment_or_argumentation) return false
    return blockHasContent(key)
  })
)

// Keys that are displayed as special cards (outside the accordion)
const profileKey = 'paper_profile'
const specialCardKeys = new Set(['paper_profile', 'critical_analysis', 'summary'])

const accordionKeys = computed(() =>
  availableKeys.value.filter(k => !specialCardKeys.has(k))
)
const topCardKeys = computed(() =>
  availableKeys.value.filter(k => k === profileKey)
)
const bottomCardKeys = computed(() =>
  availableKeys.value.filter(k => specialCardKeys.has(k) && k !== profileKey)
)

// ---------------------------------------------------------------------------
// Accordion open state (includes special cards so they can be toggled too)
// ---------------------------------------------------------------------------
const openSections = ref<Set<string>>(new Set(['method', 'results', 'evidence_chain', 'paper_profile', 'critical_analysis', 'summary']))

function toggle(key: string) {
  if (openSections.value.has(key)) {
    openSections.value.delete(key)
  } else {
    openSections.value.add(key)
  }
  openSections.value = new Set(openSections.value)
}

function expandAll() {
  openSections.value = new Set(availableKeys.value)
}

function collapseAll() {
  openSections.value = new Set()
}

function scrollToBlock(key: string) {
  const el = document.getElementById(`block-${key}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    if (!openSections.value.has(key)) {
      openSections.value.add(key)
      openSections.value = new Set(openSections.value)
    }
  }
}

// ---------------------------------------------------------------------------
// Field-level rendering helpers
// ---------------------------------------------------------------------------
function isEmptyValue(v: unknown): boolean {
  if (v === null || v === undefined) return true
  if (typeof v === 'string') return v.trim() === ''
  if (Array.isArray(v)) return v.length === 0
  return false
}

function getExtraFields(block: Record<string, unknown>): Array<{ key: string; label: string; value: unknown }> {
  const skip = new Set(['text', 'bullets'])
  return Object.entries(block)
    .filter(([k, v]) => !skip.has(k) && !isEmptyValue(v))
    .map(([k, v]) => ({ key: k, label: subFieldLabels[k] || k, value: v }))
}
</script>

<template>
  <div class="space-y-4 pb-4">

    <!-- Quick-navigation bar -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2 pb-3 border-b border-border">
      <span class="text-xs text-text-muted shrink-0">快速导航</span>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="key in availableKeys"
          :key="key"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-border bg-bg-elevated text-text-secondary transition-colors cursor-pointer hover:text-tinder-pink hover:border-tinder-pink/40"
          @click="scrollToBlock(key)"
        >
          <span>{{ blockMetas[key]?.icon }}</span>
          {{ blockMetas[key]?.label }}
        </button>
      </div>
    </div>

    <!-- paper_profile card (top, collapsible) -->
    <template v-for="key in topCardKeys" :key="key">
      <div
        :id="`block-${key}`"
        class="rounded-xl overflow-hidden border border-border"
      >
        <!-- Header button -->
        <button
          class="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated text-left cursor-pointer border-none border-l-2 transition-colors hover:bg-bg-hover"
          :class="openSections.has(key)
            ? 'border-tinder-pink/50 rounded-t-xl'
            : 'border-tinder-pink/30 rounded-xl'"
          @click="toggle(key)"
        >
          <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <span>{{ blockMetas[key]?.icon }}</span>
            {{ blockMetas[key]?.label }}
          </span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14" height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="text-text-muted transition-transform duration-250 shrink-0"
            :style="{ transform: openSections.has(key) ? 'rotate(180deg)' : 'rotate(0deg)' }"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        <!-- Animated body -->
        <div
          class="accordion-body"
          :class="openSections.has(key) ? 'is-open' : ''"
        >
          <div>
            <div class="px-4 py-3 border-l-2 border-tinder-pink/20 bg-bg-card">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                <template
                  v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)"
                  :key="field.key"
                >
                  <div class="flex flex-col gap-0.5">
                    <span class="text-xs text-text-muted">{{ field.label }}</span>
                    <span
                      v-if="typeof field.value === 'string' || typeof field.value === 'number'"
                      class="text-sm text-text-secondary"
                    >{{ field.value }}</span>
                    <div
                      v-else-if="Array.isArray(field.value)"
                      class="flex flex-wrap gap-1 mt-0.5"
                    >
                      <span
                        v-for="(item, idx) in (field.value as string[])"
                        :key="idx"
                        class="px-1.5 py-0.5 rounded text-xs bg-bg-card border border-border text-text-secondary"
                      >{{ item }}</span>
                    </div>
                  </div>
                </template>
              </div>
              <p
                v-if="(normalizedBlocks[key] as any)?.text"
                class="mt-3 text-sm text-text-secondary leading-relaxed"
              >{{ (normalizedBlocks[key] as any).text }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Expand / collapse all controls for accordion section -->
    <div v-if="accordionKeys.length" class="flex items-center gap-3 justify-end">
      <button
        class="text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer bg-transparent border-none p-0"
        @click="expandAll"
      >全部展开</button>
      <span class="text-text-muted text-xs">·</span>
      <button
        class="text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer bg-transparent border-none p-0"
        @click="collapseAll"
      >全部收起</button>
    </div>

    <!-- Accordion items (regular blocks) -->
    <div class="space-y-2.5">
      <template v-for="key in accordionKeys" :key="key">
        <div
          :id="`block-${key}`"
          class="rounded-xl overflow-hidden border border-border"
        >
          <!-- Header -->
          <button
            class="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated text-left cursor-pointer border-none border-l-2 transition-colors hover:bg-bg-hover"
            :class="openSections.has(key)
              ? 'border-tinder-pink/50 rounded-t-xl'
              : 'border-tinder-pink/30 rounded-xl'"
            @click="toggle(key)"
          >
            <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <span>{{ blockMetas[key]?.icon }}</span>
              {{ blockMetas[key]?.label }}
            </span>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14" height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="text-text-muted transition-transform duration-250 shrink-0"
              :style="{ transform: openSections.has(key) ? 'rotate(180deg)' : 'rotate(0deg)' }"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          <!-- Animated body -->
          <div
            class="accordion-body"
            :class="openSections.has(key) ? 'is-open' : ''"
          >
            <div>
              <div class="px-4 py-3 border-l-2 border-tinder-pink/20 space-y-3">
                <!-- text summary -->
                <p
                  v-if="(normalizedBlocks[key] as any)?.text"
                  class="text-sm text-text-secondary leading-relaxed"
                >{{ (normalizedBlocks[key] as any).text }}</p>

                <!-- bullets -->
                <ul
                  v-if="(normalizedBlocks[key] as any)?.bullets?.length"
                  class="space-y-1.5"
                >
                  <li
                    v-for="(bullet, idx) in (normalizedBlocks[key] as any).bullets"
                    :key="idx"
                    class="text-sm text-text-secondary leading-relaxed pl-3 border-l-2 border-tinder-pink/20"
                  >{{ bullet }}</li>
                </ul>

                <!-- extra sub-fields -->
                <template
                  v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)"
                  :key="field.key"
                >
                  <div class="pt-1">
                    <div class="text-xs font-semibold text-text-muted mb-1 uppercase tracking-wide">
                      {{ field.label }}
                    </div>
                    <!-- string or number value -->
                    <p
                      v-if="typeof field.value === 'string' || typeof field.value === 'number'"
                      class="text-sm text-text-secondary leading-relaxed pl-2 border-l-2 border-tinder-blue/20"
                    >{{ field.value }}</p>
                    <!-- list value -->
                    <ul
                      v-else-if="Array.isArray(field.value)"
                      class="space-y-1"
                    >
                      <li
                        v-for="(item, idx) in (field.value as string[])"
                        :key="idx"
                        class="text-sm text-text-secondary leading-relaxed pl-3 border-l-2 border-tinder-blue/20"
                      >{{ item }}</li>
                    </ul>
                  </div>
                </template>

                <!-- empty state -->
                <p
                  v-if="!(normalizedBlocks[key] as any)?.text
                    && !(normalizedBlocks[key] as any)?.bullets?.length
                    && !getExtraFields(normalizedBlocks[key] as Record<string, unknown>).length"
                  class="text-xs text-text-muted italic"
                >暂无数据</p>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Special bottom cards: critical_analysis & summary (collapsible) -->
    <template v-for="key in bottomCardKeys" :key="key">
      <div
        :id="`block-${key}`"
        class="rounded-xl overflow-hidden border"
        :class="key === 'critical_analysis'
          ? 'border-amber-500/30'
          : 'border-tinder-blue/30'"
      >
        <!-- Header button -->
        <button
          class="w-full flex items-center justify-between px-4 py-3 text-left cursor-pointer border-none transition-colors hover:opacity-90"
          :class="key === 'critical_analysis'
            ? (openSections.has(key) ? 'bg-amber-500/10 rounded-t-xl' : 'bg-amber-500/5 rounded-xl')
            : (openSections.has(key) ? 'bg-tinder-blue/10 rounded-t-xl' : 'bg-tinder-blue/5 rounded-xl')"
          @click="toggle(key)"
        >
          <span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <span>{{ blockMetas[key]?.icon }}</span>
            {{ blockMetas[key]?.label }}
          </span>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14" height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="text-text-muted transition-transform duration-250 shrink-0"
            :style="{ transform: openSections.has(key) ? 'rotate(180deg)' : 'rotate(0deg)' }"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        <!-- Animated body -->
        <div
          class="accordion-body"
          :class="[
            openSections.has(key) ? 'is-open' : '',
            key === 'critical_analysis' ? 'bg-amber-500/5' : 'bg-tinder-blue/5'
          ]"
        >
          <div>
            <div class="px-4 py-3 space-y-3">
              <!-- text -->
              <p
                v-if="(normalizedBlocks[key] as any)?.text"
                class="text-sm text-text-secondary leading-relaxed"
              >{{ (normalizedBlocks[key] as any).text }}</p>

              <!-- bullets -->
              <ul
                v-if="(normalizedBlocks[key] as any)?.bullets?.length"
                class="space-y-1.5"
              >
                <li
                  v-for="(b, idx) in (normalizedBlocks[key] as any).bullets"
                  :key="idx"
                  class="text-sm text-text-secondary pl-3 border-l-2"
                  :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
                >{{ b }}</li>
              </ul>

              <!-- extra sub-fields -->
              <template
                v-for="field in getExtraFields(normalizedBlocks[key] as Record<string, unknown>)"
                :key="field.key"
              >
                <div>
                  <div class="text-xs font-semibold text-text-muted mb-1 uppercase tracking-wide">
                    {{ field.label }}
                  </div>
                  <p
                    v-if="typeof field.value === 'string'"
                    class="text-sm text-text-secondary leading-relaxed pl-2 border-l-2"
                    :class="key === 'critical_analysis' ? 'border-amber-500/30' : 'border-tinder-blue/30'"
                  >{{ field.value }}</p>
                  <ul
                    v-else-if="Array.isArray(field.value)"
                    class="space-y-1"
                  >
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

    <!-- Completely empty state -->
    <p
      v-if="!availableKeys.length"
      class="text-sm text-text-muted italic text-center py-8"
    >暂无结构化分析数据</p>

  </div>
</template>

<style scoped>
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
