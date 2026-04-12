<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchAnnouncementById } from '../api'
import type { Announcement } from '../types/paper'

const props = defineProps<{ id: string }>()
const router = useRouter()

const announcement = ref<Announcement | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

function announcementTagLabel(tag: string): string {
  const map: Record<string, string> = {
    important: '重要', general: '一般', update: '更新', maintenance: '维护',
  }
  return map[tag] || tag
}

function announcementTagClass(tag: string): string {
  const map: Record<string, string> = {
    important: 'bg-red-500/15 text-red-400 border-red-500/20',
    general: 'bg-gray-500/15 text-text-muted border-gray-500/20',
    update: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
    maintenance: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
  }
  return map[tag] || 'bg-gray-500/15 text-text-muted border-gray-500/20'
}

function formatDate(ts: string): string {
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  } catch {
    return ts
  }
}

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/profile?tab=announcements')
  }
}

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const res = await fetchAnnouncementById(Number(props.id))
    announcement.value = res.announcement
  } catch {
    error.value = '公告加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="min-h-screen bg-bg-base">
    <div class="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      <!-- Back button -->
      <button
        class="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors mb-6 bg-transparent border-none cursor-pointer px-0"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        返回
      </button>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-24">
        <svg class="w-6 h-6 animate-spin text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
        </svg>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="rounded-xl border border-red-500/25 bg-red-500/10 px-5 py-4 text-sm text-red-400">
        {{ error }}
      </div>

      <!-- Content -->
      <div
        v-else-if="announcement"
        class="rounded-xl border bg-bg-card overflow-hidden"
        :class="announcement.tag === 'important' ? 'border-red-500/25' : 'border-border'"
      >
        <!-- Header -->
        <div class="px-6 py-5 border-b border-border/50">
          <div class="flex items-start gap-3">
            <!-- Pin icon -->
            <div v-if="announcement.is_pinned" class="shrink-0 mt-0.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#fd267a]" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16 3a1 1 0 0 1 .707 1.707L13 8.414V15a1 1 0 0 1-.553.894l-4 2A1 1 0 0 1 7 17v-5.586l-3.707-3.707A1 1 0 0 1 4 7h12z"/>
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap mb-2">
                <h1 class="text-base font-semibold text-text-primary">{{ announcement.title }}</h1>
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded-full border font-medium shrink-0"
                  :class="announcementTagClass(announcement.tag)"
                >{{ announcementTagLabel(announcement.tag) }}</span>
              </div>
              <p class="text-xs text-text-muted">{{ formatDate(announcement.created_at) }}</p>
            </div>
          </div>
        </div>

        <!-- Body -->
        <div class="px-6 py-5">
          <p class="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">{{ announcement.content }}</p>
        </div>
      </div>

      <!-- Not found -->
      <div v-else class="text-center py-24 text-sm text-text-muted">
        公告不存在
      </div>
    </div>
  </div>
</template>
