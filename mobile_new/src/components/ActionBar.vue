<script setup lang="ts">
withDefaults(
  defineProps<{
    mode?: 'paper' | 'idea'
    canUndo?: boolean
  }>(),
  { mode: 'paper', canUndo: false },
)

const emit = defineEmits<{
  (e: 'undo'): void
  (e: 'skip'): void
  (e: 'like'): void
  (e: 'detail'): void
}>()
</script>

<template>
  <div class="flex items-center justify-evenly py-2 px-4 max-w-md mx-auto w-full">
    <!-- Undo -->
    <button
      type="button"
      class="action-btn"
      :class="canUndo ? 'action-btn--undo-on' : 'action-btn--undo-off'"
      :disabled="!canUndo"
      aria-label="撤回"
      @click="emit('undo')"
    >
      <span class="action-ring action-ring-sm">
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
        </svg>
      </span>
      <span class="action-label">撤回</span>
    </button>

    <!-- Skip -->
    <button type="button" class="action-btn action-btn--skip" aria-label="跳过" @click="emit('skip')">
      <span class="action-ring action-ring-lg">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </span>
      <span class="action-label">跳过</span>
    </button>

    <!-- Like / Collect -->
    <button type="button" class="action-btn action-btn--like" :aria-label="mode === 'paper' ? '收藏' : '感兴趣'" @click="emit('like')">
      <span class="action-ring action-ring-lg">
        <!-- heart for paper, star for idea -->
        <svg v-if="mode === 'paper'" xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
      </span>
      <span class="action-label">{{ mode === 'paper' ? '收藏' : '感兴趣' }}</span>
    </button>

    <!-- Detail -->
    <button type="button" class="action-btn action-btn--detail" aria-label="详情" @click="emit('detail')">
      <span class="action-ring action-ring-sm">
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
      </span>
      <span class="action-label">详情</span>
    </button>
  </div>
</template>

<style scoped>
/* ===== Base button ===== */
.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: transparent;
  border: none;
  /* outer padding ensures touch target >= 44px even with smaller rings */
  padding: 4px 8px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.action-btn:active {
  transform: scale(0.84);
}
.action-btn:disabled { cursor: default; }

/* ===== Per-action explicit colors (scoped → highest priority) ===== */
.action-btn--undo-on  { color: var(--color-tinder-gold); }
.action-btn--undo-off { color: var(--color-text-muted); opacity: 0.4; }
.action-btn--skip     { color: var(--color-tinder-pink); }
.action-btn--like     { color: var(--color-tinder-green); }
.action-btn--detail   { color: var(--color-tinder-blue); }

/* ===== Ring ===== */
.action-ring {
  border-radius: 9999px;
  border: 2.5px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s ease, box-shadow 0.15s ease, border-width 0.1s ease;
}
.action-ring-lg {
  width: 52px;
  height: 52px;
  border-width: 3px;
  background: color-mix(in srgb, currentColor 30%, var(--color-bg-card));
  box-shadow: 0 0 14px color-mix(in srgb, currentColor 35%, transparent);
}
.action-ring-sm {
  width: 36px;
  height: 36px;
  border-width: 2px;
  background: color-mix(in srgb, currentColor 18%, var(--color-bg-card));
}

/* Active feedback — deepen the ring fill on press */
.action-btn:active .action-ring-lg {
  background: color-mix(in srgb, currentColor 55%, var(--color-bg-card));
  box-shadow: 0 0 24px color-mix(in srgb, currentColor 50%, transparent);
  border-width: 3.5px;
}
.action-btn:active .action-ring-sm {
  background: color-mix(in srgb, currentColor 38%, var(--color-bg-card));
}

/* ===== Label ===== */
.action-label {
  font-size: 10px;
  margin-top: 4px;
  font-weight: 500;
  color: currentColor;
  white-space: nowrap;
  line-height: 1;
}
</style>
