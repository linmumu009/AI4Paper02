<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import { issueAdminRedeemKeys, fetchAdminRedeemKeys, disableAdminRedeemKey } from '@shared/api'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AdminRedeemKeysView' })

const router = useRouter()

type RedeemKey = {
  id: number
  code: string
  plan_tier: string
  duration_days: number
  status: string
  uses_count: number
  max_uses: number | null
  valid_days: number | null
  note: string | null
  created_at: string
  expires_at?: string | null
}

const keys = ref<RedeemKey[]>([])
const loading = ref(true)
const error = ref('')

// Issue sheet
const issueVisible = ref(false)
const issuing = ref(false)
const issueForm = ref({
  plan_tier: 'pro' as 'pro' | 'pro_plus',
  duration_days: 30,
  key_count: 1,
  valid_days: null as number | null,
  max_uses: 1,
  note: '',
})

// Filter
const filterVisible = ref(false)
const filterStatus = ref<string>('all')
const filterTier = ref<string>('all')

// Newly issued codes display
const newCodes = ref<string[]>([])
const newCodesVisible = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = {}
    if (filterStatus.value !== 'all') params.status = filterStatus.value
    if (filterTier.value !== 'all') params.plan_tier = filterTier.value
    const res = await fetchAdminRedeemKeys(params)
    keys.value = (res as any).keys ?? (res as any).records ?? []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filteredKeys = computed(() => keys.value)

async function doIssue() {
  issuing.value = true
  try {
    const payload: any = {
      plan_tier: issueForm.value.plan_tier,
      duration_days: Number(issueForm.value.duration_days),
      key_count: Number(issueForm.value.key_count),
      max_uses: issueForm.value.max_uses ? Number(issueForm.value.max_uses) : undefined,
    }
    if (issueForm.value.valid_days) payload.valid_days = Number(issueForm.value.valid_days)
    if (issueForm.value.note.trim()) payload.note = issueForm.value.note.trim()
    const res = await issueAdminRedeemKeys(payload)
    newCodes.value = (res as any).codes ?? []
    issueVisible.value = false
    newCodesVisible.value = true
    await load()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '发放失败')
  } finally {
    issuing.value = false
  }
}

async function doDisable(key: RedeemKey) {
  try {
    await showDialog({ title: '禁用兑换码', message: `确定禁用 ${key.code}？`, confirmButtonText: '禁用', cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    await disableAdminRedeemKey(key.id)
    key.status = 'disabled'
    showToast('已禁用')
  } catch { /* cancelled */ }
}

function copyCode(code: string) {
  navigator.clipboard?.writeText(code).then(() => showToast('已复制')).catch(() => showToast(code))
}

function statusBadgeClass(status: string) {
  if (status === 'active') return 'bg-tinder-green/10 text-tinder-green'
  if (status === 'disabled') return 'bg-tinder-pink/10 text-tinder-pink'
  if (status === 'used') return 'bg-text-muted/10 text-text-muted'
  if (status === 'expired') return 'bg-tinder-gold/10 text-tinder-gold'
  return 'bg-bg-elevated text-text-muted'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { active: '有效', disabled: '已禁用', used: '已使用', expired: '已过期' }
  return map[status] ?? status
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="兑换码管理" @back="router.back()">
      <template #right>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="w-10 h-10 flex items-center justify-center text-text-secondary active:text-tinder-blue"
            @click="filterVisible = true"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="4" y1="6" x2="20" y2="6" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="11" y1="18" x2="13" y2="18" />
            </svg>
          </button>
          <button
            type="button"
            class="w-10 h-10 flex items-center justify-center text-tinder-pink active:opacity-70"
            @click="issueVisible = true"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" class="flex-1" message="加载兑换码…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <div v-else class="flex-1 overflow-y-auto pb-4">
      <EmptyState v-if="filteredKeys.length === 0" title="暂无兑换码" description="点击右上角「+」批量发放" />
      <div v-else class="space-y-3 px-4 pt-4">
        <div
          v-for="key in filteredKeys"
          :key="key.id"
          class="card-section"
        >
          <div class="flex items-start gap-2 mb-2">
            <button
              type="button"
              class="flex-1 font-mono text-[13px] text-text-primary text-left break-all active:text-tinder-blue"
              @click="copyCode(key.code)"
            >
              {{ key.code }}
              <span class="text-[10px] text-tinder-blue ml-1">复制</span>
            </button>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0" :class="statusBadgeClass(key.status)">
              {{ statusLabel(key.status) }}
            </span>
          </div>
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-muted">
            <span>{{ key.plan_tier === 'pro_plus' ? 'Pro+' : 'Pro' }} · {{ key.duration_days }}天</span>
            <span>已用 {{ key.uses_count }}/{{ key.max_uses ?? '∞' }}</span>
            <span>{{ new Date(key.created_at).toLocaleDateString('zh-CN') }}</span>
            <span v-if="key.note" class="text-text-secondary">{{ key.note }}</span>
          </div>
          <div v-if="key.status === 'active'" class="mt-2.5 pt-2.5 border-t border-border/50">
            <button
              type="button"
              class="text-[12px] text-tinder-pink active:opacity-70"
              @click="doDisable(key)"
            >
              禁用此码
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Issue sheet -->
    <BottomSheet :visible="issueVisible" title="批量发放兑换码" height="85dvh" @close="issueVisible = false">
      <div class="px-5 pb-8 pt-2 space-y-4 overflow-y-auto">
        <!-- Tier -->
        <div>
          <label class="form-label">套餐等级</label>
          <div class="flex gap-2">
            <button
              type="button"
              class="flex-1 py-2.5 rounded-xl border text-[13px] font-semibold"
              :class="issueForm.plan_tier === 'pro' ? 'border-tinder-gold bg-tinder-gold/10 text-tinder-gold' : 'border-border bg-bg-elevated text-text-muted'"
              @click="issueForm.plan_tier = 'pro'"
            >Pro</button>
            <button
              type="button"
              class="flex-1 py-2.5 rounded-xl border text-[13px] font-semibold"
              :class="issueForm.plan_tier === 'pro_plus' ? 'border-tinder-purple bg-tinder-purple/10 text-tinder-purple' : 'border-border bg-bg-elevated text-text-muted'"
              @click="issueForm.plan_tier = 'pro_plus'"
            >Pro+</button>
          </div>
        </div>

        <div>
          <label class="form-label">订阅天数</label>
          <input v-model.number="issueForm.duration_days" type="number" inputmode="numeric" min="1" class="input-field" placeholder="30" />
        </div>

        <div>
          <label class="form-label">发放数量</label>
          <input v-model.number="issueForm.key_count" type="number" inputmode="numeric" min="1" max="200" class="input-field" placeholder="1" />
        </div>

        <div>
          <label class="form-label">最大使用次数（留空=1次）</label>
          <input v-model.number="issueForm.max_uses" type="number" inputmode="numeric" min="1" class="input-field" placeholder="1" />
        </div>

        <div>
          <label class="form-label">兑换码有效期（天，留空=永久）</label>
          <input v-model.number="issueForm.valid_days" type="number" inputmode="numeric" min="1" class="input-field" placeholder="留空表示永久有效" />
        </div>

        <div>
          <label class="form-label">备注（可选）</label>
          <input v-model="issueForm.note" type="text" class="input-field" placeholder="例如：内测用户" maxlength="100" />
        </div>

        <button
          type="button"
          class="btn-primary"
          :disabled="issuing || !issueForm.duration_days || !issueForm.key_count"
          @click="doIssue"
        >
          {{ issuing ? '发放中…' : `发放 ${issueForm.key_count} 个兑换码` }}
        </button>
      </div>
    </BottomSheet>

    <!-- New codes display -->
    <BottomSheet :visible="newCodesVisible" title="已生成的兑换码" height="70dvh" @close="newCodesVisible = false">
      <div class="px-5 pb-6 pt-2">
        <p class="text-[12px] text-text-muted mb-3">点击码值可复制。共 {{ newCodes.length }} 个。</p>
        <div class="space-y-2 overflow-y-auto max-h-96">
          <button
            v-for="code in newCodes"
            :key="code"
            type="button"
            class="w-full text-left font-mono text-[13px] text-text-primary bg-bg-elevated border border-border rounded-xl px-4 py-3 active:bg-bg-hover"
            @click="copyCode(code)"
          >
            {{ code }}
          </button>
        </div>
      </div>
    </BottomSheet>

    <!-- Filter sheet -->
    <BottomSheet :visible="filterVisible" title="筛选" @close="filterVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-4">
        <div>
          <label class="form-label">状态</label>
          <div class="flex flex-wrap gap-2">
            <button v-for="opt in [{ v: 'all', l: '全部' }, { v: 'active', l: '有效' }, { v: 'used', l: '已使用' }, { v: 'disabled', l: '已禁用' }, { v: 'expired', l: '已过期' }]" :key="opt.v" type="button" class="px-3 py-1.5 rounded-full border text-[12px] transition-colors" :class="filterStatus === opt.v ? 'border-tinder-blue bg-tinder-blue/10 text-tinder-blue' : 'border-border text-text-muted'" @click="filterStatus = opt.v">{{ opt.l }}</button>
          </div>
        </div>
        <div>
          <label class="form-label">等级</label>
          <div class="flex gap-2">
            <button v-for="opt in [{ v: 'all', l: '全部' }, { v: 'pro', l: 'Pro' }, { v: 'pro_plus', l: 'Pro+' }]" :key="opt.v" type="button" class="flex-1 py-2 rounded-xl border text-[12px] transition-colors" :class="filterTier === opt.v ? 'border-tinder-gold bg-tinder-gold/10 text-tinder-gold' : 'border-border text-text-muted'" @click="filterTier = opt.v">{{ opt.l }}</button>
          </div>
        </div>
        <button type="button" class="btn-primary" @click="filterVisible = false; load()">应用筛选</button>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}
</style>
