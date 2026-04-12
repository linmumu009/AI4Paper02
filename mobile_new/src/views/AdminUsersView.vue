<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import {
  fetchAdminUsers,
  fetchAdminUserDetail,
  updateAdminUserTier,
  updateAdminUserRole,
  adminDisableUser,
  adminEnableUser,
  adminResetUserPassword,
  adminForceLogout,
  adminDeleteUser,
} from '@shared/api'
import type { AuthUser, UserTier } from '@shared/types/auth'
import { isAdmin, currentUser as _currentUser } from '@shared/stores/auth'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AdminUsersView' })

const router = useRouter()
const isSuperAdmin = computed(() => _currentUser.value?.role === 'superadmin')

const allUsers = ref<AuthUser[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')

// Detail sheet
const detailVisible = ref(false)
const selectedUser = ref<AuthUser | null>(null)
const detailLoading = ref(false)
const detailData = ref<any>(null)

// Reset password
const resetPwSheetVisible = ref(false)
const newPassword = ref('')
const resettingPw = ref(false)

// Delete confirm
const deleteConfirmName = ref('')
const deleting = ref(false)

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchAdminUsers()
    allUsers.value = res.users
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadUsers)

const filteredUsers = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allUsers.value
  return allUsers.value.filter((u) =>
    u.username.toLowerCase().includes(q) || (u.phone || '').includes(q) || (u.nickname || '').toLowerCase().includes(q),
  )
})

const TIER_COLORS: Record<string, string> = {
  free: 'text-text-muted', pro: 'text-tinder-gold', pro_plus: 'text-tinder-purple',
}

async function openDetail(user: AuthUser) {
  selectedUser.value = user
  detailData.value = null
  detailVisible.value = true
  detailLoading.value = true
  try {
    detailData.value = await fetchAdminUserDetail(user.id)
  } catch {
    // best-effort
  } finally {
    detailLoading.value = false
  }
}

async function setTier(tier: UserTier) {
  if (!selectedUser.value) return
  try {
    await updateAdminUserTier(selectedUser.value.id, tier)
    selectedUser.value.tier = tier
    const idx = allUsers.value.findIndex((u) => u.id === selectedUser.value!.id)
    if (idx >= 0) allUsers.value[idx].tier = tier
    showToast('等级已更新')
  } catch { showToast('操作失败') }
}

async function setRole(role: string) {
  if (!selectedUser.value) return
  try {
    await updateAdminUserRole(selectedUser.value.id, role as any)
    selectedUser.value.role = role as any
    const idx = allUsers.value.findIndex((u) => u.id === selectedUser.value!.id)
    if (idx >= 0) allUsers.value[idx].role = role as any
    showToast('角色已更新')
  } catch { showToast('操作失败') }
}

async function toggleDisable() {
  if (!selectedUser.value) return
  const isActive = !selectedUser.value.is_disabled
  const label = isActive ? '禁用' : '启用'
  try {
    await showDialog({ title: `${label}用户`, message: `确定${label} @${selectedUser.value.username}？`, confirmButtonText: label, cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    if (isActive) await adminDisableUser(selectedUser.value.id)
    else await adminEnableUser(selectedUser.value.id)
    selectedUser.value.is_disabled = isActive
    const idx = allUsers.value.findIndex((u) => u.id === selectedUser.value!.id)
    if (idx >= 0) allUsers.value[idx].is_disabled = isActive
    showToast(`已${label}`)
  } catch { /* user cancelled */ }
}

async function doForceLogout() {
  if (!selectedUser.value) return
  try {
    await showDialog({ title: '强制下线', message: `确定将 @${selectedUser.value.username} 强制下线？`, confirmButtonText: '强制下线', cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    await adminForceLogout(selectedUser.value.id)
    showToast('已强制下线')
  } catch { /* cancelled */ }
}

async function doResetPassword() {
  if (!selectedUser.value || !newPassword.value.trim()) return
  resettingPw.value = true
  try {
    await adminResetUserPassword(selectedUser.value.id, newPassword.value)
    resetPwSheetVisible.value = false
    newPassword.value = ''
    showToast('密码已重置')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '操作失败')
  } finally {
    resettingPw.value = false
  }
}

async function doDelete() {
  if (!selectedUser.value) return
  if (deleteConfirmName.value !== selectedUser.value.username) {
    showToast('用户名不匹配')
    return
  }
  deleting.value = true
  try {
    await adminDeleteUser(selectedUser.value.id)
    allUsers.value = allUsers.value.filter((u) => u.id !== selectedUser.value!.id)
    detailVisible.value = false
    showToast('已删除')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = false
    deleteConfirmName.value = ''
  }
}

function tierLabel(t?: string) { if (t === 'pro_plus') return 'Pro+'; if (t === 'pro') return 'Pro'; return 'Free' }
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="用户管理" @back="router.back()" />
    <div class="px-4 pb-3 shrink-0">
      <SearchBar v-model="search" placeholder="搜索用户名、昵称、手机号…" />
    </div>
    <LoadingState v-if="loading" class="flex-1" message="加载用户…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadUsers()" />
    <div v-else class="flex-1 overflow-y-auto">
      <p class="px-4 py-2 text-[12px] text-text-muted">共 {{ filteredUsers.length }} 个用户</p>
      <div
        v-for="user in filteredUsers"
        :key="user.id"
        class="flex items-center gap-3 px-4 py-3 border-b border-border active:bg-bg-hover cursor-pointer"
        @click="openDetail(user)"
      >
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-tinder-pink/30 to-tinder-purple/30 flex items-center justify-center text-[13px] font-bold text-text-secondary shrink-0">
          {{ (user.username || '?')[0].toUpperCase() }}
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-[13px] font-medium text-text-primary truncate">{{ user.nickname || user.username }}</p>
          <p class="text-[11px] text-text-muted">@{{ user.username }} · {{ user.phone || '无手机' }}</p>
        </div>
        <div class="flex flex-col items-end gap-0.5 shrink-0">
          <span class="text-[11px] font-semibold" :class="TIER_COLORS[user.tier] ?? 'text-text-muted'">{{ tierLabel(user.tier) }}</span>
          <span v-if="user.is_disabled" class="text-[10px] text-tinder-pink">已禁用</span>
          <span v-if="user.role !== 'user'" class="text-[10px] text-tinder-blue">{{ user.role }}</span>
        </div>
      </div>
    </div>

    <!-- User detail BottomSheet -->
    <BottomSheet :visible="detailVisible" :title="`@${selectedUser?.username}`" height="90dvh" @close="detailVisible = false; deleteConfirmName = ''">
      <div class="overflow-y-auto pb-8">
        <LoadingState v-if="detailLoading" message="加载详情…" />

        <template v-else-if="selectedUser">
          <!-- Basic info -->
          <div class="px-5 py-4 border-b border-border/50">
            <div class="flex items-center gap-4 mb-3">
              <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-tinder-pink/30 to-tinder-purple/30 flex items-center justify-center text-lg font-bold text-text-secondary shrink-0">
                {{ (selectedUser.username || '?')[0].toUpperCase() }}
              </div>
              <div>
                <p class="text-[16px] font-bold text-text-primary">{{ selectedUser.nickname || selectedUser.username }}</p>
                <p class="text-[12px] text-text-muted">@{{ selectedUser.username }}</p>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-[12px]">
              <div class="bg-bg-elevated rounded-xl px-3 py-2">
                <p class="text-text-muted">ID</p>
                <p class="font-mono text-text-secondary mt-0.5">{{ selectedUser.id }}</p>
              </div>
              <div class="bg-bg-elevated rounded-xl px-3 py-2">
                <p class="text-text-muted">注册时间</p>
                <p class="text-text-secondary mt-0.5">{{ selectedUser.created_at ? new Date(selectedUser.created_at).toLocaleDateString('zh-CN') : '-' }}</p>
              </div>
              <div class="bg-bg-elevated rounded-xl px-3 py-2">
                <p class="text-text-muted">手机</p>
                <p class="text-text-secondary mt-0.5">{{ selectedUser.phone || '-' }}</p>
              </div>
              <div class="bg-bg-elevated rounded-xl px-3 py-2">
                <p class="text-text-muted">当前等级</p>
                <p class="font-semibold mt-0.5" :class="TIER_COLORS[selectedUser.tier] ?? 'text-text-muted'">{{ tierLabel(selectedUser.tier) }}</p>
              </div>
              <div v-if="detailData?.subscription" class="bg-bg-elevated rounded-xl px-3 py-2 col-span-2">
                <p class="text-text-muted">订阅到期</p>
                <p class="text-text-secondary mt-0.5">{{ detailData.subscription.tier_expires_at ? new Date(detailData.subscription.tier_expires_at).toLocaleDateString('zh-CN') : '无活跃订阅' }}</p>
              </div>
            </div>
          </div>

          <!-- Tier management -->
          <div class="px-5 pt-4 pb-3">
            <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-2">调整等级</p>
            <div class="flex gap-2">
              <button
                v-for="tier in ['free', 'pro', 'pro_plus']"
                :key="tier"
                type="button"
                class="flex-1 py-2 rounded-xl border text-[12px] font-semibold active:scale-95 transition-transform"
                :class="selectedUser.tier === tier ? 'border-tinder-green bg-tinder-green/10 text-tinder-green' : `border-border bg-bg-elevated ${TIER_COLORS[tier]}`"
                @click="setTier(tier as UserTier)"
              >
                {{ tierLabel(tier) }}
              </button>
            </div>
          </div>

          <!-- Role management (superadmin only) -->
          <div v-if="isSuperAdmin" class="px-5 pb-3">
            <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-2">角色权限</p>
            <div class="flex gap-2">
              <button
                v-for="role in ['user', 'admin', 'superadmin']"
                :key="role"
                type="button"
                class="flex-1 py-2 rounded-xl border text-[12px] font-semibold active:scale-95 transition-transform"
                :class="selectedUser.role === role ? 'border-tinder-blue bg-tinder-blue/10 text-tinder-blue' : 'border-border bg-bg-elevated text-text-muted'"
                @click="setRole(role)"
              >
                {{ role }}
              </button>
            </div>
          </div>

          <!-- Actions -->
          <div class="px-5 pb-3 space-y-2">
            <p class="text-[12px] font-semibold text-text-muted uppercase tracking-wider mb-2">操作</p>

            <!-- Enable/Disable -->
            <button
              type="button"
              class="w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border active:opacity-80"
              :class="selectedUser.is_disabled ? 'border-tinder-green/30 bg-tinder-green/5 text-tinder-green' : 'border-tinder-gold/30 bg-tinder-gold/5 text-tinder-gold'"
              @click="toggleDisable"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <circle cx="12" cy="12" r="10" />
                <path v-if="selectedUser.is_disabled" d="M9 12l2 2 4-4" />
                <path v-else d="M18 6L6 18M6 6l12 12" />
              </svg>
              {{ selectedUser.is_disabled ? '启用用户' : '禁用用户' }}
            </button>

            <!-- Reset password -->
            <button
              type="button"
              class="w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border border-tinder-blue/30 bg-tinder-blue/5 text-tinder-blue active:opacity-80"
              @click="resetPwSheetVisible = true; newPassword = ''"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              重置密码
            </button>

            <!-- Force logout -->
            <button
              type="button"
              class="w-full flex items-center gap-3 px-4 py-3.5 rounded-xl border border-border bg-bg-elevated text-text-primary active:bg-bg-hover"
              @click="doForceLogout"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              强制下线
            </button>
          </div>

          <!-- Danger zone: Delete -->
          <div class="mx-5 mb-4 p-4 rounded-2xl bg-tinder-pink/5 border border-tinder-pink/20">
            <p class="text-[12px] font-semibold text-tinder-pink uppercase tracking-wider mb-3">危险操作</p>
            <p class="text-[12px] text-text-muted mb-3">输入用户名 <code class="text-tinder-pink font-mono">{{ selectedUser.username }}</code> 确认删除</p>
            <input
              v-model="deleteConfirmName"
              type="text"
              class="input-field mb-3"
              placeholder="输入用户名确认"
              autocomplete="off"
            />
            <button
              type="button"
              class="w-full py-3 rounded-xl bg-tinder-pink text-white font-semibold text-[14px] active:opacity-80 disabled:opacity-40"
              :disabled="deleteConfirmName !== selectedUser.username || deleting"
              @click="doDelete"
            >
              {{ deleting ? '删除中…' : '删除账号' }}
            </button>
          </div>
        </template>
      </div>
    </BottomSheet>

    <!-- Reset password inner sheet -->
    <BottomSheet :visible="resetPwSheetVisible" title="重置密码" @close="resetPwSheetVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-3">
        <p class="text-[12px] text-text-muted">为 @{{ selectedUser?.username }} 设置新密码</p>
        <input v-model="newPassword" type="password" class="input-field" placeholder="新密码（至少 8 位）" minlength="8" />
        <button
          type="button"
          class="btn-primary"
          :disabled="resettingPw || newPassword.length < 8"
          @click="doResetPassword"
        >
          {{ resettingPw ? '处理中…' : '确认重置' }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
