<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import { useEntitlements } from '@shared/composables/useEntitlements'
import { fetchSubscriptionStatus, redeemSubscriptionKey } from '@shared/api'
import { currentUser } from '@shared/stores/auth'
import type { SubscriptionStatusResponse } from '@shared/types/auth'
import { showToast } from 'vant'

const router = useRouter()
const entitlements = useEntitlements()

const subscription = ref<SubscriptionStatusResponse | null>(null)
const pageLoading = ref(true)

// Redeem
const redeemVisible = ref(false)
const redeemCode = ref('')
const redeeming = ref(false)

// Pricing expand
const pricingExpanded = ref(false)

const tierColor = computed(() => {
  const tier = currentUser.value?.tier
  if (tier === 'pro_plus') return 'text-tinder-purple'
  if (tier === 'pro') return 'text-tinder-gold'
  return 'text-text-muted'
})

const tierLabel = computed(() => {
  if (entitlements.tier.value === 'pro_plus') return 'Pro+'
  if (entitlements.tier.value === 'pro') return 'Pro'
  return 'Free'
})

const tierBg = computed(() => {
  if (entitlements.tier.value === 'pro_plus') return 'bg-tinder-purple/10 border-tinder-purple/25'
  if (entitlements.tier.value === 'pro') return 'bg-tinder-gold/10 border-tinder-gold/25'
  return 'bg-bg-elevated border-border'
})

// AI quotas to display
const quotaFeatures = [
  { key: 'chat' as const, label: 'AI 论文问答', icon: '💬' },
  { key: 'research' as const, label: '深度研究', icon: '🔬' },
  { key: 'compare' as const, label: '对比分析', icon: '⚖️' },
  { key: 'idea_gen' as const, label: '灵感生成', icon: '💡' },
  { key: 'translate' as const, label: '论文翻译', icon: '🌐' },
  { key: 'upload' as const, label: '论文上传', icon: '📤' },
]

const gateFeatures = [
  { key: 'general_chat' as const, label: '通用 AI 助手' },
  { key: 'note_file_upload' as const, label: '笔记附件上传' },
  { key: 'llm_preset' as const, label: '自定义模型预设' },
  { key: 'prompt_preset' as const, label: '自定义提示词预设' },
  { key: 'export_docx_pdf' as const, label: 'DOCX/PDF 导出' },
  { key: 'batch_export' as const, label: '批量导出' },
  { key: 'translate' as const, label: '论文全文翻译' },
]

const pricingPlans = [
  {
    name: 'Free',
    price: '免费',
    color: 'text-text-primary',
    bg: 'bg-bg-elevated border-border',
    features: ['每日浏览 3 篇论文', '知识库 20 篇', '3 个文件夹', '保存 3 条对比结果'],
  },
  {
    name: 'Pro',
    price: '订阅制',
    color: 'text-tinder-gold',
    bg: 'bg-tinder-gold/8 border-tinder-gold/25',
    features: ['每日浏览不限量', '知识库 200 篇', '知识库 30 个文件夹', 'AI 问答 / 对比 / 研究', '灵感生成 / 翻译', '通用 AI 助手', '模型预设 / 提示词预设'],
  },
  {
    name: 'Pro+',
    price: '订阅制',
    color: 'text-tinder-purple',
    bg: 'bg-tinder-purple/8 border-tinder-purple/25',
    features: ['Pro 全部权益', '更高 AI 配额', '批量导出', 'DOCX/PDF 导出', '知识库 500 篇'],
  },
]

function quotaBarColor(fraction: number): string {
  if (fraction >= 0.9) return 'bg-tinder-pink'
  if (fraction >= 0.7) return 'bg-tinder-gold'
  return 'bg-tinder-green'
}

function quotaSummaryText(key: typeof quotaFeatures[number]['key']): string {
  return entitlements.quotaSummary(key)
}

async function confirmRedeem() {
  if (!redeemCode.value.trim()) return
  redeeming.value = true
  try {
    await redeemSubscriptionKey({ code: redeemCode.value.trim() })
    redeemVisible.value = false
    redeemCode.value = ''
    showToast('兑换成功！')
    await loadData()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '兑换码无效')
  } finally {
    redeeming.value = false
  }
}

async function loadData() {
  try {
    const [sub] = await Promise.allSettled([
      fetchSubscriptionStatus(),
      entitlements.refreshEntitlements(true),
    ])
    if (sub.status === 'fulfilled') subscription.value = sub.value
  } finally {
    pageLoading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="订阅与用量" @back="router.back()" />

    <LoadingState v-if="pageLoading" class="flex-1" message="加载中…" />

    <div v-else class="flex-1 overflow-y-auto min-h-0 pb-6">

      <!-- ── Current plan card ── -->
      <div class="mx-4 mt-4 card-section">
        <div class="flex items-center justify-between mb-3">
          <div>
            <p class="text-[14px] font-bold text-text-primary">当前套餐</p>
            <p v-if="subscription?.tier_expires_at" class="text-[12px] text-text-muted mt-0.5">
              到期：{{ new Date(subscription.tier_expires_at).toLocaleDateString('zh-CN') }}
            </p>
          </div>
          <span
            class="text-[15px] font-extrabold px-3 py-1 rounded-full border"
            :class="[tierColor, tierBg]"
          >
            {{ tierLabel }}
          </span>
        </div>

        <button
          type="button"
          class="btn-ghost text-[13px] py-2 w-full"
          @click="redeemVisible = true"
        >
          兑换订阅码
        </button>
      </div>

      <!-- ── AI Quotas ── -->
      <div class="mx-4 mt-3 card-section">
        <h3 class="section-title mb-4">AI 功能配额</h3>
        <div class="space-y-3.5">
          <div v-for="feat in quotaFeatures" :key="feat.key">
            <div class="flex items-center justify-between mb-1.5">
              <div class="flex items-center gap-2">
                <span class="text-[16px]">{{ feat.icon }}</span>
                <span class="text-[13px] font-medium text-text-primary">{{ feat.label }}</span>
              </div>
              <span class="text-[12px] text-text-muted font-mono">{{ quotaSummaryText(feat.key) }}</span>
            </div>
            <div class="h-1.5 rounded-full bg-bg overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="quotaBarColor(entitlements.quotaFraction(feat.key))"
                :style="{ width: entitlements.limit(feat.key) === null ? '100%' : `${entitlements.quotaFraction(feat.key) * 100}%` }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- ── Storage & limits ── -->
      <div class="mx-4 mt-3 card-section">
        <h3 class="section-title mb-4">存储与限制</h3>
        <div class="space-y-3.5">
          <!-- KB papers -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-[13px] font-medium text-text-primary">知识库论文</span>
              <span class="text-[12px] text-text-muted font-mono">
                {{ entitlements.kbPaperStorage.value.used }}/{{ entitlements.kbPaperStorage.value.limit ?? '不限' }}
              </span>
            </div>
            <div class="h-1.5 rounded-full bg-bg overflow-hidden">
              <div
                class="h-full rounded-full bg-tinder-blue transition-all"
                :style="{ width: entitlements.kbPaperStorage.value.limit
                  ? `${Math.min(1, entitlements.kbPaperStorage.value.used / entitlements.kbPaperStorage.value.limit) * 100}%`
                  : '20%' }"
              />
            </div>
          </div>
          <!-- Browse -->
          <div class="flex items-center justify-between py-0.5">
            <span class="text-[13px] font-medium text-text-primary">每日浏览论文</span>
            <span class="text-[12px] text-text-muted">
              {{ entitlements.browseLimit.value === null ? '不限' : `每日 ${entitlements.browseLimit.value} 篇` }}
            </span>
          </div>
          <!-- Research history -->
          <div class="flex items-center justify-between py-0.5">
            <span class="text-[13px] font-medium text-text-primary">研究历史保留</span>
            <span class="text-[12px] text-text-muted">
              {{ entitlements.researchHistoryDays.value === null ? '不限' : `${entitlements.researchHistoryDays.value} 天` }}
            </span>
          </div>
        </div>
      </div>

      <!-- ── Feature gates grid ── -->
      <div class="mx-4 mt-3 card-section">
        <h3 class="section-title mb-3">功能权限</h3>
        <div class="grid grid-cols-2 gap-2">
          <div
            v-for="gate in gateFeatures"
            :key="gate.key"
            class="flex items-center gap-2 px-3 py-2.5 rounded-xl border"
            :class="entitlements.gateAllowed(gate.key) ? 'bg-tinder-green/8 border-tinder-green/25' : 'bg-bg-elevated border-border/50'"
          >
            <span class="text-[14px] shrink-0">
              {{ entitlements.gateAllowed(gate.key) ? '✅' : '🔒' }}
            </span>
            <span class="text-[11px] text-text-secondary leading-tight">{{ gate.label }}</span>
          </div>
        </div>
      </div>

      <!-- ── Pricing comparison (collapsible) ── -->
      <div class="mx-4 mt-3 card-section">
        <button
          type="button"
          class="collapsible-trigger w-full"
          @click="pricingExpanded = !pricingExpanded"
        >
          <h3 class="section-title mb-0">套餐对比</h3>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16" height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            class="text-text-muted transition-transform"
            :class="pricingExpanded ? 'rotate-180' : ''"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <Transition name="fade">
          <div v-if="pricingExpanded" class="mt-3 space-y-2.5">
            <div
              v-for="plan in pricingPlans"
              :key="plan.name"
              class="rounded-2xl border px-4 py-4"
              :class="[plan.bg, plan.name === tierLabel ? 'ring-2 ring-offset-1' : '',
                plan.name === 'Pro+' ? 'ring-tinder-purple' : plan.name === 'Pro' ? 'ring-tinder-gold' : 'ring-border']"
            >
              <div class="flex items-center justify-between mb-2.5">
                <span class="text-[16px] font-bold" :class="plan.color">{{ plan.name }}</span>
                <span class="text-[12px] text-text-muted">{{ plan.price }}</span>
              </div>
              <ul class="space-y-1.5">
                <li v-for="f in plan.features" :key="f" class="flex items-center gap-2 text-[12px] text-text-secondary">
                  <span class="text-[11px]">·</span>{{ f }}
                </li>
              </ul>
            </div>
            <p class="text-[11px] text-text-muted text-center pt-1">订阅请联系客服或使用兑换码</p>
          </div>
        </Transition>
      </div>

    </div>

    <!-- Redeem sheet -->
    <BottomSheet :visible="redeemVisible" title="兑换订阅码" @close="redeemVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-3">
        <input v-model="redeemCode" type="text" class="input-field" placeholder="输入订阅码" autocapitalize="characters" />
        <button type="button" class="btn-primary" :disabled="redeeming || !redeemCode.trim()" @click="confirmRedeem">
          {{ redeeming ? '兑换中…' : '兑换' }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
