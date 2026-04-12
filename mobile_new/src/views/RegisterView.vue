<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { register, login, sendSms } from '@shared/stores/auth'
import { useEngagement } from '@shared/composables/useEngagement'
import { useEntitlements } from '@shared/composables/useEntitlements'

const router = useRouter()
const route = useRoute()
const engagement = useEngagement()
const { refreshEntitlements } = useEntitlements()

const step = ref<1 | 2>(1)

const phone = ref('')
const smsCode = ref('')
const smsSending = ref(false)
const smsError = ref('')
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const showConfirm = ref(false)
const loading = ref(false)
const error = ref('')

const passwordStrength = computed(() => {
  const p = password.value
  if (!p) return 0
  let score = 0
  if (p.length >= 8) score++
  if (/[A-Z]/.test(p)) score++
  if (/[0-9]/.test(p)) score++
  if (/[^A-Za-z0-9]/.test(p)) score++
  return score
})

const strengthLabel = computed(() => {
  const s = passwordStrength.value
  if (s <= 1) return { text: '弱', color: '#ef4444', w: '25%' }
  if (s === 2) return { text: '一般', color: '#f59e0b', w: '50%' }
  if (s === 3) return { text: '强', color: '#22c55e', w: '75%' }
  return { text: '非常强', color: '#06b6d4', w: '100%' }
})

function startCountdown() {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      if (countdownTimer) clearInterval(countdownTimer)
      countdownTimer = null
    }
  }, 1000)
}

async function handleSendSms() {
  if (!phone.value.trim()) { smsError.value = '请输入手机号'; return }
  smsSending.value = true
  smsError.value = ''
  try {
    await sendSms(phone.value.trim())
    startCountdown()
  } catch (e: any) {
    smsError.value = e?.response?.data?.detail || '发送失败，请稍后重试'
  } finally {
    smsSending.value = false
  }
}

function handleNextStep() {
  if (!phone.value.trim()) { smsError.value = '请输入手机号'; return }
  if (!smsCode.value.trim()) { smsError.value = '请输入验证码'; return }
  smsError.value = ''
  step.value = 2
}

async function handleRegister() {
  if (!username.value || !password.value) { error.value = '请填写用户名和密码'; return }
  if (password.value.length < 8) { error.value = '密码至少 8 个字符'; return }
  if (password.value !== confirmPassword.value) { error.value = '两次密码输入不一致'; return }
  loading.value = true
  error.value = ''
  try {
    await register(username.value, password.value, phone.value.trim(), smsCode.value.trim())
    await login(username.value, password.value)
    engagement.loadStatus()
    refreshEntitlements()
    const redirect = (route.query.redirect as string) || '/recommend'
    router.replace(redirect)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('手机验证失败') || detail.includes('验证码')) {
      error.value = detail + '，请返回重新验证'
    } else {
      error.value = detail || '注册失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (step.value === 2) { step.value = 1; return }
  if (window.history.length > 1) router.back()
  else router.push('/recommend')
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg overflow-y-auto">
    <!-- Minimal back bar -->
    <div class="shrink-0 flex items-center px-4 safe-area-top" style="padding-top: max(16px, env(safe-area-inset-top, 16px));">
      <button
        type="button"
        class="w-10 h-10 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-primary active:bg-bg-hover transition-colors"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 flex flex-col items-center justify-center px-6 py-8">
      <!-- Logo -->
      <div class="flex flex-col items-center mb-8">
        <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#fd267a] to-[#ff6036] flex items-center justify-center shadow-lg mb-3">
          <span class="text-white text-2xl font-black tracking-tight">AP</span>
        </div>
        <h1 class="text-2xl font-bold gradient-text">创建账号</h1>
        <p class="text-sm text-text-muted mt-1">加入 AI4Papers 研究社区</p>
      </div>

      <!-- Step indicator -->
      <div class="w-full max-w-[340px] flex items-center mb-8">
        <div class="flex items-center gap-2">
          <div
            class="flex items-center justify-center text-xs font-bold transition-all"
            :class="step >= 1
              ? 'w-8 h-8 rounded-full bg-gradient-to-br from-[#fd267a] to-[#ff6036] text-white shadow-sm'
              : 'w-6 h-6 rounded-full bg-border text-text-muted'"
          >1</div>
          <span class="text-sm" :class="step === 1 ? 'font-medium text-text-primary' : 'text-text-muted'">手机验证</span>
        </div>
        <div class="flex-1 mx-3 h-px bg-gradient-to-r"
          :style="step >= 2 ? 'background: linear-gradient(90deg, #fd267a, #ff6036)' : 'background: var(--color-border)'"
        />
        <div class="flex items-center gap-2">
          <div
            class="flex items-center justify-center text-xs font-bold transition-all"
            :class="step >= 2
              ? 'w-8 h-8 rounded-full bg-gradient-to-br from-[#fd267a] to-[#ff6036] text-white shadow-sm'
              : 'w-6 h-6 rounded-full bg-border text-text-muted'"
          >2</div>
          <span class="text-sm" :class="step === 2 ? 'font-medium text-text-primary' : 'text-text-muted'">设置账号</span>
        </div>
      </div>

      <!-- Form -->
      <div class="w-full max-w-[340px]">
        <!-- Step 1: phone verification -->
        <div v-if="step === 1" class="space-y-3">
          <div v-if="smsError" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 text-tinder-pink text-sm text-center">
            {{ smsError }}
          </div>

          <div class="flex gap-2">
            <div class="input-with-icon flex-1">
              <span class="input-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.1 19.79 19.79 0 0 1 1.61 4.5a2 2 0 0 1 2-2.18h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
              </span>
              <input
                v-model="phone"
                type="tel"
                maxlength="11"
                placeholder="手机号"
                class="input-field"
              />
            </div>
            <button
              type="button"
              :disabled="smsSending || countdown > 0"
              class="shrink-0 px-3 rounded-xl bg-bg-elevated border border-border text-sm font-medium text-text-primary disabled:opacity-50 whitespace-nowrap"
              style="padding-top: 14px; padding-bottom: 14px;"
              @click="handleSendSms"
            >
              {{ smsSending ? '发送中' : countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </button>
          </div>

          <div class="input-with-icon">
            <span class="input-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </span>
            <input
              v-model="smsCode"
              type="text"
              maxlength="8"
              placeholder="短信验证码"
              class="input-field"
              @keydown.enter="handleNextStep"
            />
          </div>

          <button type="button" class="btn-primary" @click="handleNextStep">
            下一步
          </button>
        </div>

        <!-- Step 2: account setup -->
        <div v-else class="space-y-3">
          <div v-if="error" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 text-tinder-pink text-sm text-center">
            {{ error }}
          </div>

          <!-- Username -->
          <div class="input-with-icon">
            <span class="input-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </span>
            <input
              v-model="username"
              type="text"
              placeholder="用户名（至少 3 个字符）"
              autocomplete="username"
              class="input-field"
            />
          </div>

          <!-- Password -->
          <div>
            <div class="input-with-icon">
              <span class="input-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </span>
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="密码（至少 8 个字符）"
                autocomplete="new-password"
                class="input-field"
                style="padding-right: 44px;"
              />
              <button type="button" class="input-suffix" @click="showPassword = !showPassword">
                <svg v-if="!showPassword" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              </button>
            </div>

            <!-- Password strength bar -->
            <div v-if="password" class="mt-1.5 flex items-center gap-2">
              <div class="flex-1 h-1 rounded-full bg-border overflow-hidden">
                <div
                  class="strength-bar h-full"
                  :style="{ width: strengthLabel.w, background: strengthLabel.color }"
                />
              </div>
              <span class="text-xs shrink-0" :style="{ color: strengthLabel.color }">{{ strengthLabel.text }}</span>
            </div>
          </div>

          <!-- Confirm password -->
          <div class="input-with-icon">
            <span class="input-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
            </span>
            <input
              v-model="confirmPassword"
              :type="showConfirm ? 'text' : 'password'"
              placeholder="确认密码"
              autocomplete="new-password"
              class="input-field"
              style="padding-right: 44px;"
              @keydown.enter="handleRegister"
            />
            <button type="button" class="input-suffix" @click="showConfirm = !showConfirm">
              <svg v-if="!showConfirm" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>

          <button
            type="button"
            class="btn-primary"
            :disabled="loading"
            @click="handleRegister"
          >
            <svg v-if="loading" class="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <span>{{ loading ? '注册中' : '完成注册' }}</span>
          </button>
        </div>

        <!-- Footer -->
        <p class="mt-6 text-sm text-text-muted text-center">
          已有账号？
          <button
            type="button"
            class="btn-text text-sm"
            @click="router.push({ path: '/login', query: route.query })"
          >
            去登录
          </button>
        </p>
      </div>
    </div>
  </div>
</template>
