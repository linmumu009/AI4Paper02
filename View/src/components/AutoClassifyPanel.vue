<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import {
  fetchUserSettings, saveUserSettings, fetchUserLlmPresets,
  fetchUserPromptPresets,
  syncAutoClassifyFolders, reclassifyAllKbPapers, fetchAutoClassifyPendingCount,
  fetchAutoClassifyUnclassifiedCount,
  fetchKbTree,
} from '../api'
import type { AutoClassifyFolder } from '../api'
import type { UserLlmPreset, UserPromptPreset, KbFolder } from '../types/paper'
import PresetSelector from './PresetSelector.vue'

// ---------------------------------------------------------------------------
// Tree node type (in-memory editing state)
// ---------------------------------------------------------------------------

interface FolderNode {
  _key: string
  name: string
  description: string
  folder_id: number | null
  children: FolderNode[]
}

interface DisplayItem {
  node: FolderNode
  depth: number
  siblings: FolderNode[]
  parent: FolderNode | null
}

let _keyCounter = Date.now()
function newKey(): string { return String(++_keyCounter) }

// ---------------------------------------------------------------------------
// Flat <-> Tree conversion
// ---------------------------------------------------------------------------

function buildTree(flat: AutoClassifyFolder[]): FolderNode[] {
  if (!flat.length) return []
  const byId = new Map<number, FolderNode>()
  const nodes: FolderNode[] = flat.map(f => {
    const n: FolderNode = {
      _key: newKey(),
      name: f.name || '',
      description: f.description || '',
      folder_id: f.folder_id ?? null,
      children: [],
    }
    if (n.folder_id) byId.set(n.folder_id, n)
    return n
  })
  const roots: FolderNode[] = []
  flat.forEach((f, i) => {
    if (f.parent_id != null && byId.has(f.parent_id)) {
      byId.get(f.parent_id)!.children.push(nodes[i])
    } else {
      roots.push(nodes[i])
    }
  })
  return roots
}

/**
 * Flatten tree to a flat list (DFS, parent before children).
 * Passes _key / _parent_key so the backend sync can resolve unsynced parent-child links.
 */
function flattenTree(
  nodes: FolderNode[],
  parentFolderId: number | null = null,
  parentKey: string | null = null,
): AutoClassifyFolder[] {
  const result: AutoClassifyFolder[] = []
  for (const node of nodes) {
    result.push({
      name: node.name,
      description: node.description,
      folder_id: node.folder_id ?? null,
      parent_id: parentFolderId,
      _key: node._key,
      _parent_key: parentKey ?? undefined,
    })
    if (node.children.length) {
      result.push(...flattenTree(node.children, node.folder_id, node._key))
    }
  }
  return result
}

/** Like flattenTree but strips temp fields (for persisting to user_settings). */
function flattenTreeForSave(nodes: FolderNode[], parentFolderId: number | null = null): AutoClassifyFolder[] {
  const result: AutoClassifyFolder[] = []
  for (const node of nodes) {
    result.push({ name: node.name, description: node.description, folder_id: node.folder_id ?? null, parent_id: parentFolderId })
    if (node.children.length) result.push(...flattenTreeForSave(node.children, node.folder_id))
  }
  return result
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')
const syncingFolders = ref(false)
const reclassifying = ref(false)
const reclassifyMsg = ref('')
const pendingCount = ref(0)
const unclassifiedCount = ref(0)

// Polling timer for pending classify count while on this settings page
let _pollTimer: ReturnType<typeof setInterval> | null = null

function _stopPoll() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
}

async function _refreshPending() {
  try {
    const res = await fetchAutoClassifyPendingCount('kb')
    pendingCount.value = res.pending
    if (res.pending === 0) _stopPoll()
  } catch { /* ignore */ }
}

function _startPoll() {
  if (_pollTimer) return
  _pollTimer = setInterval(_refreshPending, 5000)
}

watch(pendingCount, (val) => {
  if (val > 0) _startPoll()
})

onBeforeUnmount(_stopPoll)

const form = reactive<{
  enabled: boolean
  llm_preset_id: string | number
  prompt_preset_id: string | number
  confidence_threshold: number
}>({
  enabled: false,
  llm_preset_id: '',
  prompt_preset_id: '',
  confidence_threshold: 0.6,
})

const folderTree = ref<FolderNode[]>([])
const llmPresets = ref<UserLlmPreset[]>([])
const promptPresets = ref<UserPromptPreset[]>([])
const showAdvancedPrompt = ref(false)

/** IDs of all folders that currently exist in the real KB (from the tree). */
const kbFolderIds = ref<Set<number>>(new Set())

/** Diff warnings: stale folder_ids in settings vs. real KB folders. */
const folderDiffWarnings = computed<string[]>(() => {
  const warnings: string[] = []
  const unsynced = displayList.value.filter(item => !item.node.folder_id).length
  if (unsynced > 0) {
    warnings.push(`${unsynced} 个目录尚未同步到知识库（点击「同步目录到知识库」按钮创建它们）`)
  }
  if (kbFolderIds.value.size > 0) {
    const stale = displayList.value.filter(
      item => item.node.folder_id != null && !kbFolderIds.value.has(item.node.folder_id!)
    ).length
    if (stale > 0) {
      warnings.push(`${stale} 个已同步的文件夹已在知识库中被删除，建议重新点击「同步目录到知识库」`)
    }
  }
  return warnings
})

const displayList = computed<DisplayItem[]>(() => {
  function build(nodes: FolderNode[], depth: number, parent: FolderNode | null): DisplayItem[] {
    const items: DisplayItem[] = []
    for (const node of nodes) {
      items.push({ node, depth, siblings: nodes, parent })
      if (node.children.length) items.push(...build(node.children, depth + 1, node))
    }
    return items
  }
  return build(folderTree.value, 0, null)
})

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

async function loadAll() {
  loading.value = true
  saveError.value = ''
  try {
    const [settingsRes, presetsRes, pendingRes, kbTreeRes, unclassifiedRes, promptPresetsRes] = await Promise.all([
      fetchUserSettings('auto_classify'),
      fetchUserLlmPresets(),
      fetchAutoClassifyPendingCount('kb'),
      fetchKbTree('kb'),
      fetchAutoClassifyUnclassifiedCount('kb'),
      fetchUserPromptPresets(),
    ])
    const s = settingsRes.settings || {}
    form.enabled = !!s.enabled
    form.llm_preset_id = s.llm_preset_id || ''
    form.prompt_preset_id = s.prompt_preset_id || ''
    form.confidence_threshold = typeof s.confidence_threshold === 'number' ? s.confidence_threshold : 0.6
    const flat: AutoClassifyFolder[] = Array.isArray(s.folders) ? s.folders : []
    folderTree.value = buildTree(flat)
    llmPresets.value = presetsRes.presets || []
    promptPresets.value = promptPresetsRes.presets || []
    pendingCount.value = pendingRes.pending
    unclassifiedCount.value = unclassifiedRes.unclassified
    const ids = new Set<number>()
    function collectIds(folders: KbFolder[]) {
      for (const f of folders) { ids.add(f.id); collectIds(f.children) }
    }
    collectIds(kbTreeRes.folders)
    kbFolderIds.value = ids
  } catch (e: any) {
    saveError.value = e?.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

// ---------------------------------------------------------------------------
// Auto-save toggle / threshold / preset (debounced)
// ---------------------------------------------------------------------------

let _autoSaveTimer: ReturnType<typeof setTimeout> | null = null

function _scheduleAutoSave() {
  if (_autoSaveTimer) clearTimeout(_autoSaveTimer)
  _autoSaveTimer = setTimeout(async () => {
    _autoSaveTimer = null
    try {
      await saveUserSettings('auto_classify', {
        enabled: form.enabled,
        llm_preset_id: form.llm_preset_id || '',
        prompt_preset_id: form.prompt_preset_id || '',
        confidence_threshold: form.confidence_threshold,
        folders: flattenTreeForSave(folderTree.value),
      })
      saveSuccess.value = true
      setTimeout(() => { saveSuccess.value = false }, 2000)
    } catch { /* silently ignore; user can still use explicit save */ }
  }, 600)
}

watch(() => form.enabled, _scheduleAutoSave)
watch(() => form.confidence_threshold, _scheduleAutoSave)
watch(() => form.llm_preset_id, _scheduleAutoSave)
watch(() => form.prompt_preset_id, _scheduleAutoSave)

// ---------------------------------------------------------------------------
// Save (explicit, used as fallback)
// ---------------------------------------------------------------------------

async function handleSave() {
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    await saveUserSettings('auto_classify', {
      enabled: form.enabled,
      llm_preset_id: form.llm_preset_id || '',
      prompt_preset_id: form.prompt_preset_id || '',
      confidence_threshold: form.confidence_threshold,
      folders: flattenTreeForSave(folderTree.value),
    })
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// Tree editing operations
// ---------------------------------------------------------------------------

function addRoot() {
  const node: FolderNode = { _key: newKey(), name: '', description: '', folder_id: null, children: [] }
  folderTree.value.push(node)
  nextTick(() => startEdit(node._key, 'name'))
}

function addChild(node: FolderNode) {
  const child: FolderNode = { _key: newKey(), name: '', description: '', folder_id: null, children: [] }
  node.children.push(child)
  nextTick(() => startEdit(child._key, 'name'))
}

function removeNode(node: FolderNode, siblings: FolderNode[]) {
  const idx = siblings.indexOf(node)
  if (idx !== -1) siblings.splice(idx, 1)
  if (editingKey.value === node._key) stopEdit()
}

function moveUp(node: FolderNode, siblings: FolderNode[]) {
  const idx = siblings.indexOf(node)
  if (idx <= 0) return
  siblings.splice(idx, 1)
  siblings.splice(idx - 1, 0, node)
}

function moveDown(node: FolderNode, siblings: FolderNode[]) {
  const idx = siblings.indexOf(node)
  if (idx < 0 || idx >= siblings.length - 1) return
  siblings.splice(idx, 1)
  siblings.splice(idx + 1, 0, node)
}

// ---------------------------------------------------------------------------
// Sync folders
// ---------------------------------------------------------------------------

async function handleSyncFolders() {
  const hasAny = folderTree.value.length > 0
  if (!hasAny) return
  syncingFolders.value = true
  saveError.value = ''
  try {
    const flat = flattenTree(folderTree.value)
    const res = await syncAutoClassifyFolders(flat, 'kb')
    folderTree.value = buildTree(res.folders)
    await saveUserSettings('auto_classify', {
      enabled: form.enabled,
      llm_preset_id: form.llm_preset_id || '',
      confidence_threshold: form.confidence_threshold,
      folders: flattenTreeForSave(folderTree.value),
    })
    try {
      const treeRes = await fetchKbTree('kb')
      const ids = new Set<number>()
      function collectIds(folders: KbFolder[]) {
        for (const f of folders) { ids.add(f.id); collectIds(f.children) }
      }
      collectIds(treeRes.folders)
      kbFolderIds.value = ids
    } catch { /* ignore */ }
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.message || '同步目录失败'
  } finally {
    syncingFolders.value = false
  }
}

// ---------------------------------------------------------------------------
// Reclassify all
// ---------------------------------------------------------------------------

async function handleReclassifyAll() {
  reclassifying.value = true
  reclassifyMsg.value = ''
  try {
    const res = await reclassifyAllKbPapers('kb')
    reclassifyMsg.value = `已将 ${res.enqueued} 篇论文排入分类队列，后台处理中…`
    setTimeout(async () => {
      const p = await fetchAutoClassifyPendingCount('kb')
      pendingCount.value = p.pending
    }, 1000)
  } catch (e: any) {
    saveError.value = e?.message || '重新分类失败'
  } finally {
    reclassifying.value = false
  }
}

// ---------------------------------------------------------------------------
// Confidence label
// ---------------------------------------------------------------------------

const confidenceLabel = computed(() => {
  const v = form.confidence_threshold
  if (v >= 0.85) return '严格'
  if (v >= 0.65) return '均衡'
  return '宽松'
})

const confidenceColor = computed(() => {
  const v = form.confidence_threshold
  if (v >= 0.85) return 'text-tinder-pink'
  if (v >= 0.65) return 'text-tinder-gold'
  return 'text-tinder-green'
})

// ---------------------------------------------------------------------------
// Inline tree editing
// ---------------------------------------------------------------------------

const editingKey = ref<string | null>(null)
const editingField = ref<'name' | 'description' | null>(null)
const expandedDescKeys = ref<Set<string>>(new Set())

function startEdit(key: string, field: 'name' | 'description') {
  editingKey.value = key
  editingField.value = field
  nextTick(() => {
    const el = document.querySelector(`[data-edit-key="${key}"][data-edit-field="${field}"]`) as HTMLInputElement | null
    el?.focus()
    el?.select()
  })
}

function stopEdit() {
  editingKey.value = null
  editingField.value = null
  _scheduleAutoSave()
}

function handleEditKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') { e.preventDefault(); stopEdit() }
  if (e.key === 'Escape') stopEdit()
}

function toggleDesc(key: string) {
  const set = expandedDescKeys.value
  if (set.has(key)) { set.delete(key) } else { set.add(key) }
  expandedDescKeys.value = new Set(set)
}

// ---------------------------------------------------------------------------
// Derived counts
// ---------------------------------------------------------------------------

const folderCount = computed(() => displayList.value.length)

const selectedLlmPreset = computed(() =>
  llmPresets.value.find(p => String(p.id) === String(form.llm_preset_id)) ?? null
)
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-8">

    <!-- ── Loading ── -->
    <div v-if="loading" class="flex items-center justify-center min-h-[400px]">
      <div class="text-center">
        <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-tinder-green border-r-tinder-green/60 animate-spin"></div>
        </div>
        <p class="text-sm text-text-muted">加载中…</p>
      </div>
    </div>

    <template v-else>

      <!-- ══════════════════════════════════════════════════════════════
           SECTION 1 — Hero 状态卡片
      ══════════════════════════════════════════════════════════════ -->
      <div class="mb-5 bg-bg-card border border-border rounded-2xl p-5 sm:p-6">
        <!-- Title row + toggle -->
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <svg class="w-5 h-5 text-tinder-green shrink-0" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <h2 class="text-base font-bold text-text-primary">自动分类</h2>
              <span
                :class="[
                  'text-[10px] font-semibold px-2 py-0.5 rounded-full',
                  form.enabled
                    ? 'bg-tinder-green/15 text-tinder-green'
                    : 'bg-bg-elevated text-text-muted'
                ]"
              >{{ form.enabled ? '已启用' : '已停用' }}</span>
            </div>
            <p class="text-xs text-text-muted leading-relaxed">
              收藏论文后自动调用 AI 判断应归入哪个文件夹，无需手动整理
            </p>
          </div>

          <!-- Toggle switch -->
          <button
            type="button"
            :class="[
              'relative inline-flex h-7 w-12 items-center rounded-full transition-colors focus:outline-none shrink-0',
              form.enabled ? 'bg-tinder-green' : 'bg-bg-elevated border border-border'
            ]"
            @click="form.enabled = !form.enabled"
          >
            <span
              :class="[
                'inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform duration-200',
                form.enabled ? 'translate-x-6' : 'translate-x-1'
              ]"
            />
          </button>
        </div>

        <!-- Stat pills -->
        <div class="mt-4 pt-4 border-t border-border/40 flex flex-wrap gap-2">
          <!-- Folder count -->
          <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-elevated border border-border/60 text-xs">
            <svg class="w-3.5 h-3.5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="text-text-secondary font-medium">{{ folderCount }}</span>
            <span class="text-text-muted">个目录</span>
          </div>

          <!-- Pending -->
          <div
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors',
              pendingCount > 0
                ? 'bg-amber-500/8 border-amber-500/25 text-amber-400'
                : 'bg-bg-elevated border-border/60 text-text-muted'
            ]"
          >
            <div v-if="pendingCount > 0" class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0"></div>
            <svg v-else class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span class="font-medium">{{ pendingCount > 0 ? pendingCount : '无' }}</span>
            <span>{{ pendingCount > 0 ? '篇处理中' : '待处理' }}</span>
          </div>

          <!-- Unclassified -->
          <div
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors',
              unclassifiedCount >= 10
                ? 'bg-sky-500/8 border-sky-500/25 text-sky-400'
                : 'bg-bg-elevated border-border/60 text-text-muted'
            ]"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span class="font-medium">{{ unclassifiedCount }}</span>
            <span>篇未分类</span>
            <span v-if="unclassifiedCount >= 10" class="opacity-70">— 建议扩充目录</span>
          </div>

          <!-- Active model chip -->
          <div v-if="selectedLlmPreset" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tinder-green/8 border border-tinder-green/20 text-xs text-tinder-green">
            <svg class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
            </svg>
            <span class="font-medium truncate max-w-[120px]">{{ selectedLlmPreset.name }}</span>
          </div>
        </div>
      </div>

      <!-- Disabled notice -->
      <div
        v-if="!form.enabled"
        class="mb-5 flex items-center gap-2 px-4 py-3 rounded-xl bg-bg-elevated border border-border/50 text-xs text-text-muted"
      >
        <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        自动分类已停用。启用后，收藏论文时若未手动选择文件夹，AI 将自动完成分类。
      </div>

      <!-- ══════════════════════════════════════════════════════════════
           SECTION 2 — 配置卡片（双列）
      ══════════════════════════════════════════════════════════════ -->
      <div
        class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5 transition-opacity duration-200"
        :class="!form.enabled ? 'opacity-40 pointer-events-none' : ''"
      >
        <!-- Left: AI 模型 -->
        <div class="bg-bg-card border border-border rounded-xl p-4 flex flex-col gap-0">
          <div class="flex items-center gap-2 mb-3">
            <svg class="w-4 h-4 text-tinder-green shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>
              <line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>
              <line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>
              <line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>
              <line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
            </svg>
            <h3 class="text-sm font-semibold text-text-primary">AI 模型</h3>
          </div>
          <p class="text-xs text-text-muted mb-3 leading-relaxed">
            分类只需一次轻量调用（约 500 token），推荐速度快、成本低的模型。
          </p>
          <PresetSelector
            v-model="form.llm_preset_id"
            :presets="llmPresets"
            show-model-hint
          />

          <!-- Custom prompt toggle -->
          <div class="mt-3 pt-3 border-t border-border/40">
            <button
              type="button"
              class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors w-full"
              @click="showAdvancedPrompt = !showAdvancedPrompt"
            >
              <svg
                v-if="!form.prompt_preset_id"
                class="w-3.5 h-3.5 text-tinder-green shrink-0"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
                stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <svg v-else class="w-3.5 h-3.5 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
              </svg>
              <span class="flex-1 text-left">
                {{ form.prompt_preset_id ? '已自定义提示词' : '系统默认提示词' }}
              </span>
              <svg
                class="w-3 h-3 shrink-0 transition-transform duration-150"
                :class="showAdvancedPrompt ? 'rotate-180' : ''"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
              >
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>

            <Transition
              enter-active-class="transition duration-150 ease-out"
              enter-from-class="opacity-0 -translate-y-1"
              enter-to-class="opacity-100 translate-y-0"
              leave-active-class="transition duration-100 ease-in"
              leave-from-class="opacity-100 translate-y-0"
              leave-to-class="opacity-0 -translate-y-1"
            >
              <div v-if="showAdvancedPrompt" class="mt-3 space-y-2">
                <p class="text-xs text-text-muted leading-relaxed">
                  选择后替换系统内置模板。支持占位符：
                  <code class="text-[10px] bg-bg-elevated px-1 py-0.5 rounded">{folder_list}</code>、
                  <code class="text-[10px] bg-bg-elevated px-1 py-0.5 rounded">{title}</code>、
                  <code class="text-[10px] bg-bg-elevated px-1 py-0.5 rounded">{abstract}</code> 等
                </p>
                <PresetSelector
                  v-model="form.prompt_preset_id"
                  :presets="promptPresets"
                  placeholder="使用系统默认提示词"
                  accent-color="#059669"
                />
              </div>
            </Transition>
          </div>
        </div>

        <!-- Right: 置信度阈值 -->
        <div class="bg-bg-card border border-border rounded-xl p-4 flex flex-col">
          <div class="flex items-center gap-2 mb-3">
            <svg class="w-4 h-4 text-tinder-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>
              <line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>
              <line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>
              <line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>
            </svg>
            <h3 class="text-sm font-semibold text-text-primary">置信度阈值</h3>
          </div>

          <!-- Current value display -->
          <div class="flex items-baseline justify-between mb-3">
            <span class="text-3xl font-bold" :class="confidenceColor">
              {{ (form.confidence_threshold * 100).toFixed(0) }}<span class="text-lg">%</span>
            </span>
            <span :class="['text-sm font-semibold px-2.5 py-1 rounded-lg', confidenceColor,
              form.confidence_threshold >= 0.85 ? 'bg-tinder-pink/10' :
              form.confidence_threshold >= 0.65 ? 'bg-tinder-gold/10' : 'bg-tinder-green/10'
            ]">{{ confidenceLabel }}</span>
          </div>

          <!-- Three-segment visual indicator -->
          <div class="flex gap-1 mb-3">
            <div
              class="flex-1 h-1.5 rounded-full transition-colors duration-200"
              :class="form.confidence_threshold < 0.65 ? 'bg-tinder-green' : 'bg-border'"
            ></div>
            <div
              class="flex-1 h-1.5 rounded-full transition-colors duration-200"
              :class="form.confidence_threshold >= 0.65 && form.confidence_threshold < 0.85 ? 'bg-tinder-gold' : 'bg-border'"
            ></div>
            <div
              class="flex-1 h-1.5 rounded-full transition-colors duration-200"
              :class="form.confidence_threshold >= 0.85 ? 'bg-tinder-pink' : 'bg-border'"
            ></div>
          </div>

          <input
            v-model.number="form.confidence_threshold"
            type="range"
            min="0.3"
            max="0.95"
            step="0.05"
            class="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-tinder-green mb-1"
          />
          <div class="flex justify-between text-[10px] text-text-muted">
            <span>宽松 (0.3)</span>
            <span>均衡 (0.65)</span>
            <span>严格 (0.95)</span>
          </div>

          <p class="text-xs text-text-muted mt-auto pt-3 leading-relaxed">
            AI 置信度低于此值时，论文归入「未分类」文件夹。提高阈值可减少误分类，但会增加未分类数量。
          </p>
        </div>
      </div>

      <!-- ══════════════════════════════════════════════════════════════
           SECTION 3 — 目录树编辑器
      ══════════════════════════════════════════════════════════════ -->
      <div
        class="bg-bg-card border border-border rounded-xl overflow-hidden transition-opacity duration-200"
        :class="!form.enabled ? 'opacity-40 pointer-events-none' : ''"
      >
        <!-- Tree header -->
        <div class="px-5 py-4 border-b border-border/50 flex items-center justify-between gap-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-text-primary">分类目录</h3>
              <span class="text-[10px] font-medium text-text-muted bg-bg-elevated px-2 py-0.5 rounded-full">
                {{ folderCount }} 个
              </span>
            </div>
            <p class="text-xs text-text-muted mt-0.5">
              为每个目录填写名称和描述，帮助 AI 理解归类依据；编辑后点击「同步」创建实际文件夹
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-tinder-green/10 border border-tinder-green/25 text-tinder-green text-xs font-medium hover:bg-tinder-green/20 transition-colors"
            @click="addRoot"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            添加目录
          </button>
        </div>

        <!-- Tree body -->
        <div class="px-3 py-2 min-h-[80px]">

          <!-- Empty state -->
          <div v-if="folderTree.length === 0" class="flex flex-col items-center justify-center py-10 gap-3">
            <div class="w-14 h-14 rounded-2xl bg-bg-elevated flex items-center justify-center">
              <svg class="w-7 h-7 text-text-muted/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <div class="text-center">
              <p class="text-sm font-medium text-text-muted">还没有分类目录</p>
              <p class="text-xs text-text-muted/60 mt-0.5">点击右上角「添加目录」开始配置</p>
            </div>
          </div>

          <!-- Tree nodes -->
          <div v-for="item in displayList" :key="item.node._key">
            <!-- Node row -->
            <div
              class="flex items-stretch"
              :style="{ paddingLeft: `${item.depth * 20}px` }"
            >
              <!-- Connector line for sub-items -->
              <div v-if="item.depth > 0" class="flex items-stretch shrink-0 mr-1">
                <div class="flex flex-col items-center w-3.5">
                  <div class="w-px flex-1 bg-border/40"></div>
                  <div class="w-2.5 h-px bg-border/40 self-center shrink-0"></div>
                  <div class="w-px flex-1 bg-transparent"></div>
                </div>
              </div>

              <!-- Node hover group -->
              <div class="group flex-1 flex flex-col mb-0.5">
                <div class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-elevated transition-colors duration-100">
                  <!-- Folder icon -->
                  <svg
                    class="w-4 h-4 shrink-0"
                    :class="item.depth === 0 ? 'text-tinder-green' : 'text-text-muted'"
                    viewBox="0 0 24 24" fill="none" stroke="currentColor"
                    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
                  >
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>

                  <!-- Name: view or edit -->
                  <div class="flex-1 min-w-0">
                    <input
                      v-if="editingKey === item.node._key && editingField === 'name'"
                      v-model="item.node.name"
                      type="text"
                      :placeholder="item.depth === 0 ? '顶级目录名称，例如：大模型' : '子目录名称，例如：推理优化'"
                      class="w-full text-sm bg-bg-card border border-tinder-green/40 rounded-md px-2 py-0.5 text-text-primary placeholder:text-text-muted/60 focus:outline-none focus:ring-1 focus:ring-tinder-green/50"
                      :data-edit-key="item.node._key"
                      data-edit-field="name"
                      @keydown="handleEditKeydown"
                      @blur="stopEdit"
                    />
                    <button
                      v-else
                      type="button"
                      class="text-sm text-left w-full truncate transition-colors"
                      :class="item.node.name ? (item.depth === 0 ? 'text-text-primary font-medium' : 'text-text-secondary') : 'text-text-muted/50 italic'"
                      @click="startEdit(item.node._key, 'name')"
                    >
                      {{ item.node.name || (item.depth === 0 ? '点击填写目录名称…' : '点击填写子目录名称…') }}
                    </button>
                  </div>

                  <!-- Description toggle -->
                  <button
                    type="button"
                    :title="expandedDescKeys.has(item.node._key) ? '收起描述' : (item.node.description ? item.node.description : '添加描述')"
                    class="shrink-0 w-5 h-5 flex items-center justify-center rounded transition-colors"
                    :class="item.node.description
                      ? 'text-tinder-green/60 hover:text-tinder-green'
                      : 'text-text-muted/40 hover:text-text-muted opacity-0 group-hover:opacity-100'"
                    @click="toggleDesc(item.node._key)"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/>
                    </svg>
                  </button>

                  <!-- Sync badge -->
                  <span
                    v-if="item.node.folder_id"
                    class="shrink-0 text-[10px] text-tinder-green/70 px-1.5 py-0.5 rounded bg-tinder-green/10 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity"
                    title="已同步到知识库"
                  >已同步</span>
                  <span
                    v-else
                    class="shrink-0 text-[10px] text-text-muted/50 px-1.5 py-0.5 rounded bg-bg-elevated border border-dashed border-border/60 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity"
                    title="需要点击「同步」创建对应文件夹"
                  >未同步</span>

                  <!-- Action buttons (hover reveal) -->
                  <div class="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <!-- Add child -->
                    <button
                      type="button"
                      class="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-tinder-green hover:bg-tinder-green/10 transition-colors"
                      title="添加子目录"
                      @click="addChild(item.node)"
                    >
                      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                        <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
                      </svg>
                    </button>
                    <!-- Move up -->
                    <button
                      type="button"
                      :disabled="item.siblings.indexOf(item.node) === 0"
                      class="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-primary disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
                      title="上移"
                      @click="moveUp(item.node, item.siblings)"
                    >
                      <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
                    </button>
                    <!-- Move down -->
                    <button
                      type="button"
                      :disabled="item.siblings.indexOf(item.node) >= item.siblings.length - 1"
                      class="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-primary disabled:opacity-20 disabled:cursor-not-allowed transition-colors"
                      title="下移"
                      @click="moveDown(item.node, item.siblings)"
                    >
                      <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                    </button>
                    <!-- Delete -->
                    <button
                      type="button"
                      class="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                      :title="item.node.children.length ? `删除此目录及其 ${item.node.children.length} 个子目录` : '删除'"
                      @click="removeNode(item.node, item.siblings)"
                    >
                      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                        <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                      </svg>
                    </button>
                  </div>
                </div>

                <!-- Description row (expandable) -->
                <Transition
                  enter-active-class="transition duration-150 ease-out"
                  enter-from-class="opacity-0 -translate-y-1"
                  enter-to-class="opacity-100 translate-y-0"
                  leave-active-class="transition duration-100 ease-in"
                  leave-from-class="opacity-100 translate-y-0"
                  leave-to-class="opacity-0 -translate-y-1"
                >
                  <div
                    v-if="expandedDescKeys.has(item.node._key)"
                    class="ml-6 mb-1 pl-2 border-l border-border/40"
                  >
                    <input
                      v-model="item.node.description"
                      type="text"
                      :placeholder="item.depth === 0 ? '描述（可选）：帮助 AI 理解归类依据，例如：关于大型语言模型的论文' : '描述（可选）：关键词或一句话说明'"
                      class="w-full text-xs bg-transparent border-0 py-1 text-text-secondary placeholder:text-text-muted/50 focus:outline-none"
                      :data-edit-key="item.node._key"
                      data-edit-field="description"
                      @keydown.enter.prevent="stopEdit"
                      @blur="_scheduleAutoSave"
                    />
                  </div>
                </Transition>
              </div>
            </div>
          </div>
        </div>

        <!-- Diff warnings -->
        <div v-if="folderDiffWarnings.length > 0" class="px-5 py-3 border-t border-border/40 space-y-1.5">
          <div
            v-for="(warn, i) in folderDiffWarnings"
            :key="i"
            class="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/20 text-xs text-amber-400"
          >
            <svg class="w-3.5 h-3.5 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            {{ warn }}
          </div>
        </div>

        <!-- ── Action bar ── -->
        <div class="px-5 py-3.5 border-t border-border/50 flex flex-wrap items-center gap-3">
          <!-- Status messages (left) -->
          <div class="flex items-center gap-2 text-xs">
            <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition-opacity duration-300" leave-active-class="transition-opacity duration-300">
              <span v-if="reclassifyMsg" class="text-tinder-green flex items-center gap-1">
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                {{ reclassifyMsg }}
              </span>
            </Transition>
          </div>

          <!-- Action buttons (right) -->
          <div class="flex flex-wrap items-center gap-2 ml-auto">
            <!-- Sync button -->
            <button
              type="button"
              :disabled="syncingFolders || folderTree.length === 0"
              class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary text-xs hover:border-tinder-green/40 hover:text-tinder-green transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              @click="handleSyncFolders"
            >
              <svg
                class="w-3.5 h-3.5"
                :class="syncingFolders ? 'animate-spin' : ''"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <template v-if="syncingFolders">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </template>
                <template v-else>
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </template>
              </svg>
              {{ syncingFolders ? '同步中…' : '同步目录' }}
            </button>

            <!-- Reclassify button -->
            <button
              type="button"
              :disabled="reclassifying || !form.enabled"
              class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-secondary text-xs hover:border-amber-400/40 hover:text-amber-400 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              @click="handleReclassifyAll"
            >
              <svg
                class="w-3.5 h-3.5"
                :class="reclassifying ? 'animate-spin' : ''"
                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              >
                <template v-if="reclassifying">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </template>
                <template v-else>
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </template>
              </svg>
              {{ reclassifying ? '队列中…' : '全部重新分类' }}
            </button>

            <!-- Divider -->
            <div class="w-px h-5 bg-border/50"></div>

            <!-- Save button -->
            <button
              type="button"
              :disabled="saving"
              class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-tinder-green hover:bg-tinder-green/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
              @click="handleSave"
            >
              <svg v-if="saving" class="w-3.5 h-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              {{ saving ? '保存中…' : '保存设置' }}
            </button>

            <!-- Save feedback -->
            <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition-opacity duration-300" leave-active-class="transition-opacity duration-300">
              <span v-if="saveSuccess" class="text-xs text-tinder-green flex items-center gap-1">
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                已保存
              </span>
            </Transition>
            <span v-if="saveError" class="text-xs text-red-400">{{ saveError }}</span>
          </div>
        </div>
      </div>

      <!-- Auto-save hint -->
      <p class="text-[11px] text-text-muted/40 text-right mt-2 px-1">
        开关、阈值和模型的变更会自动保存
      </p>

    </template>
  </div>
</template>
