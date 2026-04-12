<script setup lang="ts">
/**
 * PricingTable — Extracted pricing comparison component.
 * Supports both table layout (md+) and stacked card layout (small screens).
 */
const props = defineProps<{
  currentTier: 'free' | 'pro' | 'pro_plus'
}>()

interface FeatureRow {
  label: string
  subLabel?: string
  free: string
  pro: string
  proPlus: string
  freeOk?: boolean
  proOk?: boolean
  proPlus_ok?: boolean
}

interface FeatureGroup {
  name: string
  rows: FeatureRow[]
}

const FEATURE_GROUPS: FeatureGroup[] = [
  {
    name: '浏览与发现',
    rows: [
      { label: '每日浏览论文', free: '3 篇', pro: '9 篇', proPlus: '不限' },
    ],
  },
  {
    name: 'AI 功能',
    rows: [
      { label: 'AI 论文问答', free: '10 条/天', pro: '无限', proPlus: '无限', proOk: true, proPlus_ok: true },
      { label: '通用 AI 助手', free: '✗', pro: '✓', proPlus: '✓', proOk: true, proPlus_ok: true },
      { label: '对比分析', subLabel: '每次最多篇数', free: '3 次/月\n2 篇/次', pro: '30 次/月\n5 篇/次', proPlus: '100 次/月\n8 篇/次' },
      { label: '深度研究', free: '2 次/月', pro: '15 次/月', proPlus: '50 次/月' },
      { label: '灵感生成', free: '3 次/月', pro: '30 次/月', proPlus: '100 次/月' },
      { label: '全文翻译', free: '2 次/月', pro: '15 次/月', proPlus: '28 次/月', freeOk: true, proOk: true, proPlus_ok: true },
    ],
  },
  {
    name: '知识库与存储',
    rows: [
      { label: '论文收藏', free: '20 篇', pro: '100 篇', proPlus: '500 篇' },
      { label: '文件夹', free: '3 个', pro: '10 个', proPlus: '30 个' },
      { label: '笔记', free: '10 条', pro: '50 条', proPlus: '200 条' },
      { label: '保存对比结果', free: '3 条', pro: '20 条', proPlus: '100 条' },
    ],
  },
  {
    name: '论文上传',
    rows: [
      { label: '上传自有论文', free: '2 篇/月', pro: '30 篇/月', proPlus: '100 篇/月' },
      { label: '笔记附件上传', free: '✗', pro: '✓', proPlus: '✓', proOk: true, proPlus_ok: true },
    ],
  },
  {
    name: '导出',
    rows: [
      { label: 'Markdown 导出', free: '✓', pro: '✓', proPlus: '✓', freeOk: true, proOk: true, proPlus_ok: true },
      { label: 'DOCX / PDF 导出', free: '2 次/月', pro: '15 次/月', proPlus: '28 次/月', freeOk: true, proOk: true, proPlus_ok: true },
      { label: '批量导出', free: '✗', pro: '✗', proPlus: '✓', proPlus_ok: true },
    ],
  },
  {
    name: '高级设置与历史',
    rows: [
      { label: '自定义模型预设', free: '✗', pro: '✓', proPlus: '✓', proOk: true, proPlus_ok: true },
      { label: '自定义提示词预设', free: '✗', pro: '✓', proPlus: '✓', proOk: true, proPlus_ok: true },
      { label: '研究历史保留', free: '3 天', pro: '14 天', proPlus: '30 天' },
    ],
  },
]

function cellTextClass(val: string, isCurrentTier: boolean, isHighlighted: boolean): string {
  if (val === '✗') return 'text-text-muted/50'
  if (val === '✓' || val.includes('无限') || isHighlighted) return 'text-tinder-green font-medium'
  return isCurrentTier ? 'text-text-primary' : 'text-text-secondary'
}

function tierHeaderClass(tier: string): string {
  if (tier === props.currentTier) {
    if (tier === 'pro_plus') return 'bg-violet-500/10 border border-violet-500/40'
    if (tier === 'pro') return 'bg-blue-500/10 border border-blue-500/40'
    return 'bg-border/60 border border-border-light'
  }
  if (tier === 'pro_plus') return 'bg-violet-500/5 border border-violet-500/20'
  return ''
}

function tierCellBg(tier: string): string {
  if (tier === props.currentTier) {
    if (tier === 'pro_plus') return 'bg-violet-500/5'
    if (tier === 'pro') return 'bg-blue-500/5'
  }
  return ''
}

function formatCell(val: string) {
  return val.replace('\\n', '\n').split('\n')
}
</script>

<template>
  <div>
    <!-- ── Desktop: table layout ── -->
    <div class="hidden sm:block overflow-x-auto -mx-1">
      <table class="w-full min-w-[480px] text-xs border-collapse">
        <thead>
          <tr>
            <th class="text-left text-text-muted font-medium py-2 px-3 w-[38%]"></th>
            <!-- Free -->
            <th class="text-center py-2 px-2 w-[20%]">
              <div class="rounded-lg py-2 px-1" :class="tierHeaderClass('free')">
                <div class="font-semibold text-text-secondary text-[11px] mb-0.5">Free</div>
                <div class="text-text-muted text-[10px]">免费</div>
                <div v-if="currentTier === 'free'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-border text-text-secondary inline-block">当前套餐</div>
              </div>
            </th>
            <!-- Pro -->
            <th class="text-center py-2 px-2 w-[20%]">
              <div class="rounded-lg py-2 px-1" :class="tierHeaderClass('pro')">
                <div class="font-bold text-blue-400 text-[11px] mb-0.5">Pro</div>
                <div class="text-blue-400/70 text-[10px]">¥9.9 / 月</div>
                <div v-if="currentTier === 'pro'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 inline-block">当前套餐</div>
              </div>
            </th>
            <!-- Pro+ -->
            <th class="text-center py-2 px-2 w-[22%]">
              <div class="rounded-lg py-2 px-1 relative" :class="tierHeaderClass('pro_plus')">
                <div
                  v-if="currentTier !== 'pro_plus'"
                  class="absolute -top-2 left-1/2 -translate-x-1/2 text-[9px] px-1.5 py-0.5 rounded-full font-semibold whitespace-nowrap"
                  style="background: linear-gradient(135deg, #fd267a33, #a855f733); color: #d580ff; border: 1px solid #a855f730;"
                >推荐</div>
                <div
                  class="font-bold text-[11px] mb-0.5"
                  style="background: linear-gradient(135deg, #fd267a, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;"
                >Pro+</div>
                <div class="text-violet-400/70 text-[10px]">¥19.9 / 月</div>
                <div v-if="currentTier === 'pro_plus'" class="mt-1 text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300 inline-block">当前套餐</div>
              </div>
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border/40">
          <template v-for="group in FEATURE_GROUPS" :key="group.name">
            <!-- Group header -->
            <tr class="bg-bg-elevated/40">
              <td colspan="4" class="px-3 py-1.5 text-[10px] font-semibold text-text-muted uppercase tracking-wide">{{ group.name }}</td>
            </tr>
            <!-- Feature rows -->
            <tr
              v-for="row in group.rows"
              :key="row.label"
              class="hover:bg-bg-elevated/20 transition-colors"
            >
              <td class="px-3 py-2 text-text-secondary leading-snug">
                {{ row.label }}
                <span v-if="row.subLabel" class="block text-[10px] text-text-muted">{{ row.subLabel }}</span>
              </td>
              <!-- Free -->
              <td class="px-2 py-2 text-center leading-snug" :class="tierCellBg('free')">
                <span :class="cellTextClass(row.free, currentTier === 'free', !!row.freeOk)">
                  <template v-for="(line, i) in formatCell(row.free)" :key="i">
                    <span>{{ line }}</span>
                    <span v-if="i < formatCell(row.free).length - 1" class="block text-[10px] font-normal" />
                  </template>
                </span>
              </td>
              <!-- Pro -->
              <td class="px-2 py-2 text-center leading-snug" :class="tierCellBg('pro')">
                <span :class="cellTextClass(row.pro, currentTier === 'pro', !!row.proOk)">
                  <template v-for="(line, i) in formatCell(row.pro)" :key="i">
                    <span>{{ line }}</span>
                    <span v-if="i < formatCell(row.pro).length - 1" class="block text-[10px] font-normal" />
                  </template>
                </span>
              </td>
              <!-- Pro+ -->
              <td class="px-2 py-2 text-center leading-snug" :class="tierCellBg('pro_plus')">
                <span :class="cellTextClass(row.proPlus, currentTier === 'pro_plus', !!row.proPlus_ok)">
                  <template v-for="(line, i) in formatCell(row.proPlus)" :key="i">
                    <span>{{ line }}</span>
                    <span v-if="i < formatCell(row.proPlus).length - 1" class="block text-[10px] font-normal" />
                  </template>
                </span>
              </td>
            </tr>
          </template>

          <!-- CTA row -->
          <tr>
            <td class="px-3 pt-4 pb-2 text-[10px] text-text-muted">扫码添加微信购买</td>
            <td class="px-2 pt-4 pb-2 text-center">
              <span v-if="currentTier === 'free'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-border text-text-muted">当前套餐</span>
            </td>
            <td class="px-2 pt-4 pb-2 text-center" :class="tierCellBg('pro')">
              <span v-if="currentTier === 'pro'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-blue-500/20 text-blue-300">当前套餐</span>
              <span v-else-if="currentTier !== 'pro_plus'" class="inline-block text-[11px] px-2 py-1 rounded-md font-medium text-blue-300" style="background: linear-gradient(135deg, #3b82f620, #2563eb20); border: 1px solid #3b82f640;">¥9.9 / 月起</span>
            </td>
            <td class="px-2 pt-4 pb-2 text-center" :class="tierCellBg('pro_plus')">
              <span v-if="currentTier === 'pro_plus'" class="inline-block text-[11px] px-2 py-1 rounded-md bg-violet-500/20 text-violet-300">当前套餐</span>
              <span v-else class="inline-block text-[11px] px-2 py-1 rounded-md font-medium text-violet-300" style="background: linear-gradient(135deg, #7c3aed20, #a855f720); border: 1px solid #a855f740;">¥19.9 / 月起</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Mobile: stacked tier cards ── -->
    <div class="sm:hidden space-y-3">
      <!-- Free card -->
      <div class="rounded-xl border p-4" :class="currentTier === 'free' ? 'border-border-light bg-border/20' : 'border-border bg-bg-elevated/30'">
        <div class="flex items-center justify-between mb-3">
          <span class="font-semibold text-text-secondary">Free</span>
          <span v-if="currentTier === 'free'" class="text-[10px] px-1.5 py-0.5 rounded-full bg-border text-text-secondary">当前套餐</span>
          <span v-else class="text-[10px] text-text-muted">免费</span>
        </div>
        <ul class="space-y-1.5 text-xs text-text-muted">
          <li>每日浏览 3 篇 · AI 问答 10 条/天</li>
          <li>对比分析 3 次/月（2篇/次）</li>
          <li>深度研究 2 次/月 · 灵感 3 次/月</li>
          <li>翻译 2 次/月 · 导出 2 次/月</li>
          <li>知识库 20 篇 · 文件夹 3 个</li>
        </ul>
      </div>

      <!-- Pro card -->
      <div class="rounded-xl border p-4" :class="currentTier === 'pro' ? 'border-blue-500/40 bg-blue-500/8' : 'border-blue-500/20 bg-blue-500/4'">
        <div class="flex items-center justify-between mb-3">
          <span class="font-bold text-blue-400">Pro</span>
          <span v-if="currentTier === 'pro'" class="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300">当前套餐</span>
          <span v-else class="text-[10px] text-blue-400/70">¥9.9 / 月</span>
        </div>
        <ul class="space-y-1.5 text-xs text-text-secondary">
          <li class="text-tinder-green">✓ AI 论文问答不限次数</li>
          <li class="text-tinder-green">✓ 通用 AI 助手</li>
          <li>每日浏览 9 篇</li>
          <li>对比分析 30 次/月（5篇/次）</li>
          <li>深度研究 15 次/月 · 灵感 30 次/月</li>
          <li>翻译 15 次/月 · 导出 15 次/月</li>
          <li>知识库 100 篇</li>
        </ul>
      </div>

      <!-- Pro+ card -->
      <div class="rounded-xl border p-4 relative" :class="currentTier === 'pro_plus' ? 'border-violet-500/40 bg-violet-500/8' : 'border-violet-500/25 bg-violet-500/4'">
        <div v-if="currentTier !== 'pro_plus'" class="absolute -top-2.5 left-4 text-[9px] px-2 py-0.5 rounded-full font-semibold" style="background: linear-gradient(135deg, #fd267a33, #a855f733); color: #d580ff; border: 1px solid #a855f730;">推荐</div>
        <div class="flex items-center justify-between mb-3">
          <span class="font-bold text-[13px]" style="background: linear-gradient(135deg, #fd267a, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">Pro+</span>
          <span v-if="currentTier === 'pro_plus'" class="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-300">当前套餐</span>
          <span v-else class="text-[10px] text-violet-400/70">¥19.9 / 月</span>
        </div>
        <ul class="space-y-1.5 text-xs text-text-secondary">
          <li class="text-tinder-green">✓ 每日浏览不限篇数</li>
          <li class="text-tinder-green">✓ AI 论文问答不限次数</li>
          <li class="text-tinder-green font-medium">对比分析 100 次/月（8篇/次）</li>
          <li class="text-tinder-green font-medium">深度研究 50 次/月 · 灵感 100 次/月</li>
          <li class="text-tinder-green">翻译 28 次/月 · 导出 28 次/月</li>
          <li class="text-tinder-green">知识库 500 篇</li>
          <li class="text-tinder-green">✓ 批量导出 + 全格式</li>
        </ul>
      </div>
    </div>
  </div>
</template>
