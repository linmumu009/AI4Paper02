<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  addResearchProjectAsset,
  archiveResearchProject,
  fetchResearchProject,
  removeResearchProjectAsset,
  updateResearchProject,
} from '../api'
import type { ResearchProject, ResearchProjectAsset } from '../types/paper'
import PaperPickerDialog from '../components/PaperPickerDialog.vue'

type FilterType = 'all' | 'paper' | 'research_session' | 'compare_result' | 'idea' | 'note'

const route = useRoute()
const router = useRouter()
const project = ref<ResearchProject | null>(null)
const loading = ref(true)
const error = ref('')
const activeFilter = ref<FilterType>('all')
const showEdit = ref(false)
const showPaperPicker = ref(false)
const saving = ref(false)
const editForm = ref({ name: '', objective: '', description: '' })

const projectId = computed(() => Number(route.params.id))

const filterOptions: { key: FilterType; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'paper', label: '论文' },
  { key: 'research_session', label: '深度研究' },
  { key: 'compare_result', label: '对比报告' },
  { key: 'idea', label: '灵感' },
  { key: 'note', label: '笔记' },
]

const displayItems = computed(() => {
  if (!project.value) return []
  const assets = project.value.assets.map(asset => ({ ...asset, kind: asset.asset_type }))
  const sessions = project.value.sessions.map(session => ({
    id: `session-${session.id}`,
    project_id: project.value!.id,
    asset_type: 'research_session' as const,
    asset_id: String(session.id),
    source_scope: 'research',
    metadata: {},
    added_at: session.updated_at,
    title: session.question,
    subtitle: session.status === 'done' ? `${session.paper_ids.length} 篇论文 · 已完成` : `${session.paper_ids.length} 篇论文 · ${session.status}`,
    route: `/?tool=research-library&session=${session.id}`,
    missing: false,
    kind: 'research_session' as const,
  }))
  const all = [...sessions, ...assets].sort((a, b) => b.added_at.localeCompare(a.added_at))
  return activeFilter.value === 'all' ? all : all.filter(item => item.asset_type === activeFilter.value)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    project.value = await fetchResearchProject(projectId.value)
    editForm.value = {
      name: project.value.name,
      objective: project.value.objective,
      description: project.value.description,
    }
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
      name: editForm.value.name.trim(),
      objective: editForm.value.objective.trim(),
      description: editForm.value.description.trim(),
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
    await Promise.all(paperIds.map(paperId => addResearchProjectAsset(project.value!.id, {
      asset_type: 'paper',
      asset_id: paperId,
      source_scope: paperId.startsWith('up_') ? 'mypapers' : 'kb',
    })))
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '论文加入课题失败'
  }
}

async function removeAsset(asset: ResearchProjectAsset) {
  if (!project.value) return
  await removeResearchProjectAsset(
    project.value.id,
    asset.asset_type,
    asset.asset_id,
    asset.source_scope,
  )
  await load()
}

async function archiveProject() {
  if (!project.value || !confirm(`归档课题「${project.value.name}」？之后可以从研究库恢复。`)) return
  await archiveResearchProject(project.value.id)
  await router.push('/projects')
}

function startResearch() {
  if (!project.value) return
  if (!project.value.paper_ids.length) {
    showPaperPicker.value = true
    return
  }
  router.push({ path: '/', query: { tool: 'research', project_id: String(project.value.id) } })
}

function openItem(item: any) {
  if (!item.missing && item.route) router.push(item.route)
}

function iconFor(type: string) {
  const icons: Record<string, string> = {
    paper: '📄', research_session: '🔬', compare_result: '⚖️', idea: '💡', note: '📝',
  }
  return icons[type] || '📎'
}

function labelFor(type: string) {
  const labels: Record<string, string> = {
    paper: '论文', research_session: '深度研究', compare_result: '对比报告', idea: '研究灵感', note: '笔记',
  }
  return labels[type] || type
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

watch(projectId, load)
onMounted(load)
</script>

<template>
  <main class="h-full overflow-y-auto bg-bg px-4 py-5 sm:px-8">
    <div class="mx-auto max-w-6xl space-y-5">
      <button class="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary" @click="router.push('/projects')">← 返回研究库</button>

      <div v-if="loading" class="space-y-4">
        <div class="h-40 animate-pulse rounded-2xl border border-border bg-bg-card" />
        <div class="h-64 animate-pulse rounded-2xl border border-border bg-bg-card" />
      </div>

      <div v-else-if="error && !project" class="rounded-2xl border border-red-500/30 bg-red-500/10 px-6 py-12 text-center">
        <h1 class="text-lg font-bold text-red-300">无法打开课题</h1>
        <p class="mt-2 text-sm text-red-200/80">{{ error }}</p>
        <button class="mt-4 rounded-lg border border-red-400/30 px-4 py-2 text-sm text-red-200" @click="load">重新加载</button>
      </div>

      <template v-else-if="project">
        <section class="rounded-2xl border border-border bg-bg-card p-5 sm:p-6">
          <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full border border-tinder-pink/30 bg-tinder-pink/10 px-2.5 py-1 text-[11px] font-semibold text-tinder-pink">进行中课题</span>
                <span class="text-xs text-text-muted">更新于 {{ formatDate(project.updated_at) }}</span>
              </div>
              <h1 class="mt-3 text-2xl font-bold text-text-primary">{{ project.name }}</h1>
              <p class="mt-2 max-w-3xl whitespace-pre-wrap text-sm leading-6 text-text-secondary">
                {{ project.objective || '尚未填写核心研究问题。' }}
              </p>
              <p v-if="project.description" class="mt-2 max-w-3xl whitespace-pre-wrap text-xs leading-5 text-text-muted">{{ project.description }}</p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-2">
              <button class="rounded-lg border border-border px-3 py-2 text-xs text-text-secondary hover:bg-bg-hover" @click="showEdit = true">编辑课题</button>
              <button class="rounded-lg border border-border px-3 py-2 text-xs text-text-muted hover:bg-bg-hover" @click="archiveProject">归档</button>
              <button class="rounded-lg bg-brand-gradient px-4 py-2 text-xs font-semibold text-white" @click="startResearch">开始深度研究</button>
            </div>
          </div>

          <div class="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-5">
            <div v-for="option in filterOptions.slice(1)" :key="option.key" class="rounded-xl bg-bg-elevated px-3 py-3 text-center">
              <div class="text-lg font-bold text-text-primary">{{ project.counts[option.key] || 0 }}</div>
              <div class="text-[10px] text-text-muted">{{ option.label }}</div>
            </div>
          </div>
        </section>

        <div v-if="error" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{{ error }}</div>

        <section class="overflow-hidden rounded-2xl border border-border bg-bg-card">
          <div class="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex gap-1 overflow-x-auto">
              <button
                v-for="option in filterOptions"
                :key="option.key"
                class="whitespace-nowrap rounded-lg px-3 py-1.5 text-xs transition"
                :class="activeFilter === option.key ? 'bg-bg-elevated font-semibold text-text-primary' : 'text-text-muted hover:text-text-secondary'"
                @click="activeFilter = option.key"
              >{{ option.label }} <span v-if="option.key !== 'all'">{{ project.counts[option.key] || 0 }}</span></button>
            </div>
            <button class="shrink-0 rounded-lg border border-tinder-pink/30 px-3 py-1.5 text-xs font-medium text-tinder-pink hover:bg-tinder-pink/10" @click="showPaperPicker = true">＋ 添加论文</button>
          </div>

          <div v-if="displayItems.length" class="divide-y divide-border/70">
            <article
              v-for="item in displayItems"
              :key="`${item.asset_type}-${item.asset_id}-${item.source_scope}`"
              class="group flex items-center gap-3 px-4 py-3.5 transition"
              :class="item.missing ? 'opacity-60' : 'cursor-pointer hover:bg-bg-hover'"
              @click="openItem(item)"
            >
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bg-elevated text-lg">{{ iconFor(item.asset_type) }}</div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="truncate text-sm font-semibold text-text-primary">{{ item.title }}</span>
                  <span class="shrink-0 rounded-full bg-bg-elevated px-2 py-0.5 text-[10px] text-text-muted">{{ labelFor(item.asset_type) }}</span>
                </div>
                <p class="mt-0.5 truncate text-xs text-text-muted">{{ item.missing ? '源资产已经删除' : item.subtitle }}</p>
              </div>
              <span class="hidden shrink-0 text-[11px] text-text-muted sm:block">{{ formatDate(item.added_at) }}</span>
              <button
                v-if="item.asset_type !== 'research_session'"
                class="shrink-0 rounded-lg px-2 py-1 text-xs text-text-muted opacity-0 hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
                title="从课题移除，不删除源资产"
                @click.stop="removeAsset(item)"
              >移除</button>
            </article>
          </div>

          <div v-else class="px-6 py-14 text-center">
            <div class="text-2xl">📚</div>
            <h2 class="mt-2 text-sm font-bold text-text-primary">这个分类还没有研究资产</h2>
            <p class="mt-1 text-xs text-text-muted">先加入论文，再从课题中发起深度研究。</p>
            <button class="mt-4 rounded-lg border border-tinder-pink/30 px-4 py-2 text-xs text-tinder-pink" @click="showPaperPicker = true">添加论文</button>
          </div>
        </section>
      </template>
    </div>

    <PaperPickerDialog
      v-if="showPaperPicker"
      title="选择要加入课题的论文"
      mode="research"
      @confirm="(ids) => addPapers(ids)"
      @cancel="showPaperPicker = false"
    />

    <Teleport to="body">
      <div v-if="showEdit && project" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4" @click.self="showEdit = false">
        <form class="w-full max-w-lg space-y-4 rounded-2xl border border-border bg-bg-card p-6 shadow-2xl" @submit.prevent="saveProject">
          <h2 class="text-lg font-bold text-text-primary">编辑课题</h2>
          <label class="block text-xs font-medium text-text-secondary">课题名称<input v-model="editForm.name" maxlength="120" class="mt-1.5 w-full rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink"></label>
          <label class="block text-xs font-medium text-text-secondary">核心研究问题<textarea v-model="editForm.objective" rows="3" maxlength="2000" class="mt-1.5 w-full resize-none rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink" /></label>
          <label class="block text-xs font-medium text-text-secondary">课题说明<textarea v-model="editForm.description" rows="3" maxlength="5000" class="mt-1.5 w-full resize-none rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink" /></label>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary" @click="showEdit = false">取消</button>
            <button type="submit" :disabled="saving || !editForm.name.trim()" class="rounded-lg bg-brand-gradient px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ saving ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </Teleport>
  </main>
</template>
