<script setup lang="ts">
import { computed } from 'vue'
import ResearchPanel from '../ResearchPanel.vue'
import beakerIcon from '../../assets/heroicons/beaker.svg'
import bookIcon from '../../assets/heroicons/book-open.svg'
import checkIcon from '../../assets/heroicons/check-circle.svg'
import documentIcon from '../../assets/heroicons/document-text.svg'
import folderIcon from '../../assets/heroicons/folder.svg'

const props = withDefaults(defineProps<{
  paperIds: string[]
  paperTitles?: Record<string, string>
  scope?: string
  initialSessionId?: number | null
  projectId?: number | null
  initialQuestion?: string
}>(), { scope: 'kb', initialSessionId: null, projectId: null, initialQuestion: '' })

const emit = defineEmits<{
  close: []
  removePaper: [paperId: string]
  saveToLibrary: [sessionId: number]
}>()

const scopeLabel = computed(() => ({
  kb: '知识库', inspiration: '灵感论文', digest: '今日论文', mypapers: '我的论文',
})[props.scope] || '跨库资料')

const stages = [
  { key: 'R1', title: '相关性排序', desc: '判断问题与每篇论文的关系' },
  { key: 'R2', title: '摘要分析', desc: '归纳证据、结论与研究缺口' },
  { key: 'R3', title: '全文精读', desc: '按需阅读全文并形成报告' },
]

function titleFor(paperId: string) {
  return props.paperTitles?.[paperId] || paperId
}
</script>

<template>
  <section class="research-workspace" aria-label="深度研究工作区">
    <aside class="research-workspace__sources" aria-label="研究资料集">
      <div class="research-workspace__heading"><span>Research corpus</span><h1>研究资料集</h1><p>{{ paperIds.length }} 篇论文 · {{ scopeLabel }}</p></div>
      <div class="research-workspace__source-list">
        <article v-for="(paperId, index) in paperIds" :key="paperId">
          <b>{{ String(index + 1).padStart(2, '0') }}</b>
          <div><strong>{{ titleFor(paperId) }}</strong><small>{{ paperId }}</small></div>
        </article>
      </div>
      <div v-if="!paperIds.length" class="research-workspace__empty-source"><img :src="bookIcon" alt=""><p>还没有研究资料</p><small>在中间选择知识库论文后开始。</small></div>
      <section class="research-workspace__context-card">
        <img :src="folderIcon" alt=""><div><strong>{{ projectId ? '课题研究' : '独立研究' }}</strong><p>{{ projectId ? `结果将归入课题 #${projectId}` : '完成后可保存到研究库或加入课题' }}</p></div>
      </section>
    </aside>

    <main class="research-workspace__main">
      <ResearchPanel
        :paper-ids="paperIds"
        :paper-titles="paperTitles"
        :scope="scope"
        :initial-session-id="initialSessionId"
        :project-id="projectId"
        :initial-question="initialQuestion"
        @close="emit('close')"
        @remove-paper="emit('removePaper', $event)"
        @save-to-library="emit('saveToLibrary', $event)"
      />
    </main>

    <aside class="research-workspace__plan" aria-label="研究执行计划">
      <div class="research-workspace__heading"><span>Research plan</span><h2>执行计划</h2><p>系统按证据需求逐层加深阅读。</p></div>
      <ol>
        <li v-for="stage in stages" :key="stage.key">
          <b>{{ stage.key }}</b><div><strong>{{ stage.title }}</strong><small>{{ stage.desc }}</small></div><img :src="checkIcon" alt="">
        </li>
      </ol>
      <section class="research-workspace__output-card">
        <img :src="documentIcon" alt=""><div><strong>最终产物</strong><p>带来源依据的结构化研究报告，可继续追问、复制、下载或保存。</p></div>
      </section>
      <section class="research-workspace__principle">
        <img :src="beakerIcon" alt=""><p>只有摘要不足以回答问题时，流程才会进入全文精读。</p>
      </section>
    </aside>
  </section>
</template>

<style scoped>
.research-workspace{display:grid;width:100%;height:100%;min-width:0;min-height:0;grid-template-columns:230px minmax(0,1fr) 250px;overflow:hidden;background:var(--color-bg);color:var(--color-text-primary)}.research-workspace img{display:block}.research-workspace__sources,.research-workspace__plan{min-width:0;min-height:0;overflow-y:auto;background:var(--color-bg-card)}.research-workspace__sources{padding:19px 14px;border-right:1px solid var(--color-border)}.research-workspace__plan{padding:19px 16px;border-left:1px solid var(--color-border)}.research-workspace__main{min-width:0;min-height:0;overflow:hidden;background:var(--color-bg-card)}.research-workspace__heading>span{color:var(--color-tinder-pink);font-size:8px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}.research-workspace__heading h1,.research-workspace__heading h2{margin:4px 0 3px;font-size:15px}.research-workspace__heading p{margin:0;color:var(--color-text-muted);font-size:9px;line-height:1.5}.research-workspace__source-list{display:flex;flex-direction:column;gap:7px;margin-top:14px}.research-workspace__source-list article{display:flex;min-width:0;align-items:flex-start;gap:9px;padding:10px;border:1px solid var(--color-border);border-radius:9px;background:var(--color-bg)}.research-workspace__source-list article>b{display:grid;width:23px;height:23px;flex:0 0 auto;place-items:center;border-radius:6px;background:color-mix(in srgb,var(--color-tinder-pink) 9%,var(--color-bg-elevated));color:var(--color-tinder-pink);font-size:8px}.research-workspace__source-list article>div{min-width:0}.research-workspace__source-list strong,.research-workspace__source-list small{display:block;overflow:hidden;text-overflow:ellipsis}.research-workspace__source-list strong{display:-webkit-box;font-size:10px;line-height:1.45;-webkit-box-orient:vertical;-webkit-line-clamp:2}.research-workspace__source-list small{margin-top:5px;color:var(--color-text-muted);font-size:8px;white-space:nowrap}.research-workspace__empty-source{display:flex;align-items:center;flex-direction:column;margin-top:28px;text-align:center}.research-workspace__empty-source img{width:25px;opacity:.45}.research-workspace__empty-source p{margin:9px 0 0;font-size:10px}.research-workspace__empty-source small{margin-top:4px;color:var(--color-text-muted);font-size:8px}.research-workspace__context-card,.research-workspace__output-card,.research-workspace__principle{display:flex;align-items:flex-start;gap:9px;padding:11px;border:1px solid var(--color-border);border-radius:9px;background:var(--color-bg)}.research-workspace__context-card{margin-top:14px}.research-workspace__context-card img,.research-workspace__output-card img,.research-workspace__principle img{width:17px}.research-workspace__context-card strong,.research-workspace__output-card strong{font-size:9px}.research-workspace__context-card p,.research-workspace__output-card p,.research-workspace__principle p{margin:4px 0 0;color:var(--color-text-muted);font-size:8px;line-height:1.55}.research-workspace__plan ol{display:flex;flex-direction:column;gap:6px;margin:15px 0 0;padding:0;list-style:none}.research-workspace__plan li{display:grid;grid-template-columns:30px minmax(0,1fr) 14px;align-items:center;gap:8px;padding:10px 8px;border-radius:8px;background:var(--color-bg)}.research-workspace__plan li>b{display:grid;width:28px;height:28px;place-items:center;border-radius:8px;background:color-mix(in srgb,var(--color-tinder-pink) 8%,var(--color-bg-card));color:var(--color-tinder-pink);font-size:8px}.research-workspace__plan li strong,.research-workspace__plan li small{display:block}.research-workspace__plan li strong{font-size:9px}.research-workspace__plan li small{margin-top:3px;color:var(--color-text-muted);font-size:8px;line-height:1.4}.research-workspace__plan li>img{width:13px}.research-workspace__output-card{margin-top:18px;padding-top:13px}.research-workspace__principle{margin-top:8px;border-color:color-mix(in srgb,var(--color-tinder-blue) 20%,var(--color-border));background:color-mix(in srgb,var(--color-tinder-blue) 5%,var(--color-bg-card))}.research-workspace__principle p{margin:0}:global(.dark) .research-workspace img{filter:invert(1)}
@media(max-width:1199px){.research-workspace{grid-template-columns:210px minmax(0,1fr)}.research-workspace__plan{display:none}}
@media(max-width:767px){.research-workspace{display:flex;overflow-y:auto;flex-direction:column}.research-workspace__sources{flex:0 0 auto;overflow:visible;padding:11px 12px;border-right:0;border-bottom:1px solid var(--color-border)}.research-workspace__heading>span,.research-workspace__heading>h1,.research-workspace__heading>p,.research-workspace__context-card{display:none}.research-workspace__source-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:0}.research-workspace__source-list article{padding:8px}.research-workspace__source-list strong{-webkit-line-clamp:1}.research-workspace__main{min-height:600px;overflow:visible}}
</style>
