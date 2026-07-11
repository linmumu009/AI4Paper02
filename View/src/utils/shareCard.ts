/**
 * shareCard.ts
 * Utilities for sharing a PaperCard: link construction, clipboard copy,
 * DOM-to-PNG screenshot with optional watermark, and QR code generation.
 *
 * All heavy dependencies (modern-screenshot, qrcode) are lazy-loaded on first
 * use so they do not affect the initial bundle.
 *
 * NOTE: html2canvas was replaced with modern-screenshot because html2canvas
 * cannot parse oklch() colour values emitted by Tailwind CSS v4.
 */

// ---------------------------------------------------------------------------
// Link
// ---------------------------------------------------------------------------

// Hard-code the canonical origin so links are consistent across dev/prod and
// are never accidentally prefixed with a SPA base path.
const CANONICAL_SITE_URL = 'https://ai4papers.com'

export function buildShareUrl(paperId: string): string {
  return `${CANONICAL_SITE_URL}/papers/${paperId}`
}

// ---------------------------------------------------------------------------
// Clipboard (with iOS Safari fallback)
// ---------------------------------------------------------------------------

export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  // Fallback for older Safari / WebView
  const el = document.createElement('textarea')
  el.value = text
  el.setAttribute('readonly', '')
  el.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

// ---------------------------------------------------------------------------
// QR code (lazy-loads qrcode)
// ---------------------------------------------------------------------------

export async function generateQrDataUrl(
  text: string,
  darkMode: boolean,
): Promise<string> {
  const QRCode = (await import('qrcode')).default
  return QRCode.toDataURL(text, {
    width: 160,
    margin: 2,
    color: {
      dark: darkMode ? '#e4e4e7' : '#18181b',
      light: darkMode ? '#27272a' : '#ffffff',
    },
  })
}

// ---------------------------------------------------------------------------
// Card screenshot (lazy-loads modern-screenshot)
// ---------------------------------------------------------------------------

export interface CardImageOptions {
  /** If true, stamp a "AI4Papers" watermark band at the bottom of the image. */
  watermark: boolean
  /** Pre-generated QR DataURL used inside the watermark band. */
  qrDataUrl?: string
}

/**
 * Render the given card element to a PNG Blob.
 *
 * modern-screenshot serialises the DOM into an SVG <foreignObject> and lets the
 * browser render it, so all modern CSS (oklch, color-mix, backdrop-filter …)
 * works out of the box — unlike html2canvas which cannot parse oklch().
 *
 * The card's scrollable body is temporarily expanded to its full scroll height
 * so that all content is captured, then restored afterward.
 */
export async function generateCardImage(
  cardEl: HTMLElement,
  options: CardImageOptions,
): Promise<Blob> {
  const { domToBlob } = await import('modern-screenshot')

  // Find the scrollable body inside the card
  const scrollBody = cardEl.querySelector<HTMLElement>('.card-body')

  // Save original styles so we can restore them in `finally`
  const savedStyles: { el: HTMLElement; overflow: string; maxHeight: string; height: string }[] = []

  function expandEl(el: HTMLElement) {
    savedStyles.push({
      el,
      overflow: el.style.overflow,
      maxHeight: el.style.maxHeight,
      height: el.style.height,
    })
    el.style.overflow = 'visible'
    el.style.maxHeight = 'none'
    el.style.height = 'auto'
  }

  if (scrollBody) expandEl(scrollBody)

  // Also expand the root card container so the full content is visible
  const savedCardOverflow = cardEl.style.overflow
  const savedCardHeight = cardEl.style.height
  const savedCardMaxH = cardEl.style.maxHeight
  cardEl.style.overflow = 'visible'
  cardEl.style.height = 'auto'
  cardEl.style.maxHeight = 'none'

  // Watermark overlay DOM (appended before capture, removed after)
  let watermarkEl: HTMLElement | null = null

  try {
    if (options.watermark) {
      watermarkEl = buildWatermarkEl(options.qrDataUrl)
      cardEl.appendChild(watermarkEl)
    }

    // Capture dimensions after DOM mutations (watermark may have added height)
    const captureWidth = cardEl.offsetWidth
    const captureHeight = cardEl.scrollHeight

    const blob = await domToBlob(cardEl, {
      scale: window.devicePixelRatio || 2,
      width: captureWidth,
      height: captureHeight,
      type: 'image/png',
    })

    if (!blob) throw new Error('domToBlob 返回 null')
    return blob
  } finally {
    // Restore scroll body styles
    for (const saved of savedStyles) {
      saved.el.style.overflow = saved.overflow
      saved.el.style.maxHeight = saved.maxHeight
      saved.el.style.height = saved.height
    }
    // Restore card root styles
    cardEl.style.overflow = savedCardOverflow
    cardEl.style.height = savedCardHeight
    cardEl.style.maxHeight = savedCardMaxH

    // Remove watermark element
    if (watermarkEl && watermarkEl.parentNode === cardEl) {
      cardEl.removeChild(watermarkEl)
    }
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a watermark band element to append to the card before screenshot. */
function buildWatermarkEl(qrDataUrl?: string): HTMLElement {
  const el = document.createElement('div')
  el.style.cssText = [
    'display:flex',
    'align-items:center',
    'justify-content:space-between',
    'gap:8px',
    'padding:8px 14px',
    'background:linear-gradient(135deg,#7c3aed 0%,#a855f7 100%)',
    'border-radius:0 0 12px 12px',
    'margin-top:2px',
  ].join(';')

  // Text block
  const textEl = document.createElement('div')
  textEl.style.cssText = 'display:flex;flex-direction:column;gap:2px'

  const titleEl = document.createElement('span')
  titleEl.textContent = 'AI4Papers'
  titleEl.style.cssText = 'color:#fff;font-size:13px;font-weight:700;letter-spacing:0.04em'

  const subEl = document.createElement('span')
  subEl.textContent = '每日 arXiv 论文推荐'
  subEl.style.cssText = 'color:rgba(255,255,255,0.75);font-size:10px'

  textEl.appendChild(titleEl)
  textEl.appendChild(subEl)
  el.appendChild(textEl)

  // QR image (right side)
  if (qrDataUrl) {
    const img = document.createElement('img')
    img.src = qrDataUrl
    img.style.cssText = 'width:44px;height:44px;border-radius:4px;background:#fff;padding:2px'
    el.appendChild(img)
  }

  return el
}

/** Trigger a PNG download in the browser. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, 1000)
}
