<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import 'katex/dist/katex.min.css'
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
  fetchPaperDetail,
} from '../api'
import type { ChatEvidenceSource, ChatMessage, PaperSummary, UserLlmPreset } from '../types/paper'
import { useGlobalChat } from '../composables/useGlobalChat'
import { useEntitlements } from '../composables/useEntitlements'
import PaperPickerDialog from './PaperPickerDialog.vue'
import PresetSelector from './PresetSelector.vue'
import UpgradePrompt from './UpgradePrompt.vue'
import QuotaWarningBanner from './QuotaWarningBanner.vue'
import { renderChatMarkdown } from '../utils/chatMarkdown'
import { openExternal } from '../utils/openExternal'

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

const globalChat = useGlobalChat()

// ---------------------------------------------------------------------------
// Entitlements
// ---------------------------------------------------------------------------
const entitlements = useEntitlements()
const chatFeature = computed(() => props.chatMode === 'general' ? 'general_chat_gate' : 'chat')
const chatQuotaBlocked = computed(() => {
  if (props.chatMode === 'general') {
    return entitlements.isGated('general_chat')
  }
  return !entitlements.canUse('chat')
})
const chatQuotaSummary = computed(() => {
  if (props.chatMode === 'general') return null
  return entitlements.quotaSummary('chat')
})
const chatQuotaExhausted = computed(() => chatQuotaBlocked.value)

// ---------------------------------------------------------------------------
// Paper picker state (for 深度研究 / 对比分析 launch from chat)
// ---------------------------------------------------------------------------
type PickerMode = 'research' | 'compare'
const showPicker = ref(false)
const pickerMode = ref<PickerMode>('research')

function openPicker(mode: PickerMode) {
  pickerMode.value = mode
  showPicker.value = true
}

function onPickerConfirm(paperIds: string[], titles: Record<string, string>) {
  showPicker.value = false
  if (pickerMode.value === 'research') {
    globalChat.requestResearch(paperIds, titles, 'kb')
  } else {
    globalChat.requestCompare(paperIds, titles)
  }
}

function handleResearchClick() {
  openPicker('research')
}

function handleCompareClick() {
  openPicker('compare')
}

// Preselected state for picker (paper mode: current paper is pre-locked for both research and compare)
const pickerPreselectedIds = computed(() => {
  if (props.chatMode === 'paper' && props.paperId) {
    return [props.paperId]
  }
  return []
})

const pickerPreselectedTitles = computed(() => {
  if (props.chatMode === 'paper' && props.paperId && props.paperTitle) {
    return { [props.paperId]: props.paperTitle }
  }
  return {}
})

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
const streamingEvidence = ref<ChatEvidenceSource[]>([])
const isStreaming = computed(() => phase.value === 'streaming')

// AbortController held while a streaming request is in flight.
// Replaced on each new sendMessage() call; cancelled by stopStreaming().
let _abortController: AbortController | null = null

function stopStreaming() {
  if (!isStreaming.value) return
  _abortController?.abort()
  _abortController = null
}

// ---------------------------------------------------------------------------
// Settings state
// ---------------------------------------------------------------------------

type ContextStrategy = 'recent_k' | 'summary' | 'full'
type DataSource = 'summary' | 'abstract' | 'full_text'

const showSettings = ref(false)
const activeSettingsSection = ref<'model' | 'context' | 'display' | 'session'>('model')
const settingsButtonRef = ref<HTMLElement | null>(null)
const settingsPopoverRef = ref<HTMLElement | null>(null)
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
const copiedLatexMsgs = ref<Record<number, boolean>>({})
// All-messages copy state
const allCopied = ref(false)

// ---------------------------------------------------------------------------
// Model (LLM preset) selection
// ---------------------------------------------------------------------------

const llmPresets = ref<UserLlmPreset[]>([])
const selectedPresetId = ref<number | null>(null)

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
  await _saveAllSettings()
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

function onDocPointerdown(e: PointerEvent) {
  if (!showSettings.value) return
  const target = e.target as Node
  if (
    settingsButtonRef.value?.contains(target) ||
    settingsPopoverRef.value?.contains(target)
  ) return
  showSettings.value = false
}

onMounted(() => {
  loadHistory()
  loadSettings()
  loadLlmPresets()
  document.addEventListener('pointerdown', onDocPointerdown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerdown, true)
})

watch(
  () => [props.paperId, props.chatMode] as const,
  () => {
    messages.value = []
    streamingContent.value = ''
    streamingEvidence.value = []
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
  streamingEvidence.value = []
  phase.value = 'streaming'
  scrollToBottom()
  globalChat.signalMessageSent()

  _abortController = new AbortController()
  const signal = _abortController.signal

  try {
    const response =
      props.chatMode === 'general'
        ? await fetchGeneralChatStream(text, signal)
        : await fetchPaperChatStream(props.paperId!, text, signal)

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(`请求失败 (${response.status}): ${errText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('无法读取响应流')

    const decoder = new TextDecoder()
    let buffer = ''

    try {
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
            } else if (chunk?.type === 'evidence' && Array.isArray(chunk.sources)) {
              streamingEvidence.value = chunk.sources as ChatEvidenceSource[]
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    // Commit whatever was streamed (handles both normal finish and user stop)
    if (streamingContent.value) {
      messages.value.push({
        id: Date.now() + 1,
        role: 'assistant',
        content: streamingContent.value,
        created_at: new Date().toISOString(),
        evidence: streamingEvidence.value,
        data_source: dataSource.value,
      })
    }
    streamingContent.value = ''
    streamingEvidence.value = []
    phase.value = 'idle'
    _abortController = null
    scrollToBottom()

    // Reload from server to get accurate persisted IDs
    const fresh =
      props.chatMode === 'general'
        ? await fetchGeneralChatHistory()
        : await fetchChatHistory(props.paperId!)
    if (fresh.length > 0) messages.value = fresh

    // Refresh quota display after consuming a chat credit
    if (props.chatMode !== 'general') {
      void entitlements.refreshEntitlements(true)
    }

  } catch (e: any) {
    // AbortError = user clicked stop; treat as a clean stop, not an error
    if (e?.name === 'AbortError' || signal.aborted) {
      if (streamingContent.value) {
        messages.value.push({
          id: Date.now() + 1,
          role: 'assistant',
          content: streamingContent.value,
          created_at: new Date().toISOString(),
          evidence: streamingEvidence.value,
          data_source: dataSource.value,
        })
      }
      streamingContent.value = ''
      streamingEvidence.value = []
      phase.value = 'idle'
      _abortController = null
      scrollToBottom()
      return
    }
    streamingContent.value = ''
    streamingEvidence.value = []
    phase.value = 'error'
    _abortController = null
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
    if (!inKb) {
      let summary = props.paperSummary
      if (!summary) {
        try {
          const detail = await fetchPaperDetail(pid)
          summary = detail?.summary
        } catch { /* ignore */ }
      }
      if (summary) {
        await addKbPaper(pid, summary)
      }
    }

    // Render Markdown → HTML so Tiptap editor can display it as rich text
    const htmlContent = renderChatMarkdown(assistantMsg.content)
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
  const html = renderChatMarkdown(content)
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || content
}

function extractLatex(content: string): string[] {
  const formulas: string[] = []
  const patterns = [
    /\$\$([\s\S]+?)\$\$/g,
    /\\\[([\s\S]+?)\\\]/g,
    /\\\(([\s\S]+?)\\\)/g,
    /\$([^$\n]+?)\$/g,
  ]
  for (const pattern of patterns) {
    for (const match of content.matchAll(pattern)) {
      const value = match[1]?.trim()
      if (value && !formulas.includes(value)) formulas.push(value)
    }
  }
  return formulas
}

async function copyLatex(msg: ChatMessage) {
  const formulas = extractLatex(msg.content)
  if (!formulas.length) return
  try {
    await navigator.clipboard.writeText(formulas.join('\n\n'))
    copiedLatexMsgs.value[msg.id] = true
    setTimeout(() => { copiedLatexMsgs.value[msg.id] = false }, 2000)
  } catch {
    // clipboard not available
  }
}

function dataSourceName(source: ChatMessage['data_source']): string {
  if (source === 'full_text') return '论文全文'
  if (source === 'abstract') return '原文摘要'
  return 'AI 摘要'
}

function canOpenEvidence(source: ChatEvidenceSource): boolean {
  return !!source.page && !!props.paperId && !props.paperId.startsWith('up_')
}

function openEvidence(source: ChatEvidenceSource) {
  if (!canOpenEvidence(source) || !props.paperId) return
  openExternal(`https://arxiv.org/pdf/${encodeURIComponent(props.paperId)}#page=${source.page}`)
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


// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

function renderMarkdown(content: string): string {
  return renderChatMarkdown(content)
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

      <!-- Empty state: feature guide cards -->
      <div v-else-if="messages.length === 0 && phase === 'idle'" class="flex flex-col items-start px-3 py-4 gap-2.5">
        <!-- 深度研究 card -->
        <button
          type="button"
          class="w-full text-left flex items-start gap-3 px-4 py-3 rounded-2xl border border-border bg-bg-elevated hover:bg-bg-hover hover:border-tinder-blue/40 cursor-pointer transition-all duration-150 group"
          @click="handleResearchClick"
        >
          <span class="text-xl shrink-0 mt-0.5">🔍</span>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-text-primary group-hover:text-tinder-blue transition-colors">深度研究</p>
            <p class="text-xs text-text-muted leading-relaxed mt-0.5">
              <template v-if="chatMode === 'paper' && paperId">针对这篇论文深度问答，支持多轮提问</template>
              <template v-else>选 1-20 篇论文，AI 深度分析并多轮问答</template>
            </p>
          </div>
          <svg class="w-4 h-4 text-text-muted group-hover:text-tinder-blue shrink-0 mt-1 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>

        <!-- 对比分析 card -->
        <button
          type="button"
          class="w-full text-left flex items-start gap-3 px-4 py-3 rounded-2xl border border-border bg-bg-elevated hover:bg-bg-hover hover:border-tinder-purple/40 cursor-pointer transition-all duration-150 group"
          @click="handleCompareClick"
        >
          <span class="text-xl shrink-0 mt-0.5">⚖️</span>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-text-primary group-hover:text-tinder-purple transition-colors">对比分析</p>
            <p class="text-xs text-text-muted leading-relaxed mt-0.5">
              <template v-if="chatMode === 'paper' && paperId">将此论文与其他论文做多维对比</template>
              <template v-else>选 2-5 篇论文，AI 生成多维对比报告</template>
            </p>
          </div>
          <svg class="w-4 h-4 text-text-muted group-hover:text-tinder-purple shrink-0 mt-1 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>

        <!-- 直接提问 hint -->
        <div class="w-full flex items-center gap-3 px-4 py-2.5">
          <span class="text-xl shrink-0">💬</span>
          <p class="text-xs text-text-muted leading-relaxed">
            <template v-if="chatMode === 'paper' && paperId">或直接在下方输入框提问</template>
            <template v-else>或直接在下方输入框发起通用对话</template>
          </p>
        </div>
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
            class="shrink-0 w-8 h-8 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold mt-0.5 shadow-sm"
          >
            AI
          </div>

          <!-- Bubble + action row -->
          <div :class="msg.role === 'user' ? 'flex flex-col items-end gap-1 max-w-[80%]' : 'flex flex-col items-start gap-1 max-w-[80%]'">
            <div
              :class="[
                'rounded-2xl px-3.5 py-2.5 leading-relaxed',
                msg.role === 'user'
                  ? 'bg-brand-gradient text-white rounded-tr-sm'
                  : 'bg-bg-elevated border border-border text-text-primary rounded-tl-sm shadow-sm',
              ]"
            >
              <div
                v-if="msg.role === 'assistant'"
                class="prose max-w-none break-words"
                v-html="renderMarkdown(msg.content)"
              />
              <span v-else class="whitespace-pre-wrap break-words">{{ msg.content }}</span>
            </div>

            <details
              v-if="msg.role === 'assistant' && msg.evidence?.length"
              class="w-full rounded-xl border border-tinder-blue/20 bg-tinder-blue/5 px-3 py-2"
            >
              <summary class="cursor-pointer text-xs font-medium text-tinder-blue">
                {{ dataSourceName(msg.data_source) }} · {{ msg.evidence.length }} 条可核对证据
              </summary>
              <div class="mt-2 space-y-2">
                <article
                  v-for="source in msg.evidence"
                  :key="`${msg.id}-${source.id}`"
                  class="rounded-lg border border-border/70 bg-bg-card/70 p-2.5"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-[11px] font-semibold text-text-secondary">[{{ source.id }}] {{ source.location }}</span>
                    <button
                      v-if="canOpenEvidence(source)"
                      type="button"
                      class="shrink-0 rounded-full border border-border bg-transparent px-2 py-0.5 text-[10px] text-text-muted hover:border-tinder-blue/40 hover:text-tinder-blue"
                      @click="openEvidence(source)"
                    >
                      定位 PDF
                    </button>
                  </div>
                  <p class="mt-1 text-[11px] leading-relaxed text-text-muted">{{ source.excerpt }}</p>
                </article>
              </div>
            </details>
            <p
              v-else-if="msg.role === 'assistant' && msg.data_source"
              class="w-full rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-[11px] text-amber-400"
            >
              本条回答未返回可核对的证据编号，重要结论请结合原文复核。
            </p>

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

              <button
                v-if="extractLatex(msg.content).length"
                type="button"
                class="inline-flex items-center gap-1 rounded-full border bg-transparent px-2 py-0.5 text-xs transition-colors"
                :class="copiedLatexMsgs[msg.id]
                  ? 'border-tinder-purple/40 text-tinder-purple cursor-default'
                  : 'border-border text-text-muted hover:border-tinder-purple/40 hover:text-tinder-purple cursor-pointer'"
                :disabled="copiedLatexMsgs[msg.id]"
                title="复制本条回答中的 LaTeX 公式"
                @click="copyLatex(msg)"
              >
                {{ copiedLatexMsgs[msg.id] ? '✓ 已复制公式' : '复制公式' }}
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
          <div class="shrink-0 w-8 h-8 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold mt-0.5 shadow-sm">
            AI
          </div>
          <div class="max-w-[80%] rounded-2xl rounded-tl-sm px-3.5 py-2.5 leading-relaxed bg-bg-elevated border border-border text-text-primary shadow-sm">
            <div
              class="prose max-w-none break-words"
              v-html="renderMarkdown(streamingContent)"
            />
            <span class="inline-block w-1.5 h-4 bg-tinder-pink/70 ml-0.5 animate-pulse rounded-sm" />
          </div>
        </div>

        <!-- Thinking indicator -->
        <div v-else-if="isStreaming" class="flex gap-2 justify-start">
          <div class="shrink-0 w-8 h-8 rounded-full bg-brand-gradient-br flex items-center justify-center text-white text-xs font-bold shadow-sm">
            AI
          </div>
          <div class="rounded-2xl rounded-tl-sm px-3.5 py-2.5 bg-bg-elevated border border-border shadow-sm flex items-center gap-1">
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

    <!-- Input area (composer) -->
    <div class="shrink-0 border-t border-border bg-bg-card/80 backdrop-blur-sm">

      <!-- Composer top row: feature chips + more/settings -->
      <div class="relative px-3 pt-2 pb-1 flex items-center gap-1.5">

        <!-- 深度研究 chip -->
        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all border border-border bg-bg-elevated text-text-secondary hover:border-tinder-blue/50 hover:bg-tinder-blue/8 hover:text-tinder-blue"
          title="深度研究：针对论文 / 文献集发起多轮问答"
          @click="handleResearchClick"
        >
          <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            <path d="M11 8v3"/><path d="M8 11h6"/>
          </svg>
          深度研究
        </button>

        <!-- 对比分析 chip -->
        <button
          type="button"
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all border border-border bg-bg-elevated text-text-secondary hover:border-tinder-purple/50 hover:bg-tinder-purple/8 hover:text-tinder-purple"
          title="对比分析：将论文与其他论文做多维对比"
          @click="handleCompareClick"
        >
          <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22V12"/><path d="m21 3-7 7-4-4-7 7"/>
          </svg>
          对比分析
        </button>

        <div class="flex-1" />

        <!-- More / Settings button -->
        <button
          ref="settingsButtonRef"
          type="button"
          class="flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all border"
          :class="showSettings
            ? 'border-tinder-blue/50 bg-tinder-blue/8 text-tinder-blue'
            : 'border-border bg-bg-elevated text-text-muted hover:border-border-light hover:text-text-secondary'"
          title="设置与更多"
          @click="showSettings = !showSettings"
        >
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>
          </svg>
          <span class="hidden sm:inline">更多</span>
        </button>

        <!-- Unified popover — expands UPWARD, anchored to composer row -->
        <Transition name="settings-pop">
          <div
            ref="settingsPopoverRef"
            v-if="showSettings"
            class="absolute right-3 bottom-full mb-2 z-50 w-[calc(100%-1.5rem)] max-w-[26rem] bg-bg-card border border-border rounded-2xl shadow-xl overflow-hidden"
          >
            <!-- Header -->
            <div class="flex items-center justify-between px-3.5 pt-3 pb-2 border-b border-border/50">
              <span class="text-xs font-semibold text-text-primary">设置</span>
              <span class="text-[11px] text-text-muted truncate ml-2">
                {{ dataSourceLabel[dataSource] }} · {{ strategyLabel[contextStrategy] }} · {{ chatFontSize }}px
              </span>
            </div>

            <!-- Body: left rail + right panel -->
            <div class="flex" style="min-height: 180px; max-height: 72vh; overflow: hidden;">

              <!-- Left navigation rail -->
              <nav class="settings-rail shrink-0 flex flex-col gap-0.5 p-2 border-r border-border/40 bg-bg-elevated/50">
                <!-- 模型 -->
                <button
                  type="button"
                  class="settings-nav-btn"
                  :class="activeSettingsSection === 'model' ? 'settings-nav-btn--active' : ''"
                  @click="activeSettingsSection = 'model'"
                >
                  <svg class="settings-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="4" width="16" height="16" rx="2"/>
                    <path d="M9 9h6M9 12h4M9 15h3"/>
                  </svg>
                  <span class="settings-nav-label">模型</span>
                  <span class="settings-nav-status">{{ selectedPresetId ? (llmPresets.find(p => p.id === selectedPresetId)?.name ?? '—') : '默认' }}</span>
                </button>

                <!-- 上下文 -->
                <button
                  type="button"
                  class="settings-nav-btn"
                  :class="activeSettingsSection === 'context' ? 'settings-nav-btn--active' : ''"
                  @click="activeSettingsSection = 'context'"
                >
                  <svg class="settings-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="settings-nav-label">上下文</span>
                  <span class="settings-nav-status">{{ strategyLabel[contextStrategy] }}</span>
                </button>

                <!-- 显示 -->
                <button
                  type="button"
                  class="settings-nav-btn"
                  :class="activeSettingsSection === 'display' ? 'settings-nav-btn--active' : ''"
                  @click="activeSettingsSection = 'display'"
                >
                  <svg class="settings-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/>
                  </svg>
                  <span class="settings-nav-label">显示</span>
                  <span class="settings-nav-status">{{ chatFontSize }}px</span>
                </button>

                <!-- 会话 -->
                <button
                  type="button"
                  class="settings-nav-btn"
                  :class="activeSettingsSection === 'session' ? 'settings-nav-btn--active' : ''"
                  @click="activeSettingsSection = 'session'"
                >
                  <svg class="settings-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4"/>
                  </svg>
                  <span class="settings-nav-label">会话</span>
                  <span class="settings-nav-status">{{ messages.length }}条</span>
                </button>
              </nav>

              <!-- Right content panel -->
              <div class="flex-1 overflow-y-auto">

                <!-- Panel: 模型 -->
                <div v-if="activeSettingsSection === 'model'" class="p-3.5 flex flex-col gap-3">
                  <p class="text-[11px] font-semibold text-text-muted uppercase tracking-wide">模型预设</p>
                  <PresetSelector
                    :model-value="selectedPresetId"
                    :presets="llmPresets"
                    :none-option="{ label: '默认（全局配置）' }"
                    :show-model-hint="true"
                    accent-color="#ec4899"
                    placeholder="选择模型"
                    drop-direction="up"
                    @update:model-value="val => selectPreset(val == null ? null : Number(val))"
                  />
                  <p class="text-[11px] text-text-muted leading-relaxed">不选则使用系统默认模型。预设在账户设置中管理。</p>
                </div>

                <!-- Panel: 上下文 -->
                <div v-else-if="activeSettingsSection === 'context'" class="p-3.5 flex flex-col gap-4">
                  <!-- 上下文策略 -->
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
                    <p class="text-[11px] text-text-muted mt-1.5 leading-relaxed">
                      <template v-if="contextStrategy === 'recent_k'">只传最近 K 轮历史，token 开销最小</template>
                      <template v-else-if="contextStrategy === 'summary'">超过 K 轮时自动压缩旧对话为摘要</template>
                      <template v-else>传完整历史，超限时从旧端截断</template>
                    </p>
                  </div>
                  <!-- K 值 -->
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
                      <span class="text-[11px] text-text-muted">轮 = {{ contextK * 2 }} 条消息</span>
                    </div>
                  </div>
                  <!-- 数据源 -->
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
                    <p class="text-[11px] text-text-muted mt-1.5 leading-relaxed">
                      <template v-if="dataSource === 'summary'">AI 生成的中文结构化摘要（推荐）</template>
                      <template v-else-if="dataSource === 'abstract'">论文原文英文摘要</template>
                      <template v-else>MinerU 提取的全文（token 消耗大）</template>
                    </p>
                    <p class="text-[11px] text-amber-500/80 mt-1">切换数据源后建议清空历史以保持上下文一致</p>
                  </div>
                </div>

                <!-- Panel: 显示 -->
                <div v-else-if="activeSettingsSection === 'display'" class="p-3.5 flex flex-col gap-4">
                  <!-- Font size -->
                  <div>
                    <p class="text-xs font-semibold text-text-secondary mb-2.5">字体大小</p>
                    <div class="flex items-center gap-2.5">
                      <svg class="w-3 h-3 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="currentColor">
                        <text x="3" y="17" font-size="12" font-family="sans-serif">A</text>
                      </svg>
                      <input
                        type="range"
                        min="12"
                        max="22"
                        step="1"
                        :value="chatFontSize"
                        class="chat-font-slider flex-1 cursor-pointer"
                        title="调整字体大小"
                        @input="chatFontSize = Number(($event.target as HTMLInputElement).value); persistSettings()"
                      />
                      <svg class="w-4 h-4 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="currentColor">
                        <text x="1" y="18" font-size="16" font-family="sans-serif">A</text>
                      </svg>
                      <span class="text-xs text-text-muted w-8 shrink-0 tabular-nums text-right">{{ chatFontSize }}px</span>
                    </div>
                  </div>
                  <!-- Copy format -->
                  <div>
                    <p class="text-xs font-semibold text-text-secondary mb-2">复制格式</p>
                    <div class="flex p-0.5 bg-bg-elevated rounded-lg border border-border gap-0.5 self-start w-fit">
                      <button
                        type="button"
                        class="px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors border-none"
                        :class="copyFormat === 'markdown'
                          ? 'bg-bg-card text-tinder-purple shadow-sm'
                          : 'bg-transparent text-text-muted hover:text-text-secondary'"
                        @click="copyFormat = 'markdown'; persistSettings()"
                      >
                        Markdown
                      </button>
                      <button
                        type="button"
                        class="px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors border-none"
                        :class="copyFormat === 'plain'
                          ? 'bg-bg-card text-text-primary shadow-sm'
                          : 'bg-transparent text-text-muted hover:text-text-secondary'"
                        @click="copyFormat = 'plain'; persistSettings()"
                      >
                        纯文本
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Panel: 会话 -->
                <div v-else-if="activeSettingsSection === 'session'" class="p-3.5 flex flex-col gap-1.5">
                  <p class="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-1">会话操作</p>
                  <!-- Copy all -->
                  <button
                    type="button"
                    class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl text-xs text-left cursor-pointer transition-colors border-none"
                    :class="allCopied
                      ? 'bg-tinder-green/8 text-tinder-green cursor-default'
                      : 'text-text-secondary hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed'"
                    :disabled="messages.length === 0 || isStreaming"
                    @click="copyAllMessages"
                  >
                    <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline v-if="allCopied" points="20 6 9 17 4 12"/>
                      <template v-else>
                        <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                      </template>
                    </svg>
                    {{ allCopied ? '已复制全部对话' : '复制全部对话' }}
                  </button>
                  <!-- Clear -->
                  <button
                    type="button"
                    class="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl text-xs text-left cursor-pointer transition-colors border-none text-tinder-pink hover:bg-tinder-pink/8 disabled:opacity-30 disabled:cursor-not-allowed"
                    :disabled="clearing || isStreaming"
                    @click="handleClear"
                  >
                    <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                    </svg>
                    清空对话记录
                  </button>
                </div>

              </div>
            </div>
          </div>
        </Transition>

      </div>

      <!-- Quota / gate upgrade prompt -->
      <div v-if="chatQuotaExhausted && entitlements.loaded.value" class="px-3 pb-2">
        <UpgradePrompt
          :feature="props.chatMode === 'general' ? 'general_chat' : 'chat'"
          :inline="true"
        />
      </div>

      <!-- Chat near-limit warning (paper chat only) -->
      <div
        v-else-if="props.chatMode !== 'general' && entitlements.loaded.value"
        class="px-3 pb-1"
      >
        <QuotaWarningBanner feature="chat" :compact="true" />
      </div>

      <!-- Chat daily quota indicator (paper chat, Free tier only) -->
      <div
        v-else-if="chatQuotaSummary && entitlements.loaded.value"
        class="px-3 pb-1 flex items-center justify-end gap-1 text-[11px] text-text-muted"
      >
        <span>今日问答：</span>
        <span :class="(entitlements.remaining('chat') ?? 1) <= 2 ? 'text-amber-400 font-semibold' : ''">
          {{ chatQuotaSummary }}
        </span>
      </div>

      <!-- Textarea + send button -->
      <div class="px-3 pb-4 flex items-end gap-2">
        <textarea
          v-model="inputText"
          rows="3"
          placeholder="输入问题…（Enter 发送，Shift+Enter 换行）"
          class="flex-1 resize-none rounded-2xl border border-border bg-bg-elevated text-[15px] text-text-primary placeholder:text-text-muted px-4 py-3 focus:outline-none focus:ring-1 focus:ring-tinder-pink/50 transition-colors disabled:opacity-50"
          :disabled="isStreaming || chatQuotaExhausted"
          @keydown="onKeydown"
        />
        <!-- Stop button shown while AI is streaming -->
        <button
          v-if="isStreaming"
          type="button"
          class="shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors border-none cursor-pointer bg-bg-elevated border border-border text-tinder-pink hover:bg-bg-hover"
          title="停止生成"
          @click="stopStreaming"
        >
          <svg class="w-[16px] h-[16px]" viewBox="0 0 24 24" fill="currentColor">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
        </button>
        <!-- Send button shown when idle -->
        <button
          v-else
          type="button"
          class="shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors border-none cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          :class="inputText.trim() && !chatQuotaExhausted
            ? 'bg-brand-gradient text-white hover:opacity-90'
            : 'bg-bg-elevated border border-border text-text-muted'"
          :disabled="!inputText.trim() || chatQuotaExhausted"
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

  <!-- Paper picker dialog for 深度研究 / 对比分析 -->
  <PaperPickerDialog
    v-if="showPicker"
    :mode="pickerMode"
    :preselected-ids="pickerPreselectedIds"
    :preselected-titles="pickerPreselectedTitles"
    @confirm="onPickerConfirm"
    @cancel="showPicker = false"
  />
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
  background: var(--color-bg-elevated);
  color: var(--color-tinder-pink);
  border: 1px solid var(--color-border);
  border-radius: 0.3em;
  padding: 0.1em 0.35em;
  font-size: 0.82em;
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
}
/* Remove the prose default backtick pseudo-elements */
:deep(.prose code:not(pre code))::before,
:deep(.prose code:not(pre code))::after {
  content: none;
}

/* Code block */
:deep(.prose pre) {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  padding: 0.75em 1em;
  overflow-x: auto;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
}
:deep(.prose pre code) {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 0.82em;
  font-family: inherit;
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

/* KaTeX formulas: keep inline math readable and let long display equations
   scroll inside the message bubble instead of widening the whole drawer. */
:deep(.prose .katex) {
  font-size: 1.05em;
}
:deep(.prose .katex-display) {
  max-width: 100%;
  margin: 0.75em 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.2em 0;
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

/* ---- Settings rail navigation ---- */
.settings-rail {
  width: 84px;
}

.settings-nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  width: 100%;
  padding: 8px 4px 6px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  color: var(--color-text-muted);
}
.settings-nav-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
}
.settings-nav-btn--active {
  background: var(--color-bg-card);
  color: var(--color-tinder-blue, #2db8e2);
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.settings-nav-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.settings-nav-label {
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}
.settings-nav-status {
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 72px;
  opacity: 0.7;
}
/* ---- end settings rail ---- */

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
