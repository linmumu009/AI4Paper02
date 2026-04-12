<script setup lang="ts">
import { ref, computed } from 'vue'

export interface TocHeading {
  id: string
  text: string
  level: number
}

interface HeadingGroup {
  /** The "main" (Chinese or single-language) heading entry */
  main: TocHeading
  /** Optional paired secondary (English) heading when isBilingual is true */
  secondary?: TocHeading
}

const props = defineProps<{
  headings: TocHeading[]
  activeId: string
  isBilingual?: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const search = ref('')
const searchFocused = ref(false)

/** Returns true if the text string contains Chinese characters. */
function hasChinese(text: string): boolean {
  return /[\u4e00-\u9fa5]/.test(text)
}

/**
 * Build paired groups from the flat heading list.
 * In bilingual mode, adjacent same-level headings where one is Chinese and
 * the other is English are merged into a single group (English as secondary,
 * Chinese as main). Otherwise each heading forms its own group.
 */
const groups = computed<HeadingGroup[]>(() => {
  const src = props.headings
  if (!props.isBilingual || src.length === 0) {
    return src.map((h) => ({ main: h }))
  }

  const result: HeadingGroup[] = []
  let i = 0
  while (i < src.length) {
    const cur = src[i]
    const next = src[i + 1]
    if (
      next &&
      cur.level === next.level &&
      hasChinese(cur.text) !== hasChinese(next.text)
    ) {
      // Pair them: put English as secondary, Chinese as main
      if (hasChinese(cur.text)) {
        result.push({ main: cur, secondary: next })
      } else {
        result.push({ main: next, secondary: cur })
      }
      i += 2
    } else {
      result.push({ main: cur })
      i++
    }
  }
  return result
})

/** Filter groups by search query (matches either main or secondary text). */
const filtered = computed<HeadingGroup[]>(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter(
    (g) =>
      g.main.text.toLowerCase().includes(q) ||
      (g.secondary?.text.toLowerCase().includes(q) ?? false),
  )
})

/** True when either the main or secondary heading is active. */
function isGroupActive(g: HeadingGroup): boolean {
  return g.main.id === props.activeId || g.secondary?.id === props.activeId
}

function indentStyle(level: number): string {
  // pl values: h1→0, h2→14px, h3→26px, h4+→34px
  if (level <= 1) return 'pl-1'
  if (level === 2) return 'pl-4'
  if (level === 3) return 'pl-7'
  return 'pl-9'
}
</script>

<template>
  <div class="toc-root flex flex-col h-full min-h-0">
    <!-- Search bar -->
    <div class="shrink-0 px-3 py-2.5 border-b border-border">
      <div
        class="toc-search-wrap relative flex items-center rounded-lg transition-all duration-200"
        :class="searchFocused ? 'ring-1 ring-tinder-pink/40 bg-bg-hover' : 'bg-bg-elevated'"
      >
        <svg
          class="absolute left-2.5 w-3.5 h-3.5 shrink-0 transition-colors duration-200 pointer-events-none"
          :class="searchFocused ? 'text-tinder-pink' : 'text-text-muted'"
          viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
        >
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          v-model="search"
          type="text"
          placeholder="搜索标题…"
          class="w-full pl-8 pr-3 py-1.5 text-[12px] bg-transparent rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none"
          @focus="searchFocused = true"
          @blur="searchFocused = false"
        />
        <button
          v-if="search"
          class="absolute right-2 text-text-muted hover:text-text-primary transition-colors bg-transparent border-none cursor-pointer p-0"
          @click="search = ''"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Heading list -->
    <nav class="flex-1 overflow-y-auto py-1.5 px-1.5">
      <div
        v-if="filtered.length === 0"
        class="px-3 py-6 text-[11px] text-text-muted text-center"
      >
        无匹配标题
      </div>

      <template v-for="(g, idx) in filtered" :key="g.main.id">
        <!-- h1: top-level section separator style -->
        <div
          v-if="g.main.level <= 1"
          class="toc-item toc-h1 relative flex flex-col cursor-pointer rounded-md transition-all duration-200 select-none"
          :class="[
            indentStyle(g.main.level),
            isGroupActive(g)
              ? 'toc-active bg-tinder-pink/10'
              : 'hover:bg-bg-hover',
            idx > 0 ? 'mt-2' : 'mt-0.5',
          ]"
          @click="emit('select', g.main.id)"
        >
          <div class="flex items-start gap-2 px-2 py-1.5">
            <span
              class="toc-bar shrink-0 w-[3px] rounded-full mt-0.5 self-stretch min-h-[14px] transition-all duration-200"
              :class="isGroupActive(g) ? 'bg-gradient-to-b from-gradient-start to-gradient-end' : 'bg-border-light'"
            />
            <div class="flex flex-col min-w-0 flex-1 gap-0.5">
              <!-- Secondary (English) line in bilingual mode -->
              <span
                v-if="g.secondary"
                class="toc-secondary block leading-snug break-words text-[11px] text-text-muted"
                :class="isGroupActive(g) ? 'text-tinder-pink/70' : ''"
                @click.stop="emit('select', g.secondary.id)"
              >{{ g.secondary.text }}</span>
              <!-- Main (Chinese / primary) line -->
              <span
                class="leading-snug break-words text-[13px] font-semibold"
                :class="isGroupActive(g) ? 'text-tinder-pink' : 'text-text-primary'"
              >{{ g.main.text }}</span>
            </div>
          </div>
        </div>

        <!-- h2: section headings -->
        <div
          v-else-if="g.main.level === 2"
          class="toc-item toc-h2 relative flex flex-col cursor-pointer rounded-md transition-all duration-200 select-none"
          :class="[
            indentStyle(g.main.level),
            isGroupActive(g)
              ? 'toc-active bg-tinder-pink/10'
              : 'hover:bg-bg-hover',
            'mt-0.5',
          ]"
          @click="emit('select', g.main.id)"
        >
          <div class="flex items-start gap-2 px-2 py-1">
            <span
              class="toc-bar shrink-0 w-[2px] rounded-full mt-0.5 self-stretch min-h-[12px] transition-all duration-200"
              :class="isGroupActive(g) ? 'bg-tinder-pink' : 'bg-border'"
            />
            <div class="flex flex-col min-w-0 flex-1 gap-0.5">
              <span
                v-if="g.secondary"
                class="block leading-snug break-words text-[10.5px] text-text-muted"
                :class="isGroupActive(g) ? 'text-tinder-pink/60' : ''"
                @click.stop="emit('select', g.secondary.id)"
              >{{ g.secondary.text }}</span>
              <span
                class="leading-snug break-words text-[12.5px] font-medium"
                :class="isGroupActive(g) ? 'text-tinder-pink' : 'text-text-secondary'"
              >{{ g.main.text }}</span>
            </div>
          </div>
        </div>

        <!-- h3+: sub-section headings (no bar) -->
        <div
          v-else
          class="toc-item toc-h3 relative flex flex-col cursor-pointer rounded-md transition-all duration-200 select-none"
          :class="[
            indentStyle(g.main.level),
            isGroupActive(g)
              ? 'toc-active bg-tinder-pink/8'
              : 'hover:bg-bg-hover',
          ]"
          @click="emit('select', g.main.id)"
        >
          <div class="flex items-start gap-1.5 px-2 py-0.5">
            <span
              class="shrink-0 w-1 h-1 rounded-full mt-[5px] transition-all duration-200"
              :class="isGroupActive(g) ? 'bg-tinder-pink' : 'bg-border-light'"
            />
            <div class="flex flex-col min-w-0 flex-1">
              <span
                v-if="g.secondary"
                class="block leading-snug break-words text-[10px] text-text-muted"
                :class="isGroupActive(g) ? 'text-tinder-pink/60' : ''"
                @click.stop="emit('select', g.secondary.id)"
              >{{ g.secondary.text }}</span>
              <span
                class="leading-snug break-words text-[11.5px]"
                :class="isGroupActive(g) ? 'text-tinder-pink' : 'text-text-muted'"
              >{{ g.main.text }}</span>
            </div>
          </div>
        </div>
      </template>
    </nav>
  </div>
</template>

<style scoped>
.toc-root {
  --toc-transition: all 0.18s ease;
}

/* Active item left bar gradient override using CSS since Tailwind bg-gradient requires
   explicit from/to tokens which may not resolve inside :class bindings */
.toc-active .toc-bar {
  background: linear-gradient(to bottom, var(--color-gradient-start, #fd267a), var(--color-gradient-end, #ff6036));
}

/* Subtle scrollbar for the nav */
nav::-webkit-scrollbar {
  width: 3px;
}
nav::-webkit-scrollbar-track {
  background: transparent;
}
nav::-webkit-scrollbar-thumb {
  background: var(--color-border-light);
  border-radius: 2px;
}
</style>
