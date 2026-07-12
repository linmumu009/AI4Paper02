<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { KbScope } from '../api'
import { fetchCompareStream, saveCompareResult } from '../api'
import { useEngagement } from '../composables/useEngagement'
import { trackEvent } from '../composables/useAnalytics'
import { useEntitlements } from '../composables/useEntitlements'
import { renderChatMarkdown } from '../utils/chatMarkdown'
import 'katex/dist/katex.min.css'
import RewardBoostBanner from './RewardBoostBanner.vue'
import UpgradePrompt from './UpgradePrompt.vue'
import QuotaWarningBanner from './QuotaWarningBanner.vue'
import scaleIcon from '../assets/heroicons/scale.svg'
import documentIcon from '../assets/heroicons/document-text.svg'
import checkIcon from '../assets/heroicons/check-circle.svg'
import closeIcon from '../assets/heroicons/x-mark.svg'
import archiveIcon from '../assets/heroicons/archive-box.svg'
import bookIcon from '../assets/heroicons/book-open.svg'

const props = defineProps<{
  paperIds: string[]
  paperTitles?: Record<string, string>
  scope?: KbScope
  compareResultIds?: number[]
}>()

const emit = defineEmits<{ close: []; saved: [resultId: number] }>()
const engagement = useEngagement()
const ent = useEntitlements()
const useCompareReward = ref(false)
const compareQuotaBlocked = computed(() => !ent.canUse('compare'))
const compareQuotaSummary = computed(() => ent.quotaSummary('compare'))

type Phase = 'idle' | 'loading' | 'streaming' | 'done' | 'error'
const phase = ref<Phase>('idle')
const rawMarkdown = ref('')
const errorMsg = ref('')
const contentRef = ref<HTMLElement | null>(null)
const copied = ref(false)
const saved = ref(false)
const saving = ref(false)
const renderedHtml = computed(() => renderChatMarkdown(rawMarkdown.value))
const analysisDimensions = ['研究问题', '方法与架构', '数据与实验', '关键结果', '局限与适用边界', '证据来源']
const phaseLabel = computed(() => ({ idle: '待开始', loading: '准备资料', streaming: '分析中', done: '已完成', error: '需要重试' })[phase.value])
const phaseDescription = computed(() => ({
  idle: '确认论文来源后开始生成结构化报告。',
  loading: '正在聚合论文元数据与已保存报告。',
  streaming: 'AI 正在逐项建立差异与证据关联。',
  done: '报告已生成，可复制或保存到对比库。',
  error: '本次分析没有完成，请检查连接后重试。',
})[phase.value])
const scopeLabel = computed(() => ({ kb: '知识库', inspiration: '灵感论文', mypapers: '我的论文' })[props.scope || 'kb'] || '跨库来源')

function getPaperTitle(paperId: string) {
  return props.paperTitles?.[paperId] || paperId
}

function userFacingError(status: number, text: string) {
  try {
    const data = JSON.parse(text)
    if (typeof data?.detail === 'string') return data.detail
  } catch {}
  if (status === 401) return '登录状态已失效，请重新登录后再试。'
  if (status === 403) return '当前套餐或账号暂时无法发起本次对比。'
  if (status === 429) return '本月对比额度已用完或请求过于频繁。'
  return `对比服务暂时不可用（${status}），请稍后重试。`
}

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(rawMarkdown.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

function scrollToBottom() {
  nextTick(() => {
    if (contentRef.value) contentRef.value.scrollTop = contentRef.value.scrollHeight
  })
}

let abortController: AbortController | null = null

async function startStreaming() {
  if (!props.paperIds.length) return
  phase.value = 'loading'
  rawMarkdown.value = ''
  errorMsg.value = ''
  saved.value = false
  abortController = new AbortController()
  const reward = useCompareReward.value ? engagement.bestCompareReward.value : undefined
  try {
    const response = await fetchCompareStream(props.paperIds, props.scope || 'kb', props.compareResultIds, reward?.id)
    if (reward) {
      useCompareReward.value = false
      engagement.notifyRewardUsed(reward.reward_name)
      void engagement.loadActiveRewards('compare')
      void engagement.loadStatus(true)
    }
    if (!response.ok) {
      errorMsg.value = userFacingError(response.status, await response.text())
      phase.value = 'error'
      return
    }
    const reader = response.body?.getReader()
    if (!reader) {
      errorMsg.value = '无法读取分析结果，请稍后重试。'
      phase.value = 'error'
      return
    }
    phase.value = 'streaming'
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
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') {
          phase.value = 'done'
          void ent.refreshEntitlements(true)
          return
        }
        try { rawMarkdown.value += JSON.parse(payload) as string } catch { rawMarkdown.value += payload }
        scrollToBottom()
      }
    }
    if (phase.value === 'streaming') phase.value = 'done'
    void ent.refreshEntitlements(true)
  } catch (error: any) {
    if (error?.name === 'AbortError') return
    errorMsg.value = '网络连接中断，请检查连接后重试。'
    phase.value = 'error'
  }
}

function stopStreaming() {
  abortController?.abort()
  abortController = null
  if (phase.value === 'streaming' || phase.value === 'loading') phase.value = rawMarkdown.value ? 'done' : 'idle'
}

async function saveToLibrary() {
  if (saving.value || saved.value || !rawMarkdown.value) return
  saving.value = true
  try {
    const titles = props.paperIds.map(getPaperTitle)
    const title = titles.length <= 2 ? titles.join(' vs ') : `${titles[0]} 等${titles.length}篇对比`
    const result = await saveCompareResult(title, rawMarkdown.value, props.paperIds)
    saved.value = true
    emit('saved', result.id)
    trackEvent('compare_saved', { targetId: props.paperIds.join(','), value: props.paperIds.length })
  } catch {
    errorMsg.value = '报告保存失败，内容仍保留在当前页面，可稍后重试。'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (engagement.loaded.value) await engagement.loadActiveRewards('compare')
})
onBeforeUnmount(stopStreaming)
</script>

<template>
  <section class="compare-workspace" aria-label="论文对比工作区">
    <header class="compare-workspace__header">
      <div class="compare-workspace__heading">
        <span>Research comparison</span><h1>论文对比</h1><p>把差异、共识与证据整理成可复用的研究结论</p>
      </div>
      <div class="compare-workspace__header-actions">
        <button v-if="phase === 'streaming'" type="button" class="is-danger" @click="stopStreaming">停止生成</button>
        <button v-if="phase === 'done' && rawMarkdown" type="button" @click="copyToClipboard">{{ copied ? '已复制' : '复制报告' }}</button>
        <button v-if="phase === 'done' && rawMarkdown" type="button" class="is-primary" :disabled="saving || saved" @click="saveToLibrary">
          <img :src="archiveIcon" alt="">{{ saving ? '保存中' : saved ? '已保存' : '保存到对比库' }}
        </button>
        <button type="button" class="compare-workspace__close" aria-label="关闭论文对比" @click="emit('close')"><img :src="closeIcon" alt=""></button>
      </div>
    </header>
    <div class="compare-workspace__body">
      <aside class="compare-workspace__sources" aria-label="参与对比的论文">
        <div class="compare-workspace__section-heading"><h2>论文来源</h2><span>{{ paperIds.length }} 篇</span></div>
        <div class="compare-workspace__source-list">
          <article v-for="(paperId, index) in paperIds" :key="paperId" class="compare-workspace__source-card">
            <b>{{ String(index + 1).padStart(2, '0') }}</b><div><strong>{{ getPaperTitle(paperId) }}</strong><small>{{ paperId }}</small></div>
          </article>
        </div>
        <article v-if="compareResultIds?.length" class="compare-workspace__history-source">
          <img :src="archiveIcon" alt=""><div><strong>历史对比报告</strong><small>{{ compareResultIds.length }} 份作为补充上下文</small></div>
        </article>
        <div class="compare-workspace__source-meta"><span>来源范围</span><strong>{{ scopeLabel }}</strong></div>
      </aside>
      <main ref="contentRef" class="compare-workspace__report">
        <div v-if="phase === 'idle'" class="compare-workspace__start">
          <div class="compare-workspace__start-icon"><img :src="scaleIcon" alt=""></div>
          <span>Comparison brief</span><h2>准备比较 {{ paperIds.length }} 篇论文</h2>
          <p>AI 会统一研究问题、方法、实验与结论的表达口径，并在报告中保留可核对的论文来源。</p>
          <UpgradePrompt v-if="compareQuotaBlocked && ent.loaded.value" feature="compare" class="compare-workspace__notice" />
          <template v-else>
            <QuotaWarningBanner v-if="ent.loaded.value" feature="compare" class="compare-workspace__notice" />
            <RewardBoostBanner :reward="engagement.bestCompareReward.value" v-model="useCompareReward" class="compare-workspace__notice" />
            <button type="button" class="compare-workspace__start-button" :disabled="!paperIds.length" @click="startStreaming">开始生成对比报告</button>
            <small v-if="ent.loaded.value && ent.limit('compare') !== null">本月对比：{{ compareQuotaSummary }}</small>
          </template>
        </div>
        <div v-else-if="phase === 'loading'" class="compare-workspace__loading">
          <span class="compare-workspace__spinner"><img :src="bookIcon" alt=""></span><h2>正在建立统一比较口径</h2><p>先读取论文信息，再逐项生成差异与证据。</p>
        </div>
        <div v-else-if="phase === 'error'" class="compare-workspace__error">
          <span><img :src="closeIcon" alt=""></span><h2>本次分析没有完成</h2><p>{{ errorMsg }}</p><button type="button" @click="startStreaming">重新生成</button>
        </div>
        <article v-else class="compare-workspace__markdown" v-html="renderedHtml"></article>
      </main>
      <aside class="compare-workspace__outline" aria-label="对比分析结构">
        <section class="compare-workspace__status-card">
          <div><span>当前状态</span><b :class="`is-${phase}`">{{ phaseLabel }}</b></div><p>{{ phaseDescription }}</p>
          <div class="compare-workspace__progress"><i :style="{ width: phase === 'done' ? '100%' : phase === 'streaming' ? '68%' : phase === 'loading' ? '28%' : phase === 'error' ? '12%' : '8%' }" /></div>
        </section>
        <section>
          <div class="compare-workspace__section-heading"><h2>分析结构</h2><span>6 项</span></div>
          <ul class="compare-workspace__dimension-list"><li v-for="dimension in analysisDimensions" :key="dimension"><img :src="checkIcon" alt=""><span>{{ dimension }}</span></li></ul>
        </section>
        <section class="compare-workspace__output-note"><img :src="documentIcon" alt=""><div><strong>结构化输出</strong><p>报告支持表格、引用、公式与 Markdown，可保存后加入研究课题。</p></div></section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.compare-workspace{display:flex;width:100%;height:100%;min-width:0;min-height:0;flex-direction:column;overflow:hidden;background:var(--color-bg);color:var(--color-text-primary)}
.compare-workspace img{display:block}.compare-workspace button{font:inherit}
.compare-workspace__header{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:18px;padding:17px 22px;border-bottom:1px solid var(--color-border);background:var(--color-bg-card)}
.compare-workspace__heading>span,.compare-workspace__start>span{color:var(--color-tinder-pink);font-size:9px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
.compare-workspace__heading h1{margin:3px 0 2px;font-size:20px;line-height:1.2}.compare-workspace__heading p{margin:0;color:var(--color-text-muted);font-size:10px}
.compare-workspace__header-actions{display:flex;align-items:center;gap:7px}.compare-workspace__header-actions button{display:inline-flex;min-height:32px;align-items:center;justify-content:center;gap:5px;border:1px solid var(--color-border);border-radius:8px;padding:0 10px;background:var(--color-bg-card);color:var(--color-text-secondary);font-size:10px;font-weight:700;cursor:pointer}.compare-workspace__header-actions button:hover{background:var(--color-bg-hover)}.compare-workspace__header-actions button:disabled{cursor:default;opacity:.58}.compare-workspace__header-actions button.is-primary{border-color:var(--color-tinder-pink);background:var(--color-tinder-pink);color:#fff}.compare-workspace__header-actions button.is-danger{color:var(--color-tinder-pink)}.compare-workspace__header-actions img{width:13px}.compare-workspace__header-actions .compare-workspace__close{width:32px;padding:0}
.compare-workspace__body{display:grid;flex:1 1 auto;min-height:0;grid-template-columns:230px minmax(0,1fr) 250px}.compare-workspace__sources,.compare-workspace__outline{min-width:0;min-height:0;overflow-y:auto;background:var(--color-bg-card)}.compare-workspace__sources{padding:18px 14px;border-right:1px solid var(--color-border)}.compare-workspace__outline{padding:18px 16px;border-left:1px solid var(--color-border)}
.compare-workspace__section-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.compare-workspace__section-heading h2{margin:0;font-size:11px}.compare-workspace__section-heading>span{color:var(--color-text-muted);font-size:9px}.compare-workspace__source-list{display:flex;flex-direction:column;gap:7px;margin-top:12px}.compare-workspace__source-card{display:flex;min-width:0;align-items:flex-start;gap:9px;padding:11px;border:1px solid var(--color-border);border-radius:9px;background:var(--color-bg)}.compare-workspace__source-card>b{display:grid;width:23px;height:23px;flex:0 0 auto;place-items:center;border-radius:6px;background:color-mix(in srgb,var(--color-tinder-pink) 9%,var(--color-bg-elevated));color:var(--color-tinder-pink);font-size:8px}.compare-workspace__source-card>div{min-width:0}.compare-workspace__source-card strong,.compare-workspace__source-card small{display:block;overflow:hidden;text-overflow:ellipsis}.compare-workspace__source-card strong{display:-webkit-box;font-size:10px;line-height:1.45;-webkit-box-orient:vertical;-webkit-line-clamp:2}.compare-workspace__source-card small{margin-top:5px;color:var(--color-text-muted);font-size:8px;white-space:nowrap}
.compare-workspace__history-source{display:flex;align-items:center;gap:8px;margin-top:10px;padding:10px;border:1px solid color-mix(in srgb,var(--color-tinder-blue) 22%,var(--color-border));border-radius:9px;background:color-mix(in srgb,var(--color-tinder-blue) 6%,var(--color-bg-card))}.compare-workspace__history-source img{width:16px}.compare-workspace__history-source strong,.compare-workspace__history-source small{display:block}.compare-workspace__history-source strong{font-size:9px}.compare-workspace__history-source small{margin-top:3px;color:var(--color-text-muted);font-size:8px}.compare-workspace__source-meta{display:flex;align-items:center;justify-content:space-between;margin-top:14px;padding-top:12px;border-top:1px solid var(--color-border);font-size:9px}.compare-workspace__source-meta span{color:var(--color-text-muted)}.compare-workspace__source-meta strong{color:var(--color-tinder-blue)}
.compare-workspace__report{min-width:0;min-height:0;overflow-y:auto;background:var(--color-bg-card)}
.compare-workspace__start,.compare-workspace__loading,.compare-workspace__error{display:flex;width:min(100% - 36px,620px);min-height:100%;box-sizing:border-box;align-items:center;justify-content:center;flex-direction:column;margin:0 auto;padding:36px 28px;text-align:center}.compare-workspace__start-icon{display:grid;width:54px;height:54px;place-items:center;margin-bottom:15px;border:1px solid color-mix(in srgb,var(--color-tinder-pink) 28%,var(--color-border));border-radius:16px;background:color-mix(in srgb,var(--color-tinder-pink) 7%,var(--color-bg-card))}.compare-workspace__start-icon img{width:26px}.compare-workspace__start h2,.compare-workspace__loading h2,.compare-workspace__error h2{margin:6px 0 0;font-size:20px}.compare-workspace__start>p,.compare-workspace__loading p,.compare-workspace__error p{max-width:500px;margin:9px 0 0;color:var(--color-text-muted);font-size:11px;line-height:1.7}.compare-workspace__notice{width:100%;margin-top:14px;text-align:left}.compare-workspace__start-button,.compare-workspace__error button{min-height:38px;margin-top:18px;border:0;border-radius:9px;padding:0 20px;background:var(--color-tinder-pink);color:#fff;font-size:11px;font-weight:800;cursor:pointer}.compare-workspace__start-button:disabled{opacity:.45}.compare-workspace__start>small{margin-top:8px;color:var(--color-text-muted);font-size:8px}
.compare-workspace__spinner{display:grid;width:54px;height:54px;place-items:center;border:2px solid color-mix(in srgb,var(--color-tinder-pink) 15%,var(--color-border));border-top-color:var(--color-tinder-pink);border-radius:50%;animation:compare-spin 1s linear infinite}.compare-workspace__spinner img{width:23px;animation:compare-spin 1s linear infinite reverse}.compare-workspace__error>span{display:grid;width:46px;height:46px;place-items:center;border-radius:50%;background:color-mix(in srgb,var(--color-tinder-pink) 9%,var(--color-bg-card))}.compare-workspace__error>span img{width:22px}
.compare-workspace__markdown{width:min(100% - 48px,860px);box-sizing:border-box;margin:0 auto;padding:28px 0 60px}.compare-workspace__markdown :deep(h1){margin:0 0 18px;padding-bottom:12px;border-bottom:1px solid var(--color-border);font-size:22px}.compare-workspace__markdown :deep(h2){margin:28px 0 10px;font-size:16px}.compare-workspace__markdown :deep(h3){margin:22px 0 8px;font-size:13px}.compare-workspace__markdown :deep(p),.compare-workspace__markdown :deep(li){color:var(--color-text-secondary);font-size:12px;line-height:1.8}.compare-workspace__markdown :deep(table){display:block;width:100%;overflow-x:auto;border-collapse:collapse;font-size:11px}.compare-workspace__markdown :deep(th),.compare-workspace__markdown :deep(td){min-width:120px;padding:9px 10px;border:1px solid var(--color-border);text-align:left}.compare-workspace__markdown :deep(th){background:var(--color-bg-elevated)}.compare-workspace__markdown :deep(blockquote){margin:14px 0;padding:4px 0 4px 13px;border-left:3px solid var(--color-tinder-pink);color:var(--color-text-muted)}.compare-workspace__markdown :deep(code){border-radius:4px;padding:2px 4px;background:var(--color-bg-elevated);color:var(--color-tinder-purple)}.compare-workspace__markdown :deep(.katex-display){max-width:100%;overflow-x:auto;overflow-y:hidden;padding:6px 0}
.compare-workspace__outline>section+section{margin-top:18px;padding-top:18px;border-top:1px solid var(--color-border)}.compare-workspace__status-card{padding:12px;border:1px solid var(--color-border);border-radius:10px;background:var(--color-bg)}.compare-workspace__status-card>div:first-child{display:flex;align-items:center;justify-content:space-between;color:var(--color-text-muted);font-size:9px}.compare-workspace__status-card b{border-radius:99px;padding:4px 6px;background:var(--color-bg-elevated);color:var(--color-text-secondary);font-size:8px}.compare-workspace__status-card b.is-streaming,.compare-workspace__status-card b.is-loading{background:#fff2df;color:#a26412}.compare-workspace__status-card b.is-done{background:#e8f8ee;color:#267a48}.compare-workspace__status-card b.is-error{background:#fff0f2;color:#be314b}.compare-workspace__status-card p{margin:10px 0 0;color:var(--color-text-muted);font-size:9px;line-height:1.55}.compare-workspace__progress{height:3px;margin-top:10px;overflow:hidden;border-radius:99px;background:var(--color-bg-elevated)}.compare-workspace__progress i{display:block;height:100%;border-radius:inherit;background:var(--color-tinder-pink);transition:width .3s ease}.compare-workspace__dimension-list{display:flex;flex-direction:column;gap:5px;margin:11px 0 0;padding:0;list-style:none}.compare-workspace__dimension-list li{display:flex;align-items:center;gap:7px;padding:7px 8px;border-radius:7px;background:var(--color-bg);color:var(--color-text-secondary);font-size:9px}.compare-workspace__dimension-list img{width:13px}.compare-workspace__output-note{display:flex;align-items:flex-start;gap:9px}.compare-workspace__output-note>img{width:18px}.compare-workspace__output-note strong{font-size:10px}.compare-workspace__output-note p{margin:5px 0 0;color:var(--color-text-muted);font-size:9px;line-height:1.55}
@keyframes compare-spin{to{transform:rotate(360deg)}}
:global(.dark) .compare-workspace img{filter:invert(1)}
@media(max-width:1199px){.compare-workspace__body{grid-template-columns:210px minmax(0,1fr)}.compare-workspace__outline{display:none}.compare-workspace__header{padding-inline:17px}}
@media(max-width:767px){.compare-workspace{overflow-y:auto}.compare-workspace__header{align-items:flex-start;flex-direction:column;padding:13px 12px}.compare-workspace__heading p{display:none}.compare-workspace__header-actions{width:100%;overflow-x:auto}.compare-workspace__header-actions button{white-space:nowrap}.compare-workspace__header-actions .compare-workspace__close{margin-left:auto;flex:0 0 auto}.compare-workspace__body{display:flex;min-height:auto;flex-direction:column}.compare-workspace__sources{flex:0 0 auto;overflow:visible;padding:12px;border-right:0;border-bottom:1px solid var(--color-border)}.compare-workspace__source-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.compare-workspace__source-card{padding:8px}.compare-workspace__source-card strong{-webkit-line-clamp:1}.compare-workspace__source-meta{display:none}.compare-workspace__report{min-height:520px;overflow:visible}.compare-workspace__start,.compare-workspace__loading,.compare-workspace__error{width:100%;min-height:500px;padding:28px 17px}.compare-workspace__markdown{width:100%;padding:22px 15px 48px}.compare-workspace__markdown :deep(h1){font-size:19px}}
</style>
