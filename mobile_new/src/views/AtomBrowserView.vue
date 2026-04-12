<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SearchBar from '@/components/SearchBar.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { fetchIdeaAtoms } from '@shared/api'
import type { IdeaAtom } from '@shared/types/idea'

defineOptions({ name: 'AtomBrowserView' })

const router = useRouter()

const atoms = ref<IdeaAtom[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const filterType = ref('')

const ATOM_TYPES = ['claim', 'method', 'setup', 'limitation', 'tag']
const ATOM_TYPE_LABELS: Record<string, string> = {
  claim: '主张', method: '方法', setup: '设置', limitation: '局限', tag: '标签',
}
const ATOM_TYPE_COLORS: Record<string, string> = {
  claim: 'text-tinder-blue', method: 'text-tinder-green', setup: 'text-tinder-gold',
  limitation: 'text-tinder-pink', tag: 'text-text-muted',
}

async function loadAtoms() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaAtoms({
      atom_type: filterType.value || undefined,
      search: search.value || undefined,
      limit: 50,
    })
    atoms.value = res.atoms
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadAtoms)
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <PageHeader title="原子库" @back="router.back()" />
    <div class="px-4 pb-2 shrink-0">
      <SearchBar v-model="search" placeholder="搜索原子内容…" />
    </div>
    <!-- Type filter pills -->
    <div class="flex gap-2 px-4 pb-3 overflow-x-auto shrink-0">
      <button
        type="button"
        class="mode-pill shrink-0"
        :class="filterType === '' ? 'active' : 'inactive'"
        @click="filterType = ''; loadAtoms()"
      >
        全部
      </button>
      <button
        v-for="type in ATOM_TYPES"
        :key="type"
        type="button"
        class="mode-pill shrink-0"
        :class="filterType === type ? 'active' : 'inactive'"
        @click="filterType = type; loadAtoms()"
      >
        {{ ATOM_TYPE_LABELS[type] ?? type }}
      </button>
    </div>
    <div class="px-4 pb-2 shrink-0">
      <button type="button" class="btn-ghost text-[12px] py-2 w-full" @click="loadAtoms">搜索</button>
    </div>
    <LoadingState v-if="loading" class="flex-1" message="加载原子…" />
    <ErrorState v-else-if="error" class="flex-1" :message="error" @retry="loadAtoms" />
    <div v-else class="flex-1 overflow-y-auto pb-4">
      <p class="px-4 py-2 text-[12px] text-text-muted">共 {{ atoms.length }} 个原子</p>
      <div
        v-for="atom in atoms"
        :key="atom.id"
        class="px-4 py-3 border-b border-border"
      >
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[11px] font-semibold uppercase tracking-wider" :class="ATOM_TYPE_COLORS[atom.atom_type] ?? 'text-text-muted'">
            {{ ATOM_TYPE_LABELS[atom.atom_type] ?? atom.atom_type }}
          </span>
          <span class="text-[10px] text-text-muted">{{ atom.section }}</span>
          <span class="text-[10px] text-text-muted ml-auto">{{ new Date(atom.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) }}</span>
        </div>
        <p class="text-[13px] text-text-secondary leading-relaxed">{{ atom.content }}</p>
        <div v-if="atom.tags?.length" class="flex flex-wrap gap-1 mt-2">
          <span v-for="tag in atom.tags" :key="tag" class="text-[10px] px-1.5 py-0.5 rounded-full bg-bg-elevated text-text-muted">#{{ tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
