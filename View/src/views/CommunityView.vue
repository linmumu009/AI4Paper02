<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import CommunitySidebar from '../components/CommunitySidebar.vue'
import {
  fetchCommunityPosts,
  createCommunityPost,
  type CommunityPost,
} from '../api/index'
import { isAuthenticated } from '../stores/auth'

const router = useRouter()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const posts = ref<CommunityPost[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')

const currentPage = ref(1)
const pageSize = 20
const currentCategory = ref<string>('')
const currentSort = ref<string>('latest')

const showCreateDialog = ref(false)
const submitting = ref(false)
const createError = ref('')
const newPost = ref({ category: 'discussion', title: '', content: '' })

const categories = [
  { value: '', label: '全部' },
  { value: 'question', label: '提问' },
  { value: 'discussion', label: '讨论' },
  { value: 'sharing', label: '分享' },
  { value: 'help', label: '求助' },
]

const categoryMeta: Record<string, { label: string; color: string }> = {
  question:   { label: '提问',  color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' },
  discussion: { label: '讨论',  color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' },
  sharing:    { label: '分享',  color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' },
  help:       { label: '求助',  color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' },
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

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

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------
async function loadPosts() {
  loading.value = true
  error.value = ''
  try {
    const result = await fetchCommunityPosts({
      category: currentCategory.value || undefined,
      page: currentPage.value,
      page_size: pageSize,
      sort: currentSort.value,
    })
    posts.value = result.posts
    total.value = result.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPosts()
})

watch([currentCategory, currentSort], () => {
  currentPage.value = 1
  loadPosts()
})

// ---------------------------------------------------------------------------
// Create post
// ---------------------------------------------------------------------------
function openCreateDialog() {
  newPost.value = { category: 'discussion', title: '', content: '' }
  createError.value = ''
  showCreateDialog.value = true
}

function closeCreateDialog() {
  showCreateDialog.value = false
}

async function submitCreatePost() {
  createError.value = ''
  if (!newPost.value.title.trim()) {
    createError.value = '请填写标题'
    return
  }
  if (!newPost.value.content.trim()) {
    createError.value = '请填写内容'
    return
  }
  submitting.value = true
  try {
    const created = await createCommunityPost({
      category: newPost.value.category,
      title: newPost.value.title.trim(),
      content: newPost.value.content.trim(),
    })
    showCreateDialog.value = false
    router.push(`/community/post/${created.id}`)
  } catch (e: any) {
    createError.value = e?.response?.data?.detail || '发帖失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function openPost(post: CommunityPost) {
  router.push(`/community/post/${post.id}`)
}

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
          :current-category="currentCategory"
          :current-sort="currentSort"
          :show-sidebar="showSidebar"
          @update:current-category="currentCategory = $event"
          @update:current-sort="currentSort = $event"
          @toggle-sidebar="showSidebar = false"
          @open-create-dialog="openCreateDialog"
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
      <div class="max-w-3xl mx-auto px-4 py-6">

        <!-- Page title row -->
        <div class="flex items-center justify-between mb-5">
          <div>
            <h1 class="text-lg font-semibold text-text-primary">社区讨论</h1>
            <p class="text-xs text-text-muted mt-0.5">与研究者交流，提问、分享与探讨</p>
          </div>
          <button
            v-if="isAuthenticated"
            class="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-semibold bg-brand-gradient text-white hover:opacity-90 transition-opacity lg:hidden"
            @click="openCreateDialog"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            发帖
          </button>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex flex-col items-center gap-3 py-16">
          <svg class="animate-spin h-8 w-8 text-[#fd267a]" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-text-muted text-sm">加载中...</span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-center px-8">
          <div class="text-5xl mb-2">⚠️</div>
          <p class="text-text-secondary text-sm">{{ error }}</p>
          <button
            class="px-5 py-2 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="loadPosts"
          >重试</button>
        </div>

        <!-- Empty -->
        <div v-else-if="posts.length === 0" class="flex flex-col items-center gap-4 text-center py-16 px-8">
          <div class="text-5xl mb-2">📭</div>
          <h2 class="text-xl font-bold text-text-primary">暂无帖子</h2>
          <p class="text-sm text-text-muted">来发第一篇帖子吧，开启社区讨论！</p>
          <button
            v-if="isAuthenticated"
            class="px-6 py-2.5 rounded-full bg-brand-gradient text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="openCreateDialog"
          >发第一篇帖子</button>
        </div>

        <!-- Post list -->
        <div v-else class="space-y-2">
          <div
            v-for="post in posts"
            :key="post.id"
            class="bg-bg-card border border-border rounded-2xl p-4 hover:border-[#fd267a]/40 hover:shadow-md cursor-pointer transition-all group"
            @click="openPost(post)"
          >
            <!-- Pinned badge -->
            <div v-if="post.is_pinned" class="flex items-center gap-1 mb-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-[#fd267a]" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
              </svg>
              <span class="text-[10px] font-semibold text-[#fd267a] uppercase tracking-wide">置顶</span>
            </div>

            <div class="flex items-start gap-3">
              <div class="flex-1 min-w-0">
                <!-- Title row -->
                <div class="flex items-start gap-2 mb-1.5">
                  <span
                    v-if="post.category"
                    class="mt-0.5 shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                    :class="categoryMeta[post.category]?.color || 'bg-bg-hover text-text-muted'"
                  >{{ categoryMeta[post.category]?.label || post.category }}</span>
                  <h3 class="text-sm font-medium text-text-primary leading-snug group-hover:text-[#fd267a] transition-colors line-clamp-2">
                    {{ post.title }}
                  </h3>
                  <span v-if="post.is_closed" class="mt-0.5 shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-bg-hover text-text-muted">已关闭</span>
                </div>

                <!-- Meta row -->
                <div class="flex items-center gap-3 text-[11px] text-text-muted flex-wrap">
                  <span class="font-medium text-text-secondary">{{ post.username || '匿名' }}</span>
                  <span>{{ formatTime(post.last_reply_at || post.created_at) }}</span>

                  <span class="flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                    {{ post.reply_count }}
                  </span>

                  <span class="flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                    </svg>
                    {{ post.view_count }}
                  </span>

                  <span class="flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                    </svg>
                    {{ post.like_count }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-8">
          <button
            class="px-4 py-1.5 text-xs rounded-full border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            :disabled="currentPage <= 1"
            @click="currentPage--; loadPosts()"
          >上一页</button>
          <span class="text-xs text-text-muted px-2">{{ currentPage }} / {{ totalPages }}</span>
          <button
            class="px-4 py-1.5 text-xs rounded-full border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            :disabled="currentPage >= totalPages"
            @click="currentPage++; loadPosts()"
          >下一页</button>
        </div>

      </div>
    </div>

    <!-- Create post dialog -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="showCreateDialog"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        @click.self="closeCreateDialog"
      >
        <div class="bg-bg-card border border-border rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh]">
          <!-- Dialog header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <h2 class="text-base font-semibold text-text-primary">发新帖</h2>
            <button
              class="p-1 rounded-lg hover:bg-bg-hover text-text-muted transition-colors"
              @click="closeCreateDialog"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <!-- Dialog body -->
          <div class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            <!-- Category select -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">分类</label>
              <div class="flex gap-2 flex-wrap">
                <button
                  v-for="cat in categories.slice(1)"
                  :key="cat.value"
                  class="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
                  :class="newPost.category === cat.value
                    ? 'border-[#fd267a] bg-brand-gradient text-white'
                    : 'border-border text-text-secondary hover:border-[#fd267a]/50'"
                  @click="newPost.category = cat.value"
                >{{ cat.label }}</button>
              </div>
            </div>

            <!-- Title -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">标题 <span class="text-red-400">*</span></label>
              <input
                v-model="newPost.title"
                type="text"
                maxlength="200"
                placeholder="简洁明了地描述你的问题或主题"
                class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#fd267a]/50 transition-colors"
              />
              <div class="text-right text-[11px] text-text-muted mt-1">{{ newPost.title.length }}/200</div>
            </div>

            <!-- Content -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">内容 <span class="text-red-400">*</span>（支持 Markdown）</label>
              <textarea
                v-model="newPost.content"
                rows="10"
                placeholder="详细描述你的问题、想法或分享内容...&#10;&#10;支持 Markdown 格式，例如 **加粗**、`代码`、## 标题 等"
                class="w-full px-3 py-2 text-sm bg-bg-primary border border-border rounded-xl text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#fd267a]/50 transition-colors resize-none font-mono"
              />
            </div>

            <!-- Error -->
            <p v-if="createError" class="text-xs text-red-400">{{ createError }}</p>
          </div>

          <!-- Dialog footer -->
          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-border shrink-0">
            <button
              class="px-4 py-2 text-sm text-text-secondary hover:bg-bg-hover rounded-full transition-colors"
              @click="closeCreateDialog"
            >取消</button>
            <button
              class="px-5 py-2 text-sm font-semibold bg-brand-gradient text-white rounded-full hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="submitting"
              @click="submitCreatePost"
            >
              <span v-if="submitting">发布中...</span>
              <span v-else>发布</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
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
</style>
