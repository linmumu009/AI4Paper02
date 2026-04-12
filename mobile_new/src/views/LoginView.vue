<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, loginBySms, sendSms } from '@shared/stores/auth'
import { useEngagement } from '@shared/composables/useEngagement'
import { useEntitlements } from '@shared/composables/useEntitlements'

const router = useRouter()
const route = useRoute()
const engagement = useEngagement()
const { refreshEntitlements } = useEntitlements()

type Tab = 'password' | 'sms'
const activeTab = ref<Tab>('password')

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const pwdLoading = ref(false)
const pwdError = ref('')

const phone = ref('')
const smsCode = ref('')
const smsLoading = ref(false)
const smsSending = ref(false)
const smsError = ref('')
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

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

async function handlePasswordLogin() {
  if (!username.value || !password.value) { pwdError.value = '请填写用户名和密码'; return }
  pwdLoading.value = true
  pwdError.value = ''
  try {
    await login(username.value, password.value)
    engagement.loadStatus()
    refreshEntitlements()
    const redirect = (route.query.redirect as string) || '/recommend'
    router.replace(redirect)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || '用户名或密码错误'
  } finally {
    pwdLoading.value = false
  }
}

async function handleSmsLogin() {
  if (!phone.value.trim() || !smsCode.value.trim()) { smsError.value = '请填写手机号和验证码'; return }
  smsLoading.value = true
  smsError.value = ''
  try {
    const res = await loginBySms(phone.value.trim(), smsCode.value.trim())
    engagement.loadStatus()
    refreshEntitlements()
    if (res.is_new_user) {
      router.replace({ path: '/profile', query: { welcome: '1' } })
    } else {
      const redirect = (route.query.redirect as string) || '/recommend'
      router.replace(redirect)
    }
  } catch (e: any) {
    smsError.value = e?.response?.data?.detail || '验证码错误或已过期'
  } finally {
    smsLoading.value = false
  }
}

function goBack() {
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
        <h1 class="text-2xl font-bold gradient-text">AI4Papers</h1>
        <p class="text-sm text-text-muted mt-1">每日 arXiv 论文精选</p>
      </div>

      <!-- Form card -->
      <div class="w-full max-w-[340px]">
        <!-- Underline tabs -->
        <div class="tab-underline mb-6">
          <button
            type="button"
            class="tab-underline-item"
            :class="activeTab === 'password' ? 'active' : ''"
            @click="activeTab = 'password'"
          >密码登录</button>
          <button
            type="button"
            class="tab-underline-item"
            :class="activeTab === 'sms' ? 'active' : ''"
            @click="activeTab = 'sms'"
          >验证码登录</button>
        </div>

        <!-- Password form -->
        <div v-if="activeTab === 'password'" class="space-y-3">
          <div v-if="pwdError" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 text-tinder-pink text-sm text-center">
            {{ pwdError }}
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
              placeholder="用户名"
              autocomplete="username"
              class="input-field"
              @keydown.enter="handlePasswordLogin"
            />
          </div>

          <!-- Password -->
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
              placeholder="密码"
              autocomplete="current-password"
              class="input-field"
              style="padding-right: 44px;"
              @keydown.enter="handlePasswordLogin"
            />
            <button
              type="button"
              class="input-suffix"
              @click="showPassword = !showPassword"
            >
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

          <button
            type="button"
            class="btn-primary"
            :disabled="pwdLoading"
            @click="handlePasswordLogin"
          >
            <svg v-if="pwdLoading" class="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <span>{{ pwdLoading ? '登录中' : '登录' }}</span>
          </button>
        </div>

        <!-- SMS form -->
        <div v-else class="space-y-3">
          <div v-if="smsError" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 text-tinder-pink text-sm text-center">
            {{ smsError }}
          </div>

          <!-- Phone + send code -->
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

          <!-- SMS code -->
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
              placeholder="验证码"
              class="input-field"
              @keydown.enter="handleSmsLogin"
            />
          </div>

          <button
            type="button"
            class="btn-primary"
            :disabled="smsLoading"
            @click="handleSmsLogin"
          >
            <svg v-if="smsLoading" class="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            <span>{{ smsLoading ? '登录中' : '登录' }}</span>
          </button>
        </div>

        <!-- Footer links -->
        <p class="mt-6 text-sm text-text-muted text-center leading-relaxed">
          验证码登录即自动注册账号 ·
          <button
            type="button"
            class="btn-text text-sm"
            @click="router.push({ path: '/register', query: route.query })"
          >
            密码注册
          </button>
        </p>
      </div>
    </div>
  </div>
</template>
