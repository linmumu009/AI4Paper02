<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { PaperSummary } from '../types/paper'
import {
  buildShareUrl,
  copyToClipboard,
  generateQrDataUrl,
  generateCardImage,
  downloadBlob,
} from '../utils/shareCard'
import { useToast } from '../composables/useToast'

const props = defineProps<{
  paper: PaperSummary
  cardRef: HTMLElement | null
  tier: string
  /** Plain-text card content for "复制纯文本" option */
  plainText: string
}>()

const { showToast } = useToast()

// ---------- dropdown state ----------
const menuOpen = ref(false)
const menuEl = ref<HTMLElement | null>(null)
const btnEl = ref<HTMLElement | null>(null)

function toggleMenu(e: MouseEvent) {
  e.stopPropagation()
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function handleOutsideClick(e: MouseEvent) {
  if (
    menuEl.value && !menuEl.value.contains(e.target as Node) &&
    btnEl.value && !btnEl.value.contains(e.target as Node)
  ) {
    closeMenu()
  }
}

onMounted(() => document.addEventListener('click', handleOutsideClick, true))
onUnmounted(() => document.removeEventListener('click', handleOutsideClick, true))

// ---------- QR modal state ----------
const qrModalOpen = ref(false)
const qrDataUrl = ref('')
const shareUrl = computed(() => buildShareUrl(props.paper.paper_id))

// ---------- loading flags ----------
const loadingImage = ref(false)
const loadingQr = ref(false)

// ---------- actions ----------

async function doCopyText() {
  closeMenu()
  try {
    await copyToClipboard(props.plainText)
    showToast('卡片内容已复制', 'success', 2000)
  } catch {
    showToast('复制失败，请手动选取文本', 'error')
  }
}

async function doCopyLink() {
  closeMenu()
  try {
    await copyToClipboard(shareUrl.value)
    showToast('链接已复制到剪贴板', 'success', 2000)
  } catch {
    showToast('复制失败', 'error')
  }
}

async function doDownloadImage() {
  closeMenu()
  if (!props.cardRef) {
    showToast('无法获取卡片元素，请稍后重试', 'error')
    return
  }
  loadingImage.value = true
  try {
    const isDark = document.documentElement.classList.contains('dark')
    const watermark = props.tier === 'free'
    let siteQrDataUrl: string | undefined
    if (watermark) {
      siteQrDataUrl = await generateQrDataUrl(window.location.origin, isDark)
    }
    const blob = await generateCardImage(props.cardRef, {
      watermark,
      qrDataUrl: siteQrDataUrl,
    })
    downloadBlob(blob, `ai4papers-${props.paper.paper_id}.png`)
    showToast('图片已下载', 'success', 2000)
  } catch (err) {
    console.error('[ShareMenu] screenshot error:', err)
    const msg = err instanceof Error && err.message
      ? `截图失败：${err.message.slice(0, 60)}`
      : '截图失败，请重试'
    showToast(msg, 'error')
  } finally {
    loadingImage.value = false
  }
}

async function doShowQr() {
  closeMenu()
  loadingQr.value = true
  qrModalOpen.value = true
  try {
    const isDark = document.documentElement.classList.contains('dark')
    qrDataUrl.value = await generateQrDataUrl(shareUrl.value, isDark)
  } catch {
    showToast('二维码生成失败', 'error')
    qrModalOpen.value = false
  } finally {
    loadingQr.value = false
  }
}

function closeQrModal() {
  qrModalOpen.value = false
}
</script>

<template>
  <!-- Wrapper: relative container for dropdown positioning -->
  <div class="relative">
    <!-- Trigger button -->
    <button
      ref="btnEl"
      class="quick-action-btn"
      :title="menuOpen ? '关闭分享菜单' : '分享'"
      aria-label="分享卡片"
      :aria-expanded="menuOpen"
      @click.stop="toggleMenu"
    >
      <!-- Share icon -->
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
        <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
      </svg>
    </button>

    <!-- Dropdown menu -->
    <Transition name="share-menu">
      <div
        v-if="menuOpen"
        ref="menuEl"
        class="share-dropdown"
        role="menu"
        aria-label="分享选项"
      >
        <!-- 复制纯文本 -->
        <button class="share-item" role="menuitem" @click.stop="doCopyText">
          <span class="share-item-icon">⎘</span>
          <span>复制纯文本</span>
        </button>

        <!-- 复制链接 -->
        <button class="share-item" role="menuitem" @click.stop="doCopyLink">
          <span class="share-item-icon">🔗</span>
          <span>复制链接</span>
        </button>

        <!-- 下载图片 -->
        <button
          class="share-item"
          role="menuitem"
          :disabled="loadingImage"
          @click.stop="doDownloadImage"
        >
          <span class="share-item-icon">
            <svg v-if="loadingImage" class="spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            <span v-else>🖼</span>
          </span>
          <span>{{ loadingImage ? '生成中…' : '下载图片' }}</span>
          <span v-if="tier === 'free'" class="share-badge">含水印</span>
        </button>

        <!-- 显示二维码 -->
        <button
          class="share-item"
          role="menuitem"
          :disabled="loadingQr"
          @click.stop="doShowQr"
        >
          <span class="share-item-icon">⬛</span>
          <span>显示二维码</span>
        </button>
      </div>
    </Transition>
  </div>

  <!-- QR modal (Teleport to body to avoid z-index clipping) -->
  <Teleport to="body">
    <Transition name="qr-modal">
      <div
        v-if="qrModalOpen"
        class="qr-overlay"
        role="dialog"
        aria-modal="true"
        aria-label="分享二维码"
        @click.self="closeQrModal"
      >
        <div class="qr-card">
          <button class="qr-close" aria-label="关闭" @click="closeQrModal">✕</button>
          <p class="qr-title">扫码查看论文</p>

          <div class="qr-img-wrap">
            <div v-if="loadingQr" class="qr-loading">
              <svg class="spin" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
            </div>
            <img v-else-if="qrDataUrl" :src="qrDataUrl" alt="分享二维码" class="qr-img" />
          </div>

          <p class="qr-url">{{ shareUrl }}</p>

          <button class="qr-copy-btn" @click="doCopyLink">复制链接</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ---------- Trigger button (matches PaperCard .quick-action-btn) ---------- */
.quick-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.quick-action-btn:hover {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

/* ---------- Dropdown ---------- */
.share-dropdown {
  position: absolute;
  bottom: calc(100% + 6px);
  right: 0;
  min-width: 148px;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-border, #e4e4e7);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.14);
  padding: 4px;
  z-index: 200;
  overflow: hidden;
}

.share-item {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 10px;
  font-size: 12px;
  color: var(--color-text-primary);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
  white-space: nowrap;
}
.share-item:hover:not(:disabled) {
  background: var(--color-bg-elevated, #f4f4f5);
}
.share-item:disabled {
  opacity: 0.55;
  cursor: default;
}

.share-item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  font-size: 13px;
  flex-shrink: 0;
}

.share-badge {
  margin-left: auto;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 99px;
  background: var(--color-bg-elevated, #f4f4f5);
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* ---------- Dropdown transition ---------- */
.share-menu-enter-active,
.share-menu-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.share-menu-enter-from,
.share-menu-leave-to {
  opacity: 0;
  transform: translateY(4px) scale(0.97);
}

/* ---------- QR overlay ---------- */
.qr-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: rgba(0,0,0,0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.qr-card {
  position: relative;
  background: var(--color-bg-card, #fff);
  border-radius: 16px;
  padding: 24px 20px 20px;
  width: min(320px, 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
}

.qr-close {
  position: absolute;
  top: 10px;
  right: 12px;
  width: 26px;
  height: 26px;
  border: none;
  background: var(--color-bg-elevated, #f4f4f5);
  border-radius: 50%;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.qr-close:hover {
  background: var(--color-border, #e4e4e7);
}

.qr-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.qr-img-wrap {
  width: 160px;
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-border, #e4e4e7);
}

.qr-img {
  width: 160px;
  height: 160px;
  display: block;
}

.qr-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
}

.qr-url {
  font-size: 11px;
  color: var(--color-text-muted);
  word-break: break-all;
  text-align: center;
  margin: 0;
  max-width: 260px;
}

.qr-copy-btn {
  padding: 7px 20px;
  border-radius: 8px;
  border: none;
  background: var(--color-tinder-blue, #3b82f6);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.qr-copy-btn:hover {
  opacity: 0.87;
}

/* ---------- QR modal transition ---------- */
.qr-modal-enter-active,
.qr-modal-leave-active {
  transition: opacity 0.2s ease;
}
.qr-modal-enter-active .qr-card,
.qr-modal-leave-active .qr-card {
  transition: transform 0.2s ease;
}
.qr-modal-enter-from,
.qr-modal-leave-to {
  opacity: 0;
}
.qr-modal-enter-from .qr-card {
  transform: scale(0.95);
}
.qr-modal-leave-to .qr-card {
  transform: scale(0.95);
}

/* ---------- Spinner ---------- */
.spin {
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
