/**
 * useMyPapersState — extracts "我的论文" (My Papers) feature state from DailyDigest.vue
 *
 * This composable owns:
 *   - My papers list (center panel), pagination, search/filter/sort, polling
 *   - Viewing a single user paper (detail panel), polling during processing
 *   - Upload dialog state
 *
 * Migration note: DailyDigest.vue should be progressively refactored to use this
 * composable instead of inline state. See plan item p2-digest-refactor.
 */

import { ref, watch, computed } from 'vue'
import {
  fetchUserPapers,
  fetchUserPaperInstitutions,
  fetchUserPaperDetail,
  processUserPaper,
} from '../api'
import type { UserPaper } from '../types/paper'
import { useToast } from './useToast'

export function useMyPapersState() {
  const { showError } = useToast()

  // ── Center list state ──────────────────────────────────────────────────────
  const myPapersMode = ref(false)
  const myPapersCenter = ref<UserPaper[]>([])
  const myPapersCenterLoading = ref(false)
  const myPapersSearch = ref('')
  const myPapersSourceFilter = ref('')
  const myPapersInstitutionFilter = ref('')
  const myPapersInstitutions = ref<string[]>([])
  const myPapersSort = ref<'date_desc' | 'date_asc' | 'title_asc'>('date_desc')
  const myPapersViewMode = ref<'card' | 'compact'>('card')
  const myPapersTotal = ref(0)
  const myPapersPageSize = 20
  const myPapersHasMore = ref(false)

  let _myPapersCenterPollTimer: ReturnType<typeof setInterval> | null = null
  let _myPapersSearchDebounce: ReturnType<typeof setTimeout> | null = null

  // ── Detail / single paper view state ──────────────────────────────────────
  const viewingUserPaperId = ref<string | null>(null)
  const viewingUserPaper = ref<UserPaper | null>(null)
  const userPaperLoading = ref(false)
  const processingElapsedSeconds = ref(0)
  const showUploadDialog = ref(false)

  let _userPaperPollTimer: ReturnType<typeof setInterval> | null = null
  let _processingTickTimer: ReturnType<typeof setInterval> | null = null

  // ── Sorted view ────────────────────────────────────────────────────────────
  const myPapersCenterSorted = computed(() => {
    const list = myPapersCenter.value
    if (myPapersSort.value === 'title_asc') {
      return [...list].sort((a, b) => (a.title || '').localeCompare(b.title || '', 'zh-CN'))
    }
    if (myPapersSort.value === 'date_asc') {
      return [...list].sort((a, b) => a.created_at.localeCompare(b.created_at))
    }
    return list
  })

  // ── Center list operations ─────────────────────────────────────────────────
  async function loadMyPapersInstitutions() {
    try {
      myPapersInstitutions.value = await fetchUserPaperInstitutions()
    } catch (e) {
      console.warn('[MyPapers] 加载机构列表失败', e)
    }
  }

  async function loadMyPapersCenter(opts?: { append?: boolean }) {
    myPapersCenterLoading.value = true
    try {
      const offset = opts?.append ? myPapersCenter.value.length : 0
      const res = await fetchUserPapers({
        limit: myPapersPageSize,
        offset,
        search: myPapersSearch.value.trim() || undefined,
        source_type: myPapersSourceFilter.value || undefined,
        institution: myPapersInstitutionFilter.value || undefined,
      })
      if (opts?.append) {
        myPapersCenter.value = [...myPapersCenter.value, ...res.papers]
      } else {
        myPapersCenter.value = res.papers
      }
      myPapersTotal.value = res.total
      myPapersHasMore.value = res.papers.length >= myPapersPageSize

      const hasProcessing = res.papers.some(
        p => p.process_status === 'processing' || p.process_status === 'pending',
      )
      if (hasProcessing) {
        _startMyPapersCenterPoll()
      } else {
        _stopMyPapersCenterPoll()
      }
    } catch (e) {
      showError('加载上传论文列表失败，请稍后重试')
      console.error('[MyPapers] loadMyPapersCenter 失败', e)
    } finally {
      myPapersCenterLoading.value = false
    }
  }

  function loadMoreMyPapers() {
    loadMyPapersCenter({ append: true })
  }

  function _startMyPapersCenterPoll() {
    if (_myPapersCenterPollTimer) return
    _myPapersCenterPollTimer = setInterval(async () => {
      try {
        const loadedCount = Math.max(myPapersCenter.value.length, myPapersPageSize)
        const res = await fetchUserPapers({
          limit: loadedCount,
          offset: 0,
          search: myPapersSearch.value.trim() || undefined,
          source_type: myPapersSourceFilter.value || undefined,
          institution: myPapersInstitutionFilter.value || undefined,
        })
        const updatedMap = new Map(res.papers.map(p => [p.paper_id, p]))
        myPapersCenter.value = myPapersCenter.value.map(p => updatedMap.get(p.paper_id) ?? p)
        myPapersTotal.value = res.total
        myPapersHasMore.value =
          res.papers.length >= loadedCount && myPapersCenter.value.length < res.total
        const hasProcessing = res.papers.some(
          p => p.process_status === 'processing' || p.process_status === 'pending',
        )
        if (!hasProcessing) _stopMyPapersCenterPoll()
      } catch (e) {
        console.warn('[MyPapers] 轮询刷新失败', e)
      }
    }, 3000)
  }

  function _stopMyPapersCenterPoll() {
    if (_myPapersCenterPollTimer) {
      clearInterval(_myPapersCenterPollTimer)
      _myPapersCenterPollTimer = null
    }
  }

  // Debounced reload on search/filter change
  watch([myPapersSearch, myPapersSourceFilter, myPapersInstitutionFilter], () => {
    if (_myPapersSearchDebounce) clearTimeout(_myPapersSearchDebounce)
    _myPapersSearchDebounce = setTimeout(() => {
      myPapersCenter.value = []
      loadMyPapersCenter()
    }, 300)
  })

  // ── Single paper view operations ───────────────────────────────────────────
  async function loadUserPaper(paperId: string) {
    userPaperLoading.value = true
    try {
      const p = await fetchUserPaperDetail(paperId)
      viewingUserPaper.value = p
      if (p.process_status === 'processing' || p.process_status === 'pending') {
        _startUserPaperPoll(paperId)
      } else {
        _stopUserPaperPoll()
      }
    } catch (e) {
      showError('加载论文详情失败，请稍后重试')
      console.error('[UserPaper] loadUserPaper 失败', e)
    } finally {
      userPaperLoading.value = false
    }
  }

  function _startUserPaperPoll(paperId: string) {
    if (_userPaperPollTimer) return
    _userPaperPollTimer = setInterval(async () => {
      try {
        const p = await fetchUserPaperDetail(paperId)
        viewingUserPaper.value = p
        if (p.process_status !== 'processing' && p.process_status !== 'pending') {
          _stopUserPaperPoll()
        }
      } catch (e) {
        console.warn('[UserPaper] 轮询失败', e)
      }
    }, 3000)

    if (!_processingTickTimer) {
      const p = viewingUserPaper.value
      const startedAt = p?.process_started_at
        ? new Date(p.process_started_at).getTime()
        : Date.now()
      _processingTickTimer = setInterval(() => {
        processingElapsedSeconds.value = Math.floor((Date.now() - startedAt) / 1000)
      }, 1000)
    }
  }

  function _stopUserPaperPoll() {
    if (_userPaperPollTimer) {
      clearInterval(_userPaperPollTimer)
      _userPaperPollTimer = null
    }
    if (_processingTickTimer) {
      clearInterval(_processingTickTimer)
      _processingTickTimer = null
      processingElapsedSeconds.value = 0
    }
  }

  async function retryUserPaper() {
    if (!viewingUserPaperId.value) return
    try {
      await processUserPaper(viewingUserPaperId.value)
      await loadUserPaper(viewingUserPaperId.value)
    } catch (e) {
      showError('重新处理论文失败，请稍后重试')
      console.error('[UserPaper] retryUserPaper 失败', e)
    }
  }

  // ── Cleanup ────────────────────────────────────────────────────────────────
  function cleanup() {
    _stopUserPaperPoll()
    _stopMyPapersCenterPoll()
    if (_myPapersSearchDebounce) clearTimeout(_myPapersSearchDebounce)
  }

  return {
    // center list
    myPapersMode,
    myPapersCenter,
    myPapersCenterLoading,
    myPapersCenterSorted,
    myPapersSearch,
    myPapersSourceFilter,
    myPapersInstitutionFilter,
    myPapersInstitutions,
    myPapersSort,
    myPapersViewMode,
    myPapersTotal,
    myPapersPageSize,
    myPapersHasMore,
    loadMyPapersInstitutions,
    loadMyPapersCenter,
    loadMoreMyPapers,
    // single paper
    viewingUserPaperId,
    viewingUserPaper,
    userPaperLoading,
    processingElapsedSeconds,
    showUploadDialog,
    loadUserPaper,
    retryUserPaper,
    // lifecycle
    cleanup,
  }
}
