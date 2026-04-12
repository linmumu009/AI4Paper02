<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import {
  fetchCommunityPost,
  createCommunityReply,
  toggleCommunityLike,
  type CommunityPost,
  type CommunityReply,
} from '@shared/api'
import { isAuthenticated } from '@shared/stores/auth'
import { showToast } from 'vant'

defineOptions({ name: 'CommunityPostView' })

const props = defineProps<{ id: string }>()
const router = useRouter()

const post = ref<CommunityPost | null>(null)
const loading = ref(true)
const error = ref('')
const replyText = ref('')
const replying = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    post.value = await fetchCommunityPost(Number(props.id))
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submitReply() {
  if (!replyText.value.trim() || !post.value || replying.value) return
  replying.value = true
  try {
    const reply = await createCommunityReply(post.value.id, { content: replyText.value.trim() })
    post.value.replies = [...(post.value.replies ?? []), reply]
    post.value.reply_count++
    replyText.value = ''
    showToast('回复成功')
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '回复失败')
  } finally {
    replying.value = false
  }
}

async function togglePostLike() {
  if (!post.value || !isAuthenticated.value) { showToast('请先登录'); return }
  try {
    const res = await toggleCommunityLike('post', post.value.id)
    post.value.user_liked = res.liked
    post.value.like_count = res.like_count
  } catch { showToast('操作失败') }
}

async function toggleReplyLike(reply: CommunityReply) {
  if (!isAuthenticated.value) { showToast('请先登录'); return }
  try {
    const res = await toggleCommunityLike('reply', reply.id)
    reply.user_liked = res.liked
    reply.like_count = res.like_count
  } catch { showToast('操作失败') }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader :title="post?.title || '帖子'" @back="router.back()" />

    <LoadingState v-if="loading" class="flex-1" message="加载帖子…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="load" />

    <template v-else-if="post">
      <div class="flex-1 overflow-y-auto pb-28">
        <!-- Post header -->
        <div class="px-4 py-4 border-b border-border">
          <h1 class="text-[18px] font-bold text-text-primary leading-snug mb-3">{{ post.title }}</h1>
          <div class="flex items-center gap-3 mb-3">
            <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-tinder-blue to-tinder-purple flex items-center justify-center text-white text-[12px] font-bold">
              {{ (post.username || '?')[0].toUpperCase() }}
            </div>
            <div>
              <p class="text-[13px] font-medium text-text-primary">{{ post.username || '匿名' }}</p>
              <p class="text-[11px] text-text-muted">{{ formatDate(post.created_at) }}</p>
            </div>
          </div>
          <!-- Content -->
          <div class="prose-mobile">
            <MarkdownRenderer v-if="post.content" :content="post.content" />
          </div>
          <!-- Like row -->
          <div class="flex items-center gap-4 mt-4 pt-4 border-t border-border">
            <button
              type="button"
              class="flex items-center gap-1.5 text-[13px] font-medium"
              :class="post.user_liked ? 'text-tinder-pink' : 'text-text-muted'"
              @click="togglePostLike"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"
                  :fill="post.user_liked ? 'currentColor' : 'none'" />
              </svg>
              {{ post.like_count }}
            </button>
            <span class="text-[13px] text-text-muted">💬 {{ post.reply_count }} 条回复</span>
          </div>
        </div>

        <!-- Replies -->
        <div>
          <div v-if="!post.replies?.length" class="px-4 py-8 text-center text-[13px] text-text-muted">
            还没有回复，来第一个回复！
          </div>
          <div
            v-for="reply in post.replies"
            :key="reply.id"
            class="px-4 py-4 border-b border-border"
          >
            <div class="flex items-start gap-3">
              <div class="shrink-0 w-8 h-8 rounded-xl bg-bg-elevated flex items-center justify-center text-[12px] font-bold text-text-secondary">
                {{ (reply.username || '?')[0].toUpperCase() }}
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-[13px] font-medium text-text-primary">{{ reply.username || '匿名' }}</span>
                  <span class="text-[11px] text-text-muted">{{ formatDate(reply.created_at) }}</span>
                </div>
                <p class="text-[13px] text-text-secondary leading-relaxed">{{ reply.content }}</p>
                <button
                  type="button"
                  class="flex items-center gap-1 mt-2 text-[11px]"
                  :class="reply.user_liked ? 'text-tinder-pink' : 'text-text-muted'"
                  @click="toggleReplyLike(reply)"
                >
                  ❤️ {{ reply.like_count }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Reply input -->
      <div
        class="shrink-0 border-t border-border bg-bg-card px-4 pt-3"
        style="padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));"
      >
        <div v-if="!isAuthenticated" class="text-center pb-1">
          <button type="button" class="btn-text text-[13px]" @click="router.push('/login')">登录后发表回复</button>
        </div>
        <div v-else-if="!post.is_closed" class="flex items-end gap-2">
          <textarea
            v-model="replyText"
            placeholder="写下你的回复…"
            class="flex-1 bg-bg-elevated border border-border rounded-2xl px-3 py-2.5 text-[13px] text-text-primary resize-none outline-none focus:border-tinder-pink max-h-24"
            rows="1"
          />
          <button
            type="button"
            class="shrink-0 w-10 h-10 rounded-2xl flex items-center justify-center"
            :class="replyText.trim() && !replying ? 'bg-tinder-pink text-white' : 'bg-bg-elevated text-text-muted'"
            :disabled="!replyText.trim() || replying"
            @click="submitReply"
          >
            <svg v-if="replying" class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
          </button>
        </div>
        <div v-else class="text-center text-[12px] text-text-muted pb-1">此帖已关闭</div>
      </div>
    </template>
  </div>
</template>
