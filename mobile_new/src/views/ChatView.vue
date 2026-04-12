<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import QuotaGate from '@/components/QuotaGate.vue'
import {
  fetchGeneralChatHistory,
  fetchGeneralChatStream,
  clearGeneralChatHistory,
  fetchChatHistory,
  fetchPaperChatStream,
  clearChatHistory,
} from '@shared/api/chat'
import type { ChatMessage } from '@shared/types/research'
import { useEntitlements } from '@shared/composables/useEntitlements'
import { isAuthenticated } from '@shared/stores/auth'
import { showDialog, showToast } from 'vant'

type ChatMode = 'general' | 'paper'

const route = useRoute()
const router = useRouter()
const entitlements = useEntitlements()

// Mode & context
const mode = ref<ChatMode>('general')
const paperId = ref('')
const paperTitle = ref('')

// Messages
const messages = ref<ChatMessage[]>([])
const streamingContent = ref('')
const isStreaming = ref(false)

// Input
const inputText = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
const messagesEl = ref<HTMLDivElement | null>(null)

// State
const loadingHistory = ref(false)
const historyError = ref('')
const sending = ref(false)

// Quota / gate
const quotaBlocked = computed(() => {
  if (!entitlements.loaded.value) return false
  if (mode.value === 'general') {
    return !entitlements.gateAllowed('general_chat') || !entitlements.canUse('chat')
  }
  return !entitlements.canUse('chat')
})

const quotaBlockedMessage = computed(() => {
  if (mode.value === 'general' && !entitlements.gateAllowed('general_chat')) {
    return '通用 AI 助手仅 Pro 及以上套餐可用，升级 Pro 即可使用'
  }
  return `${mode.value === 'paper' ? 'AI 论文问答' : '通用 AI 助手'}配额已用完，升级 Pro 可获得更多`
})


function initFromRoute() {
  const qPaperId = route.query.paperId as string | undefined
  const qTitle = route.query.title as string | undefined
  if (qPaperId) {
    paperId.value = qPaperId
    paperTitle.value = qTitle || qPaperId
    mode.value = 'paper'
  }
}

async function loadHistory() {
  loadingHistory.value = true
  historyError.value = ''
  messages.value = []
  try {
    if (mode.value === 'paper' && paperId.value) {
      messages.value = await fetchChatHistory(paperId.value)
    } else if (mode.value === 'general') {
      messages.value = await fetchGeneralChatHistory()
    }
  } catch (e: any) {
    historyError.value = e?.message || '加载历史失败'
  } finally {
    loadingHistory.value = false
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

async function sendHint(hint: string) {
  inputText.value = hint
  await nextTick()
  sendMessage()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value || isStreaming.value) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  if (quotaBlocked.value) return

  inputText.value = ''
  adjustTextarea()

  // Add user message optimistically
  const userMsg: ChatMessage = {
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  }
  messages.value.push(userMsg)
  await scrollToBottom()

  isStreaming.value = true
  streamingContent.value = ''
  sending.value = true

  try {
    let response: Response
    if (mode.value === 'paper' && paperId.value) {
      response = await fetchPaperChatStream(paperId.value, text)
    } else {
      response = await fetchGeneralChatStream(text)
    }

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) throw new Error('无法读取响应流')

    let done = false
    let buffer = ''
    while (!done) {
      const { value, done: readerDone } = await reader.read()
      done = readerDone
      if (value) {
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') {
            done = true
            break
          }
          try {
            const parsed = JSON.parse(data)
            if (typeof parsed === 'string') {
              streamingContent.value += parsed
              await scrollToBottom()
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
    }

    if (streamingContent.value) {
      messages.value.push({
        role: 'assistant',
        content: streamingContent.value,
        created_at: new Date().toISOString(),
      })
    }
  } catch (e: any) {
    showToast(e?.message || '发送失败，请重试')
    messages.value.pop()
    inputText.value = text
  } finally {
    streamingContent.value = ''
    isStreaming.value = false
    sending.value = false
    await scrollToBottom()
  }
}

async function clearHistory() {
  try {
    await showDialog({
      title: '清空对话',
      message: '确定清空所有对话记录？此操作不可恢复。',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      confirmButtonColor: 'var(--color-tinder-pink)',
    })
    if (mode.value === 'paper' && paperId.value) {
      await clearChatHistory(paperId.value)
    } else {
      await clearGeneralChatHistory()
    }
    messages.value = []
    showToast('已清空')
  } catch { /* cancelled */ }
}

function switchMode(newMode: ChatMode) {
  if (newMode === mode.value) return
  mode.value = newMode
  loadHistory()
}

function clearPaperContext() {
  paperId.value = ''
  paperTitle.value = ''
  mode.value = 'general'
  loadHistory()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function adjustTextarea() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

watch(
  () => route.query,
  () => {
    initFromRoute()
    loadHistory()
  },
)

onMounted(async () => {
  initFromRoute()
  await entitlements.refreshEntitlements()
  await loadHistory()
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Header -->
    <PageHeader @back="router.back()">
      <template #title>
        <span class="text-[15px] font-semibold text-text-primary">AI 对话</span>
      </template>
      <template #right>
        <button
          v-if="messages.length > 0"
          type="button"
          class="w-10 h-10 flex items-center justify-center text-text-muted active:text-tinder-pink"
          @click="clearHistory"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
      </template>
    </PageHeader>

    <!-- Mode switch tabs -->
    <div class="shrink-0 px-4 pb-2 pt-1 flex gap-1.5">
      <button
        type="button"
        class="flex-1 py-2 rounded-xl text-[13px] font-semibold transition-all"
        :class="mode === 'general'
          ? 'bg-tinder-blue/15 text-tinder-blue'
          : 'bg-bg-elevated text-text-muted'"
        @click="switchMode('general')"
      >
        通用助手
      </button>
      <button
        type="button"
        class="flex-1 py-2 rounded-xl text-[13px] font-semibold transition-all"
        :class="mode === 'paper'
          ? 'bg-tinder-pink/15 text-tinder-pink'
          : 'bg-bg-elevated text-text-muted'"
        @click="switchMode('paper')"
      >
        论文问答
      </button>
    </div>

    <!-- Paper context bar (when in paper mode with context) -->
    <div
      v-if="mode === 'paper' && paperId"
      class="shrink-0 mx-4 mb-2 px-3 py-2.5 rounded-xl bg-tinder-pink/8 border border-tinder-pink/25 flex items-center gap-2"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-pink shrink-0">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
      </svg>
      <span class="flex-1 text-[12px] text-tinder-pink truncate font-medium">{{ paperTitle || paperId }}</span>
      <button
        type="button"
        class="shrink-0 w-5 h-5 flex items-center justify-center text-tinder-pink/60 active:text-tinder-pink"
        @click="clearPaperContext"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <!-- Paper mode - no context prompt -->
    <div
      v-else-if="mode === 'paper' && !paperId"
      class="shrink-0 mx-4 mb-2 px-3.5 py-3 rounded-xl bg-bg-elevated border border-border text-center"
    >
      <p class="text-[12px] text-text-muted leading-relaxed">
        从<span class="text-tinder-blue font-medium">论文详情页</span>进入可自动关联论文上下文，或在通用模式下自由提问
      </p>
    </div>

    <!-- Quota blocked -->
    <div v-if="quotaBlocked" class="flex-1 relative">
      <QuotaGate :message="quotaBlockedMessage" />
    </div>

    <!-- Messages area -->
    <div
      v-else
      ref="messagesEl"
      class="flex-1 overflow-y-auto min-h-0 px-4 py-2"
    >
      <!-- Loading history -->
      <div v-if="loadingHistory" class="flex items-center justify-center py-12">
        <div class="w-6 h-6 rounded-full border-2 border-tinder-blue border-t-transparent animate-spin" />
      </div>

      <!-- History error -->
      <div v-else-if="historyError" class="flex flex-col items-center justify-center py-12 gap-3">
        <p class="text-[13px] text-text-muted text-center">{{ historyError }}</p>
        <button type="button" class="text-[13px] text-tinder-blue" @click="loadHistory">重试</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="!messages.length && !isStreaming" class="flex flex-col items-center justify-center py-16 gap-4 px-4">
        <div class="w-16 h-16 rounded-3xl bg-bg-elevated border border-border flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div class="text-center">
          <p class="text-[15px] font-semibold text-text-primary mb-1">
            {{ mode === 'paper' ? '与 AI 讨论这篇论文' : '有什么想问的？' }}
          </p>
          <p class="text-[12px] text-text-muted leading-relaxed">
            {{ mode === 'paper'
              ? '可以问方法、实验、贡献等任何问题'
              : '关于 AI、论文、研究方法……随时提问' }}
          </p>
        </div>
        <div class="flex flex-col gap-2 w-full max-w-[280px]">
          <button
            v-for="hint in (mode === 'paper' ? ['这篇论文的核心贡献是什么？', '这个方法的局限性有哪些？'] : ['帮我解释一下 Transformer 架构', '如何找好的研究方向？'])"
            :key="hint"
            type="button"
            class="px-4 py-2.5 rounded-xl bg-bg-elevated border border-border text-[13px] text-text-secondary text-left active:bg-bg-hover transition-colors"
            @click="sendHint(hint)"
          >
            {{ hint }}
          </button>
        </div>
      </div>

      <!-- Message list -->
      <div v-else class="space-y-4 pb-2">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="flex gap-2.5"
          :class="msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'"
        >
          <!-- Avatar -->
          <div
            class="shrink-0 w-8 h-8 rounded-2xl flex items-center justify-center text-[12px] font-bold mt-0.5"
            :class="msg.role === 'user'
              ? 'bg-gradient-to-br from-tinder-pink to-tinder-purple text-white'
              : 'bg-tinder-blue/15 text-tinder-blue'"
          >
            {{ msg.role === 'user' ? '我' : 'AI' }}
          </div>

          <!-- Bubble -->
          <div
            class="max-w-[80%] rounded-2xl px-3.5 py-2.5"
            :class="msg.role === 'user'
              ? 'bg-gradient-to-br from-tinder-pink to-tinder-purple text-white rounded-tr-sm'
              : 'bg-bg-elevated border border-border rounded-tl-sm'"
          >
            <div v-if="msg.role === 'user'" class="text-[14px] leading-relaxed whitespace-pre-wrap">
              {{ msg.content }}
            </div>
            <MarkdownRenderer v-else :content="msg.content" class="text-[13px]" />
          </div>
        </div>

        <!-- Streaming bubble -->
        <div v-if="isStreaming" class="flex gap-2.5 flex-row">
          <div class="shrink-0 w-8 h-8 rounded-2xl bg-tinder-blue/15 flex items-center justify-center text-[12px] font-bold text-tinder-blue mt-0.5">
            AI
          </div>
          <div class="max-w-[80%] rounded-2xl rounded-tl-sm bg-bg-elevated border border-border px-3.5 py-2.5">
            <div v-if="streamingContent">
              <MarkdownRenderer :content="streamingContent" class="text-[13px]" />
            </div>
            <div v-else class="flex items-center gap-1 py-1">
              <span class="w-1.5 h-1.5 rounded-full bg-tinder-blue animate-bounce" style="animation-delay: 0ms" />
              <span class="w-1.5 h-1.5 rounded-full bg-tinder-blue animate-bounce" style="animation-delay: 150ms" />
              <span class="w-1.5 h-1.5 rounded-full bg-tinder-blue animate-bounce" style="animation-delay: 300ms" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div
      v-if="!quotaBlocked"
      class="shrink-0 bg-bg/95 backdrop-blur-sm border-t border-border safe-area-bottom px-4 py-3 flex items-end gap-2.5"
    >
      <textarea
        ref="inputEl"
        v-model="inputText"
        rows="1"
        class="flex-1 min-h-[40px] max-h-[100px] bg-bg-elevated border border-border rounded-2xl px-4 py-2.5 text-[14px] text-text-primary placeholder-text-muted resize-none outline-none focus:border-tinder-blue/50 transition-colors leading-relaxed"
        :placeholder="mode === 'paper' ? '问这篇论文…' : '有什么想问的？'"
        :disabled="sending || isStreaming"
        @keydown="handleKeydown"
        @input="adjustTextarea"
      />
      <button
        type="button"
        class="shrink-0 w-10 h-10 rounded-2xl flex items-center justify-center transition-all"
        :class="inputText.trim() && !sending && !isStreaming
          ? 'bg-gradient-to-br from-tinder-pink to-tinder-purple text-white'
          : 'bg-bg-elevated border border-border text-text-muted'"
        :disabled="!inputText.trim() || sending || isStreaming"
        @click="sendMessage"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
    </div>
  </div>
</template>
