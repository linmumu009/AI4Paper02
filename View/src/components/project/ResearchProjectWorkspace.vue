<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type {
  PaperDetailResponse,
  PaperSummary,
  ResearchProject,
  ResearchProjectAsset,
  ResearchProjectSummary,
} from '../../types/paper'
import archiveIcon from '../../assets/heroicons/archive-box.svg'
import beakerIcon from '../../assets/heroicons/beaker.svg'
import bookIcon from '../../assets/heroicons/book-open.svg'
import checkIcon from '../../assets/heroicons/check-circle.svg'
import documentIcon from '../../assets/heroicons/document-text.svg'
import folderIcon from '../../assets/heroicons/folder.svg'
import paperclipIcon from '../../assets/heroicons/paper-clip.svg'
import plusIcon from '../../assets/heroicons/plus.svg'
import scaleIcon from '../../assets/heroicons/scale.svg'
import closeIcon from '../../assets/heroicons/x-mark.svg'
import ImmersivePaperReader from '../workspace/ImmersivePaperReader.vue'

export type ProjectWorkspaceTab = 'workspace' | 'evidence' | 'compare' | 'notes' | 'reports'

const props = withDefaults(defineProps<{
  project: ResearchProject
  projects?: ResearchProjectSummary[]
  paperDetails?: Record<string, PaperDetailResponse>
  candidates?: PaperSummary[]
  candidatesLoading?: boolean
  activeTab?: ProjectWorkspaceTab
}>(), {
  projects: () => [],
  paperDetails: () => ({}),
  candidates: () => [],
  candidatesLoading: false,
  activeTab: 'workspace',
})

const emit = defineEmits<{
  'update:activeTab': [tab: ProjectWorkspaceTab]
  createProject: []
  switchProject: [projectId: number]
  editProject: []
  archiveProject: []
  startResearch: [question?: string]
  startCompare: []
  addPapers: []
  addCandidate: [paper: PaperSummary]
  removeAsset: [asset: ResearchProjectAsset]
  openAsset: [asset: ResearchProjectAsset]
  openPaperPdf: [paperId: string]
  openCandidate: [paper: PaperSummary]
  openResearchSession: [sessionId: number]
}>()

const prompt = ref('')
const showMobileInbox = ref(false)
const immersiveAssetId = ref<string | null>(null)

const tabs: { key: ProjectWorkspaceTab; label: string }[] = [
  { key: 'workspace', label: '工作台' },
  { key: 'evidence', label: '证据库' },
  { key: 'compare', label: '论文对比' },
  { key: 'notes', label: '笔记' },
  { key: 'reports', label: '研究报告' },
]

const paperAssets = computed(() => props.project.assets.filter(asset => asset.asset_type === 'paper'))
const immersiveEntries = computed(() => paperAssets.value.filter(asset => Boolean(props.paperDetails[asset.asset_id])))
const immersiveIndex = computed(() => immersiveEntries.value.findIndex(asset => asset.asset_id === immersiveAssetId.value))
const immersiveAsset = computed(() => immersiveIndex.value >= 0 ? immersiveEntries.value[immersiveIndex.value] : null)
const immersiveDetail = computed(() => immersiveAsset.value ? props.paperDetails[immersiveAsset.value.asset_id] || null : null)
const immersiveRelated = computed(() => immersiveEntries.value
  .filter(asset => asset.asset_id !== immersiveAssetId.value)
  .map(asset => props.paperDetails[asset.asset_id]?.summary)
  .filter((paper): paper is PaperSummary => Boolean(paper))
  .slice(0, 4))
const noteAssets = computed(() => props.project.assets.filter(asset => ['note', 'idea'].includes(asset.asset_type)))
const compareAssets = computed(() => props.project.assets.filter(asset => asset.asset_type === 'compare_result'))
const activeProjectCount = computed(() => Math.max(1, props.projects.filter(item => item.status === 'active').length))
const progress = computed(() => {
  const evidence = Math.min(paperAssets.value.length / 6, 1) * 55
  const analysis = Math.min((compareAssets.value.length + props.project.sessions.length) / 2, 1) * 30
  const notes = Math.min(noteAssets.value.length / 3, 1) * 15
  return Math.max(8, Math.round(evidence + analysis + notes))
})

const evidenceRows = computed(() => paperAssets.value.slice(0, 5).map((asset) => {
  const detail = props.paperDetails[asset.asset_id]
  const summary = detail?.summary
  const blocks = detail?.paper_assets?.blocks
  const method = blocks?.method?.novelty?.[0] || blocks?.method?.text || summary?.['📝重点思路']?.[0] || asset.subtitle
  const evidence = blocks?.results?.main_findings?.[0] || blocks?.evidence_chain?.strongly_supported_claims?.[0] || summary?.['🔎分析总结']?.[0] || '等待补充结构化证据'
  const support = blocks?.limitations?.threats_to_validity?.length ? '中' : detail ? '高' : '待分析'
  return { asset, summary, method, evidence, support }
}))

const synthesis = computed(() => {
  if (props.project.description.trim()) return props.project.description
  const findings = evidenceRows.value
    .map(row => row.evidence)
    .filter(item => item && item !== '等待补充结构化证据')
    .slice(0, 2)
  return findings.length
    ? `${findings.join('；')}。下一步建议围绕边界条件和可复现实验补充证据。`
    : '证据尚在积累。先加入核心论文，再发起深度研究，系统会逐步形成可追溯的综合结论。'
})

function submitResearch() {
  const question = prompt.value.trim()
  emit('startResearch', question || undefined)
}

function paperTitle(paper: PaperSummary) {
  return paper.short_title || paper['📖标题'] || paper.paper_id
}

function candidateReason(paper: PaperSummary) {
  return paper.why_recommended || paper['推荐理由'] || paper['🛎️文章简介']?.['🔸主要贡献'] || '论文元数据与当前课题关键词匹配。'
}

function openPaperAsset(asset: ResearchProjectAsset) {
  if (props.paperDetails[asset.asset_id]) {
    immersiveAssetId.value = asset.asset_id
    return
  }
  emit('openAsset', asset)
}

function closeImmersiveReader() {
  immersiveAssetId.value = null
}

function navigateImmersive(delta: number) {
  const nextIndex = immersiveIndex.value + delta
  const nextAsset = immersiveEntries.value[nextIndex]
  if (nextAsset) immersiveAssetId.value = nextAsset.asset_id
}

function selectRelatedPaper(paperId: string) {
  if (props.paperDetails[paperId]) immersiveAssetId.value = paperId
}

function handleImmersiveKeydown(event: KeyboardEvent) {
  if (!immersiveAsset.value) return
  const target = event.target
  if (target instanceof Element && target.matches('input, textarea, select, [contenteditable="true"]')) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeImmersiveReader()
  } else if (event.key === 'j' || event.key === 'J' || event.key === 'ArrowRight') {
    event.preventDefault()
    navigateImmersive(1)
  } else if (event.key === 'k' || event.key === 'K' || event.key === 'ArrowLeft') {
    event.preventDefault()
    navigateImmersive(-1)
  }
}

watch(() => props.project.id, closeImmersiveReader)
watch(immersiveEntries, (entries) => {
  if (immersiveAssetId.value && !entries.some(asset => asset.asset_id === immersiveAssetId.value)) closeImmersiveReader()
})
onMounted(() => window.addEventListener('keydown', handleImmersiveKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleImmersiveKeydown))
</script>

<template>
  <ImmersivePaperReader
    v-if="immersiveAsset && immersiveDetail"
    :paper="immersiveDetail.summary"
    :detail-override="immersiveDetail"
    :related-papers="immersiveRelated"
    :position="immersiveIndex + 1"
    :total="immersiveEntries.length"
    :can-go-previous="immersiveIndex > 0"
    :can-go-next="immersiveIndex < immersiveEntries.length - 1"
    :can-compare="immersiveEntries.length > 1"
    :show-collection-action="false"
    :show-bookmark-action="false"
    :source-scope="immersiveAsset.source_scope || 'project'"
    :project-context="{ name: project.name, objective: project.objective, paperCount: paperAssets.length }"
    return-label="返回研究项目"
    decision-mode="project"
    @exit="closeImmersiveReader"
    @previous="navigateImmersive(-1)"
    @next="navigateImmersive(1)"
    @skip="navigateImmersive(1)"
    @compare="emit('startCompare')"
    @open-detail="emit('openAsset', immersiveAsset)"
    @open-pdf="emit('openPaperPdf', immersiveAsset.asset_id)"
    @start-research="emit('startResearch')"
    @select-related="selectRelatedPaper"
  />
  <div v-else class="project-workspace">
    <aside class="project-workspace__rail" aria-label="课题导航">
      <div class="project-workspace__rail-head">
        <div>
          <span class="project-workspace__eyebrow">研究空间</span>
          <strong>课题</strong>
        </div>
        <button class="icon-button" type="button" title="新建课题" @click="emit('createProject')">
          <img :src="plusIcon" alt="">
        </button>
      </div>
      <button
        v-for="item in projects.filter(projectItem => projectItem.status === 'active')"
        :key="item.id"
        type="button"
        class="project-workspace__project-link"
        :class="{ 'is-active': item.id === project.id }"
        @click="emit('switchProject', item.id)"
      >
        <img :src="folderIcon" alt="">
        <span><strong>{{ item.name }}</strong><small>{{ item.asset_count }} 项资产</small></span>
      </button>
      <p v-if="projects.length === 0" class="project-workspace__empty-nav">当前课题</p>
      <div class="project-workspace__rail-section">
        <span class="project-workspace__eyebrow">课题资产</span>
        <button type="button" @click="emit('update:activeTab', 'evidence')"><img :src="bookIcon" alt="">论文 <b>{{ paperAssets.length }}</b></button>
        <button type="button" @click="emit('update:activeTab', 'notes')"><img :src="documentIcon" alt="">笔记 <b>{{ noteAssets.length }}</b></button>
        <button type="button" @click="emit('update:activeTab', 'compare')"><img :src="scaleIcon" alt="">对比 <b>{{ compareAssets.length }}</b></button>
        <button type="button" @click="emit('update:activeTab', 'reports')"><img :src="beakerIcon" alt="">研究 <b>{{ project.sessions.length }}</b></button>
      </div>
      <div class="project-workspace__rail-footer">
        <img :src="archiveIcon" alt="">
        <span>{{ activeProjectCount }} 个进行中课题</span>
      </div>
    </aside>

    <main class="project-workspace__main">
      <header class="project-workspace__header">
        <div class="project-workspace__heading-row">
          <div class="project-workspace__title">
            <span class="project-workspace__status"><i />进行中</span>
            <h1>{{ project.name }}</h1>
            <p>{{ project.objective || '尚未设置核心研究问题。' }}</p>
          </div>
          <div class="project-workspace__header-actions">
            <button class="secondary-button" type="button" @click="emit('editProject')">编辑</button>
            <button class="secondary-button" type="button" @click="emit('archiveProject')">归档</button>
            <button class="primary-button" type="button" @click="emit('startResearch')"><img :src="beakerIcon" alt="">深度研究</button>
          </div>
        </div>
        <div class="project-workspace__progress">
          <div><span>研究进度</span><b>{{ progress }}%</b></div>
          <div class="project-workspace__progress-track"><i :style="{ width: `${progress}%` }" /></div>
          <small>基于论文、对比、笔记与研究报告自动估算</small>
        </div>
      </header>

      <nav class="project-workspace__tabs" aria-label="课题视图">
        <button v-for="tab in tabs" :key="tab.key" type="button" :class="{ 'is-active': activeTab === tab.key }" @click="emit('update:activeTab', tab.key)">{{ tab.label }}</button>
        <button class="project-workspace__mobile-inbox" type="button" @click="showMobileInbox = !showMobileInbox">候选论文 {{ candidates.length }}</button>
      </nav>

      <div class="project-workspace__content">
        <template v-if="activeTab === 'workspace' || activeTab === 'evidence'">
          <section class="project-workspace__question">
            <span class="project-workspace__section-label">核心研究问题</span>
            <h2>{{ project.objective || '这个课题要回答什么问题？' }}</h2>
            <button type="button" @click="emit('editProject')">编辑问题</button>
          </section>

          <section class="project-workspace__section">
            <div class="project-workspace__section-head">
              <div><span class="project-workspace__section-label">Evidence matrix</span><h2>证据矩阵</h2></div>
              <button class="secondary-button" type="button" @click="emit('addPapers')"><img :src="plusIcon" alt="">添加论文</button>
            </div>
            <div v-if="evidenceRows.length" class="project-workspace__evidence-table">
              <div class="project-workspace__evidence-header"><span>论文</span><span>关键方法</span><span>核心证据</span><span>支持度</span></div>
              <article v-for="row in evidenceRows" :key="row.asset.id" class="project-workspace__evidence-row" @click="openPaperAsset(row.asset)">
                <div><strong>{{ row.summary?.short_title || row.asset.title }}</strong><small>{{ row.summary?.authors?.slice(0, 2).join('、') || row.asset.subtitle }}</small></div>
                <p>{{ row.method }}</p><p>{{ row.evidence }}</p>
                <span class="project-workspace__support" :class="`is-${row.support}`">{{ row.support }}</span>
                <button type="button" title="从课题移除" @click.stop="emit('removeAsset', row.asset)">移除</button>
              </article>
            </div>
            <div v-else class="project-workspace__empty">
              <img :src="bookIcon" alt=""><strong>还没有课题论文</strong><p>加入论文后，这里会自动汇总方法、证据与支持度。</p>
              <button class="primary-button" type="button" @click="emit('addPapers')">选择论文</button>
            </div>
          </section>

          <section class="project-workspace__synthesis">
            <div class="project-workspace__synthesis-icon"><img :src="checkIcon" alt=""></div>
            <div><span class="project-workspace__section-label">当前综合结论</span><h2>阶段性认识</h2><p>{{ synthesis }}</p></div>
            <button type="button" @click="emit('startResearch')">继续验证</button>
          </section>
        </template>

        <section v-else-if="activeTab === 'compare'" class="project-workspace__section project-workspace__asset-view">
          <div class="project-workspace__section-head"><div><span class="project-workspace__section-label">Compare</span><h2>论文对比</h2></div><button class="primary-button" type="button" @click="emit('startCompare')">新建对比</button></div>
          <button v-for="asset in compareAssets" :key="asset.id" class="project-workspace__asset-row" type="button" @click="emit('openAsset', asset)"><img :src="scaleIcon" alt=""><span><strong>{{ asset.title }}</strong><small>{{ asset.subtitle }}</small></span></button>
          <div v-if="!compareAssets.length" class="project-workspace__empty"><img :src="scaleIcon" alt=""><strong>还没有对比结果</strong><p>从课题论文发起对比，结果会沉淀在这里。</p></div>
        </section>

        <section v-else-if="activeTab === 'notes'" class="project-workspace__section project-workspace__asset-view">
          <div class="project-workspace__section-head"><div><span class="project-workspace__section-label">Notes</span><h2>研究笔记与灵感</h2></div></div>
          <button v-for="asset in noteAssets" :key="asset.id" class="project-workspace__asset-row" type="button" @click="emit('openAsset', asset)"><img :src="documentIcon" alt=""><span><strong>{{ asset.title }}</strong><small>{{ asset.subtitle }}</small></span></button>
          <div v-if="!noteAssets.length" class="project-workspace__empty"><img :src="documentIcon" alt=""><strong>还没有研究笔记</strong><p>论文笔记和研究灵感会自动归集到课题中。</p></div>
        </section>

        <section v-else class="project-workspace__section project-workspace__asset-view">
          <div class="project-workspace__section-head"><div><span class="project-workspace__section-label">Reports</span><h2>深度研究报告</h2></div><button class="primary-button" type="button" @click="emit('startResearch')">发起研究</button></div>
          <button v-for="session in project.sessions" :key="session.id" class="project-workspace__asset-row" type="button" @click="emit('openResearchSession', session.id)"><img :src="beakerIcon" alt=""><span><strong>{{ session.question }}</strong><small>{{ session.paper_ids.length }} 篇论文 · {{ session.status }}</small></span></button>
          <div v-if="!project.sessions.length" class="project-workspace__empty"><img :src="beakerIcon" alt=""><strong>还没有深度研究报告</strong><p>以核心问题为起点，让 AI 整合课题内的证据。</p></div>
        </section>

        <form class="project-workspace__composer" @submit.prevent="submitResearch">
          <img :src="paperclipIcon" alt="">
          <textarea v-model="prompt" rows="1" :placeholder="project.objective || '围绕当前课题提出一个研究问题…'" @keydown.ctrl.enter.prevent="submitResearch" />
          <button type="submit"><img :src="beakerIcon" alt="">开始研究</button>
        </form>
      </div>
    </main>

    <button v-if="showMobileInbox" class="project-workspace__inbox-backdrop" type="button" aria-label="关闭候选论文遮罩" @click="showMobileInbox = false" />
    <aside class="project-workspace__inbox" :class="{ 'is-mobile-open': showMobileInbox }">
      <div class="project-workspace__inbox-head">
        <div><span class="project-workspace__eyebrow">Project inbox</span><h2>候选论文</h2></div>
        <div class="project-workspace__inbox-actions"><b>{{ candidates.length }}</b><button type="button" aria-label="关闭候选论文" @click="showMobileInbox = false"><img :src="closeIcon" alt=""></button></div>
      </div>
      <p>按课题关键词与推荐相关度，从今日论文中筛选。</p>
      <div v-if="candidatesLoading" class="project-workspace__candidate-loading">正在匹配候选论文…</div>
      <article v-for="paper in candidates" :key="paper.paper_id" class="project-workspace__candidate">
        <button type="button" @click="emit('openCandidate', paper)"><span>{{ paper.institution || '新论文' }}</span><strong>{{ paperTitle(paper) }}</strong><p>{{ candidateReason(paper) }}</p></button>
        <button type="button" title="加入课题" @click="emit('addCandidate', paper)"><img :src="plusIcon" alt="">加入</button>
      </article>
      <div v-if="!candidatesLoading && !candidates.length" class="project-workspace__candidate-empty">今天暂时没有匹配的候选论文。</div>
      <div class="project-workspace__recent">
        <span class="project-workspace__eyebrow">最近证据</span>
        <button v-for="asset in paperAssets.slice(0, 3)" :key="asset.id" type="button" @click="openPaperAsset(asset)"><i /><span><strong>{{ asset.title }}</strong><small>{{ asset.subtitle }}</small></span></button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.project-workspace{--ink:#18202c;--muted:#6f7886;--line:#e4e7eb;--soft:#f6f7f8;--accent:#ff385c;display:grid;grid-template-columns:210px minmax(540px,1fr) 300px;height:100%;min-height:0;background:#fff;color:var(--ink)}
button{font:inherit}.project-workspace__rail,.project-workspace__inbox{min-width:0;background:#fafafa}.project-workspace__rail{display:flex;flex-direction:column;border-right:1px solid var(--line);padding:26px 14px 18px;overflow:auto}.project-workspace__rail-head,.project-workspace__inbox-head,.project-workspace__heading-row,.project-workspace__section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.project-workspace__rail-head strong{display:block;margin-top:4px;font-size:20px}.project-workspace__eyebrow,.project-workspace__section-label{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#9aa1aa}.icon-button{display:grid;width:32px;height:32px;place-items:center;border:1px solid var(--line);border-radius:9px;background:#fff}.icon-button img,.secondary-button img,.primary-button img{width:16px;height:16px}.project-workspace img{display:block}
.project-workspace__project-link{display:flex;gap:10px;width:100%;margin-top:14px;padding:11px;border:0;border-radius:10px;background:transparent;text-align:left;color:var(--ink)}.project-workspace__project-link:hover,.project-workspace__project-link.is-active{background:#fff;box-shadow:0 2px 10px rgba(24,32,44,.07)}.project-workspace__project-link.is-active{box-shadow:inset 3px 0 var(--accent),0 2px 10px rgba(24,32,44,.07)}.project-workspace__project-link>img{width:18px;margin-top:2px}.project-workspace__project-link span{min-width:0}.project-workspace__project-link strong,.project-workspace__project-link small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.project-workspace__project-link strong{font-size:12px}.project-workspace__project-link small{margin-top:3px;font-size:10px;color:var(--muted)}.project-workspace__empty-nav{margin:18px 10px 0;font-size:12px;color:var(--muted)}
.project-workspace__rail-section{margin-top:28px;padding-top:20px;border-top:1px solid var(--line)}.project-workspace__rail-section>span{display:block;padding:0 10px 7px}.project-workspace__rail-section button{display:flex;align-items:center;width:100%;gap:9px;padding:9px 10px;border:0;border-radius:8px;background:transparent;color:#586170;font-size:12px;text-align:left}.project-workspace__rail-section button:hover{background:#fff;color:var(--ink)}.project-workspace__rail-section img{width:16px}.project-workspace__rail-section b{margin-left:auto;font-size:10px;color:#9aa1aa}.project-workspace__rail-footer{display:flex;align-items:center;gap:8px;margin-top:auto;padding:18px 10px 0;color:#8c949f;font-size:10px}.project-workspace__rail-footer img{width:15px}
.project-workspace__main{min-width:0;overflow:auto;background:#fff}.project-workspace__header{padding:30px 34px 20px;border-bottom:1px solid var(--line)}.project-workspace__status{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:99px;background:#ecf9f0;color:#26804a;font-size:10px;font-weight:700}.project-workspace__status i{width:6px;height:6px;border-radius:50%;background:#32b461}.project-workspace__title h1{margin:11px 0 7px;font-size:26px;line-height:1.2;letter-spacing:-.03em}.project-workspace__title p{max-width:680px;margin:0;color:var(--muted);font-size:13px;line-height:1.6}.project-workspace__header-actions{display:flex;gap:8px}.secondary-button,.primary-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;border-radius:9px;padding:9px 12px;font-size:11px;font-weight:700}.secondary-button{border:1px solid var(--line);background:#fff;color:#596171}.primary-button{border:1px solid var(--accent);background:var(--accent);color:#fff;box-shadow:0 4px 12px rgba(255,56,92,.18)}.primary-button img{filter:brightness(0) invert(1)}.project-workspace__progress{max-width:520px;margin-top:22px}.project-workspace__progress>div:first-child{display:flex;justify-content:space-between;font-size:10px;color:var(--muted)}.project-workspace__progress b{color:var(--ink)}.project-workspace__progress-track{height:5px;margin-top:7px;border-radius:99px;background:#eef0f2;overflow:hidden}.project-workspace__progress-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#ff385c,#ff7b6b)}.project-workspace__progress small{display:block;margin-top:7px;color:#a0a6ae;font-size:9px}
.project-workspace__tabs{position:sticky;top:0;z-index:3;display:flex;gap:24px;padding:0 34px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.96);backdrop-filter:blur(12px)}.project-workspace__tabs button{position:relative;padding:15px 0 13px;border:0;background:transparent;color:#7a828e;font-size:11px;font-weight:700;white-space:nowrap}.project-workspace__tabs button.is-active{color:var(--ink)}.project-workspace__tabs button.is-active:after{position:absolute;right:0;bottom:-1px;left:0;height:2px;background:var(--accent);content:''}.project-workspace__mobile-inbox{display:none;margin-left:auto!important;color:var(--accent)!important}.project-workspace__content{max-width:1020px;margin:0 auto;padding:26px 34px 120px}.project-workspace__question{position:relative;padding:20px 22px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:11px;background:#fff}.project-workspace__question h2{margin:7px 70px 0 0;font-size:16px;line-height:1.55}.project-workspace__question button{position:absolute;right:18px;top:18px;border:0;background:transparent;color:var(--accent);font-size:10px;font-weight:700}
.project-workspace__section{margin-top:22px}.project-workspace__section-head{align-items:center}.project-workspace__section-head h2,.project-workspace__synthesis h2{margin:3px 0 0;font-size:17px}.project-workspace__evidence-table{margin-top:13px;border:1px solid var(--line);border-radius:11px;overflow:hidden}.project-workspace__evidence-header,.project-workspace__evidence-row{display:grid;grid-template-columns:minmax(150px,1.1fr) minmax(130px,1fr) minmax(150px,1.2fr) 52px;gap:14px;align-items:center}.project-workspace__evidence-header{padding:9px 14px;background:var(--soft);color:#8e96a1;font-size:9px;font-weight:800;text-transform:uppercase}.project-workspace__evidence-row{position:relative;padding:14px;border-top:1px solid var(--line);cursor:pointer}.project-workspace__evidence-row:hover{background:#fcfcfd}.project-workspace__evidence-row strong,.project-workspace__evidence-row small{display:block}.project-workspace__evidence-row strong{font-size:11px;line-height:1.4}.project-workspace__evidence-row small{margin-top:4px;color:#959ca5;font-size:9px}.project-workspace__evidence-row p{display:-webkit-box;margin:0;overflow:hidden;color:#626b78;font-size:10px;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:3}.project-workspace__support{justify-self:start;padding:4px 7px;border-radius:99px;background:#eef0f2;color:#68717d;font-size:9px;font-weight:800}.project-workspace__support.is-高{background:#e7f8ed;color:#28804b}.project-workspace__support.is-中{background:#fff4df;color:#9a6517}.project-workspace__evidence-row>button{position:absolute;right:8px;bottom:4px;border:0;background:transparent;color:#a1a6ad;font-size:8px;opacity:0}.project-workspace__evidence-row:hover>button{opacity:1}
.project-workspace__synthesis{display:flex;align-items:flex-start;gap:14px;margin-top:20px;padding:18px 20px;border-radius:12px;background:#18202c;color:#fff}.project-workspace__synthesis-icon{display:grid;flex:0 0 34px;height:34px;place-items:center;border-radius:9px;background:#293342}.project-workspace__synthesis-icon img{width:18px;filter:brightness(0) invert(1)}.project-workspace__synthesis>div:nth-child(2){flex:1}.project-workspace__synthesis p{margin:9px 0 0;color:#c7cdd5;font-size:11px;line-height:1.65}.project-workspace__synthesis button{border:0;background:transparent;color:#ff8da1;font-size:10px;font-weight:800}.project-workspace__empty{display:flex;flex-direction:column;align-items:center;margin-top:13px;padding:44px 20px;border:1px dashed #d9dde2;border-radius:11px;text-align:center}.project-workspace__empty>img{width:26px;opacity:.42}.project-workspace__empty strong{margin-top:12px;font-size:13px}.project-workspace__empty p{margin:6px 0 14px;color:var(--muted);font-size:10px}.project-workspace__asset-view{min-height:420px}.project-workspace__asset-row{display:flex;width:100%;align-items:center;gap:12px;margin-top:9px;padding:14px;border:1px solid var(--line);border-radius:10px;background:#fff;text-align:left}.project-workspace__asset-row:hover{border-color:#cfd4da}.project-workspace__asset-row>img{width:20px}.project-workspace__asset-row span{min-width:0}.project-workspace__asset-row strong,.project-workspace__asset-row small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.project-workspace__asset-row strong{font-size:12px}.project-workspace__asset-row small{margin-top:4px;color:var(--muted);font-size:10px}
.project-workspace__composer{position:sticky;bottom:18px;z-index:4;display:flex;align-items:center;gap:10px;margin-top:30px;padding:9px 9px 9px 14px;border:1px solid #d9dde2;border-radius:13px;background:rgba(255,255,255,.97);box-shadow:0 12px 36px rgba(24,32,44,.14);backdrop-filter:blur(12px)}.project-workspace__composer>img{width:17px;opacity:.55}.project-workspace__composer textarea{min-width:0;flex:1;resize:none;border:0;outline:0;background:transparent;color:var(--ink);font:inherit;font-size:11px;line-height:1.5}.project-workspace__composer button{display:flex;align-items:center;gap:6px;padding:9px 12px;border:0;border-radius:9px;background:#18202c;color:#fff;font-size:10px;font-weight:800}.project-workspace__composer button img{width:14px;filter:brightness(0) invert(1)}
.project-workspace__inbox{border-left:1px solid var(--line);padding:28px 18px;overflow:auto}.project-workspace__inbox-head{align-items:center}.project-workspace__inbox-head h2{margin:4px 0 0;font-size:17px}.project-workspace__inbox-actions{display:flex;align-items:center;gap:8px}.project-workspace__inbox-actions>b{display:grid;width:27px;height:27px;place-items:center;border-radius:50%;background:#fff0f3;color:var(--accent);font-size:10px}.project-workspace__inbox-actions>button{display:none;width:30px;height:30px;place-items:center;border:1px solid var(--line);border-radius:8px;background:#fff}.project-workspace__inbox-actions img{width:16px}.project-workspace__inbox-backdrop{display:none}.project-workspace__inbox>p{margin:9px 0 18px;color:#939aa4;font-size:9px;line-height:1.5}.project-workspace__candidate{padding:13px 0;border-top:1px solid var(--line)}.project-workspace__candidate>button:first-child{width:100%;padding:0;border:0;background:transparent;text-align:left}.project-workspace__candidate span{color:var(--accent);font-size:8px;font-weight:800;text-transform:uppercase}.project-workspace__candidate strong{display:block;margin-top:5px;font-size:11px;line-height:1.45}.project-workspace__candidate p{display:-webkit-box;margin:6px 0 0;overflow:hidden;color:#747d89;font-size:9px;line-height:1.55;-webkit-box-orient:vertical;-webkit-line-clamp:3}.project-workspace__candidate>button:last-child{display:flex;align-items:center;gap:4px;margin-top:9px;padding:5px 7px;border:1px solid #f2cbd2;border-radius:7px;background:#fff;color:var(--accent);font-size:8px;font-weight:800}.project-workspace__candidate>button:last-child img{width:11px}.project-workspace__candidate-loading,.project-workspace__candidate-empty{padding:24px 4px;color:#959ca5;font-size:10px;text-align:center}.project-workspace__recent{margin-top:25px;padding-top:18px;border-top:1px solid var(--line)}.project-workspace__recent>span{display:block;margin-bottom:8px}.project-workspace__recent button{display:flex;width:100%;align-items:flex-start;gap:8px;padding:8px 0;border:0;background:transparent;text-align:left}.project-workspace__recent i{flex:0 0 6px;height:6px;margin-top:4px;border-radius:50%;background:#38ad67}.project-workspace__recent strong,.project-workspace__recent small{display:block}.project-workspace__recent strong{font-size:9px;line-height:1.35}.project-workspace__recent small{margin-top:3px;color:#999fa7;font-size:8px}
@media(max-width:1199px){.project-workspace{grid-template-columns:190px minmax(0,1fr)}.project-workspace__inbox-backdrop{position:fixed;z-index:19;inset:0;display:block;border:0;background:rgba(24,32,44,.18)}.project-workspace__inbox{position:fixed;z-index:20;top:0;right:0;bottom:0;width:310px;transform:translateX(105%);box-shadow:-18px 0 40px rgba(24,32,44,.16);transition:transform .2s ease}.project-workspace__inbox.is-mobile-open{transform:translateX(0)}.project-workspace__inbox-actions>button{display:grid}.project-workspace__mobile-inbox{display:block}}
@media(max-width:767px){.project-workspace{display:block;overflow:auto}.project-workspace__rail{display:none}.project-workspace__main{overflow:visible}.project-workspace__header{padding:20px 18px 16px}.project-workspace__heading-row{display:block}.project-workspace__title h1{font-size:22px}.project-workspace__header-actions{margin-top:16px}.project-workspace__header-actions .primary-button{flex:1}.project-workspace__tabs{gap:18px;padding:0 18px;overflow-x:auto}.project-workspace__content{padding:20px 14px 100px}.project-workspace__question h2{margin-right:0;padding-top:15px;font-size:14px}.project-workspace__question button{top:16px}.project-workspace__evidence-header{display:none}.project-workspace__evidence-row{grid-template-columns:1fr auto;gap:8px}.project-workspace__evidence-row>p{grid-column:1/-1}.project-workspace__support{grid-column:2;grid-row:1}.project-workspace__synthesis{flex-wrap:wrap}.project-workspace__synthesis>button{margin-left:48px}.project-workspace__composer{bottom:10px}.project-workspace__composer button{font-size:0}.project-workspace__composer button img{width:16px}.project-workspace__inbox{width:min(88vw,330px)}}
</style>
