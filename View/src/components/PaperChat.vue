<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import {
  fetchChatHistory,
  fetchPaperChatStream,
  clearChatHistory,
  fetchGeneralChatHistory,
  fetchGeneralChatStream,
  clearGeneralChatHistory,
  fetchUserSettings,
  saveUserSettings,
  fetchUserLlmPresets,
  checkPaperInKb,
  addKbPaper,
  createNote,
} from '../api'
import type { ChatMessage, PaperSummary, UserLlmPreset } from '../types/paper'

const props = withDefaults(
  defineProps<{
    paperId?: string
    paperTitle?: string
    paperSummary?: PaperSummary
    /** general = 站点通用助手，不绑定论文 */
    chatMode?: 'paper' | 'general'
    /** 是否显示顶部「收起」按钮 */
    showCloseButton?: boolean
  }>(),
  { chatMode: 'paper', showCloseButton: true },
)

const emit = defineEmits<{
  close: []
  noteSaved: []
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

type Phase = 'idle' | 'loading' | 'streaming' | 'error'
const phase = ref<Phase>('loading')
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const errorMsg = ref('')
const messagesRef = ref<HTMLElement | null>(null)

const streamingContent = ref('')
const isStreaming = computed(() => phase.value === 'streaming')

// ---------------------------------------------------------------------------
// Settings state
// ---------------------------------------------------------------------------

type ContextStrategy = 'recent_k' | 'summary' | 'full'
type DataSource = 'summary' | 'abstract' | 'full_text'

const showSettings = ref(false)
const settingsLoading = ref(false)
const contextStrategy = ref<ContextStrategy>('recent_k')
const contextK = ref(10)
const dataSource = ref<DataSource>('summary')

const strategyLabel: Record<ContextStrategy, string> = {
  recent_k: '最近K轮',
  summary: '摘要压缩',
  full: '完整历史',
}
const dataSourceLabel: Record<DataSource, string> = {
  summary: 'AI摘要',
  abstract: '原文摘要',
  full_text: '全文',
}

// Font size (px value, 12-22)
const chatFontSize = ref<number>(14)

// Copy format
type CopyFormat = 'markdown' | 'plain'
const copyFormat = ref<CopyFormat>('markdown')

// Per-message copy state
const copiedMsgs = ref<Record<number, boolean>>({})
// All-messages copy state
const allCopied = ref(false)

// ---------------------------------------------------------------------------
// Model (LLM preset) selection
// ---------------------------------------------------------------------------

const llmPresets = ref<UserLlmPreset[]>([])
const selectedPresetId = ref<number | null>(null)
const showModelPicker = ref(false)

const selectedPresetName = computed(() => {
  if (selectedPresetId.value == null) return '选择模型'
  const preset = llmPresets.value.find(p => p.id === selectedPresetId.value)
  return preset ? preset.name : '选择模型'
})

async function loadLlmPresets() {
  try {
    const res = await fetchUserLlmPresets()
    llmPresets.value = res.presets || []
  } catch {
    // Non-critical
  }
}

async function selectPreset(id: number | null) {
  selectedPresetId.value = id
  showModelPicker.value = false
  await _saveAllSettings()
}

function onModelPickerOverlayClick() {
  showModelPicker.value = false
}

async function loadSettings() {
  try {
    const res = await fetchUserSettings('paper_chat')
    const s = res.settings || {}
    contextStrategy.value = (s.context_strategy as ContextStrategy) || 'recent_k'
    contextK.value = Number(s.context_k) || 10
    dataSource.value = (s.data_source as DataSource) || 'summary'
    selectedPresetId.value = s.llm_preset_id ? Number(s.llm_preset_id) : null
    chatFontSize.value = s.chat_font_size ? Number(s.chat_font_size) : 14
    copyFormat.value = (s.copy_format as CopyFormat) || 'markdown'
  } catch {
    // Non-critical: use defaults
  }
}

async function persistSettings() {
  settingsLoading.value = true
  try {
    await saveUserSettings('paper_chat', {
      context_strategy: contextStrategy.value,
      context_k: contextK.value,
      data_source: dataSource.value,
      llm_preset_id: selectedPresetId.value ?? '',
      chat_font_size: chatFontSize.value,
      copy_format: copyFormat.value,
    })
  } catch {
    // Non-critical
  } finally {
    settingsLoading.value = false
  }
}

// Also update selectPreset to include new fields
async function _saveAllSettings() {
  await saveUserSettings('paper_chat', {
    context_strategy: contextStrategy.value,
    context_k: contextK.value,
    data_source: dataSource.value,
    llm_preset_id: selectedPresetId.value ?? '',
    chat_font_size: chatFontSize.value,
    copy_format: copyFormat.value,
  })
}

// ---------------------------------------------------------------------------
// Scroll helpers
// ---------------------------------------------------------------------------

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// ---------------------------------------------------------------------------
// Load history
// ---------------------------------------------------------------------------

async function loadHistory() {
  phase.value = 'loading'
  errorMsg.value = ''
  try {
    if (props.chatMode === 'general') {
      messages.value = await fetchGeneralChatHistory()
    } else {
      const pid = props.paperId
      if (!pid) {
        phase.value = 'idle'
        return
      }
      messages.value = await fetchChatHistory(pid)
    }
    phase.value = 'idle'
    scrollToBottom()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载聊天记录失败'
    phase.value = 'error'
  }
}

onMounted(() => {
  loadHistory()
  loadSettings()
  loadLlmPresets()
})

watch(
  () => [props.paperId, props.chatMode] as const,
  () => {
    messages.value = []
    streamingContent.value = ''
    inputText.value = ''
    loadHistory()
  },
)

// ---------------------------------------------------------------------------
// Send message
// ---------------------------------------------------------------------------

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  errorMsg.value = ''

  const tempUserMsg: ChatMessage = {
    id: Date.now(),
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  }
  messages.value.push(tempUserMsg)
  streamingContent.value = ''
  phase.value = 'streaming'
  scrollToBottom()

  try {
    const response =
      props.chatMode === 'general'
        ? await fetchGeneralChatStream(text)
        : await fetchPaperChatStream(props.paperId!, text)

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(`请求失败 (${response.status}): ${errText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('无法读取响应流')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]') break
        try {
          const chunk = JSON.parse(payload)
          if (typeof chunk === 'string') {
            streamingContent.value += chunk
            scrollToBottom()
          }
        } catch {
          // ignore malformed chunks
        }
      }
    }

    if (streamingContent.value) {
      messages.value.push({
        id: Date.now() + 1,
        role: 'assistant',
        content: streamingContent.value,
        created_at: new Date().toISOString(),
      })
    }
    streamingContent.value = ''
    phase.value = 'idle'
    scrollToBottom()

    // Reload from server to get accurate persisted IDs
    const fresh =
      props.chatMode === 'general'
        ? await fetchGeneralChatHistory()
        : await fetchChatHistory(props.paperId!)
    if (fresh.length > 0) messages.value = fresh

  } catch (e: any) {
    streamingContent.value = ''
    phase.value = 'error'
    errorMsg.value = e?.message || '发送失败，请重试'
  }
}

// ---------------------------------------------------------------------------
// Clear history
// ---------------------------------------------------------------------------

const clearing = ref(false)

async function handleClear() {
  const msg =
    props.chatMode === 'general'
      ? '确定要清空通用助手的所有对话记录吗？'
      : '确定要清空本篇论文的所有对话记录吗？'
  if (!confirm(msg)) return
  clearing.value = true
  try {
    if (props.chatMode === 'general') {
      await clearGeneralChatHistory()
    } else {
      await clearChatHistory(props.paperId!)
    }
    messages.value = []
    streamingContent.value = ''
    phase.value = 'idle'
  } catch {
    // non-critical
  } finally {
    clearing.value = false
  }
}

// ---------------------------------------------------------------------------
// Save to note
// ---------------------------------------------------------------------------

/** Map of msgId → saving state */
const savingNotes = ref<Record<number, boolean>>({})
const savedNotes = ref<Record<number, boolean>>({})

async function saveToNote(assistantMsg: ChatMessage) {
  savingNotes.value[assistantMsg.id] = true
  try {
    // Find the user message just before this assistant message
    const idx = messages.value.findIndex(m => m.id === assistantMsg.id)
    const prevUser = idx > 0
      ? messages.value.slice(0, idx).reverse().find(m => m.role === 'user')
      : null
    const questionSnippet = prevUser
      ? prevUser.content.slice(0, 20).replace(/\n/g, ' ')
      : '问答'
    const noteTitle = `AI问答 - ${questionSnippet}`

    // Auto-add paper to KB if not already present
    const pid = props.paperId
    if (!pid) return
    const inKb = await checkPaperInKb(pid)
    if (!inKb && props.paperSummary) {
      await addKbPaper(pid, props.paperSummary)
    }

    // Render Markdown → HTML so Tiptap editor can display it as rich text
    const htmlContent = md.render(assistantMsg.content)
    await createNote(pid, noteTitle, htmlContent, 'kb')
    savedNotes.value[assistantMsg.id] = true
    emit('noteSaved')
  } catch {
    // Show brief error state
    savedNotes.value[assistantMsg.id] = false
  } finally {
    savingNotes.value[assistantMsg.id] = false
  }
}

// ---------------------------------------------------------------------------
// Copy helpers
// ---------------------------------------------------------------------------

/** Convert markdown string to plain text via DOM */
function stripMarkdown(content: string): string {
  const html = md.render(content)
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || content
}

/** Copy a single assistant message */
async function copyMessage(msg: ChatMessage) {
  const text = copyFormat.value === 'markdown' ? msg.content : stripMarkdown(msg.content)
  try {
    await navigator.clipboard.writeText(text)
    copiedMsgs.value[msg.id] = true
    setTimeout(() => { copiedMsgs.value[msg.id] = false }, 2000)
  } catch {
    // clipboard not available — fail silently
  }
}

/** Copy all messages as formatted conversation.
 * Each turn (user + assistant) is separated by a long dash line.
 * Within the same turn, user and AI messages are separated by ---. */
async function copyAllMessages() {
  if (messages.value.length === 0) return

  // Build turns: [ [userMsg, assistantMsg?], ... ]
  type Turn = { user: string; ai: string | null }
  const turns: Turn[] = []
  for (const msg of messages.value) {
    if (msg.role === 'user') {
      turns.push({ user: msg.content, ai: null })
    } else if (turns.length > 0 && turns[turns.length - 1].ai === null) {
      const body = copyFormat.value === 'plain' ? stripMarkdown(msg.content) : msg.content
      turns[turns.length - 1].ai = body
    }
  }

  const turnTexts = turns.map(t => {
    const lines = [`【用户】\n${t.user}`]
    if (t.ai !== null) lines.push(`【AI】\n${t.ai}`)
    return lines.join('\n\n---\n\n')
  })

  const text = turnTexts.join('\n\n————————————————\n\n')

  try {
    await navigator.clipboard.writeText(text)
    allCopied.value = true
    setTimeout(() => { allCopied.value = false }, 2000)
  } catch {
    // clipboard not available — fail silently
  }
}

// ---------------------------------------------------------------------------
// Keyboard input
// ---------------------------------------------------------------------------

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// Click outside to close settings panel
function onSettingsOverlayClick() {
  showSettings.value = false
}

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

function renderMarkdown(content: string): string {
  return md.render(content)
}
</script>

<template>
  <div class="paper-chat flex flex-col h-full overflow-hidden">
    <!-- Header: title + collapse only -->
    <div class="shrink-0 px-4 py-3 border-b border-border flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-sm font-semibold text-text-primary truncate">
          {{ chatMode === 'general' ? '💬 通用助手' : '💬 AI 问答' }}
        </span>
        <span v-if="paperTitle && chatMode === 'paper'" class="text-xs text-text-muted truncate">— {{ paperTitle }}</span>
      </div>
      <button
        v-if="showCloseButton"
        type="button"
        class="shrink-0 px-2.5 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
        @click="emit('close')"
      >
        收起
      </button>
    </div>

    <!-- Messages -->
    <div
      ref="messagesRef"
      class="flex-1 overflow-y-auto p-4 flex flex-col gap-3"
      :style="{ fontSize: chatFontSize + 'px' }"
    >
      <!-- Loading skeleton -->
      <div v-if="phase === 'loading'" class="flex justify-center py-8">
        <svg class="animate-spin h-6 w-6 text-tinder-pink" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <!-- Error state (no messages yet) -->
      <div v-else-if="phase === 'error' && messages.length === 0" class="text-center py-8">
        <p class="text-sm text-tinder-pink mb-3">{{ errorMsg }}</p>
        <button
          type="button"
          class="px-4 py-1.5 rounded-full bg-tinder-pink text-white text-xs font-medium cursor-pointer border-none hover:bg-[#e01f6e] transition-colors"
          @click="loadHistory"
        >
          重试
        </button>
      </div>

      <!-- Empty state -->
      <div v-else-if="messages.length === 0 && phase === 'idle'" class="flex flex-col items-center justify-center py-12 text-center gap-3">
        <div class="w-12 h-12 rounded-full bg-tinder-pink/10 flex items-center justify-center text-2xl">
          💬
        </div>
        <template v-if="chatMode === 'general'">
          <p class="text-sm text-text-muted">有什么想问的？直接输入即可</p>
          <p class="text-xs text-text-muted opacity-70">通用模式不绑定论文；需要针对某篇论文时请切换到论文问答</p>
        </template>
        <template v-else>
          <p class="text-sm text-text-muted">对这篇论文有疑问？直接问吧！</p>
          <p class="text-xs text-text-muted opacity-70">基于论文内容作答，未提及的内容会如实说明</p>
        </template>
      </div>

      <!-- Message list -->
      <template v-else>
        <div
          v-for="msg in messages"
          :key="msg.id"
          :class="[
            'flex gap-2 group',
            msg.role === 'user' ? 'justify-end' : 'justify-start',
          ]"
        >
          <!-- Assistant avatar -->
          <div
            v-if="msg.role === 'assistant'"
            class="shrink-0 w-7 h-7 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold mt-0.5"
          >
            AI
          </div>

          <!-- Bubble + action row -->
          <div :class="msg.role === 'user' ? 'flex flex-col items-end gap-1 max-w-[80%]' : 'flex flex-col items-start gap-1 max-w-[80%]'">
            <div
              :class="[
                'rounded-2xl px-3.5 py-2.5 leading-relaxed',
                msg.role === 'user'
                  ? 'bg-tinder-pink text-white rounded-tr-sm'
                  : 'bg-bg-elevated border border-border text-text-primary rounded-tl-sm',
              ]"
            >
              <div
                v-if="msg.role === 'assistant'"
                class="prose max-w-none break-words"
                v-html="renderMarkdown(msg.content)"
              />
              <span v-else class="whitespace-pre-wrap break-words">{{ msg.content }}</span>
            </div>

            <!-- Save-to-note + copy actions (assistant only, hover-visible) -->
            <div
              v-if="msg.role === 'assistant'"
              class="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1"
            >
              <!-- Copy single message -->
              <button
                type="button"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border bg-transparent transition-colors"
                :class="copiedMsgs[msg.id]
                  ? 'border-tinder-blue/40 text-tinder-blue cursor-default'
                  : 'border-border text-text-muted hover:border-tinder-blue/40 hover:text-tinder-blue cursor-pointer'"
                :disabled="copiedMsgs[msg.id]"
                :title="copyFormat === 'markdown' ? '复制（Markdown）' : '复制（纯文本）'"
                @click="copyMessage(msg)"
              >
                <svg v-if="!copiedMsgs[msg.id]" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                </svg>
                <span>{{ copiedMsgs[msg.id] ? '✓ 已复制' : '复制' }}</span>
              </button>

              <!-- Save to note -->
              <button
                v-if="chatMode !== 'general'"
                type="button"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border bg-transparent transition-colors"
                :class="savedNotes[msg.id]
                  ? 'border-green-500/40 text-green-500 cursor-default'
                  : 'border-border text-text-muted hover:border-tinder-blue/40 hover:text-tinder-blue cursor-pointer'"
                :disabled="savingNotes[msg.id] || savedNotes[msg.id]"
                @click="saveToNote(msg)"
              >
                <svg v-if="savingNotes[msg.id]" class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                <span v-else-if="savedNotes[msg.id]">✓ 已保存</span>
                <span v-else>📝 存入笔记</span>
              </button>
            </div>
          </div>

          <!-- User avatar -->
          <div
            v-if="msg.role === 'user'"
            class="shrink-0 w-7 h-7 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-muted text-xs mt-0.5"
          >
            我
          </div>
        </div>

        <!-- Streaming assistant reply -->
        <div v-if="streamingContent" class="flex gap-2 justify-start">
          <div class="shrink-0 w-7 h-7 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold mt-0.5">
            AI
          </div>
          <div class="max-w-[80%] rounded-2xl rounded-tl-sm px-3.5 py-2.5 leading-relaxed bg-bg-elevated border border-border text-text-primary">
            <div
              class="prose max-w-none break-words"
              v-html="renderMarkdown(streamingContent)"
            />
            <span class="inline-block w-1.5 h-4 bg-tinder-pink/70 ml-0.5 animate-pulse rounded-sm" />
          </div>
        </div>

        <!-- Thinking indicator -->
        <div v-else-if="isStreaming" class="flex gap-2 justify-start">
          <div class="shrink-0 w-7 h-7 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold">
            AI
          </div>
          <div class="rounded-2xl rounded-tl-sm px-3.5 py-2.5 bg-bg-elevated border border-border flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style="animation-delay:0ms" />
            <span class="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style="animation-delay:150ms" />
            <span class="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" style="animation-delay:300ms" />
          </div>
        </div>
      </template>

      <!-- Send error inline -->
      <div v-if="phase === 'error' && messages.length > 0" class="text-xs text-tinder-pink text-center py-1">
        {{ errorMsg }}
      </div>
    </div>

    <!-- Input area (toolbar + textarea) -->
    <div class="shrink-0 border-t border-border">
      <!-- Toolbar row -->
      <div class="px-2 pt-2 pb-1">
        <div class="flex items-center gap-0.5 bg-bg-elevated/60 rounded-xl px-2 py-1 relative">

        <!-- Settings button + upward dropdown -->
        <div class="relative">
          <button
            type="button"
            class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer transition-all duration-150 border-none"
            :class="showSettings
              ? 'bg-tinder-blue/12 text-tinder-blue'
              : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'"
            title="对话设置"
            @click="showSettings = !showSettings"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <span class="hidden sm:inline">{{ strategyLabel[contextStrategy] }}</span>
          </button>

          <!-- Settings dropdown — expands UPWARD -->
          <Transition name="settings-pop">
            <div
              v-if="showSettings"
              class="absolute left-0 bottom-full mb-2 z-50 w-72 bg-bg-card border border-border rounded-2xl shadow-xl p-4 flex flex-col gap-3"
            >
              <!-- Context strategy -->
              <div>
                <p class="text-xs font-semibold text-text-secondary mb-2">上下文策略</p>
                <div class="flex gap-1.5 flex-wrap">
                  <button
                    v-for="s in (['recent_k', 'summary', 'full'] as const)"
                    :key="s"
                    type="button"
                    class="px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer border transition-colors"
                    :class="contextStrategy === s
                      ? 'bg-tinder-blue/10 border-tinder-blue/40 text-tinder-blue'
                      : 'bg-bg-elevated border-border text-text-muted hover:bg-bg-hover'"
                    @click="contextStrategy = s; persistSettings()"
                  >
                    {{ strategyLabel[s] }}
                  </button>
                </div>
                <p class="text-xs text-text-muted mt-1.5 leading-relaxed">
                  <template v-if="contextStrategy === 'recent_k'">只传最近 K 轮历史，token 开销最小</template>
                  <template v-else-if="contextStrategy === 'summary'">超过 K 轮时自动压缩旧对话为摘要</template>
                  <template v-else>传完整历史，超限时从旧端截断</template>
                </p>
              </div>

              <!-- K value (hidden for full) -->
              <div v-if="contextStrategy !== 'full'">
                <p class="text-xs font-semibold text-text-secondary mb-2">K 值（轮数）</p>
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="contextK"
                    type="number"
                    min="1"
                    max="50"
                    class="w-20 px-2 py-1 rounded-lg border border-border bg-bg-elevated text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-tinder-blue/50"
                    @change="persistSettings"
                  />
                  <span class="text-xs text-text-muted">轮 = {{ contextK * 2 }} 条消息</span>
                </div>
              </div>

              <!-- Data source -->
              <div>
                <p class="text-xs font-semibold text-text-secondary mb-2">论文数据源</p>
                <div class="flex gap-1.5 flex-wrap">
                  <button
                    v-for="src in (['summary', 'abstract', 'full_text'] as const)"
                    :key="src"
                    type="button"
                    class="px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer border transition-colors"
                    :class="dataSource === src
                      ? 'bg-tinder-pink/10 border-tinder-pink/40 text-tinder-pink'
                      : 'bg-bg-elevated border-border text-text-muted hover:bg-bg-hover'"
                    @click="dataSource = src; persistSettings()"
                  >
                    {{ dataSourceLabel[src] }}
                  </button>
                </div>
                <p class="text-xs text-text-muted mt-1.5 leading-relaxed">
                  <template v-if="dataSource === 'summary'">AI 生成的中文结构化摘要（推荐）</template>
                  <template v-else-if="dataSource === 'abstract'">论文原文英文摘要</template>
                  <template v-else>MinerU 提取的全文（token 消耗大）</template>
                </p>
                <p class="text-xs text-amber-500/80 mt-1">切换数据源后建议清空历史以保持上下文一致</p>
              </div>
            </div>
          </Transition>

          <!-- Click-outside overlay -->
          <div
            v-if="showSettings"
            class="fixed inset-0 z-40"
            @click="onSettingsOverlayClick"
          />
        </div>

        <!-- Model picker button -->
        <div class="relative">
          <button
            type="button"
            class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer transition-all duration-150 border-none max-w-[120px]"
            :class="showModelPicker
              ? 'bg-tinder-pink/12 text-tinder-pink'
              : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'"
            title="选择模型"
            @click="showModelPicker = !showModelPicker"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/><path d="M12 8v4l3 3"/>
            </svg>
            <span class="truncate hidden sm:inline">{{ selectedPresetName }}</span>
          </button>

          <!-- Model picker dropdown — expands UPWARD -->
          <Transition name="settings-pop">
            <div
              v-if="showModelPicker"
              class="absolute left-0 bottom-full mb-2 z-50 w-64 bg-bg-card border border-border rounded-2xl shadow-xl overflow-hidden"
            >
              <div class="px-3 pt-3 pb-1">
                <p class="text-xs font-semibold text-text-secondary">选择模型预设</p>
              </div>

              <!-- No presets -->
              <div v-if="llmPresets.length === 0" class="px-3 py-3 text-xs text-text-muted">
                暂无预设，请前往个人中心添加
              </div>

              <!-- Preset list -->
              <div v-else class="max-h-48 overflow-y-auto">
                <!-- None option -->
                <button
                  type="button"
                  class="w-full px-3 py-2 text-left text-xs flex items-center justify-between gap-2 cursor-pointer transition-colors"
                  :class="selectedPresetId === null
                    ? 'bg-bg-elevated text-text-primary'
                    : 'text-text-muted hover:bg-bg-hover'"
                  @click="selectPreset(null)"
                >
                  <span>默认（使用全局配置）</span>
                  <svg v-if="selectedPresetId === null" class="w-3 h-3 shrink-0 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </button>
                <button
                  v-for="preset in llmPresets"
                  :key="preset.id"
                  type="button"
                  class="w-full px-3 py-2 text-left text-xs flex items-center justify-between gap-2 cursor-pointer transition-colors"
                  :class="selectedPresetId === preset.id
                    ? 'bg-bg-elevated text-text-primary'
                    : 'text-text-muted hover:bg-bg-hover'"
                  @click="selectPreset(preset.id)"
                >
                  <div class="min-w-0">
                    <div class="font-medium truncate">{{ preset.name }}</div>
                    <div class="text-text-muted truncate opacity-70">{{ preset.model || '未配置 model' }}</div>
                  </div>
                  <svg v-if="selectedPresetId === preset.id" class="w-3 h-3 shrink-0 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </button>
              </div>

              <!-- Footer: go to settings -->
              <div class="border-t border-border px-3 py-2">
                <a
                  href="/profile?tab=llm_presets"
                  class="text-xs text-tinder-blue no-underline hover:underline"
                  @click="showModelPicker = false"
                >
                  前往个人中心管理预设 →
                </a>
              </div>
            </div>
          </Transition>

          <!-- Click-outside overlay -->
          <div
            v-if="showModelPicker"
            class="fixed inset-0 z-40"
            @click="onModelPickerOverlayClick"
          />
        </div>

        <!-- Divider -->
        <div class="w-px h-3.5 bg-border mx-1 shrink-0" />

        <!-- Font size slider -->
        <div class="flex items-center gap-1.5 px-1">
          <svg class="w-3 h-3 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="currentColor">
            <text x="3" y="17" font-size="12" font-family="sans-serif">A</text>
          </svg>
          <input
            type="range"
            min="12"
            max="22"
            step="1"
            :value="chatFontSize"
            class="chat-font-slider w-16 cursor-pointer"
            title="调整字体大小"
            @input="chatFontSize = Number(($event.target as HTMLInputElement).value); persistSettings()"
          />
          <svg class="w-4 h-4 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="currentColor">
            <text x="1" y="18" font-size="16" font-family="sans-serif">A</text>
          </svg>
          <span class="text-[10px] text-text-muted w-6 shrink-0 tabular-nums">{{ chatFontSize }}px</span>
        </div>

        <!-- Divider -->
        <div class="w-px h-3.5 bg-border mx-1 shrink-0" />

        <!-- Copy format toggle (single icon button) -->
        <button
          type="button"
          class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer transition-all duration-150 border-none"
          :class="copyFormat === 'markdown'
            ? 'text-tinder-purple bg-tinder-purple/10'
            : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'"
          :title="copyFormat === 'markdown' ? '当前：复制 Markdown（点击切换为纯文本）' : '当前：复制纯文本（点击切换为 Markdown）'"
          @click="copyFormat = copyFormat === 'markdown' ? 'plain' : 'markdown'; persistSettings()"
        >
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="copyFormat === 'markdown'" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline v-if="copyFormat === 'markdown'" points="14 2 14 8 20 8"/><line v-if="copyFormat === 'markdown'" x1="16" y1="13" x2="8" y2="13"/><line v-if="copyFormat === 'markdown'" x1="16" y1="17" x2="8" y2="17"/><polyline v-if="copyFormat === 'markdown'" points="10 9 9 9 8 9"/>
            <path v-if="copyFormat === 'plain'" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline v-if="copyFormat === 'plain'" points="14 2 14 8 20 8"/><line v-if="copyFormat === 'plain'" x1="16" y1="13" x2="8" y2="13"/><line v-if="copyFormat === 'plain'" x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <span class="text-[10px] font-medium">{{ copyFormat === 'markdown' ? 'MD' : 'TXT' }}</span>
        </button>

        <!-- Push right -->
        <div class="flex-1" />

        <!-- Copy all button -->
        <button
          type="button"
          class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer transition-all duration-150 border-none disabled:opacity-30"
          :class="allCopied
            ? 'text-tinder-green bg-tinder-green/10'
            : 'text-text-muted hover:text-text-primary hover:bg-bg-hover'"
          :disabled="messages.length === 0 || isStreaming"
          title="复制全部对话"
          @click="copyAllMessages"
        >
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline v-if="allCopied" points="20 6 9 17 4 12"/>
            <template v-else>
              <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </template>
          </svg>
          <span class="hidden sm:inline text-[10px]">{{ allCopied ? '已复制' : '全部' }}</span>
        </button>

        <!-- Clear button -->
        <button
          type="button"
          class="flex items-center gap-1 px-2 py-1 rounded-lg text-xs cursor-pointer transition-all duration-150 border-none disabled:opacity-30 text-text-muted hover:text-tinder-pink hover:bg-tinder-pink/8"
          :disabled="clearing || isStreaming"
          title="清空对话记录"
          @click="handleClear"
        >
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
          <span class="hidden sm:inline text-[10px]">清空</span>
        </button>

        </div>
      </div>

      <!-- Textarea + send button -->
      <div class="px-3 pb-4 flex items-end gap-2">
        <textarea
          v-model="inputText"
          rows="3"
          placeholder="输入问题…（Enter 发送，Shift+Enter 换行）"
          class="flex-1 resize-none rounded-2xl border border-border bg-bg-elevated text-[15px] text-text-primary placeholder:text-text-muted px-4 py-3 focus:outline-none focus:ring-1 focus:ring-tinder-pink/50 transition-colors disabled:opacity-50"
          :disabled="isStreaming"
          @keydown="onKeydown"
        />
        <button
          type="button"
          class="shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors border-none cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          :class="inputText.trim() && !isStreaming
            ? 'bg-tinder-pink text-white hover:bg-[#e01f6e]'
            : 'bg-bg-elevated border border-border text-text-muted'"
          :disabled="!inputText.trim() || isStreaming"
          title="发送"
          @click="sendMessage"
        >
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Mobile: card style with rounded corners */
.paper-chat {
  background: var(--color-bg-card);
  border-radius: 1rem;
  border: 1px solid var(--color-border);
}

/* Desktop: sidebar-style panel flush to right edge */
@media (min-width: 768px) {
  .paper-chat {
    background: var(--color-bg-sidebar);
    border-radius: 0;
    border: none;
    border-left: 1px solid var(--color-border);
  }
}

/* ---- AI reply Markdown (prose) overrides for chat bubble context ---- */

/* Force prose text color to follow our theme — override typography plugin defaults */
:deep(.prose) {
  --tw-prose-body: var(--color-text-primary);
  --tw-prose-headings: var(--color-text-primary);
  --tw-prose-bold: var(--color-text-primary);
  --tw-prose-counters: var(--color-text-secondary);
  --tw-prose-bullets: var(--color-text-secondary);
  --tw-prose-quotes: var(--color-text-secondary);
  --tw-prose-code: var(--color-text-primary);
  --tw-prose-links: var(--color-tinder-blue, #4299e1);
  color: var(--color-text-primary);
  font-size: inherit;
  line-height: 1.6;
}
:deep(.prose p) {
  margin-top: 0.4em;
  margin-bottom: 0.4em;
}
:deep(.prose p:first-child) { margin-top: 0; }
:deep(.prose p:last-child)  { margin-bottom: 0; }

/* Headings — keep hierarchy but reduce vertical gap */
:deep(.prose h1),
:deep(.prose h2),
:deep(.prose h3),
:deep(.prose h4) {
  margin-top: 0.75em;
  margin-bottom: 0.3em;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Lists */
:deep(.prose ul),
:deep(.prose ol) {
  margin-top: 0.35em;
  margin-bottom: 0.35em;
  padding-left: 1.3em;
}
:deep(.prose li) {
  margin-top: 0.15em;
  margin-bottom: 0.15em;
  color: var(--color-text-primary);
}
:deep(.prose li::marker) {
  color: var(--color-text-secondary);
}
:deep(.prose strong) {
  color: var(--color-text-primary);
}

/* Inline code — adapt to theme colors instead of hardcoded gray */
:deep(.prose code:not(pre code)) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  border-radius: 0.3em;
  padding: 0.1em 0.35em;
  font-size: 0.82em;
}
/* Remove the prose default backtick pseudo-elements */
:deep(.prose code:not(pre code))::before,
:deep(.prose code:not(pre code))::after {
  content: none;
}

/* Code block */
:deep(.prose pre) {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  padding: 0.75em 1em;
  overflow-x: auto;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
}
:deep(.prose pre code) {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 0.82em;
  color: var(--color-text-primary);
}

/* Blockquote */
:deep(.prose blockquote) {
  border-left: 3px solid var(--color-tinder-pink);
  padding-left: 0.75em;
  color: var(--color-text-secondary);
  font-style: normal;
  margin-top: 0.4em;
  margin-bottom: 0.4em;
}
:deep(.prose blockquote p) { margin: 0; }

/* Horizontal rule */
:deep(.prose hr) {
  border-color: var(--color-border);
  margin: 0.6em 0;
}

/* Links */
:deep(.prose a) {
  color: var(--color-tinder-blue, #4299e1);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}

/* Table */
:deep(.prose table) {
  font-size: 0.82em;
  border-collapse: collapse;
  width: 100%;
  margin: 0.5em 0;
}
:deep(.prose th),
:deep(.prose td) {
  border: 1px solid var(--color-border);
  padding: 0.3em 0.6em;
}
:deep(.prose thead th) {
  background: var(--color-bg-hover);
  font-weight: 600;
}

/* ---- end prose overrides ---- */

/* ---- Font size range slider ---- */
.chat-font-slider {
  -webkit-appearance: none;
  appearance: none;
  height: 3px;
  background: var(--color-border);
  border-radius: 9999px;
  outline: none;
  transition: background 0.15s;
}
.chat-font-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-tinder-blue, #2db8e2);
  cursor: pointer;
  transition: transform 0.1s;
}
.chat-font-slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}
.chat-font-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: none;
  border-radius: 50%;
  background: var(--color-tinder-blue, #2db8e2);
  cursor: pointer;
}
/* ---- end font size slider ---- */

/* Settings dropdown pop-up animation */
.settings-pop-enter-active {
  transition: opacity 0.18s ease-out, transform 0.18s ease-out;
}
.settings-pop-leave-active {
  transition: opacity 0.14s ease-in, transform 0.14s ease-in;
}
.settings-pop-enter-from,
.settings-pop-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
}
</style>
