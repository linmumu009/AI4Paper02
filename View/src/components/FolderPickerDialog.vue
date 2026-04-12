<script setup lang="ts">
import { ref, computed } from 'vue'

interface AnyFolder {
  id: number
  name: string
  children?: AnyFolder[]
}

const props = defineProps<{
  folders: AnyFolder[]
  title?: string
}>()

const emit = defineEmits<{
  select: [folderId: number | null]
  cancel: []
}>()

const selectedId = ref<number | null>(null)

/** Flatten nested folders into a list with depth info for indentation */
interface FlatFolder {
  id: number
  name: string
  depth: number
}

const flatFolders = computed(() => {
  const result: FlatFolder[] = []
  function walk(list: AnyFolder[], depth: number) {
    for (const f of list) {
      result.push({ id: f.id, name: f.name, depth })
      if (f.children?.length) {
        walk(f.children, depth + 1)
      }
    }
  }
  walk(props.folders, 0)
  return result
})

function pick(id: number | null) {
  selectedId.value = id
}

function confirm() {
  emit('select', selectedId.value)
}
</script>

<template>
  <Teleport to="body">
    <!-- Overlay -->
    <div
      class="fixed inset-0 z-[9998] bg-black/60 flex items-center justify-center"
      @click.self="emit('cancel')"
    >
      <!-- Dialog -->
      <div class="w-[320px] max-h-[70vh] bg-bg-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-border">
          <h3 class="text-sm font-bold text-text-primary">{{ title || '移动到文件夹' }}</h3>
        </div>

        <!-- Folder list -->
        <div class="flex-1 overflow-y-auto p-2">
        <!-- Root option -->
          <button
            class="w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-colors cursor-pointer border-none"
            :class="selectedId === null
              ? 'bg-tinder-pink/12 text-tinder-pink font-semibold'
              : 'bg-transparent text-text-secondary hover:bg-bg-hover'"
            @click="pick(null)"
          >
            <!-- Root folder icon -->
            <svg
              class="shrink-0 transition-colors"
              style="width:16px;height:16px;"
              :class="selectedId === null ? 'text-tinder-pink' : 'text-text-secondary'"
              viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            根目录
            <!-- Check mark when selected -->
            <svg v-if="selectedId === null" class="ml-auto w-3.5 h-3.5 shrink-0 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </button>

          <!-- Flattened folder list with indent -->
          <button
            v-for="ff in flatFolders"
            :key="ff.id"
            class="w-full text-left flex items-center gap-2.5 py-2 rounded-lg text-xs transition-colors cursor-pointer border-none"
            :class="selectedId === ff.id
              ? 'bg-tinder-pink/10 text-tinder-pink font-medium'
              : 'bg-transparent text-text-secondary hover:bg-bg-hover'"
            :style="{ paddingLeft: (12 + ff.depth * 16) + 'px', paddingRight: '12px' }"
            @click="pick(ff.id)"
          >
            <!-- Folder icon -->
            <svg
              class="shrink-0 transition-colors"
              style="width:16px;height:16px;"
              :class="selectedId === ff.id ? 'text-tinder-pink' : 'text-text-secondary'"
              viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
            >
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            {{ ff.name }}
            <!-- Check mark when selected -->
            <svg v-if="selectedId === ff.id" class="ml-auto w-3.5 h-3.5 shrink-0 text-tinder-pink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </button>

          <!-- Empty state -->
          <div v-if="flatFolders.length === 0" class="text-center py-6 text-xs text-text-muted">
            暂无文件夹，请先创建
          </div>
        </div>

        <!-- Footer buttons -->
        <div class="flex items-center justify-end gap-2 px-4 py-3 border-t border-border">
          <button
            class="px-4 py-1.5 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="emit('cancel')"
          >
            取消
          </button>
          <button
            class="px-4 py-1.5 rounded-full text-xs text-white font-semibold bg-brand-gradient border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="confirm"
          >
            确认移动
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
