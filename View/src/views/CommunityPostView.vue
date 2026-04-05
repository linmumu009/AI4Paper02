<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import CommunitySidebar from '../components/CommunitySidebar.vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import {
  fetchCommunityPost,
  updateCommunityPost,
  deleteCommunityPost,
  createCommunityReply,
  updateCommunityReply,
  deleteCommunityReply,
  toggleCommunityLike,
  pinCommunityPost,
  closeCommunityPost,
  type CommunityPost,
  type CommunityReply,
} from '../api/index'
import { isAuthenticated, currentUser, isAdmin } from '../stores/auth'

const props = defineProps<{ id: string }>()
const router = useRouter()

// ---------------------------------------------------------------------------
// Sidebar state (mirrors DailyDigest pattern)
// ---------------------------------------------------------------------------
const mql = window.matchMedia('(min-width: 1024px)')
const showSidebar = ref(mql.matches)

function onMqlChange(e: MediaQueryListEvent) {
  showSidebar.value = e.matches
}
mql.addEventListener('change', onMqlChange)

onBeforeUnmount(() => {
  mql.removeEventListener('change', onMqlChange)
})

// Navigate to community list with optional category filter
function navigateToCommunity(category: string) {
  router.push({ path: '/community', query: category ? { category } : {} })
}

// Markdown renderer
const md = new MarkdownIt({ html: false, linkify: true, breaks: true }).use(texmath, {
  engine: katex,
  delimiters: 'dollars',
  katexOptions: { throwOnError: false },
})

function renderMd(text: string): string {
  return md.render(text || '')
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const post = ref<CommunityPost | null>(null)
const loading = ref(true)
const error = ref('')

const replyContent = ref('')
const submittingReply = ref(false)
const replyError = ref('')

// Inline nested reply state
const replyingToReply = ref<CommunityReply | null>(null)
const inlineReplyContent = ref('')
const submittingInlineReply = ref(false)
const inlineReplyError = ref('')

// Edit post
const showEditPost = ref(false)
const editPostData = ref({ category: '', title: '', content: '' })
const savingPost = ref(false)
const editPostError = ref('')

// Edit reply
const editingReplyId = ref<number | null>(null)
const editReplyContent = ref('')
const savingReply = ref(false)

// Confirm delete dialog
const confirmDeleteTarget = ref<{ type: 'post' | 'reply'; id: number } | null>(null)
const deleting = ref(false)

const categoryMeta: Record<string, { label: string; color: string }> = {
  question:   { label: '提问',  color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  discussion: { label: '讨论',  color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
  sharing:    { label: '分享',  color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' },
  help:       { label: '求助',  color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' },
}

const categories = [
  { value: 'question', label: '提问' },
  { value: 'discussion', label: '讨论' },
  { value: 'sharing', label: '分享' },
  { value: 'help', label: '求助' },
]

const postId = computed(() => parseInt(props.id, 10))

const canEditPost = computed(() => {
  if (!post.value || !currentUser.value) return false
  return post.value.user_id === currentUser.value.id || isAdmin.value
})

// ---------------------------------------------------------------------------
// Reply tree helpers
// ---------------------------------------------------------------------------
const topLevelReplies = computed(() =>
  post.value?.replies?.filter(r => !r.parent_reply_id) ?? []
)

function getChildReplies(parentId: number): CommunityReply[] {
  return post.value?.replies?.filter(r => r.parent_reply_id === parentId) ?? []
}

function openInlineReply(reply: CommunityReply) {
  if (replyingToReply.value?.id === reply.id) {
    replyingToReply.value = null
  } else {
    replyingToReply.value = reply
    inlineReplyContent.value = ''
    inlineReplyError.value = ''
  }
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------
async function loadPost() {
  loading.value = true
  error.value = ''
  try {
    post.value = await fetchCommunityPost(postId.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPost()
})

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString('zh-CN')
}

function avatar(username: string | null | undefined): string {
  return (username || '?').charAt(0).toUpperCase()
}

const AVATAR_COLORS = [
  '#7c3aed', '#2563eb', '#059669', '#d97706', '#dc2626',
  '#db2777', '#0891b2', '#65a30d', '#9333ea', '#ea580c',
]
function strHash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}
function avatarColor(username: string | null | undefined): string {
  return AVATAR_COLORS[strHash(username || '') % AVATAR_COLORS.length]
}

// ---------------------------------------------------------------------------
// Like
// ---------------------------------------------------------------------------
async function likePost() {
  if (!post.value || !isAuthenticated.value) return
  const r = await toggleCommunityLike('post', post.value.id)
  post.value.like_count = r.like_count
  post.value.user_liked = r.liked
}

async function likeReply(reply: CommunityReply) {
  if (!isAuthenticated.value) return
  const r = await toggleCommunityLike('reply', reply.id)
  reply.like_count = r.like_count
  reply.user_liked = r.liked
}

// ---------------------------------------------------------------------------
// Reply submit
// ---------------------------------------------------------------------------
async function submitReply() {
  if (!replyContent.value.trim()) return
  replyError.value = ''
  submittingReply.value = true
  try {
    const newReply = await createCommunityReply(postId.value, { content: replyContent.value.trim() })
    post.value?.replies?.push(newReply)
    if (post.value) post.value.reply_count += 1
    replyContent.value = ''
  } catch (e: any) {
    replyError.value = e?.response?.data?.detail || '回复失败'
  } finally {
    submittingReply.value = false
  }
}

async function submitInlineReply() {
  if (!replyingToReply.value || !inlineReplyContent.value.trim()) return
  inlineReplyError.value = ''
  submittingInlineReply.value = true
  const targetReply = replyingToReply.value
  // Always hang sub-replies under the top-level reply
  const parentId = targetReply.parent_reply_id ?? targetReply.id
  try {
    const newReply = await createCommunityReply(postId.value, {
      content: inlineReplyContent.value.trim(),
      parent_reply_id: parentId,
    })
    post.value?.replies?.push(newReply)
    if (post.value) post.value.reply_count += 1
    inlineReplyContent.value = ''
    replyingToReply.value = null
  } catch (e: any) {
    inlineReplyError.value = e?.response?.data?.detail || '回复失败'
  } finally {
    submittingInlineReply.value = false
  }
}

// ---------------------------------------------------------------------------
// Edit post
// ---------------------------------------------------------------------------
function openEditPost() {
  if (!post.value) return
  editPostData.value = {
    category: post.value.category,
    title: post.value.title,
    content: post.value.content || '',
  }
  editPostError.value = ''
  showEditPost.value = true
}

async function saveEditPost() {
  if (!post.value) return
  editPostError.value = ''
  if (!editPostData.value.title.trim()) { editPostError.value = '请填写标题'; return }
  if (!editPostData.value.content.trim()) { editPostError.value = '请填写内容'; return }
  savingPost.value = true
  try {
    const updated = await updateCommunityPost(post.value.id, editPostData.value)
    post.value = { ...post.value, ...updated, replies: post.value.replies }
    showEditPost.value = false
  } catch (e: any) {
    editPostError.value = e?.response?.data?.detail || '保存失败'
  } finally {
    savingPost.value = false
  }
}

// ---------------------------------------------------------------------------
// Edit reply
// ---------------------------------------------------------------------------
function openEditReply(reply: CommunityReply) {
  editingReplyId.value = reply.id
  editReplyContent.value = reply.content
}

async function saveEditReply(reply: CommunityReply) {
  if (!editReplyContent.value.trim()) return
  savingReply.value = true
  try {
    const updated = await updateCommunityReply(reply.id, { content: editReplyContent.value.trim() })
    reply.content = updated.content
    reply.updated_at = updated.updated_at
    editingReplyId.value = null
  } catch (e: any) {
    /* swallow for now */
  } finally {
    savingReply.value = false
  }
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
function confirmDelete(type: 'post' | 'reply', id: number) {
  confirmDeleteTarget.value = { type, id }
}

async function doDelete() {
  if (!confirmDeleteTarget.value) return
  deleting.value = true
  try {
    const { type, id } = confirmDeleteTarget.value
    if (type === 'post') {
      await deleteCommunityPost(id)
      router.replace('/community')
    } else {
      await deleteCommunityReply(id)
      if (post.value) {
        post.value.replies = post.value.replies?.filter(r => r.id !== id)
        post.value.reply_count = Math.max(0, post.value.reply_count - 1)
      }
    }
    confirmDeleteTarget.value = null
  } catch (e: any) {
    /* silently fail, retry */
  } finally {
    deleting.value = false
  }
}

// ---------------------------------------------------------------------------
// Admin actions
// ---------------------------------------------------------------------------
async function togglePin() {
  if (!post.value) return
  const result = await pinCommunityPost(post.value.id, !post.value.is_pinned)
  post.value.is_pinned = result.is_pinned
}

async function toggleClose() {
  if (!post.value) return
  const result = await closeCommunityPost(post.value.id, !post.value.is_closed)
  post.value.is_closed = result.is_closed
}

function canEditReply(reply: CommunityReply): boolean {
  if (!currentUser.value) return false
  return reply.user_id === currentUser.value.id || isAdmin.value
}
</script>

<template>
  <div class="h-full flex relative">

    <!-- Sidebar overlay backdrop (mobile only) -->
    <Transition name="fade">
      <div
        v-if="showSidebar"
        class="fixed inset-0 z-20 bg-black/60 lg:hidden"
        @click="showSidebar = false"
      />
    </Transition>

    <!-- ===== Sidebar ===== -->
    <Transition name="sidebar-slide">
      <div
        v-show="showSidebar"
        class="shrink-0 z-30 h-full fixed lg:relative inset-y-0 left-0 transition-transform duration-300 ease-in-out"
      >
        <CommunitySidebar
          :current-category="post?.category || ''"
          current-sort="latest"
          :show-sidebar="showSidebar"
          @update:current-category="navigateToCommunity($event)"
          @update:current-sort="router.push('/community')"
          @toggle-sidebar="showSidebar = false"
          @open-create-dialog="router.push('/community')"
        />
      </div>
    </Transition>

    <!-- Universal "open sidebar" button -->
    <Transition name="fade">
      <button
        v-if="!showSidebar"
        class="fixed top-[100px] left-0 z-10 flex items-center justify-center w-11 h-11 bg-bg-card border border-border border-l-0 rounded-r-lg shadow-sm text-text-muted/60 hover:text-text-primary hover:bg-bg-elevated transition-colors cursor-pointer"
        title="展开侧边栏"
        @click="showSidebar = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/>
        </svg>
      </button>
    </Transition>

    <!-- ===== Main content ===== -->
    <div class="flex-1 overflow-y-auto min-w-0">
      <!-- Back navigation bar -->
      <div class="border-b border-border bg-bg-card sticky top-0 z-10">
        <div class="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            class="p-1.5 rounded-lg hover:bg-bg-hover transition-colors text-text-muted"
            @click="router.push('/community')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <span class="text-sm text-text-muted">返回社区</span>
        </div>
      </div>

    <div class="max-w-3xl mx-auto px-4 py-6">
      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center gap-3 py-20">
        <svg class="animate-spin h-8 w-8 text-[#fd267a]" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <span class="text-text-muted text-sm">加载中...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center gap-3 py-20 text-center px-8">
        <div class="text-5xl mb-2">⚠️</div>
        <p class="text-text-secondary text-sm">{{ error }}</p>
        <button
          class="px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="loadPost"
        >重试</button>
      </div>

      <template v-else-if="post">
        <!-- Post card -->
        <div class="bg-bg-card border border-border rounded-2xl mb-6">
          <!-- Post header -->
          <div class="px-6 pt-5 pb-4 border-b border-border">
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <!-- Badges -->
                <div class="flex flex-wrap items-center gap-2 mb-2">
                  <span
                    class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                    :class="categoryMeta[post.category]?.color || 'bg-bg-hover text-text-muted'"
                  >{{ categoryMeta[post.category]?.label || post.category }}</span>
                  <span v-if="post.is_pinned" class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-[#fd267a]/10 text-[#fd267a]">置顶</span>
                  <span v-if="post.is_closed" class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-bg-hover text-text-muted">已关闭</span>
                </div>
                <!-- Title -->
                <h1 class="text-xl font-bold text-text-primary leading-snug">{{ post.title }}</h1>
              </div>

              <!-- Actions menu -->
              <div class="flex items-center gap-1 shrink-0">
                <button
                  v-if="canEditPost"
                  class="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted transition-colors text-xs flex items-center gap-1"
                  @click="openEditPost"
                  title="编辑"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button
                  v-if="isAdmin"
                  class="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted transition-colors"
                  :title="post.is_pinned ? '取消置顶' : '置顶'"
                  @click="togglePin"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
                  </svg>
                </button>
                <button
                  v-if="isAdmin"
                  class="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted transition-colors text-xs"
                  :title="post.is_closed ? '重新开放' : '关闭帖子'"
                  @click="toggleClose"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10" /><line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                  </svg>
                </button>
                <button
                  v-if="canEditPost"
                  class="p-1.5 rounded-lg hover:bg-bg-hover text-red-400 transition-colors"
                  title="删除"
                  @click="confirmDelete('post', post.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                  </svg>
                </button>
              </div>
            </div>

            <!-- Author / meta -->
            <div class="flex items-center gap-3 mt-3">
              <div
                class="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                :style="{ backgroundColor: avatarColor(post.username) }"
              >{{ avatar(post.username) }}</div>
              <div>
                <div class="text-sm font-medium text-text-primary">{{ post.username || '匿名' }}</div>
                <div class="text-[11px] text-text-muted">{{ formatTime(post.created_at) }}</div>
              </div>
              <div class="ml-auto flex items-center gap-3 text-[11px] text-text-muted">
                <span class="flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                  {{ post.view_count }}
                </span>
              </div>
            </div>
          </div>

          <!-- Post content (Markdown) -->
          <div
            class="px-6 py-5 prose prose-sm max-w-none text-text-primary"
            v-html="renderMd(post.content || '')"
          />

          <!-- Like bar -->
          <div class="px-6 pb-5 flex items-center gap-3">
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border transition-colors"
              :class="post.user_liked
                ? 'border-[#fd267a] text-[#fd267a] bg-[#fd267a]/5'
                : 'border-border text-text-muted hover:border-[#fd267a]/50 hover:text-[#fd267a]'"
              @click="likePost"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" :fill="post.user_liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              <span>{{ post.like_count }}</span>
            </button>
            <span class="text-xs text-text-muted">{{ post.reply_count }} 条回复</span>
          </div>
        </div>

        <!-- Replies -->
        <div v-if="topLevelReplies.length > 0" class="space-y-3 mb-6">
          <div
            v-for="(reply, idx) in topLevelReplies"
            :key="reply.id"
            class="bg-bg-card border border-border rounded-2xl px-5 py-4"
          >
            <!-- Reply header -->
            <div class="flex items-start justify-between gap-2 mb-3">
              <div class="flex items-center gap-2">
                <div
                  class="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                  :style="{ backgroundColor: avatarColor(reply.username) }"
                >{{ avatar(reply.username) }}</div>
                <div>
                  <span class="text-xs font-medium text-text-primary">{{ reply.username || '匿名' }}</span>
                  <span class="ml-2 text-[11px] text-text-muted">#{{ idx + 1 }} · {{ formatTime(reply.created_at) }}</span>
                </div>
              </div>

              <!-- Reply actions -->
              <div v-if="canEditReply(reply)" class="flex items-center gap-1">
                <button
                  class="p-1 rounded-lg hover:bg-bg-hover text-text-muted transition-colors"
                  title="编辑"
                  @click="openEditReply(reply)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
                <button
                  class="p-1 rounded-lg hover:bg-bg-hover text-red-400 transition-colors"
                  title="删除"
                  @click="confirmDelete('reply', reply.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                  </svg>
                </button>
              </div>
            </div>

            <!-- Reply content or edit -->
            <div v-if="editingReplyId === reply.id" class="space-y-2">
              <textarea
                v-model="editReplyContent"
                rows="4"
                class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
              />
              <div class="flex gap-2">
                <button
                  class="px-4 py-1.5 text-xs font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 disabled:opacity-50"
                  :disabled="savingReply"
                  @click="saveEditReply(reply)"
                >保存</button>
                <button
                  class="px-4 py-1.5 text-xs text-text-secondary hover:bg-bg-hover rounded-full transition-colors"
                  @click="editingReplyId = null"
                >取消</button>
              </div>
            </div>
            <div
              v-else
              class="prose prose-sm max-w-none text-text-primary"
              v-html="renderMd(reply.content)"
            />

            <!-- Reply like + reply-to-reply button -->
            <div v-if="editingReplyId !== reply.id" class="mt-3 flex items-center gap-3">
              <button
                class="flex items-center gap-1 text-[11px] transition-colors"
                :class="reply.user_liked ? 'text-[#fd267a]' : 'text-text-muted hover:text-[#fd267a]'"
                @click="likeReply(reply)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" :fill="reply.user_liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                </svg>
                {{ reply.like_count }}
              </button>

              <button
                v-if="isAuthenticated && !post.is_closed"
                class="flex items-center gap-1 text-[11px] text-text-muted hover:text-[#fd267a] transition-colors"
                :class="replyingToReply?.id === reply.id ? 'text-[#fd267a]' : ''"
                @click="openInlineReply(reply)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>
                </svg>
                回复
              </button>
            </div>

            <!-- Inline reply input box -->
            <div v-if="replyingToReply?.id === reply.id" class="mt-3 space-y-2">
              <textarea
                v-model="inlineReplyContent"
                rows="3"
                :placeholder="`回复 @${reply.username || '匿名'}...（支持 Markdown）`"
                class="w-full px-3 py-2 text-sm border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
                style="background: var(--color-bg);"
                autofocus
              />
              <p v-if="inlineReplyError" class="text-xs text-red-400">{{ inlineReplyError }}</p>
              <div class="flex gap-2 justify-end">
                <button
                  class="px-4 py-1.5 text-xs text-text-secondary hover:bg-bg-hover rounded-full transition-colors"
                  @click="replyingToReply = null"
                >取消</button>
                <button
                  class="px-4 py-1.5 text-xs font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 disabled:opacity-50"
                  :disabled="submittingInlineReply || !inlineReplyContent.trim()"
                  @click="submitInlineReply"
                >
                  <span v-if="submittingInlineReply">提交中...</span>
                  <span v-else>发送</span>
                </button>
              </div>
            </div>

            <!-- Child replies -->
            <div
              v-if="getChildReplies(reply.id).length > 0"
              class="mt-4 space-y-3 ml-8 pl-4 border-l-2 border-border"
            >
              <div
                v-for="child in getChildReplies(reply.id)"
                :key="child.id"
                class="relative"
              >
                <!-- Child reply header -->
                <div class="flex items-start justify-between gap-2 mb-1.5">
                  <div class="flex items-center gap-2">
                    <div
                      class="w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0"
                      :style="{ backgroundColor: avatarColor(child.username) }"
                    >{{ avatar(child.username) }}</div>
                    <div>
                      <span class="text-xs font-medium text-text-primary">{{ child.username || '匿名' }}</span>
                      <span class="ml-1.5 text-[11px] text-text-muted">{{ formatTime(child.created_at) }}</span>
                    </div>
                  </div>
                  <div v-if="canEditReply(child)" class="flex items-center gap-1">
                    <button class="p-1 rounded-lg hover:bg-bg-hover text-text-muted transition-colors" title="编辑" @click="openEditReply(child)">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                    <button class="p-1 rounded-lg hover:bg-bg-hover text-red-400 transition-colors" title="删除" @click="confirmDelete('reply', child.id)">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                      </svg>
                    </button>
                  </div>
                </div>

                <!-- Child content or edit -->
                <div v-if="editingReplyId === child.id" class="space-y-2">
                  <textarea v-model="editReplyContent" rows="3" class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono" />
                  <div class="flex gap-2">
                    <button class="px-4 py-1.5 text-xs font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 disabled:opacity-50" :disabled="savingReply" @click="saveEditReply(child)">保存</button>
                    <button class="px-4 py-1.5 text-xs text-text-secondary hover:bg-bg-hover rounded-full transition-colors" @click="editingReplyId = null">取消</button>
                  </div>
                </div>
                <div v-else class="prose prose-sm max-w-none text-text-primary" v-html="renderMd(child.content)" />

                <!-- Child like + reply -->
                <div v-if="editingReplyId !== child.id" class="mt-2 flex items-center gap-3">
                  <button
                    class="flex items-center gap-1 text-[11px] transition-colors"
                    :class="child.user_liked ? 'text-[#fd267a]' : 'text-text-muted hover:text-[#fd267a]'"
                    @click="likeReply(child)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" :fill="child.user_liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                    </svg>
                    {{ child.like_count }}
                  </button>
                  <button
                    v-if="isAuthenticated && !post.is_closed"
                    class="flex items-center gap-1 text-[11px] transition-colors"
                    :class="replyingToReply?.id === child.id ? 'text-[#fd267a]' : 'text-text-muted hover:text-[#fd267a]'"
                    @click="openInlineReply(child)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>
                    </svg>
                    回复
                  </button>
                </div>

                <!-- Inline reply box under child -->
                <div v-if="replyingToReply?.id === child.id" class="mt-2 space-y-2">
                  <textarea
                    v-model="inlineReplyContent"
                    rows="3"
                    :placeholder="`回复 @${child.username || '匿名'}...（支持 Markdown）`"
                    class="w-full px-3 py-2 text-sm border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
                    style="background: var(--color-bg);"
                  />
                  <p v-if="inlineReplyError" class="text-xs text-red-400">{{ inlineReplyError }}</p>
                  <div class="flex gap-2 justify-end">
                    <button class="px-4 py-1.5 text-xs text-text-secondary hover:bg-bg-hover rounded-full transition-colors" @click="replyingToReply = null">取消</button>
                    <button
                      class="px-4 py-1.5 text-xs font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 disabled:opacity-50"
                      :disabled="submittingInlineReply || !inlineReplyContent.trim()"
                      @click="submitInlineReply"
                    >
                      <span v-if="submittingInlineReply">提交中...</span>
                      <span v-else>发送</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- No replies yet -->
        <div v-else-if="!post.is_closed" class="text-center py-8 text-text-muted text-sm mb-6">
          还没有回复，来发表第一个回复吧
        </div>

        <!-- Reply box -->
        <div
          v-if="isAuthenticated && !post.is_closed"
          class="bg-bg-card border border-border rounded-2xl px-5 py-4"
        >
          <h3 class="text-sm font-semibold text-text-secondary mb-3">发表回复</h3>
          <textarea
            v-model="replyContent"
            rows="5"
            placeholder="输入回复内容（支持 Markdown）..."
            class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
          />
          <p v-if="replyError" class="text-xs text-red-400 mt-1">{{ replyError }}</p>
          <div class="mt-3 flex justify-end">
            <button
              class="px-5 py-2 text-sm font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="submittingReply || !replyContent.trim()"
              @click="submitReply"
            >
              <span v-if="submittingReply">提交中...</span>
              <span v-else>发表回复</span>
            </button>
          </div>
        </div>

        <!-- Closed notice -->
        <div v-if="post.is_closed" class="text-center py-6 text-text-muted text-sm bg-bg-card border border-border rounded-2xl">
          该帖子已关闭，暂停接受新回复
        </div>
      </template>
    </div>
    </div><!-- end main content scroll -->

    <!-- Edit Post Dialog -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="showEditPost"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        @click.self="showEditPost = false"
      >
        <div class="bg-bg-card border border-border rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh]">
          <div class="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <h2 class="text-base font-semibold text-text-primary">编辑帖子</h2>
            <button class="p-1 rounded-lg hover:bg-bg-hover text-text-muted" @click="showEditPost = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <div class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            <!-- Category -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">分类</label>
              <div class="flex gap-2 flex-wrap">
                <button
                  v-for="cat in categories"
                  :key="cat.value"
                  class="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
                  :class="editPostData.category === cat.value
                    ? 'border-[#fd267a] bg-brand-gradient text-white'
                    : 'border-border text-text-secondary hover:border-[#fd267a]/50'"
                  @click="editPostData.category = cat.value"
                >{{ cat.label }}</button>
              </div>
            </div>
            <!-- Title -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">标题</label>
              <input
                v-model="editPostData.title"
                type="text"
                maxlength="200"
                class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary focus:outline-none focus:border-[#fd267a]/50 transition-colors"
              />
            </div>
            <!-- Content -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">内容</label>
              <textarea
                v-model="editPostData.content"
                rows="12"
                class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
              />
            </div>
            <p v-if="editPostError" class="text-xs text-red-400">{{ editPostError }}</p>
          </div>

          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-border shrink-0">
            <button class="px-4 py-2 text-sm text-text-secondary hover:bg-bg-hover rounded-full transition-colors" @click="showEditPost = false">取消</button>
            <button
              class="px-5 py-2 text-sm font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 disabled:opacity-50"
              :disabled="savingPost"
              @click="saveEditPost"
            >
              <span v-if="savingPost">保存中...</span>
              <span v-else>保存</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Confirm Delete Dialog -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="confirmDeleteTarget"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        @click.self="confirmDeleteTarget = null"
      >
        <div class="bg-bg-card border border-border rounded-2xl shadow-2xl w-full max-w-sm p-6">
          <h3 class="text-base font-semibold text-text-primary mb-2">确认删除</h3>
          <p class="text-sm text-text-muted mb-5">
            确定要删除这{{ confirmDeleteTarget.type === 'post' ? '个帖子' : '条回复' }}吗？此操作不可撤销。
          </p>
          <div class="flex justify-end gap-3">
            <button class="px-4 py-2 text-sm text-text-secondary hover:bg-bg-hover rounded-full transition-colors" @click="confirmDeleteTarget = null">取消</button>
            <button
              class="px-4 py-2 text-sm font-semibold bg-red-500 text-white rounded-full hover:bg-red-600 disabled:opacity-50"
              :disabled="deleting"
              @click="doDelete"
            >
              <span v-if="deleting">删除中...</span>
              <span v-else>确认删除</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div><!-- end h-full flex relative -->
</template>

<style scoped>
.sidebar-slide-enter-active,
.sidebar-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Markdown prose styles — plain CSS, no @apply */
.prose :deep(h1),
.prose :deep(h2),
.prose :deep(h3),
.prose :deep(h4) {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}
.prose :deep(h1) { font-size: 1.25rem; }
.prose :deep(h2) { font-size: 1.125rem; }
.prose :deep(h3) { font-size: 1rem; }

.prose :deep(p) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.625;
  color: var(--color-text-primary);
}

.prose :deep(ul),
.prose :deep(ol) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  padding-left: 1.25rem;
  color: var(--color-text-primary);
}
.prose :deep(ul) { list-style-type: disc; }
.prose :deep(ol) { list-style-type: decimal; }
.prose :deep(li) { margin-top: 0.125rem; margin-bottom: 0.125rem; }

.prose :deep(pre) {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  overflow-x: auto;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
}
.prose :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.875rem;
}
.prose :deep(pre code) {
  background: transparent;
  padding: 0;
}
.prose :deep(:not(pre) > code) {
  background: var(--color-bg-hover);
  border-radius: 0.25rem;
  padding: 0.125rem 0.25rem;
  font-size: 0.75rem;
  color: #fd267a;
}

.prose :deep(blockquote) {
  border-left: 4px solid rgba(253, 38, 122, 0.4);
  padding-left: 1rem;
  color: var(--color-text-muted);
  font-style: italic;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
}

.prose :deep(a) {
  color: #fd267a;
  text-decoration: underline;
}

.prose :deep(hr) {
  border-color: var(--color-border);
  margin-top: 1rem;
  margin-bottom: 1rem;
}

.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}
.prose :deep(th),
.prose :deep(td) {
  border: 1px solid var(--color-border);
  padding: 0.375rem 0.75rem;
}
.prose :deep(th) {
  background: var(--color-bg-hover);
  font-weight: 600;
}
</style>
