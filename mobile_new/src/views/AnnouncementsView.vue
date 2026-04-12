<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { fetchAnnouncements, markAllAnnouncementsRead, createAnnouncement, updateAnnouncement, deleteAnnouncement } from '@shared/api'
import type { Announcement } from '@shared/types/auth'
import { isAdmin } from '@shared/stores/auth'
import { showToast, showDialog } from 'vant'

defineOptions({ name: 'AnnouncementsView' })

const router = useRouter()
const announcements = ref<Announcement[]>([])
const loading = ref(true)
const error = ref('')
const expanded = ref<Set<number>>(new Set())

// Admin CRUD state
const formVisible = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
  title: '',
  content: '',
  tag: 'general' as string,
  is_pinned: false,
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchAnnouncements({ limit: 50 })
    announcements.value = res.announcements
    markAllAnnouncementsRead().catch(() => {/* best-effort */})
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function toggle(id: number) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

function openCreate() {
  editingId.value = null
  form.value = { title: '', content: '', tag: 'general', is_pinned: false }
  formVisible.value = true
}

function openEdit(ann: Announcement) {
  editingId.value = ann.id
  form.value = {
    title: ann.title,
    content: ann.content,
    tag: ann.tag ?? 'general',
    is_pinned: ann.is_pinned ?? false,
  }
  formVisible.value = true
}

async function confirmSave() {
  if (!form.value.title.trim() || !form.value.content.trim()) { showToast('标题和内容不能为空'); return }
  saving.value = true
  try {
    const payload = { title: form.value.title.trim(), content: form.value.content, tag: form.value.tag, is_pinned: form.value.is_pinned }
    if (editingId.value !== null) {
      const res = await updateAnnouncement(editingId.value, payload)
      const idx = announcements.value.findIndex((a) => a.id === editingId.value)
      if (idx >= 0) announcements.value[idx] = res.announcement ?? announcements.value[idx]
    } else {
      const res = await createAnnouncement(payload)
      if (res.announcement) announcements.value.unshift(res.announcement)
    }
    formVisible.value = false
    showToast(editingId.value !== null ? '已更新' : '已发布')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(ann: Announcement) {
  try {
    await showDialog({ title: '删除公告', message: `确定删除「${ann.title}」？`, confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonColor: 'var(--color-tinder-pink)' })
    await deleteAnnouncement(ann.id)
    announcements.value = announcements.value.filter((a) => a.id !== ann.id)
    showToast('已删除')
  } catch { /* cancelled */ }
}

const TAG_COLORS: Record<string, string> = {
  update: 'bg-tinder-blue/15 text-tinder-blue',
  maintenance: 'bg-tinder-gold/15 text-tinder-gold',
  feature: 'bg-tinder-green/15 text-tinder-green',
  alert: 'bg-tinder-pink/15 text-tinder-pink',
  general: 'bg-bg-elevated text-text-muted',
}
const TAG_LABELS: Record<string, string> = {
  update: '更新', maintenance: '维护', feature: '新功能', alert: '紧急', general: '通知',
}
const TAGS = ['general', 'update', 'feature', 'maintenance', 'alert']
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="系统公告" @back="router.back()">
      <template v-if="isAdmin" #right>
        <button
          type="button"
          class="w-10 h-10 flex items-center justify-center text-tinder-pink active:opacity-70"
          @click="openCreate"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" class="flex-1" message="加载公告…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <div v-else class="flex-1 overflow-y-auto pb-4">
      <div v-if="announcements.length === 0" class="flex flex-col items-center justify-center h-40 text-text-muted">
        <p class="text-sm">暂无公告</p>
      </div>
      <div v-for="ann in announcements" :key="ann.id" class="border-b border-border">
        <div class="flex items-start gap-3 px-4 py-3.5">
          <button
            type="button"
            class="flex-1 min-w-0 text-left active:opacity-80"
            @click="toggle(ann.id)"
          >
            <div class="flex items-center gap-2 mb-1.5">
              <span v-if="ann.is_pinned" class="text-[10px] bg-tinder-gold/20 text-tinder-gold px-1.5 py-0.5 rounded-full">📌</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded-full" :class="TAG_COLORS[ann.tag] ?? TAG_COLORS.general">
                {{ TAG_LABELS[ann.tag] ?? ann.tag }}
              </span>
              <span v-if="!ann.is_read" class="w-2 h-2 rounded-full bg-tinder-pink shrink-0" />
            </div>
            <p class="text-[14px] font-semibold text-text-primary leading-snug">{{ ann.title }}</p>
            <p class="text-[11px] text-text-muted mt-1">{{ new Date(ann.created_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }) }}</p>
          </button>

          <!-- Admin action buttons -->
          <div v-if="isAdmin" class="flex gap-1 shrink-0">
            <button
              type="button"
              class="w-8 h-8 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-text-secondary active:bg-bg-hover"
              @click="openEdit(ann)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
            <button
              type="button"
              class="w-8 h-8 rounded-xl bg-tinder-pink/10 border border-tinder-pink/20 flex items-center justify-center text-tinder-pink active:bg-tinder-pink/20"
              @click="confirmDelete(ann)"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </button>
          </div>

          <svg class="shrink-0 text-text-muted transition-transform mt-1" :class="expanded.has(ann.id) ? 'rotate-90' : ''" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" @click="toggle(ann.id)"><polyline points="9 18 15 12 9 6" /></svg>
        </div>
        <div v-if="expanded.has(ann.id)" class="px-4 pb-4">
          <MarkdownRenderer :content="ann.content" />
        </div>
      </div>
    </div>

    <!-- Create/Edit Sheet -->
    <BottomSheet :visible="formVisible" :title="editingId !== null ? '编辑公告' : '发布公告'" height="90dvh" @close="formVisible = false">
      <div class="px-5 pb-8 pt-2 space-y-4 overflow-y-auto">
        <div>
          <label class="form-label">标题 <span class="text-tinder-pink">*</span></label>
          <input v-model="form.title" type="text" class="input-field" placeholder="公告标题" maxlength="100" />
        </div>

        <div>
          <label class="form-label">标签</label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="tag in TAGS"
              :key="tag"
              type="button"
              class="px-3 py-1.5 rounded-full text-[12px] border transition-colors"
              :class="form.tag === tag ? (TAG_COLORS[tag] ?? TAG_COLORS.general) + ' border-current' : 'border-border text-text-muted'"
              @click="form.tag = tag"
            >{{ TAG_LABELS[tag] ?? tag }}</button>
          </div>
        </div>

        <!-- Pinned toggle -->
        <div class="flex items-center justify-between">
          <p class="text-[14px] text-text-primary">置顶</p>
          <button
            type="button"
            class="relative inline-flex h-7 w-12 items-center rounded-full transition-colors"
            :class="form.is_pinned ? 'bg-tinder-gold' : 'bg-bg-elevated border border-border'"
            @click="form.is_pinned = !form.is_pinned"
          >
            <span class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform" :class="form.is_pinned ? 'translate-x-6' : 'translate-x-1'" />
          </button>
        </div>

        <div class="flex-1">
          <label class="form-label">内容（支持 Markdown）<span class="text-tinder-pink">*</span></label>
          <textarea
            v-model="form.content"
            class="input-field resize-none font-mono text-[13px]"
            placeholder="公告内容，支持 Markdown 格式…"
            style="min-height: 200px;"
          />
        </div>

        <button
          type="button"
          class="btn-primary"
          :disabled="saving || !form.title.trim() || !form.content.trim()"
          @click="confirmSave"
        >
          {{ saving ? '保存中…' : (editingId !== null ? '更新' : '发布') }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}
</style>
