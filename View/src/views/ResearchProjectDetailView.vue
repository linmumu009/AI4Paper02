<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  addResearchProjectAsset, archiveResearchProject, fetchDates, fetchDigest,
  fetchPaperDetail, fetchResearchProject, fetchResearchProjects,
  removeResearchProjectAsset, updateResearchProject,
} from '../api'
import type { PaperDetailResponse, PaperSummary, ResearchProject, ResearchProjectAsset, ResearchProjectSummary } from '../types/paper'
import PaperPickerDialog from '../components/PaperPickerDialog.vue'
import ResearchProjectWorkspace, { type ProjectWorkspaceTab } from '../components/project/ResearchProjectWorkspace.vue'
import { resolvePaperPdfUrl } from '../composables/usePdfUrl'
import { rankProjectCandidates } from '../composables/useProjectWorkspace'
import { openExternal } from '../utils/openExternal'

const route = useRoute()
const router = useRouter()
const project = ref<ResearchProject | null>(null)
const projects = ref<ResearchProjectSummary[]>([])
const paperDetails = ref<Record<string, PaperDetailResponse>>({})
const candidates = ref<PaperSummary[]>([])
const candidatesLoading = ref(false)
const loading = ref(true)
const error = ref('')
const showEdit = ref(false)
const showPaperPicker = ref(false)
const saving = ref(false)
const activeTab = ref<ProjectWorkspaceTab>('workspace')
const editForm = ref({ name: '', objective: '', description: '' })
const projectId = computed(() => Number(route.params.id))

async function loadEvidenceDetails(current: ResearchProject) {
  const ids = current.paper_ids.slice(0, 12)
  const settled = await Promise.allSettled(ids.map(id => fetchPaperDetail(id)))
  const next: Record<string, PaperDetailResponse> = {}
  settled.forEach((result, index) => {
    if (result.status === 'fulfilled') next[ids[index]] = result.value
  })
  if (project.value?.id === current.id) paperDetails.value = next
}

async function loadCandidates(current: ResearchProject) {
  candidatesLoading.value = true
  try {
    const dates = await fetchDates()
    const date = dates.dates[0]
    if (!date) return void (candidates.value = [])
    const digest = await fetchDigest(date)
    if (project.value?.id === current.id) candidates.value = rankProjectCandidates(current, digest.papers, 6)
  } catch {
    candidates.value = []
  } finally {
    candidatesLoading.value = false
  }
}

async function load() {
  if (!Number.isFinite(projectId.value)) return
  loading.value = true
  error.value = ''
  try {
    const [current, allProjects] = await Promise.all([fetchResearchProject(projectId.value), fetchResearchProjects(false)])
    project.value = current
    projects.value = allProjects
    editForm.value = { name: current.name, objective: current.objective, description: current.description }
    void loadEvidenceDetails(current)
    void loadCandidates(current)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '课题加载失败'
  } finally {
    loading.value = false
  }
}

async function saveProject() {
  if (!project.value || !editForm.value.name.trim() || saving.value) return
  saving.value = true
  try {
    await updateResearchProject(project.value.id, {
      name: editForm.value.name.trim(), objective: editForm.value.objective.trim(), description: editForm.value.description.trim(),
    })
    showEdit.value = false
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '课题保存失败'
  } finally {
    saving.value = false
  }
}

async function addPapers(paperIds: string[]) {
  if (!project.value) return
  showPaperPicker.value = false
  try {
    const existing = new Set(project.value.paper_ids)
    await Promise.all(paperIds.filter(id => !existing.has(id)).map(paperId => addResearchProjectAsset(project.value!.id, {
      asset_type: 'paper', asset_id: paperId, source_scope: paperId.startsWith('up_') ? 'mypapers' : 'kb',
    })))
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '论文加入课题失败'
  }
}

async function removeAsset(asset: ResearchProjectAsset) {
  if (!project.value) return
  try {
    await removeResearchProjectAsset(project.value.id, asset.asset_type, asset.asset_id, asset.source_scope)
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '资产移除失败'
  }
}

async function archiveProject() {
  if (!project.value || !confirm(`归档课题「${project.value.name}」？之后可以从研究库恢复。`)) return
  await archiveResearchProject(project.value.id)
  await router.push('/projects')
}

function startResearch(question?: string) {
  if (!project.value) return
  if (!project.value.paper_ids.length) return void (showPaperPicker.value = true)
  router.push({ path: '/', query: { tool: 'research', project_id: String(project.value.id), ...(question?.trim() ? { question: question.trim() } : {}) } })
}

function startCompare() {
  if (!project.value) return
  if (project.value.paper_ids.length < 2) return void (showPaperPicker.value = true)
  router.push({ path: '/', query: { tool: 'compare', project_id: String(project.value.id) } })
}

function openAsset(asset: ResearchProjectAsset) { if (!asset.missing && asset.route) router.push(asset.route) }
function openPaperPdf(paperId: string) { openExternal(resolvePaperPdfUrl(paperId)) }
function openCandidate(paper: PaperSummary) { router.push(`/papers/${encodeURIComponent(paper.paper_id)}`) }
function openResearchSession(sessionId: number) { router.push({ path: '/', query: { tool: 'research-library', session: String(sessionId) } }) }
function switchProject(id: number) { if (id !== projectId.value) router.push(`/projects/${id}`) }

watch(projectId, load)
onMounted(load)
</script>

<template>
  <main class="project-detail-page">
    <div v-if="loading" class="project-detail-page__loading"><div /><div /><div /></div>
    <div v-else-if="error && !project" class="project-detail-page__error">
      <h1>无法打开课题</h1><p>{{ error }}</p><button type="button" @click="load">重新加载</button>
    </div>
    <template v-else-if="project">
      <div v-if="error" class="project-detail-page__notice">{{ error }}<button type="button" @click="error = ''">关闭</button></div>
      <ResearchProjectWorkspace
        v-model:active-tab="activeTab" :project="project" :projects="projects"
        :paper-details="paperDetails" :candidates="candidates" :candidates-loading="candidatesLoading"
        @create-project="router.push({ path: '/projects', query: { create: '1' } })"
        @switch-project="switchProject" @edit-project="showEdit = true" @archive-project="archiveProject"
        @start-research="startResearch" @start-compare="startCompare" @add-papers="showPaperPicker = true"
        @add-candidate="paper => addPapers([paper.paper_id])" @remove-asset="removeAsset"
        @open-asset="openAsset" @open-paper-pdf="openPaperPdf" @open-candidate="openCandidate" @open-research-session="openResearchSession"
      />
    </template>
    <PaperPickerDialog v-if="showPaperPicker" title="选择要加入课题的论文" mode="research" @confirm="addPapers" @cancel="showPaperPicker = false" />
    <Teleport to="body">
      <div v-if="showEdit && project" class="project-edit-modal" @click.self="showEdit = false">
        <form @submit.prevent="saveProject">
          <h2>编辑课题</h2>
          <label>课题名称<input v-model="editForm.name" maxlength="120"></label>
          <label>核心研究问题<textarea v-model="editForm.objective" rows="3" maxlength="2000" /></label>
          <label>课题说明<textarea v-model="editForm.description" rows="3" maxlength="5000" /></label>
          <div><button type="button" @click="showEdit = false">取消</button><button type="submit" :disabled="saving || !editForm.name.trim()">{{ saving ? '保存中…' : '保存' }}</button></div>
        </form>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.project-detail-page{height:100%;min-height:0;background:#fff}.project-detail-page__loading{display:grid;height:100%;grid-template-columns:210px 1fr 300px;gap:1px;background:#e8eaed}.project-detail-page__loading div{background:linear-gradient(90deg,#fafafa 25%,#f1f2f4 50%,#fafafa 75%);background-size:200% 100%;animation:project-shimmer 1.4s infinite}.project-detail-page__error{display:grid;height:100%;place-content:center;text-align:center;color:#252c36}.project-detail-page__error p{color:#747d89;font-size:12px}.project-detail-page__error button{justify-self:center;border:1px solid #e1e4e8;border-radius:8px;padding:8px 12px;background:#fff}.project-detail-page__notice{position:fixed;z-index:30;top:78px;left:50%;display:flex;align-items:center;gap:12px;transform:translateX(-50%);border:1px solid #ffc5cf;border-radius:9px;padding:9px 12px;background:#fff2f4;color:#a82740;font-size:11px}.project-detail-page__notice button{border:0;background:transparent;color:inherit;font-weight:800}.project-edit-modal{position:fixed;z-index:9999;inset:0;display:grid;place-items:center;padding:16px;background:rgba(12,17,24,.62)}.project-edit-modal form{width:min(100%,520px);padding:24px;border:1px solid #e1e4e8;border-radius:16px;background:#fff}.project-edit-modal h2{margin:0 0 18px;color:#18202c;font-size:18px}.project-edit-modal label{display:block;margin-top:13px;color:#56606e;font-size:11px;font-weight:700}.project-edit-modal input,.project-edit-modal textarea{box-sizing:border-box;width:100%;margin-top:7px;border:1px solid #dfe3e8;border-radius:9px;padding:10px 11px;outline:0;background:#fafafa;color:#18202c;font:inherit;font-size:12px}.project-edit-modal textarea{resize:vertical}.project-edit-modal form>div{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}.project-edit-modal form>div button{border:1px solid #dfe3e8;border-radius:8px;padding:9px 14px;background:#fff;color:#596171;font-size:11px;font-weight:700}.project-edit-modal form>div button[type=submit]{border-color:#ff385c;background:#ff385c;color:#fff}@keyframes project-shimmer{to{background-position:-200% 0}}@media(max-width:1199px){.project-detail-page__loading{grid-template-columns:190px 1fr}}@media(max-width:767px){.project-detail-page__loading{display:block}.project-detail-page__loading div:not(:nth-child(2)){display:none}}
</style>
