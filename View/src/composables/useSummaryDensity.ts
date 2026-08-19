import { computed, ref } from 'vue'
import type { SummaryDensity } from '../types/paper'

export const SUMMARY_DENSITY_STORAGE_KEY = 'ai4papers-summary-density'

const explicitDensity = ref<SummaryDensity | null>(null)
let hydrated = false

function hydratePreference() {
  if (hydrated || typeof window === 'undefined') return
  hydrated = true
  try {
    const stored = window.localStorage.getItem(SUMMARY_DENSITY_STORAGE_KEY)
    if (stored === 'concise' || stored === 'detailed') explicitDensity.value = stored
  } catch {
    // Reading remains fully usable when storage is unavailable.
  }
}

export function useSummaryDensity(defaultDensity: SummaryDensity = 'concise') {
  hydratePreference()

  const density = computed<SummaryDensity>({
    get: () => explicitDensity.value ?? defaultDensity,
    set: (value) => {
      explicitDensity.value = value
      if (typeof window === 'undefined') return
      try {
        window.localStorage.setItem(SUMMARY_DENSITY_STORAGE_KEY, value)
      } catch {
        // Keep the in-memory preference for this session.
      }
    },
  })

  return {
    density,
    hasExplicitPreference: computed(() => explicitDensity.value !== null),
    setDensity: (value: SummaryDensity) => {
      density.value = value
    },
  }
}

/** Clear the explicit choice so each surface can use its own sensible default. */
export function clearSummaryDensityPreference() {
  explicitDensity.value = null
  hydrated = true
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(SUMMARY_DENSITY_STORAGE_KEY)
  } catch {
    // Nothing else is required when storage is unavailable.
  }
}
