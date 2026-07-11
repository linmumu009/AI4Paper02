<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchPaperResearchMemory, extractPaperResearchMemory, updateIdeaAtom, deleteIdeaAtom } from '@shared/api'
import type { ResearchMemoryGroup, IdeaAtom } from '@shared/types/idea'
import { isAuthenticated } from '../stores/auth'

const props = defineProps<{
  paperId: string
}>()

const router = useRouter()

// ── State ──────────────────────────────────────────────────────────────────
const loading = ref(false)
const extracting = ref(false)
const error = ref('')
const hasAtoms = ref(false)
const atomCount = ref(0)
const lastExtractedAt = ref<string | null>(null)
const groups = ref<ResearchMemoryGroup[]>([])

// ── Edit state ─────────────────────────────────────────────────────────────
const editingAtomId = ref<number | null>(null)
const editContent = ref('')
const saving = ref(false)

// ── Load ───────────────────────────────────────────────────────────────────
async function load() {
  if (!props.paperId || !isAuthenticated.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchPaperResearchMemory(props.paperId)
    hasAtoms.value = res.has_atoms
    atomCount.value = res.atom_count
    lastExtractedAt.value = res.last_extracted_at
    groups.value = res.groups
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function extract() {
  if (!isAuthenticated.value) return
  extracting.value = true
  error.value = ''
  try {
    const res = await extractPaperResearchMemory(props.paperId)
    hasAtoms.value = res.has_atoms
    atomCount.value = res.atom_count
    lastExtractedAt.value = res.last_extracted_at
    groups.value = res.groups
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '提取失败'
  } finally {
    extracting.value = false
  }
}

onMounted(load)
watch(() => props.paperId, load)

// ── Editing ────────────────────────────────────────────────────────────────
function startEdit(atom: IdeaAtom) {
  editingAtomId.value = atom.id
  editContent.value = atom.content
}

function cancelEdit() {
  editingAtomId.value = null
  editContent.value = ''
}

async function saveEdit(atom: IdeaAtom) {
  if (!editContent.value.trim()) return
  saving.value = true
  try {
    const res = await updateIdeaAtom(atom.id, { content: editContent.value.trim() })
    atom.content = res.atom.content
    editingAtomId.value = null
  } catch {
    // ignore
  } finally {
    saving.value = false
  }
}

async function archiveAtom(atom: IdeaAtom, group: ResearchMemoryGroup) {
  try {
    await updateIdeaAtom(atom.id, { status: 'archived' } as any)
    group.atoms = group.atoms.filter(a => a.id !== atom.id)
    group.count = group.atoms.length
    atomCount.value = groups.value.reduce((s, g) => s + g.count, 0)
    hasAtoms.value = atomCount.value > 0
  } catch {
    // ignore
  }
}

async function removeAtom(atom: IdeaAtom, group: ResearchMemoryGroup) {
  try {
    await deleteIdeaAtom(atom.id)
    group.atoms = group.atoms.filter(a => a.id !== atom.id)
    group.count = group.atoms.length
    atomCount.value = groups.value.reduce((s, g) => s + g.count, 0)
    hasAtoms.value = atomCount.value > 0
  } catch {
    // ignore
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
const typeColor: Record<string, string> = {
  claim:      'border-l-blue-400',
  method:     'border-l-green-400',
  setup:      'border-l-yellow-400',
  limitation: 'border-l-red-400',
  tag:        'border-l-purple-400',
}

const typeIcon: Record<string, string> = {
  claim:      '💬',
  method:     '⚙️',
  setup:      '📊',
  limitation: '⚠️',
  tag:        '🏷️',
}

function formatDate(iso: string | null) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch { return iso }
}

function goToAtomBrowser() {
  router.push({ path: '/workbench', query: { tab: 'atoms', paper_id: props.paperId } })
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header bar -->
    <div class="shrink-0 flex items-center justify-between gap-3 px-4 sm:px-6 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <span class="text-base">🧠</span>
        <span class="text-sm font-semibold text-text-primary">研究记忆</span>
        <span v-if="atomCount > 0" class="text-xs text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">{{ atomCount }} 条</span>
        <span v-if="lastExtractedAt" class="text-xs text-text-muted hidden sm:inline">· {{ formatDate(lastExtractedAt) }}</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-if="isAuthenticated && hasAtoms"
          class="text-xs px-2.5 py-1 rounded border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
          @click="goToAtomBrowser"
        >
          全部原子
        </button>
        <button
          v-if="isAuthenticated"
          :disabled="extracting"
          class="text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
          :class="extracting
            ? 'border-border bg-bg-elevated text-text-muted cursor-not-allowed'
            : hasAtoms
              ? 'border-border bg-transparent text-text-muted hover:text-text-secondary hover:bg-bg-hover'
              : 'border-tinder-pink bg-tinder-pink/10 text-tinder-pink hover:bg-tinder-pink/20'"
          @click="extract"
        >
          <span v-if="extracting">提取中...</span>
          <span v-else-if="hasAtoms">重新提取</span>
          <span v-else>生成研究记忆</span>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center min-h-[200px]">
        <div class="flex flex-col items-center gap-3">
          <div class="w-8 h-8 rounded-full border-2 border-transparent border-t-tinder-pink animate-spin" />
          <p class="text-sm text-text-muted">加载中...</p>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>

      <!-- Not authenticated -->
      <div v-else-if="!isAuthenticated" class="flex items-center justify-center min-h-[200px]">
        <p class="text-sm text-text-muted">登录后可生成和查看研究记忆。</p>
      </div>

      <!-- Empty – no atoms yet -->
      <div v-else-if="!hasAtoms && !extracting" class="flex flex-col items-center justify-center min-h-[200px] gap-4">
        <div class="text-center">
          <p class="text-3xl mb-3">🧠</p>
          <p class="text-sm font-semibold text-text-primary mb-1">尚未生成研究记忆</p>
          <p class="text-xs text-text-muted mb-4">点击"生成研究记忆"，AI 会从论文中提取核心论断、方法、数据设置、局限与机会。</p>
          <button
            class="text-sm px-4 py-2 rounded-full border border-tinder-pink bg-tinder-pink/10 text-tinder-pink cursor-pointer hover:bg-tinder-pink/20 transition-colors"
            @click="extract"
          >
            生成研究记忆
          </button>
        </div>
      </div>

      <!-- Extracting in progress -->
      <div v-else-if="extracting" class="flex items-center justify-center min-h-[200px]">
        <div class="flex flex-col items-center gap-3">
          <div class="relative w-12 h-12 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-tinder-pink border-r-tinder-blue animate-spin" />
            <span class="text-xl">🧠</span>
          </div>
          <p class="text-sm text-text-muted">正在提取研究记忆，请稍候...</p>
        </div>
      </div>

      <!-- Atom groups -->
      <template v-else>
        <div
          v-for="group in groups"
          :key="group.type"
          class="space-y-2"
        >
          <!-- Group header -->
          <div class="flex items-center gap-2">
            <span class="text-sm">{{ typeIcon[group.type] }}</span>
            <span class="text-xs font-semibold text-text-secondary uppercase tracking-wider">{{ group.label }}</span>
            <span class="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">{{ group.count }}</span>
          </div>

          <!-- Empty group -->
          <p v-if="group.atoms.length === 0" class="text-xs text-text-muted pl-5 italic">暂无</p>

          <!-- Atoms -->
          <div
            v-for="atom in group.atoms"
            :key="atom.id"
            class="group bg-bg-card border border-border rounded-lg overflow-hidden border-l-4"
            :class="typeColor[atom.atom_type] || 'border-l-border'"
          >
            <!-- View mode -->
            <div v-if="editingAtomId !== atom.id" class="flex items-start gap-2 p-3">
              <p class="flex-1 text-sm text-text-primary leading-relaxed">{{ atom.content }}</p>
              <div class="shrink-0 flex items-center gap-1 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  class="text-[10px] px-1.5 py-0.5 rounded border border-transparent text-text-muted cursor-pointer hover:text-tinder-blue hover:border-tinder-blue/30 transition-colors"
                  title="编辑"
                  @click="startEdit(atom)"
                >编辑</button>
                <button
                  class="text-[10px] px-1.5 py-0.5 rounded border border-transparent text-text-muted cursor-pointer hover:text-amber-400 hover:border-amber-400/30 transition-colors"
                  title="隐藏此原子"
                  @click="archiveAtom(atom, group)"
                >隐藏</button>
                <button
                  class="text-[10px] px-1.5 py-0.5 rounded border border-transparent text-text-muted cursor-pointer hover:text-red-400 hover:border-red-400/30 transition-colors"
                  title="删除"
                  @click="removeAtom(atom, group)"
                >删除</button>
              </div>
            </div>
            <!-- Always show action row on non-hover devices -->
            <div class="flex items-center gap-1.5 px-3 pb-2 sm:hidden">
              <button
                class="text-[10px] px-1.5 py-0.5 rounded border border-border text-text-muted cursor-pointer hover:text-tinder-blue transition-colors"
                @click="startEdit(atom)"
              >编辑</button>
              <button
                class="text-[10px] px-1.5 py-0.5 rounded border border-border text-text-muted cursor-pointer hover:text-amber-400 transition-colors"
                @click="archiveAtom(atom, group)"
              >隐藏</button>
              <button
                class="text-[10px] px-1.5 py-0.5 rounded border border-border text-text-muted cursor-pointer hover:text-red-400 transition-colors"
                @click="removeAtom(atom, group)"
              >删除</button>
            </div>

            <!-- Edit mode -->
            <div v-if="editingAtomId === atom.id" class="p-3 space-y-2">
              <textarea
                v-model="editContent"
                class="w-full text-sm px-3 py-2 rounded border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light resize-none"
                rows="3"
              />
              <div class="flex gap-2">
                <button
                  :disabled="saving"
                  class="text-xs px-3 py-1.5 rounded border border-tinder-blue bg-tinder-blue/10 text-tinder-blue cursor-pointer hover:bg-tinder-blue/20 transition-colors disabled:opacity-50"
                  @click="saveEdit(atom)"
                >{{ saving ? '保存中...' : '保存' }}</button>
                <button
                  class="text-xs px-3 py-1.5 rounded border border-border bg-transparent text-text-muted cursor-pointer hover:bg-bg-hover transition-colors"
                  @click="cancelEdit"
                >取消</button>
              </div>
            </div>

            <!-- Tags row -->
            <div v-if="atom.tags?.length" class="flex flex-wrap gap-1 px-3 pb-2">
              <span
                v-for="t in atom.tags.slice(0, 5)"
                :key="t"
                class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted"
              >{{ t }}</span>
            </div>
          </div>
        </div>

        <!-- Footer: link to atom browser -->
        <div class="pt-2 border-t border-border flex justify-end">
          <button
            class="text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer bg-transparent border-none"
            @click="goToAtomBrowser"
          >
            在原子库中查看全部 →
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
