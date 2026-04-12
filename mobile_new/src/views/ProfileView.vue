<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import LoadingState from '@/components/LoadingState.vue'
import {
  currentUser,
  isAuthenticated,
  isAdmin,
  logout,
  saveProfile,
  setPassword,
  changePassword,
} from '@shared/stores/auth'
import { fetchSubscriptionStatus, redeemSubscriptionKey, fetchUnreadAnnouncementCount } from '@shared/api'
import { useEngagement } from '@shared/composables/useEngagement'
import { useEntitlements } from '@shared/composables/useEntitlements'
import { toggleTheme, isDark } from '@shared/stores/theme'
const currentTheme = isDark
import type { SubscriptionStatusResponse } from '@shared/types/auth'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'ProfileView' })

const router = useRouter()
const engagement = useEngagement()
const entitlements = useEntitlements()

const subscription = ref<SubscriptionStatusResponse | null>(null)
const unreadCount = ref(0)
const loading = ref(true)

// Edit profile sheet
const editProfileVisible = ref(false)
const editNickname = ref('')
const editUsername = ref('')
const savingProfile = ref(false)

// Password sheet
const passwordSheetVisible = ref(false)
const passwordMode = ref<'set' | 'change'>('change')
const oldPassword = ref('')
const newPassword = ref('')
const savingPassword = ref(false)

// Redeem sheet
const redeemVisible = ref(false)
const redeemCode = ref('')
const redeeming = ref(false)

const tierLabel = computed(() => {
  const tier = currentUser.value?.tier
  if (tier === 'pro_plus') return 'Pro+'
  if (tier === 'pro') return 'Pro'
  return 'Free'
})

const tierColor = computed(() => {
  const tier = currentUser.value?.tier
  if (tier === 'pro_plus') return 'text-tinder-purple'
  if (tier === 'pro') return 'text-tinder-gold'
  return 'text-text-muted'
})

async function loadData() {
  loading.value = true
  try {
    if (isAuthenticated.value) {
      const [sub, unread] = await Promise.allSettled([
        fetchSubscriptionStatus(),
        fetchUnreadAnnouncementCount(),
      ])
      if (sub.status === 'fulfilled') subscription.value = sub.value
      if (unread.status === 'fulfilled') unreadCount.value = unread.value.count ?? 0
      await Promise.allSettled([
        engagement.loadStatus(),
        entitlements.refreshEntitlements(),
      ])
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

function openEditProfile() {
  editNickname.value = currentUser.value?.nickname || ''
  editUsername.value = currentUser.value?.username || ''
  editProfileVisible.value = true
}

async function confirmEditProfile() {
  savingProfile.value = true
  try {
    await saveProfile({ nickname: editNickname.value.trim(), username: editUsername.value.trim() })
    editProfileVisible.value = false
    showToast('已更新')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '更新失败')
  } finally {
    savingProfile.value = false
  }
}

function openPasswordSheet() {
  passwordMode.value = currentUser.value?.has_password ? 'change' : 'set'
  oldPassword.value = ''
  newPassword.value = ''
  passwordSheetVisible.value = true
}

async function confirmPassword() {
  if (!newPassword.value.trim()) return
  savingPassword.value = true
  try {
    if (passwordMode.value === 'set') {
      await setPassword(newPassword.value)
    } else {
      await changePassword(oldPassword.value, newPassword.value)
    }
    passwordSheetVisible.value = false
    showToast('密码已更新')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '操作失败')
  } finally {
    savingPassword.value = false
  }
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

async function doLogout() {
  try {
    await showDialog({
      title: '退出登录',
      message: '确定退出当前账号？',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    await logout()
    router.replace('/login')
  } catch {/* user cancelled */}
}

const streakCount = computed(() => engagement.status.value?.streak?.current ?? 0)
const signedInToday = computed(() => engagement.status.value?.progress?.tasks?.view ?? false)
const todayProgress = computed(() => engagement.status.value?.progress?.progress_count ?? 0)
const todayTarget = computed(() => engagement.status.value?.progress?.target_count ?? 3)
const hasNewRewards = computed(() => engagement.hasNewRewards.value)
</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-y-auto">
    <PageHeader title="我的" />

    <!-- Not logged in -->
    <div v-if="!isAuthenticated" class="flex-1 flex flex-col items-center justify-center gap-5 px-8 pb-16">
      <div class="w-20 h-20 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
        </svg>
      </div>
      <div class="text-center">
        <h2 class="text-[17px] font-bold text-text-primary mb-1.5">尚未登录</h2>
        <p class="text-[13px] text-text-secondary leading-relaxed">登录后可使用知识库、灵感生成等所有功能</p>
      </div>
      <button type="button" class="btn-primary max-w-xs" @click="router.push('/login')">登录 / 注册</button>
    </div>

    <template v-else>
      <LoadingState v-if="loading" class="flex-1" message="加载中…" />
      <div v-else class="pb-6">

        <!-- User card -->
        <div class="mx-4 mb-4 card-section">
          <div class="flex items-center gap-4 mb-3">
            <!-- Avatar -->
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-tinder-pink to-tinder-purple flex items-center justify-center text-white text-xl font-bold shrink-0">
              {{ (currentUser?.nickname || currentUser?.username || '?')[0].toUpperCase() }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <p class="text-[16px] font-bold text-text-primary truncate">
                  {{ currentUser?.nickname || currentUser?.username || '用户' }}
                </p>
                <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-bg-elevated" :class="tierColor">
                  {{ tierLabel }}
                </span>
              </div>
              <p class="text-[12px] text-text-muted mt-0.5">@{{ currentUser?.username }}</p>
            </div>
            <button
              type="button"
              class="shrink-0 w-8 h-8 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-text-secondary"
              @click="openEditProfile"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
          </div>

          <!-- Streak + sign-in -->
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-bg border border-border flex-1">
              <span class="text-[18px]">🔥</span>
              <div>
                <p class="text-[15px] font-bold text-text-primary leading-none">{{ streakCount }}</p>
                <p class="text-[10px] text-text-muted">连续天数</p>
              </div>
            </div>
            <button
              v-if="!signedInToday"
              type="button"
              class="flex-1 py-2.5 rounded-xl font-semibold text-[13px] text-white"
              style="background: linear-gradient(135deg, var(--color-gradient-start), var(--color-gradient-end));"
              @click="engagement.record('view', 'profile', 'sign-in')"
            >
              签到打卡
            </button>
            <div v-else class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-tinder-green/10 text-tinder-green text-[13px] font-medium">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              今日已签到
            </div>
          </div>

          <!-- Today's task progress bar -->
          <div class="mt-2.5">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[11px] text-text-muted">今日任务进度</span>
              <span class="text-[11px] font-semibold text-text-secondary">{{ todayProgress }}/{{ todayTarget }}</span>
            </div>
            <div class="h-1.5 rounded-full bg-bg overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-500"
                :style="{ width: `${(todayProgress / todayTarget) * 100}%`, background: todayProgress >= todayTarget ? 'var(--color-tinder-green)' : 'var(--color-tinder-blue)' }"
              />
            </div>
          </div>

          <!-- Achievements link -->
          <button
            type="button"
            class="mt-2.5 w-full flex items-center justify-between py-1.5 px-1 text-[12px] text-text-muted active:text-tinder-blue"
            @click="router.push('/achievements')"
          >
            <span class="flex items-center gap-1.5">
              <span v-if="hasNewRewards" class="w-2 h-2 rounded-full bg-tinder-pink inline-block" />
              查看成就与奖励
            </span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>
        </div>

        <!-- Subscription card -->
        <div v-if="subscription" class="mx-4 mb-4 card-section">
          <div class="flex items-center justify-between mb-2">
            <p class="text-[13px] font-semibold text-text-primary">订阅与配额</p>
            <span class="text-[12px] font-semibold" :class="tierColor">{{ tierLabel }}</span>
          </div>
          <div v-if="subscription.tier_expires_at" class="text-[12px] text-text-muted mb-2">
            到期时间：{{ new Date(subscription.tier_expires_at).toLocaleDateString('zh-CN') }}
          </div>

          <!-- Mini quota bar (chat) -->
          <div v-if="entitlements.loaded.value" class="mb-3">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[11px] text-text-muted">论文问答配额</span>
              <span class="text-[11px] font-mono text-text-secondary">{{ entitlements.quotaSummary('chat') }}</span>
            </div>
            <div class="h-1.5 rounded-full bg-bg overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="entitlements.quotaFraction('chat') >= 0.9 ? 'bg-tinder-pink' : entitlements.quotaFraction('chat') >= 0.7 ? 'bg-tinder-gold' : 'bg-tinder-green'"
                :style="{ width: entitlements.limit('chat') === null ? '100%' : `${entitlements.quotaFraction('chat') * 100}%` }"
              />
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="flex-1 btn-ghost text-[13px] py-2"
              @click="redeemVisible = true"
            >
              兑换订阅码
            </button>
            <button
              type="button"
              class="flex-1 py-2 rounded-xl border border-border bg-bg-elevated text-[13px] text-tinder-blue active:bg-bg-hover"
              @click="router.push('/subscription')"
            >
              查看详情
            </button>
          </div>
        </div>

        <!-- Settings list -->
        <div class="mx-4 mb-4 rounded-2xl overflow-hidden border border-border bg-bg-card divide-y divide-border">
          <!-- Account -->
          <button type="button" class="settings-row" @click="openEditProfile">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-tinder-blue">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
            <span class="flex-1">编辑资料</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>
          <button type="button" class="settings-row" @click="openPasswordSheet">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-tinder-gold">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            <span class="flex-1">{{ currentUser?.has_password ? '修改密码' : '设置密码' }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>

          <!-- Announcements -->
          <button type="button" class="settings-row" @click="router.push('/announcements')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-tinder-pink">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span class="flex-1">系统公告</span>
            <span v-if="unreadCount > 0" class="text-[11px] bg-tinder-pink text-white rounded-full px-1.5 py-0.5 font-semibold mr-1">{{ unreadCount }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>

          <!-- Theme -->
          <button type="button" class="settings-row" @click="toggleTheme()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-tinder-purple">
              <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
            <span class="flex-1">外观</span>
            <span class="text-[12px] text-text-muted mr-1">{{ currentTheme ? '深色' : '浅色' }}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>

          <!-- Admin -->
          <button v-if="isAdmin" type="button" class="settings-row" @click="router.push('/admin')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-text-muted">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            <span class="flex-1">管理员后台</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>

          <!-- Advanced settings -->
          <button type="button" class="settings-row" @click="router.push('/settings')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="text-tinder-gold">
              <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            <span class="flex-1">高级设置</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted"><polyline points="9 18 15 12 9 6" /></svg>
          </button>
        </div>

        <!-- Logout -->
        <div class="mx-4">
          <button
            type="button"
            class="w-full py-3.5 rounded-2xl text-[15px] font-medium text-tinder-pink bg-tinder-pink/10 active:bg-tinder-pink/20"
            @click="doLogout"
          >
            退出登录
          </button>
        </div>
      </div>
    </template>

    <!-- Edit profile sheet -->
    <BottomSheet :visible="editProfileVisible" title="编辑资料" @close="editProfileVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-3">
        <div>
          <label class="text-[12px] text-text-muted mb-1 block">昵称</label>
          <input v-model="editNickname" type="text" class="input-field" placeholder="输入昵称" maxlength="30" />
        </div>
        <div>
          <label class="text-[12px] text-text-muted mb-1 block">用户名</label>
          <input v-model="editUsername" type="text" class="input-field" placeholder="输入用户名" maxlength="30" />
        </div>
        <button type="button" class="btn-primary" :disabled="savingProfile" @click="confirmEditProfile">
          {{ savingProfile ? '保存中…' : '保存' }}
        </button>
      </div>
    </BottomSheet>

    <!-- Password sheet -->
    <BottomSheet :visible="passwordSheetVisible" :title="passwordMode === 'set' ? '设置密码' : '修改密码'" @close="passwordSheetVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-3">
        <div v-if="passwordMode === 'change'">
          <label class="text-[12px] text-text-muted mb-1 block">旧密码</label>
          <input v-model="oldPassword" type="password" class="input-field" placeholder="输入旧密码" />
        </div>
        <div>
          <label class="text-[12px] text-text-muted mb-1 block">新密码</label>
          <input v-model="newPassword" type="password" class="input-field" placeholder="至少 8 位" minlength="8" />
        </div>
        <button type="button" class="btn-primary" :disabled="savingPassword || !newPassword.trim()" @click="confirmPassword">
          {{ savingPassword ? '保存中…' : '确认' }}
        </button>
      </div>
    </BottomSheet>

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

<style scoped>
.settings-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  width: 100%;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  font-size: 14px;
  color: var(--color-text-primary);
  -webkit-tap-highlight-color: transparent;
  transition: background 0.1s ease;
}
.settings-row:active { background: var(--color-bg-hover); }
</style>
