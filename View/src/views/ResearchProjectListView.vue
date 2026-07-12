<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  archiveResearchProject,
  createResearchProject,
  deleteResearchProject,
  fetchResearchProjects,
  restoreResearchProject,
} from '../api'
import type { ResearchProjectSummary } from '../types/paper'

const router = useRouter()
const route = useRoute()
const projects = ref<ResearchProjectSummary[]>([])
const loading = ref(true)
const error = ref('')
const includeArchived = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const form = ref({ name: '', objective: '', description: '' })

const activeProjects = computed(() => projects.value.filter(project => project.status === 'active'))
const archivedProjects = computed(() => projects.value.filter(project => project.status === 'archived'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    projects.value = await fetchResearchProjects(includeArchived.value)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '课题加载失败'
  } finally {
    loading.value = false
  }
}

async function createProject() {
  const name = form.value.name.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const project = await createResearchProject({
      name,
      objective: form.value.objective.trim(),
      description: form.value.description.trim(),
    })
    showCreate.value = false
    form.value = { name: '', objective: '', description: '' }
    await router.push(`/projects/${project.id}`)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '课题创建失败'
  } finally {
    creating.value = false
  }
}

async function archive(project: ResearchProjectSummary) {
  await archiveResearchProject(project.id)
  await load()
}

async function restore(project: ResearchProjectSummary) {
  await restoreResearchProject(project.id)
  await load()
}

async function remove(project: ResearchProjectSummary) {
  if (!confirm(`确认删除课题「${project.name}」？只会解除课题关系，不会删除论文和研究报告。`)) return
  await deleteResearchProject(project.id)
  await load()
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

onMounted(() => {
  if (route.query.create === '1') showCreate.value = true
  void load()
})
</script>

<template>
  <main class="h-full overflow-y-auto bg-bg px-4 py-6 sm:px-8">
    <div class="mx-auto max-w-6xl space-y-6">
      <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-tinder-pink">Research workspace</p>
          <h1 class="mt-1 text-2xl font-bold text-text-primary">研究库 · 课题空间</h1>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
            围绕一个长期课题集中管理论文、深度研究、对比报告、灵感和笔记。
          </p>
        </div>
        <div class="flex items-center gap-2">
          <label class="flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-text-secondary">
            <input v-model="includeArchived" type="checkbox" class="accent-pink-500" @change="load">
            显示已归档
          </label>
          <button class="rounded-lg bg-brand-gradient px-4 py-2 text-sm font-semibold text-white" @click="showCreate = true">
            新建课题
          </button>
        </div>
      </header>

      <div v-if="error" class="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {{ error }}
        <button class="ml-2 underline" @click="load">重试</button>
      </div>

      <div v-if="loading" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="正在加载课题">
        <div v-for="index in 6" :key="index" class="h-44 animate-pulse rounded-2xl border border-border bg-bg-card" />
      </div>

      <section v-else-if="activeProjects.length" class="space-y-3">
        <h2 class="text-sm font-semibold text-text-secondary">进行中的课题 · {{ activeProjects.length }}</h2>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="project in activeProjects"
            :key="project.id"
            class="group cursor-pointer rounded-2xl border border-border bg-bg-card p-5 transition hover:-translate-y-0.5 hover:border-tinder-pink/40 hover:shadow-lg"
            @click="router.push(`/projects/${project.id}`)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h3 class="truncate text-base font-bold text-text-primary">{{ project.name }}</h3>
                <p class="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-text-muted">
                  {{ project.objective || project.description || '还没有填写核心研究问题' }}
                </p>
              </div>
              <button
                class="shrink-0 rounded-lg px-2 py-1 text-xs text-text-muted opacity-0 hover:bg-bg-hover group-hover:opacity-100"
                title="归档课题"
                @click.stop="archive(project)"
              >归档</button>
            </div>
            <div class="mt-5 grid grid-cols-3 gap-2 text-center">
              <div class="rounded-lg bg-bg-elevated px-2 py-2">
                <div class="text-sm font-bold text-text-primary">{{ project.counts.paper || 0 }}</div>
                <div class="text-[10px] text-text-muted">论文</div>
              </div>
              <div class="rounded-lg bg-bg-elevated px-2 py-2">
                <div class="text-sm font-bold text-text-primary">{{ project.counts.research_session || 0 }}</div>
                <div class="text-[10px] text-text-muted">研究</div>
              </div>
              <div class="rounded-lg bg-bg-elevated px-2 py-2">
                <div class="text-sm font-bold text-text-primary">{{ project.asset_count }}</div>
                <div class="text-[10px] text-text-muted">总资产</div>
              </div>
            </div>
            <p class="mt-4 text-[11px] text-text-muted">更新于 {{ formatDate(project.updated_at) }}</p>
          </article>
        </div>
      </section>

      <section v-else-if="!includeArchived" class="rounded-2xl border border-dashed border-border bg-bg-card px-6 py-16 text-center">
        <div class="text-3xl">🗂️</div>
        <h2 class="mt-3 text-lg font-bold text-text-primary">还没有课题空间</h2>
        <p class="mt-2 text-sm text-text-muted">创建一个课题，把分散的研究资产放到同一条研究主线上。</p>
        <button class="mt-5 rounded-lg bg-brand-gradient px-5 py-2 text-sm font-semibold text-white" @click="showCreate = true">创建第一个课题</button>
      </section>

      <section v-if="includeArchived && archivedProjects.length" class="space-y-3">
        <h2 class="text-sm font-semibold text-text-secondary">已归档 · {{ archivedProjects.length }}</h2>
        <div class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-bg-card">
          <div v-for="project in archivedProjects" :key="project.id" class="flex items-center gap-3 px-4 py-3">
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-semibold text-text-primary">{{ project.name }}</div>
              <div class="text-xs text-text-muted">{{ project.asset_count }} 项研究资产</div>
            </div>
            <button class="rounded-lg px-3 py-1.5 text-xs text-tinder-green hover:bg-bg-hover" @click="restore(project)">恢复</button>
            <button class="rounded-lg px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10" @click="remove(project)">删除</button>
          </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showCreate" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4" @click.self="showCreate = false">
        <form class="w-full max-w-lg space-y-4 rounded-2xl border border-border bg-bg-card p-6 shadow-2xl" @submit.prevent="createProject">
          <div>
            <h2 class="text-lg font-bold text-text-primary">新建课题</h2>
            <p class="mt-1 text-xs text-text-muted">之后可以随时补充目标、论文和研究资料。</p>
          </div>
          <label class="block text-xs font-medium text-text-secondary">
            课题名称
            <input v-model="form.name" maxlength="120" autofocus class="mt-1.5 w-full rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink" placeholder="例如：长时程智能体记忆机制">
          </label>
          <label class="block text-xs font-medium text-text-secondary">
            核心研究问题
            <textarea v-model="form.objective" rows="3" maxlength="2000" class="mt-1.5 w-full resize-none rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink" placeholder="希望回答的核心问题，可稍后填写" />
          </label>
          <label class="block text-xs font-medium text-text-secondary">
            课题说明
            <textarea v-model="form.description" rows="3" maxlength="5000" class="mt-1.5 w-full resize-none rounded-lg border border-border bg-bg-elevated px-3 py-2.5 text-sm text-text-primary outline-none focus:border-tinder-pink" placeholder="研究范围、约束或阶段目标" />
          </label>
          <div class="flex justify-end gap-2 pt-2">
            <button type="button" class="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary" @click="showCreate = false">取消</button>
            <button type="submit" :disabled="!form.name.trim() || creating" class="rounded-lg bg-brand-gradient px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {{ creating ? '创建中…' : '创建课题' }}
            </button>
          </div>
        </form>
      </div>
    </Teleport>
  </main>
</template>
