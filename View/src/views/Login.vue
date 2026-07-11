<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, loginBySms, sendSms, isAuthenticated } from '../stores/auth'
import { API_ORIGIN, getSessionToken } from '../api'
import { getApiErrorMessage, reportClientError } from '../utils/apiError'

function getTauriInvoke(): ((cmd: string, args?: Record<string, unknown>) => Promise<any>) | null {
  return (window as any).__TAURI_INTERNALS__?.invoke ?? null
}

const router = useRouter()
const route = useRoute()

type Tab = 'password' | 'sms'
const activeTab = ref<Tab>('password')

// 用户名密码登录
const username = ref('')
const password = ref('')
const pwdLoading = ref(false)
const pwdError = ref('')

// 手机号验证码登录
const phone = ref('')
const smsCode = ref('')
const smsLoading = ref(false)
const smsSending = ref(false)
const smsError = ref('')
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ---------------------------------------------------------------------------
// 网络诊断（仅在桌面端显示，帮助定位连接问题）
// ---------------------------------------------------------------------------
const diagShow = ref(import.meta.env.DEV && !!API_ORIGIN)
const diagStatus = ref('检测中...')
const diagDetail = ref('')
const diagLoginResult = ref('')          // 最近一次登录响应摘要
const diagTokenState = ref('未设置')      // Never expose the bearer token itself.
const diagIsAuthed = ref<boolean | null>(null)  // isAuthenticated 当前值
const diagRawShape = ref('')             // 登录响应原始结构摘要

function refreshDiagState() {
  diagTokenState.value = getSessionToken() ? '已设置（内容已隐藏）' : '未设置'
  diagIsAuthed.value = isAuthenticated.value
}

async function runDiag() {
  if (!API_ORIGIN) return
  diagStatus.value = '检测中...'
  diagDetail.value = ''
  refreshDiagState()
  try {
    const t0 = Date.now()
    let status = 0
    const invoke = getTauriInvoke()
    if (invoke) {
      const result = await invoke('direct_request', {
        method: 'GET',
        url: `${API_ORIGIN}/api/auth/me`,
        headers: { Accept: 'application/json' },
        body: null,
      })
      status = result.status
    } else {
      const resp = await fetch(`${API_ORIGIN}/api/auth/me`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
      status = resp.status
    }
    const ms = Date.now() - t0
    if (status >= 200 && status < 500) {
      diagStatus.value = `✅ 服务器可达 (${ms}ms, HTTP ${status})`
    } else {
      diagStatus.value = `⚠️ 服务器返回 ${status} (${ms}ms)`
    }
  } catch (err: any) {
    diagStatus.value = '❌ 无法连接服务器'
    diagDetail.value = String(err?.message || err)
  }
}

onMounted(() => { runDiag() })

// ---------------------------------------------------------------------------
// 把原始错误格式化为用户可读的文字
// ---------------------------------------------------------------------------
function startCountdown() {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(countdownTimer!)
      countdownTimer = null
    }
  }, 1000)
}

async function handleSendSms() {
  if (!phone.value.trim()) {
    smsError.value = '请输入手机号'
    return
  }
  smsSending.value = true
  smsError.value = ''
  try {
    await sendSms(phone.value.trim())
    startCountdown()
  } catch (error: unknown) {
    reportClientError('auth.sms.send', error, '发送失败，请稍后重试')
    smsError.value = getApiErrorMessage(error, '发送失败，请稍后重试')
  } finally {
    smsSending.value = false
  }
}

async function handlePasswordLogin() {
  pwdError.value = ''
  pwdLoading.value = true
  diagLoginResult.value = ''
  diagRawShape.value = ''
  try {
    const user = await login(username.value.trim(), password.value)
    if (API_ORIGIN) {
      refreshDiagState()
      diagRawShape.value = `login()返回 user=${user ? user.username ?? user.id : 'null'}`
      const authed = isAuthenticated.value
      diagLoginResult.value = authed
        ? '✅ 已登录'
        : `⚠️ user=${user ? 'ok' : 'null'} isAuthed=false`
    }
    const redirect = (route.query.redirect as string) || '/'
    await router.replace(redirect)
  } catch (error: unknown) {
    if (API_ORIGIN) {
      refreshDiagState()
      diagLoginResult.value = `login() 失败: ${getApiErrorMessage(error, '未知错误').slice(0, 200)}`
    }
    reportClientError('auth.login.password', error, '登录失败，请检查用户名和密码')
    pwdError.value = getApiErrorMessage(error, '登录失败，请检查用户名和密码')
  } finally {
    pwdLoading.value = false
  }
}

async function handleSmsLogin() {
  if (!phone.value.trim() || !smsCode.value.trim()) {
    smsError.value = '请填写手机号和验证码'
    return
  }
  smsError.value = ''
  smsLoading.value = true
  diagLoginResult.value = ''
  diagRawShape.value = ''
  try {
    const res = await loginBySms(phone.value.trim(), smsCode.value.trim())
    if (API_ORIGIN) {
      refreshDiagState()
      const authed = isAuthenticated.value
      diagLoginResult.value = authed
        ? '✅ SMS已登录'
        : `⚠️ SMS user=${res?.user ? 'ok' : 'null'} isAuthed=false`
    }
    if (res.is_new_user) {
      await router.replace({ path: '/profile', query: { tab: 'account_info', welcome: '1' } })
    } else {
      const redirect = (route.query.redirect as string) || '/'
      await router.replace(redirect)
    }
  } catch (error: unknown) {
    if (API_ORIGIN) {
      refreshDiagState()
      diagLoginResult.value = `SMS登录失败: ${getApiErrorMessage(error, '未知错误').slice(0, 200)}`
    }
    reportClientError('auth.login.sms', error, '登录失败，请检查手机号和验证码')
    smsError.value = getApiErrorMessage(error, '登录失败，请检查手机号和验证码')
  } finally {
    smsLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-[calc(100vh-56px)] flex items-center justify-center bg-bg px-4">
    <div class="w-full max-w-md bg-bg-elevated border border-border rounded-2xl p-6">
      <h1 class="text-2xl font-bold text-text-primary mb-1">登录</h1>
      <p class="text-sm text-text-muted mb-5">免费使用全部功能：AI 论文推荐 · 中文摘要 · 知识库 · 论文对比 · AI 问答 · 灵感生成</p>

      <!-- Tab 切换 -->
      <div class="flex rounded-lg bg-bg border border-border mb-6 overflow-hidden" role="tablist" aria-label="登录方式">
        <button
          id="password-login-tab"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'password'"
          aria-controls="password-login-panel"
          class="flex-1 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'password'
            ? 'bg-brand-gradient text-white'
            : 'text-text-muted hover:text-text-primary'"
          @click="activeTab = 'password'"
        >
          用户名密码
        </button>
        <button
          id="sms-login-tab"
          type="button"
          role="tab"
          :aria-selected="activeTab === 'sms'"
          aria-controls="sms-login-panel"
          class="flex-1 py-2 text-sm font-medium transition-colors"
          :class="activeTab === 'sms'
            ? 'bg-brand-gradient text-white'
            : 'text-text-muted hover:text-text-primary'"
          @click="activeTab = 'sms'"
        >
          手机号验证码
        </button>
      </div>

      <!-- 用户名密码登录 -->
      <form v-if="activeTab === 'password'" id="password-login-panel" class="space-y-4" role="tabpanel" aria-labelledby="password-login-tab" @submit.prevent="handlePasswordLogin">
        <div>
          <label for="login-username" class="block text-sm text-text-secondary mb-1">用户名</label>
          <input
            id="login-username"
            v-model="username"
            type="text"
            autocomplete="username"
            minlength="3"
            maxlength="32"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="请输入用户名"
          />
        </div>
        <div>
          <label for="login-password" class="block text-sm text-text-secondary mb-1">密码</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            minlength="8"
            maxlength="128"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="请输入密码"
          />
        </div>
        <p v-if="pwdError" class="text-sm text-red-500" role="alert" aria-live="polite">{{ pwdError }}</p>
        <button
          type="submit"
          :disabled="pwdLoading"
          class="w-full py-2.5 rounded-lg border-none text-white font-semibold bg-brand-gradient cursor-pointer disabled:opacity-60"
        >
          {{ pwdLoading ? '登录中...' : '登录' }}
        </button>
      </form>

      <!-- 手机号验证码登录 -->
      <form v-else id="sms-login-panel" class="space-y-4" role="tabpanel" aria-labelledby="sms-login-tab" @submit.prevent="handleSmsLogin">
        <div>
          <label for="login-phone" class="block text-sm text-text-secondary mb-1">手机号</label>
          <div class="flex gap-2">
            <input
              id="login-phone"
              v-model="phone"
              type="tel"
              autocomplete="tel"
              maxlength="11"
              required
              class="flex-1 px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
              placeholder="请输入手机号"
            />
            <button
              type="button"
              :disabled="smsSending || countdown > 0"
              class="shrink-0 px-3 py-2 rounded-lg border border-border text-sm font-medium text-text-primary bg-bg-elevated disabled:opacity-50 hover:border-tinder-pink/60 transition-colors whitespace-nowrap"
              @click="handleSendSms"
            >
              {{ smsSending ? '发送中...' : countdown > 0 ? `${countdown}s` : '发送验证码' }}
            </button>
          </div>
        </div>
        <div>
          <label for="login-sms-code" class="block text-sm text-text-secondary mb-1">验证码</label>
          <input
            id="login-sms-code"
            v-model="smsCode"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="8"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="请输入短信验证码"
          />
        </div>
        <p v-if="smsError" class="text-sm text-red-500" role="alert" aria-live="polite">{{ smsError }}</p>
        <button
          type="submit"
          :disabled="smsLoading"
          class="w-full py-2.5 rounded-lg border-none text-white font-semibold bg-brand-gradient cursor-pointer disabled:opacity-60"
        >
          {{ smsLoading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p class="text-sm text-text-muted mt-5">
        手机号验证码登录即自动注册 ·
        <router-link
          class="text-tinder-pink no-underline hover:underline"
          :to="{ path: '/register', query: { redirect: (route.query.redirect as string) || '/' } }"
        >
          使用用户名密码注册
        </router-link>
      </p>

      <!-- 桌面端网络诊断 -->
      <div v-if="diagShow" class="mt-4 p-2 rounded-lg bg-bg border border-border text-[11px] text-text-muted leading-relaxed space-y-1">
        <div class="flex items-center justify-between">
          <span class="font-semibold">桌面端诊断</span>
          <button type="button" class="text-tinder-pink underline" @click="runDiag">重新检测</button>
        </div>
        <div>API: {{ API_ORIGIN || '(未设置)' }}</div>
        <div>{{ diagStatus }}</div>
        <div v-if="diagDetail" class="text-red-400 break-all">{{ diagDetail }}</div>
        <div v-if="diagRawShape" class="text-yellow-400 break-all">{{ diagRawShape }}</div>
        <div v-if="diagLoginResult" :class="diagLoginResult.startsWith('✅') ? 'text-green-400' : 'text-red-400'" class="break-all">{{ diagLoginResult }}</div>
        <div v-if="diagIsAuthed !== null">isAuthenticated: <span :class="diagIsAuthed ? 'text-green-400' : 'text-red-400'">{{ diagIsAuthed }}</span></div>
        <div>localStorage token: {{ diagTokenState }}</div>
      </div>
    </div>
  </div>
</template>
