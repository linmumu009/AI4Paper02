<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  createAnnouncement,
  deleteAnnouncement,
  fetchAnnouncements,
  updateAnnouncement,
} from '../../api'
import type { Announcement, AnnouncementTag } from '../../types/paper'
import { getApiErrorMessage, reportClientError } from '../../utils/apiError'

const announcements = ref<Announcement[]>([])
const loading = ref(false)
const errorMessage = ref('')
const showForm = ref(false)
const editingAnnouncement = ref<Announcement | null>(null)
const formSaving = ref(false)
const formError = ref('')
const form = ref({
  title: '',
  content: '',
  tag: 'general' as AnnouncementTag,
  is_pinned: false,
})

const tagOptions: { label: string; value: AnnouncementTag }[] = [
  { label: '一般', value: 'general' },
  { label: '重要', value: 'important' },
  { label: '更新', value: 'update' },
  { label: '维护', value: 'maintenance' },
]

function tagLabel(tag: string): string {
  return ({ important: '重要', general: '一般', update: '更新', maintenance: '维护' })[tag] || tag
}

function tagClass(tag: string): string {
  return ({
    important: 'bg-red-500/15 text-red-400 border-red-500/20',
    general: 'bg-gray-500/15 text-text-muted border-gray-500/20',
    update: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    maintenance: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  })[tag] || 'bg-gray-500/15 text-text-muted border-gray-500/20'
}

function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime())
    ? timestamp
    : date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

async function loadAnnouncements() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchAnnouncements({ limit: 100 })
    announcements.value = response.announcements
  } catch (error) {
    reportClientError('admin.announcements.load', error, '加载公告失败')
    errorMessage.value = getApiErrorMessage(error, '加载公告失败')
  } finally {
    loading.value = false
  }
}

function openNewForm() {
  editingAnnouncement.value = null
  form.value = { title: '', content: '', tag: 'general', is_pinned: false }
  formError.value = ''
  showForm.value = true
}

function openEditForm(item: Announcement) {
  editingAnnouncement.value = item
  form.value = {
    title: item.title,
    content: item.content,
    tag: item.tag,
    is_pinned: item.is_pinned,
  }
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingAnnouncement.value = null
}

async function saveForm() {
  if (!form.value.title.trim()) {
    formError.value = '标题不能为空'
    return
  }
  if (!form.value.content.trim()) {
    formError.value = '内容不能为空'
    return
  }

  formSaving.value = true
  formError.value = ''
  try {
    const payload = {
      title: form.value.title.trim(),
      content: form.value.content.trim(),
      tag: form.value.tag,
      is_pinned: form.value.is_pinned,
    }
    if (editingAnnouncement.value) {
      await updateAnnouncement(editingAnnouncement.value.id, payload)
    } else {
      await createAnnouncement(payload)
    }
    closeForm()
    await loadAnnouncements()
  } catch (error) {
    reportClientError('admin.announcements.save', error, '保存失败')
    formError.value = getApiErrorMessage(error, '保存失败')
  } finally {
    formSaving.value = false
  }
}

async function removeAnnouncement(item: Announcement) {
  if (!window.confirm(`确定要删除公告「${item.title}」吗？`)) return
  try {
    await deleteAnnouncement(item.id)
    await loadAnnouncements()
  } catch (error) {
    reportClientError('admin.announcements.delete', error, '删除失败')
    errorMessage.value = getApiErrorMessage(error, '删除失败')
  }
}

onMounted(loadAnnouncements)
</script>

<template>
  <section class="flex-1 flex flex-col p-3 sm:p-6 overflow-hidden" aria-labelledby="announcements-title">
    <div class="flex items-center justify-between mb-4 shrink-0">
      <div>
        <h1 id="announcements-title" class="text-lg font-bold text-text-primary">📢 公告管理</h1>
        <p class="text-xs text-text-muted mt-0.5">发布和管理平台公告通知</p>
      </div>
      <button type="button" class="px-4 py-2 rounded-lg text-sm font-semibold text-white cursor-pointer hover:opacity-90 transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fd267a]" style="background: linear-gradient(135deg, #fd267a, #ff6036);" @click="openNewForm">+ 新建公告</button>
    </div>

    <div v-if="errorMessage" class="mb-3 rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2.5 text-sm text-red-400 shrink-0" role="alert">
      {{ errorMessage }}
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12" role="status">
      <svg class="w-6 h-6 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
      </svg>
      <span class="sr-only">正在加载公告</span>
    </div>

    <div v-else-if="announcements.length === 0" class="text-center py-12 text-sm text-text-muted">暂无公告</div>

    <div v-else class="flex-1 overflow-y-auto">
      <div class="space-y-3">
        <article v-for="item in announcements" :key="item.id" class="rounded-xl border bg-bg-card p-4 flex items-start gap-4" :class="item.tag === 'important' ? 'border-red-500/25' : 'border-border'">
          <div v-if="item.is_pinned" class="shrink-0 mt-0.5" title="置顶公告">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#fd267a]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 3a1 1 0 0 1 .707 1.707L13 8.414V15a1 1 0 0 1-.553.894l-4 2A1 1 0 0 1 7 17v-5.586l-3.707-3.707A1 1 0 0 1 4 7h12z"/></svg>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <h2 class="text-sm font-semibold text-text-primary">{{ item.title }}</h2>
              <span class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium shrink-0" :class="tagClass(item.tag)">{{ tagLabel(item.tag) }}</span>
            </div>
            <p class="text-xs text-text-muted line-clamp-2 mb-1.5">{{ item.content }}</p>
            <time class="text-[10px] text-text-muted" :datetime="item.created_at">{{ formatDate(item.created_at) }}</time>
          </div>
          <div class="flex gap-2 shrink-0">
            <button type="button" class="px-3 py-1.5 rounded-lg text-xs border border-border text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer transition-colors" :aria-label="`编辑公告：${item.title}`" @click="openEditForm(item)">编辑</button>
            <button type="button" class="px-3 py-1.5 rounded-lg text-xs border border-red-500/20 text-red-400 hover:bg-red-500/10 cursor-pointer transition-colors" :aria-label="`删除公告：${item.title}`" @click="removeAnnouncement(item)">删除</button>
          </div>
        </article>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="announcement-dialog-title">
        <button type="button" class="absolute inset-0 bg-black/60" aria-label="关闭公告表单" @click="closeForm"></button>
        <div class="relative w-full max-w-lg bg-bg-card rounded-2xl border border-border shadow-2xl overflow-hidden">
          <div class="px-6 py-5 border-b border-border flex items-center justify-between">
            <h2 id="announcement-dialog-title" class="text-base font-semibold text-text-primary">{{ editingAnnouncement ? '编辑公告' : '新建公告' }}</h2>
            <button type="button" class="text-text-muted hover:text-text-primary transition-colors cursor-pointer" aria-label="关闭" @click="closeForm">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
            <div>
              <label for="announcement-title" class="block text-xs font-medium text-text-secondary mb-1.5">标题 <span class="text-red-400">*</span></label>
              <input id="announcement-title" v-model="form.title" type="text" maxlength="100" placeholder="公告标题" class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors" />
            </div>
            <div>
              <label for="announcement-content" class="block text-xs font-medium text-text-secondary mb-1.5">内容 <span class="text-red-400">*</span></label>
              <textarea id="announcement-content" v-model="form.content" rows="6" maxlength="5000" placeholder="公告详细内容..." class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors resize-y"></textarea>
            </div>
            <div class="flex gap-4">
              <div class="flex-1">
                <label for="announcement-tag" class="block text-xs font-medium text-text-secondary mb-1.5">标签</label>
                <select id="announcement-tag" v-model="form.tag" class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors cursor-pointer">
                  <option v-for="option in tagOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
              <div class="flex-1">
                <span class="block text-xs font-medium text-text-secondary mb-1.5">置顶</span>
                <button type="button" class="w-full flex items-center gap-2 px-3 py-2.5 bg-bg-elevated border border-border rounded-lg cursor-pointer select-none" role="switch" :aria-checked="form.is_pinned" @click="form.is_pinned = !form.is_pinned">
                  <span class="w-9 h-5 rounded-full transition-colors relative" :class="form.is_pinned ? 'bg-[#fd267a]' : 'bg-border'"><span class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform" :class="form.is_pinned ? 'translate-x-4' : 'translate-x-0.5'"></span></span>
                  <span class="text-sm text-text-secondary">{{ form.is_pinned ? '已置顶' : '不置顶' }}</span>
                </button>
              </div>
            </div>
            <p v-if="formError" class="text-xs text-red-400" role="alert">{{ formError }}</p>
          </div>
          <div class="px-6 py-4 border-t border-border flex items-center justify-end gap-3">
            <button type="button" class="px-4 py-2 rounded-lg text-sm border border-border text-text-secondary hover:bg-bg-hover cursor-pointer transition-colors" @click="closeForm">取消</button>
            <button type="button" class="px-5 py-2 rounded-lg text-sm font-semibold text-white cursor-pointer hover:opacity-90 transition-all disabled:opacity-50" style="background: linear-gradient(135deg, #fd267a, #ff6036);" :disabled="formSaving" @click="saveForm">{{ formSaving ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>
