<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import FloatingButton from '@/components/FloatingButton.vue'
import BottomSheet from '@/components/BottomSheet.vue'
import {
  fetchCommunityPosts,
  createCommunityPost,
  type CommunityPost,
} from '@shared/api'
import { isAuthenticated } from '@shared/stores/auth'
import { showToast } from 'vant'

defineOptions({ name: 'CommunityView' })

const router = useRouter()

const posts = ref<CommunityPost[]>([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const hasMore = ref(true)
const loadingMore = ref(false)

type SortType = 'latest' | 'hot'
const sortType = ref<SortType>('latest')

// New post sheet
const newPostVisible = ref(false)
const newTitle = ref('')
const newContent = ref('')
const newCategory = ref('general')
const posting = ref(false)

const CATEGORIES = [
  { key: 'general', label: '💬 综合讨论' },
  { key: 'question', label: '❓ 提问' },
  { key: 'share', label: '📚 分享' },
  { key: 'feedback', label: '💡 反馈建议' },
]

async function loadPosts(reset = true) {
  if (reset) {
    page.value = 1
    loading.value = true
    error.value = ''
  } else {
    loadingMore.value = true
  }
  try {
    const res = await fetchCommunityPosts({
      page: page.value,
      page_size: 20,
      sort: sortType.value === 'hot' ? 'hot' : 'latest',
    })
    if (reset) {
      posts.value = res.posts
    } else {
      posts.value.push(...res.posts)
    }
    hasMore.value = posts.value.length < res.total
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

onMounted(() => loadPosts())

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  page.value++
  await loadPosts(false)
}

async function submitPost() {
  if (!newTitle.value.trim() || !newContent.value.trim() || posting.value) return
  posting.value = true
  try {
    const post = await createCommunityPost({
      category: newCategory.value,
      title: newTitle.value.trim(),
      content: newContent.value.trim(),
    })
    newPostVisible.value = false
    newTitle.value = ''
    newContent.value = ''
    posts.value.unshift(post)
    showToast('发布成功')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '发布失败')
  } finally {
    posting.value = false
  }
}

function formatDate(d: string) {
  const now = Date.now()
  const diff = now - new Date(d).getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return new Date(d).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const categoryLabel: Record<string, string> = {
  general: '综合', question: '提问', share: '分享', feedback: '反馈',
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="社区" :show-back="false" />

    <!-- Sort tabs -->
    <div class="tab-underline shrink-0 mx-4">
      <button
        type="button"
        class="tab-underline-item"
        :class="{ active: sortType === 'latest' }"
        @click="sortType = 'latest'; loadPosts()"
      >
        最新
      </button>
      <button
        type="button"
        class="tab-underline-item"
        :class="{ active: sortType === 'hot' }"
        @click="sortType = 'hot'; loadPosts()"
      >
        热门
      </button>
    </div>

    <LoadingState v-if="loading" class="flex-1" message="加载社区…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadPosts()" />

    <div v-else class="flex-1 overflow-y-auto pb-6">
      <EmptyState v-if="posts.length === 0" title="社区还没有帖子" description="成为第一个发帖的人！" />

      <div v-else>
        <!-- Pinned posts -->
        <div
          v-for="post in posts.filter(p => p.is_pinned)"
          :key="post.id"
          class="mx-4 mb-3 mt-3 card-section cursor-pointer active:scale-[0.99] transition-transform border-tinder-gold/30 bg-tinder-gold/5"
          @click="router.push(`/community/post/${post.id}`)"
        >
          <div class="flex items-center gap-2 mb-2">
            <span class="text-[10px] bg-tinder-gold/20 text-tinder-gold px-2 py-0.5 rounded-full font-semibold">📌 置顶</span>
            <span class="text-[10px] text-text-muted">{{ categoryLabel[post.category] ?? post.category }}</span>
          </div>
          <h3 class="text-[14px] font-semibold text-text-primary line-clamp-2 mb-1">{{ post.title }}</h3>
          <div class="flex items-center gap-3 text-[11px] text-text-muted">
            <span>{{ post.username || '匿名' }}</span>
            <span>💬 {{ post.reply_count }}</span>
            <span>❤️ {{ post.like_count }}</span>
            <span class="ml-auto">{{ formatDate(post.created_at) }}</span>
          </div>
        </div>

        <!-- Regular posts -->
        <template v-for="post in posts.filter(p => !p.is_pinned)" :key="post.id">
          <div
            class="flex items-start gap-3 px-4 py-3.5 border-b border-border cursor-pointer active:bg-bg-hover"
            @click="router.push(`/community/post/${post.id}`)"
          >
            <!-- Avatar placeholder -->
            <div class="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-tinder-blue to-tinder-purple flex items-center justify-center text-white text-[13px] font-bold">
              {{ (post.username || '?')[0].toUpperCase() }}
            </div>

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5 mb-0.5">
                <span class="text-[11px] font-medium text-text-secondary truncate">{{ post.username || '匿名' }}</span>
                <span class="text-[10px] text-text-muted">·</span>
                <span class="text-[10px] bg-bg-elevated px-1.5 py-0.5 rounded-full text-text-muted">{{ categoryLabel[post.category] ?? post.category }}</span>
              </div>
              <p class="text-[14px] font-semibold text-text-primary line-clamp-2 leading-snug mb-1.5">{{ post.title }}</p>
              <div class="flex items-center gap-3 text-[11px] text-text-muted">
                <span>💬 {{ post.reply_count }}</span>
                <span :class="post.user_liked ? 'text-tinder-pink' : ''">❤️ {{ post.like_count }}</span>
                <span class="ml-auto">{{ formatDate(post.last_reply_at || post.created_at) }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Load more -->
        <div v-if="hasMore" class="flex justify-center py-4">
          <button
            type="button"
            class="btn-ghost text-[13px] py-2 px-6"
            :disabled="loadingMore"
            @click="loadMore"
          >
            {{ loadingMore ? '加载中…' : '加载更多' }}
          </button>
        </div>
      </div>
    </div>

    <!-- FAB: new post -->
    <FloatingButton v-if="isAuthenticated" label="发帖" @click="newPostVisible = true" />

    <!-- New post sheet -->
    <BottomSheet :visible="newPostVisible" title="发布帖子" height="85dvh" @close="newPostVisible = false">
      <div class="px-5 pb-6 pt-2 space-y-4">
        <!-- Category select -->
        <div class="flex gap-2 flex-wrap">
          <button
            v-for="cat in CATEGORIES"
            :key="cat.key"
            type="button"
            class="px-3 py-1.5 rounded-full text-[12px] font-medium border transition-all"
            :class="newCategory === cat.key ? 'border-tinder-pink bg-tinder-pink/10 text-tinder-pink' : 'border-border bg-bg-elevated text-text-muted'"
            @click="newCategory = cat.key"
          >
            {{ cat.label }}
          </button>
        </div>
        <input
          v-model="newTitle"
          type="text"
          placeholder="标题"
          class="input-field"
          maxlength="100"
        />
        <textarea
          v-model="newContent"
          placeholder="内容（支持 Markdown）"
          class="input-field resize-none"
          rows="6"
          maxlength="5000"
        />
        <button
          type="button"
          class="btn-primary"
          :disabled="posting || !newTitle.trim() || !newContent.trim()"
          @click="submitPost"
        >
          {{ posting ? '发布中…' : '发布' }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>
