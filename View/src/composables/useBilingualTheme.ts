import { ref, readonly } from 'vue'

const STORAGE_KEY = 'ai4papers-bilingual-theme'

export interface BilingualPreset {
  name: string
  hue: number
  saturation: number
}

export interface BilingualTheme {
  hue: number
  saturation: number
  intensity: number  // 2–15 (背景 opacity %)
  fontSize: number   // 12–20 (px，双语模式基准字号)
}

export const BILINGUAL_PRESETS: BilingualPreset[] = [
  { name: '蓝',   hue: 195, saturation: 70 },
  { name: '绿',   hue: 150, saturation: 60 },
  { name: '紫',   hue: 270, saturation: 60 },
  { name: '橙',   hue: 30,  saturation: 80 },
  { name: '玫瑰', hue: 340, saturation: 70 },
  { name: '灰',   hue: 220, saturation: 10 },
]

const DEFAULT_THEME: BilingualTheme = {
  hue: 195,
  saturation: 70,
  intensity: 6,
  fontSize: 15,
}

function loadFromStorage(): BilingualTheme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_THEME }
    const parsed = JSON.parse(raw) as Partial<BilingualTheme>
    return {
      hue: typeof parsed.hue === 'number' ? parsed.hue : DEFAULT_THEME.hue,
      saturation: typeof parsed.saturation === 'number' ? parsed.saturation : DEFAULT_THEME.saturation,
      intensity: typeof parsed.intensity === 'number' ? parsed.intensity : DEFAULT_THEME.intensity,
      fontSize: typeof parsed.fontSize === 'number' ? parsed.fontSize : DEFAULT_THEME.fontSize,
    }
  } catch {
    return { ...DEFAULT_THEME }
  }
}

function applyToDOM(theme: BilingualTheme) {
  const root = document.documentElement
  root.style.setProperty('--bilingual-hue', String(theme.hue))
  root.style.setProperty('--bilingual-saturation', `${theme.saturation}%`)
  root.style.setProperty('--bilingual-intensity', String(theme.intensity))
  root.style.setProperty('--bilingual-font-size', `${theme.fontSize}px`)
}

const _theme = ref<BilingualTheme>(loadFromStorage())

export function initBilingualTheme() {
  _theme.value = loadFromStorage()
  applyToDOM(_theme.value)
}

export function useBilingualTheme() {
  function setPreset(preset: BilingualPreset) {
    _theme.value = { ..._theme.value, hue: preset.hue, saturation: preset.saturation }
    _persist()
  }

  function setIntensity(value: number) {
    _theme.value = { ..._theme.value, intensity: Math.min(15, Math.max(2, value)) }
    _persist()
  }

  function setFontSize(value: number) {
    _theme.value = { ..._theme.value, fontSize: Math.min(20, Math.max(12, value)) }
    _persist()
  }

  function _persist() {
    applyToDOM(_theme.value)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(_theme.value))
    } catch {
      // ignore storage errors
    }
  }

  function isActivePreset(preset: BilingualPreset): boolean {
    return _theme.value.hue === preset.hue && _theme.value.saturation === preset.saturation
  }

  return {
    theme: readonly(_theme),
    presets: BILINGUAL_PRESETS,
    setPreset,
    setIntensity,
    setFontSize,
    isActivePreset,
  }
}
