import axios from 'axios'
import type {
  DatesResponse,
  PapersResponse,
  PaperDetailResponse,
  DigestResponse,
  PipelineStatusResponse,
  KbTree,
  KbFolder,
  KbPaper,
  KbNote,
  KbNotesResponse,
  KbAnnotation,
  KbAnnotationsResponse,
  KbCompareResult,
  KbCompareResultsTree,
  PaperSummary,
  AuthPayload,
  AuthRegisterPayload,
  AuthSmsLoginPayload,
  SmsSendPayload,
  SmsSendResponse,
  SmsVerifyPayload,
  SmsVerifyResponse,
  AuthActionResponse,
  AuthMeResponse,
  AuthLogoutResponse,
  UserPaper,
  UserPapersListResponse,
  UserPaperProcessStatusResponse,
  UserPaperTranslateStatusResponse,
  UserPaperFilesResponse,
  UserPaperTree,
  AdminUsersResponse,
  AdminUserDetailResponse,
  SubscriptionStatusResponse,
  SubscriptionRedeemResponse,
  AdminIssueRedeemKeysResponse,
  AdminRedeemKeyListResponse,
  UserTier,
  UserRole,
  PipelineRunStatus,
  ScheduleConfig,
  SystemConfigResponse,
  SystemConfigUpdateResponse,
  ChatMessage,
  ChatHistoryResponse,
} from '../types/paper'

// In production builds (Tauri exe), VITE_API_BASE provides the remote server
// origin so all requests use absolute URLs.  In dev mode the Vite proxy
// forwards /api to the target, avoiding CORS issues entirely.
//
// Normalisation rules (applied at runtime so mis-configured .env values are
// corrected automatically instead of silently breaking all API calls):
//   1. Trim whitespace
//   2. Strip trailing slashes   → "https://host.com///" → "https://host.com"
//   3. Strip accidental /api    → "https://host.com/api" → "https://host.com"
//      so that baseURL never becomes "…/api/api/…"
function _normaliseApiBase(raw: string): string {
  let s = (raw || '').trim().replace(/\/+$/, '') // 1+2: trim & strip trailing slashes
  if (s.toLowerCase().endsWith('/api')) s = s.slice(0, -4) // 3: strip /api suffix
  return s
}

export const API_ORIGIN: string = import.meta.env.PROD
  ? _normaliseApiBase(import.meta.env.VITE_API_BASE || '')
  : ''

// Warn early so developers can catch misconfiguration immediately
if (import.meta.env.PROD && !API_ORIGIN) {
  console.error(
    '[AI4Papers] VITE_API_BASE is not configured — all API requests will fail in the ' +
    'desktop app.  Set VITE_API_BASE=https://your-server.com in exe/.env.production and rebuild.',
  )
}

// ---------------------------------------------------------------------------
// Session token 持久化（桌面端跨域场景使用 Authorization header 代替 Cookie）
// ---------------------------------------------------------------------------
const SESSION_TOKEN_KEY = 'ai4papers_session_id'

export function getSessionToken(): string {
  return localStorage.getItem(SESSION_TOKEN_KEY) || ''
}

export function setSessionToken(token: string) {
  if (token) {
    localStorage.setItem(SESSION_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(SESSION_TOKEN_KEY)
  }
}

export function clearSessionToken() {
  localStorage.removeItem(SESSION_TOKEN_KEY)
}

// ---------------------------------------------------------------------------
// Tauri IPC bridge —— 桌面端所有 HTTP 请求都走 Rust reqwest，
// 完全绕过 WebView2 的网络栈（WebView2 无法 fetch 外部域名）。
// ---------------------------------------------------------------------------

/** Tauri 2 全局 IPC invoke（不依赖 @tauri-apps/api） */
const _tauriInvoke: ((cmd: string, args?: Record<string, unknown>) => Promise<any>) | null =
  (window as any).__TAURI_INTERNALS__?.invoke ?? null

/** 是否处于 Tauri 桌面环境 */
export const IS_TAURI = !!API_ORIGIN && !!_tauriInvoke

/**
 * Tauri 专用：通过 Rust IPC 获取文本内容（用于 MarkdownViewer 等 fetch 场景）。
 * WebView2 无法直接 fetch 外部域名，必须走此路径。
 */
export async function tauriFetchText(url: string): Promise<string> {
  if (!_tauriInvoke) throw new Error('Tauri IPC not available')
  const headers: Record<string, string> = { Accept: '*/*' }
  const token = getSessionToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const result = await _tauriInvoke('direct_request', {
    method: 'GET', url, headers, body: null,
  })
  if (result.status >= 400) throw new Error(`HTTP ${result.status}`)
  return result.body
}

/**
 * Tauri 专用：通过 Rust IPC 下载 PDF 二进制并返回 Blob URL。
 * 用于在本地 PDF.js viewer（iframe）中加载跨域 PDF 文件。
 * 调用方负责在不再需要时调用 URL.revokeObjectURL() 释放内存。
 */
export async function tauriFetchPdfBlobUrl(pdfUrl: string): Promise<string> {
  if (!_tauriInvoke) throw new Error('Tauri IPC not available')
  const headers: Record<string, string> = {}
  const token = getSessionToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const result: { base64: string; content_type: string; file_name: string } =
    await _tauriInvoke('direct_download_binary', { method: 'GET', url: pdfUrl, headers, body: null })
  const binary = atob(result.base64)
  const arr = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i)
  const blob = new Blob([arr], { type: 'application/pdf' })
  return URL.createObjectURL(blob)
}

/**
 * 将 File/Blob 读取为 base64 字符串（不含 data URI 前缀）。
 */
function fileToBase64(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // 去掉 "data:<mime>;base64," 前缀
      const idx = result.indexOf(',')
      resolve(idx >= 0 ? result.slice(idx + 1) : result)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/**
 * 自定义 Axios adapter：把请求转发给 Rust 端 `direct_request` / `direct_upload` 命令。
 * 返回一个符合 Axios 内部格式的 AxiosResponse。
 *
 * FormData（文件上传）路径：
 *   - 检测到 config.data 为 FormData 时，从中提取 File 条目转成 base64
 *   - 调用 Rust `direct_upload` 命令，由 Rust 用 reqwest 重建 multipart 请求
 */
async function tauriAdapter(config: any): Promise<any> {
  if (!_tauriInvoke) throw new Error('Tauri IPC not available')

  // ---- 拼完整 URL ----
  let fullUrl: string = config.url || ''
  if (config.baseURL && !fullUrl.startsWith('http')) {
    fullUrl = config.baseURL.replace(/\/+$/, '') + '/' + fullUrl.replace(/^\/+/, '')
  }

  // ---- 处理 query params ----
  if (config.params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(config.params)) {
      if (v !== undefined && v !== null) qs.append(k, String(v))
    }
    const qsStr = qs.toString()
    if (qsStr) fullUrl += (fullUrl.includes('?') ? '&' : '?') + qsStr
  }

  // ---- 请求头（通用） ----
  const headers: Record<string, string> = {}
  if (config.headers) {
    // Axios headers 可能是 AxiosHeaders 对象，遍历时需 toJSON
    const raw = typeof config.headers.toJSON === 'function' ? config.headers.toJSON() : config.headers
    for (const [k, v] of Object.entries(raw)) {
      if (v !== undefined && v !== null && v !== false) headers[k] = String(v)
    }
  }
  // 移除浏览器自动添加的无用头
  delete headers['User-Agent']

  // ================================================================
  // FormData 路径 → 调用 Rust direct_upload（multipart/form-data）
  // ================================================================
  if (config.data instanceof FormData) {
    const formData: FormData = config.data
    // 从 Content-Type 头中删除浏览器设置的 multipart 边界（Rust 会重建）
    delete headers['Content-Type']
    delete headers['content-type']

    // 找到第一个 File 条目
    let fileBase64 = ''
    let fileName = 'upload'
    let mimeType = 'application/octet-stream'
    const formFields: Record<string, string> = {}

    for (const [key, value] of formData.entries()) {
      if (value instanceof File) {
        fileName = value.name || key
        mimeType = value.type || 'application/octet-stream'
        fileBase64 = await fileToBase64(value)
      } else {
        formFields[key] = String(value)
      }
    }

    if (!fileBase64) {
      throw new Error('FormData 中未找到 File 条目')
    }

    const result = await _tauriInvoke('direct_upload', {
      url: fullUrl,
      headers,
      fileName,
      fileBase64,
      mimeType,
      formFields,
    })

    // 构造 Axios 兼容响应
    let responseData: any = result.body
    const ct = (result.headers?.['content-type'] || '')
    if (ct.includes('application/json')) {
      try { responseData = JSON.parse(result.body) } catch { /* keep raw */ }
    }

    const response = {
      data: responseData,
      status: result.status,
      statusText: '',
      headers: result.headers || {},
      config,
      request: {},
    }

    if (result.status >= 400) {
      const error: any = new Error(`Request failed with status code ${result.status}`)
      error.config = config
      error.response = response
      error.isAxiosError = true
      throw error
    }

    return response
  }

  // ================================================================
  // 普通 JSON / 文本路径 → 调用 Rust direct_request
  // ================================================================

  // ---- body ----
  let body: string | null = null
  if (config.data !== undefined && config.data !== null) {
    body = typeof config.data === 'string' ? config.data : JSON.stringify(config.data)
    if (!headers['Content-Type'] && !headers['content-type']) {
      headers['Content-Type'] = 'application/json'
    }
  }

  // ---- 调用 Rust direct_request ----
  const result = await _tauriInvoke('direct_request', {
    method: (config.method || 'get').toUpperCase(),
    url: fullUrl,
    headers,
    body,
  })

  // ---- 构造 Axios 兼容响应 ----
  let responseData: any = result.body
  const ct = (result.headers?.['content-type'] || '')
  if (ct.includes('application/json')) {
    try { responseData = JSON.parse(result.body) } catch { /* keep raw */ }
  }

  const response = {
    data: responseData,
    status: result.status,
    statusText: '',
    headers: result.headers || {},
    config,
    request: {},  // Axios 内部需要此字段
  }

  // 非 2xx 状态码时，模拟 Axios 的错误抛出行为
  if (result.status >= 400) {
    const error: any = new Error(`Request failed with status code ${result.status}`)
    error.config = config
    error.response = response
    error.isAxiosError = true
    throw error
  }

  return response
}

// ---------------------------------------------------------------------------
// Tauri 专用：二进制文件下载（通过 Rust 下载 → base64 → Blob URL 触发保存）
// ---------------------------------------------------------------------------

/**
 * 通过 Tauri Rust 命令下载二进制文件，并在浏览器侧通过 Blob URL 触发"另存为"。
 * 解决 WebView2 中 <a href="外部URL"> 无法下载且不携带 Auth header 的问题。
 */
async function tauriDownloadBinary(
  url: string,
  headers: Record<string, string>,
  fileName: string,
  method: string = 'GET',
  body: string | null = null,
): Promise<void> {
  if (!_tauriInvoke) throw new Error('Tauri IPC not available')

  const result: { base64: string; content_type: string; file_name: string } =
    await _tauriInvoke('direct_download_binary', { method, url, headers, body })

  // base64 → Uint8Array
  const binary = atob(result.base64)
  const arr = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i)

  const contentType = result.content_type || 'application/octet-stream'
  const name = result.file_name || fileName

  const blob = new Blob([arr], { type: contentType })
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}

// ---------------------------------------------------------------------------
// Tauri 专用：SSE 流式请求（通过 Rust Channel 逐行推送，返回 ReadableStream Response）
// ---------------------------------------------------------------------------

/**
 * 在 Tauri 环境下向 Rust 发起 SSE 流式请求，通过 Tauri Channel API 逐行接收数据，
 * 并包装成标准 Response（ReadableStream body）返回给调用方。
 * 调用方可以用相同的 reader 逻辑读取，与浏览器 fetch SSE 体验一致。
 *
 * Channel 机制：
 *   - JS 通过 __TAURI_INTERNALS__.transformCallback 注册持久回调，得到整数 ID
 *   - Rust 端 Channel<String> 接收该 ID，每次 send(line) 调用对应 JS 回调
 *   - 回调参数格式：{ message: string, id: number }
 */
function tauriStreamResponse(
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string | null,
): Response {
  if (!_tauriInvoke) throw new Error('Tauri IPC not available')

  const encoder = new TextEncoder()
  let ctrl!: ReadableStreamDefaultController<Uint8Array>

  const readable = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c
    },
  })

  const __TAURI__ = (window as any).__TAURI_INTERNALS__
  // once=false：持久回调，每次 Rust channel.send() 都会触发
  const channelId: number = __TAURI__.transformCallback(
    ({ message }: { message: string }) => {
      try {
        ctrl.enqueue(encoder.encode(message + '\n'))
      } catch {
        // stream 已关闭，忽略
      }
    },
    false,
  )

  _tauriInvoke('direct_request_stream', {
    method,
    url,
    headers,
    body,
    onEvent: channelId,
  })
    .then(() => {
      try {
        ctrl.close()
      } catch { /* already closed */ }
    })
    .catch((err: unknown) => {
      try {
        ctrl.error(new Error(String(err)))
      } catch { /* already errored */ }
    })

  return new Response(readable, { status: 200 })
}

// ---------------------------------------------------------------------------

const http = axios.create({
  baseURL: API_ORIGIN ? `${API_ORIGIN}/api` : '/api',
  timeout: 30000,
  withCredentials: !API_ORIGIN,  // web=true (cookie), desktop=false (Bearer)
  headers: { 'Cache-Control': 'no-cache' },
  ...(IS_TAURI ? { adapter: tauriAdapter } : {}),
})

// 请求拦截器：附加 Authorization header（桌面端跨域 Cookie 不可用时的回退）
http.interceptors.request.use((config) => {
  const token = getSessionToken()
  if (token && !config.headers['Authorization']) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：从 auth 登录/短信登录接口响应中提取并保存 session_id
http.interceptors.response.use(
  (response) => {
    const url: string = response.config?.url || ''
    // 登录 / 短信登录成功时保存 session_id 到 localStorage
    if (
      (url.includes('/auth/login') || url.includes('/auth/login/sms')) &&
      response.data?.session_id
    ) {
      setSessionToken(response.data.session_id)
    }
    return response
  },
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    const isKbEndpoint = url.startsWith('/kb') || url.includes('/kb/')
    if (status === 401 && isKbEndpoint) {
      window.dispatchEvent(new CustomEvent('auth-required'))
    }
    return Promise.reject(error)
  },
)

// ---------------------------------------------------------------------------
// 网络层工具：代理绕行直连（仅用于关键只读接口兜底）
// ---------------------------------------------------------------------------

/**
 * 判断 axios 错误是否属于网络层失败（非服务端返回的 HTTP 错误）。
 * 有 response 说明服务端已响应，属于应用/认证错误，不走直连回退。
 */
function isNetworkError(e: any): boolean {
  return !e?.response
}

/**
 * 通过 Tauri Rust 命令直接发起 HTTP GET，绕过系统代理。
 * 使用 Tauri 2 全局 IPC bridge（window.__TAURI_INTERNALS__）
 * 避免在 View/ 项目引入 @tauri-apps/api 模块依赖。
 * 仅在 Tauri 生产包（API_ORIGIN 非空）中调用。
 */
async function tauriDirectGet(urlPath: string): Promise<any> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tauriInvoke = (window as any).__TAURI_INTERNALS__?.invoke
  if (!tauriInvoke) throw new Error('Tauri IPC not available')
  const body: string = await tauriInvoke('direct_get', { url: `${API_ORIGIN}${urlPath}` })
  return JSON.parse(body)
}

/** 获取所有可用日期（含代理异常自动直连回退） */
export async function fetchDates(): Promise<DatesResponse> {
  try {
    const { data } = await http.get<DatesResponse>('/dates')
    return data
  } catch (e: any) {
    if (API_ORIGIN && isNetworkError(e)) {
      try {
        return await tauriDirectGet('/api/dates') as DatesResponse
      } catch {
        const err: any = new Error('网络连接失败，请检查系统代理是否已关闭或正常运行')
        err.errorType = 'proxy'
        throw err
      }
    }
    throw e
  }
}

/** 获取某天的论文列表 */
export async function fetchPapers(
  date: string,
  search?: string,
  institution?: string,
): Promise<PapersResponse> {
  const { data } = await http.get<PapersResponse>('/papers', {
    params: { date, search: search || undefined, institution: institution || undefined },
  })
  return data
}

/** 获取单篇论文详情 */
export async function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const { data } = await http.get<PaperDetailResponse>(`/papers/${paperId}`)
  return data
}

/** 获取每日摘要（含代理异常自动直连回退） */
export async function fetchDigest(date: string): Promise<DigestResponse> {
  try {
    const { data } = await http.get<DigestResponse>(`/digest/${date}`)
    return data
  } catch (e: any) {
    if (API_ORIGIN && isNetworkError(e)) {
      try {
        return await tauriDirectGet(`/api/digest/${date}`) as DigestResponse
      } catch {
        const err: any = new Error('网络连接失败，请检查系统代理是否已关闭或正常运行')
        err.errorType = 'proxy'
        throw err
      }
    }
    throw e
  }
}

/** 获取 Pipeline 状态 */
export async function fetchPipelineStatus(date: string): Promise<PipelineStatusResponse> {
  const { data } = await http.get<PipelineStatusResponse>('/pipeline/status', {
    params: { date },
  })
  return data
}

// ---------------------------------------------------------------------------
// Knowledge Base API
// ---------------------------------------------------------------------------

export type KbScope = 'kb' | 'inspiration' | 'mypapers'

/** 获取知识库完整树 */
export async function fetchKbTree(scope: KbScope = 'kb'): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree', { params: { scope } })
  return data
}

/** 创建文件夹 */
export async function createKbFolder(name: string, parentId?: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', {
    name,
    parent_id: parentId ?? null,
    scope,
  })
  return data
}

/** 重命名文件夹 */
export async function renameKbFolder(folderId: number, name: string, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name, scope })
  return data
}

/** 移动文件夹到新的父目录 (null = 根目录) */
export async function moveKbFolder(folderId: number, targetParentId: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, {
    target_parent_id: targetParentId,
    scope,
  })
  return data
}

/** 删除文件夹 */
export async function deleteKbFolder(folderId: number, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`, { params: { scope } })
}

/** 将论文加入知识库 */
export async function addKbPaper(
  paperId: string,
  paperData: PaperSummary,
  folderId?: number | null,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.post<KbPaper>('/kb/papers', {
    paper_id: paperId,
    paper_data: paperData,
    folder_id: folderId ?? null,
    scope,
  })
  return data
}

/** 从知识库移除论文 */
export async function removeKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`, { params: { scope } })
}

/** 批量移动论文到目标文件夹 (null = 根目录) */
export async function moveKbPapers(
  paperIds: string[],
  targetFolderId: number | null,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/kb/papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
    scope,
  })
  return data
}

// ---------------------------------------------------------------------------
// Note / File API
// ---------------------------------------------------------------------------

/** 获取论文下所有笔记/文件 */
export async function fetchNotes(paperId: string, scope: KbScope = 'kb'): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`, { params: { scope } })
  return data
}

/** 新建 Markdown 笔记 */
export async function createNote(
  paperId: string,
  title: string = '未命名笔记',
  content: string = '',
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content, scope })
  return data
}

/** 获取单个笔记详情（含内容） — scope 不需要，note_id 全局唯一 */
export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

/** 更新笔记标题/内容 — scope 不需要，note_id 全局唯一 */
export async function updateNote(
  noteId: number,
  payload: { title?: string; content?: string },
): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

/** 删除笔记/文件 — scope 不需要，note_id 全局唯一 */
export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

/** 上传文件到论文 */
export async function uploadNoteFile(paperId: string, file: File, scope: KbScope = 'kb'): Promise<KbNote> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/upload`, form, {
    params: { scope },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

/** 添加外部链接 */
export async function addNoteLink(
  paperId: string,
  title: string,
  url: string,
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/link`, { title, url, scope })
  return data
}

// ---------------------------------------------------------------------------
// Paper Compare (SSE streaming)
// ---------------------------------------------------------------------------

/** Initiate a streaming comparison analysis of 2-5 KB papers.
 *  Returns a raw Response whose body is an SSE text/event-stream.
 *  Each `data:` line is a JSON-encoded string chunk; the final line is `data: [DONE]`.
 *
 *  桌面端：SSE 流通过 Rust direct_request 一次性拿回全部内容再逐行解析。
 */
export async function fetchCompareStream(
  paperIds: string[],
  scope: KbScope = 'kb',
  compareResultIds?: number[],
): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getSessionToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const body: Record<string, unknown> = { paper_ids: paperIds, scope }
  if (compareResultIds && compareResultIds.length > 0) {
    body.compare_result_ids = compareResultIds
  }

  if (IS_TAURI && _tauriInvoke !== null) {
    // 桌面端走 Rust Channel 流式（逐行推送，真正 streaming）
    return tauriStreamResponse(
      'POST',
      `${API_ORIGIN}/api/kb/compare`,
      headers,
      JSON.stringify(body),
    )
  }

  return fetch(`${API_ORIGIN}/api/kb/compare`, {
    method: 'POST',
    headers,
    credentials: API_ORIGIN ? 'omit' : 'include',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Paper Chat API (论文追问问答)
// ---------------------------------------------------------------------------

/** 获取某篇论文的聊天历史记录 */
export async function fetchChatHistory(paperId: string): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatHistoryResponse>(`/papers/${encodeURIComponent(paperId)}/chat`)
  return data.messages
}

/**
 * 向论文发送追问消息并获取 SSE 流式回复。
 * 返回原始 Response，调用方负责读取 body stream。
 * 每行 `data: <json_chunk>` 或最终的 `data: [DONE]`。
 *
 * 桌面端：SSE 流通过 Rust direct_request 一次性拿回全部内容再逐行解析。
 */
export async function fetchPaperChatStream(paperId: string, message: string): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getSessionToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = `${API_ORIGIN}/api/papers/${encodeURIComponent(paperId)}/chat`

  if (IS_TAURI && _tauriInvoke !== null) {
    return tauriStreamResponse('POST', url, headers, JSON.stringify({ message }))
  }

  return fetch(url, {
    method: 'POST',
    headers,
    credentials: API_ORIGIN ? 'omit' : 'include',
    body: JSON.stringify({ message }),
  })
}

/** 清空某篇论文的聊天记录 */
export async function clearChatHistory(paperId: string): Promise<void> {
  await http.delete(`/papers/${encodeURIComponent(paperId)}/chat`)
}

/** 通用助手聊天历史 */
export async function fetchGeneralChatHistory(): Promise<ChatMessage[]> {
  const { data } = await http.get<{ messages: ChatMessage[] }>('/chat/general')
  return data.messages
}

export async function fetchGeneralChatStream(message: string): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getSessionToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = `${API_ORIGIN}/api/chat/general`

  if (IS_TAURI && _tauriInvoke !== null) {
    return tauriStreamResponse('POST', url, headers, JSON.stringify({ message }))
  }

  return fetch(url, {
    method: 'POST',
    headers,
    credentials: API_ORIGIN ? 'omit' : 'include',
    body: JSON.stringify({ message }),
  })
}

export async function clearGeneralChatHistory(): Promise<void> {
  await http.delete('/chat/general')
}

/** 检查论文是否已在知识库 */
export async function checkPaperInKb(paperId: string, scope: KbScope = 'kb'): Promise<boolean> {
  const { data } = await http.get<{ exists: boolean }>(
    `/kb/papers/${encodeURIComponent(paperId)}/exists`,
    { params: { scope } },
  )
  return data.exists
}

// ---------------------------------------------------------------------------
// Dismiss Paper API
// ---------------------------------------------------------------------------

/** 标记论文为不感兴趣 */
export async function dismissPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/kb/dismiss', { paper_id: paperId })
  return data
}

// ---------------------------------------------------------------------------
// Paper Rename API
// ---------------------------------------------------------------------------

/** 重命名论文显示标题 */
export async function renameKbPaper(
  paperId: string,
  title: string,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.patch<KbPaper>(`/kb/papers/${paperId}/rename`, { title, scope })
  return data
}

// ---------------------------------------------------------------------------
// Compare Results API
// ---------------------------------------------------------------------------

/** 获取对比分析结果树 */
export async function fetchCompareResultsTree(): Promise<KbCompareResultsTree> {
  const { data } = await http.get<KbCompareResultsTree>('/kb/compare-results/tree')
  return data
}

/** 保存对比分析结果 */
export async function saveCompareResult(
  title: string,
  markdown: string,
  paperIds: string[],
  folderId?: number | null,
): Promise<KbCompareResult> {
  const { data } = await http.post<KbCompareResult>('/kb/compare-results', {
    title,
    markdown,
    paper_ids: paperIds,
    folder_id: folderId ?? null,
  })
  return data
}

/** 获取单个对比分析结果 */
export async function fetchCompareResult(resultId: number): Promise<KbCompareResult> {
  const { data } = await http.get<KbCompareResult>(`/kb/compare-results/${resultId}`)
  return data
}

/** 重命名对比分析结果 */
export async function renameCompareResult(resultId: number, title: string): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}`, { title })
  return data
}

/** 移动对比分析结果到文件夹 */
export async function moveCompareResult(resultId: number, targetFolderId: number | null): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}/move`, {
    target_folder_id: targetFolderId,
  })
  return data
}

/** 删除对比分析结果 */
export async function deleteCompareResult(resultId: number): Promise<void> {
  await http.delete(`/kb/compare-results/${resultId}`)
}

// ---------------------------------------------------------------------------
// Annotation API
// ---------------------------------------------------------------------------

/** 获取论文的所有批注 */
export async function fetchAnnotations(paperId: string, scope: KbScope = 'kb'): Promise<KbAnnotationsResponse> {
  const { data } = await http.get<KbAnnotationsResponse>(`/kb/papers/${paperId}/annotations`, { params: { scope } })
  return data
}

/** 创建批注 */
export async function createAnnotation(
  paperId: string,
  payload: {
    page: number
    type?: string
    content?: string
    color?: string
    position_data?: string
  },
  scope: KbScope = 'kb',
): Promise<KbAnnotation> {
  const { data } = await http.post<KbAnnotation>(`/kb/papers/${paperId}/annotations`, { ...payload, scope })
  return data
}

/** 更新批注 — scope 不需要，annotation_id 全局唯一 */
export async function updateAnnotation(
  annotationId: number,
  payload: { content?: string; color?: string },
): Promise<KbAnnotation> {
  const { data } = await http.patch<KbAnnotation>(`/kb/annotations/${annotationId}`, payload)
  return data
}

/** 删除批注 — scope 不需要，annotation_id 全局唯一 */
export async function deleteAnnotation(annotationId: number): Promise<void> {
  await http.delete(`/kb/annotations/${annotationId}`)
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

export async function authSendSms(payload: SmsSendPayload): Promise<SmsSendResponse> {
  const { data } = await http.post<SmsSendResponse>('/auth/sms/send', payload)
  return data
}

export async function authVerifySms(payload: SmsVerifyPayload): Promise<SmsVerifyResponse> {
  const { data } = await http.post<SmsVerifyResponse>('/auth/sms/verify', payload)
  return data
}

export async function authRegister(payload: AuthRegisterPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/register', payload)
  return data
}

export async function authLogin(payload: AuthPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login', payload)
  return data
}

export async function authLoginSms(payload: AuthSmsLoginPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login/sms', payload)
  return data
}

export async function authMe(): Promise<AuthMeResponse> {
  const { data } = await http.get<AuthMeResponse>('/auth/me')
  return data
}

export async function checkUsername(username: string, excludeUserId?: number): Promise<{ available: boolean; message: string }> {
  const params: Record<string, any> = { username }
  if (excludeUserId !== undefined) params.exclude_user_id = excludeUserId
  const { data } = await http.get<{ available: boolean; message: string }>('/auth/check-username', { params })
  return data
}

export async function authLogout(): Promise<AuthLogoutResponse> {
  const { data } = await http.post<AuthLogoutResponse>('/auth/logout')
  return data
}

export async function fetchAuthProfile(): Promise<AuthActionResponse> {
  const { data } = await http.get<AuthActionResponse>('/auth/profile')
  return data
}

export async function updateAuthProfile(payload: {
  nickname?: string
  username?: string
}): Promise<AuthActionResponse> {
  const { data } = await http.put<AuthActionResponse>('/auth/profile', payload)
  return data
}

export async function setAuthPassword(payload: { password: string }): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/set-password', payload)
  return data
}

export async function changeAuthPassword(payload: {
  old_password: string
  new_password: string
}): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/change-password', payload)
  return data
}

// ---------------------------------------------------------------------------
// Subscription API
// ---------------------------------------------------------------------------

export async function fetchSubscriptionStatus(): Promise<SubscriptionStatusResponse> {
  const { data } = await http.get<SubscriptionStatusResponse>('/subscription/me')
  return data
}

export async function redeemSubscriptionKey(payload: {
  code: string
  device_id?: string
}): Promise<SubscriptionRedeemResponse> {
  const { data } = await http.post<SubscriptionRedeemResponse>('/subscription/redeem', payload)
  return data
}

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  const { data } = await http.get<AdminUsersResponse>('/admin/users')
  return data
}

export async function fetchAdminUserDetail(userId: number): Promise<AdminUserDetailResponse> {
  const { data } = await http.get<AdminUserDetailResponse>(`/admin/users/${userId}/detail`)
  return data
}

export async function updateAdminUserTier(
  userId: number,
  tier: UserTier,
): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/tier`, { tier })
  return data
}

export async function updateAdminUserRole(
  userId: number,
  role: UserRole,
): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/role`, { role })
  return data
}

export async function issueAdminRedeemKeys(payload: {
  plan_tier: 'pro' | 'pro_plus'
  duration_days: number
  key_count: number
  valid_days?: number | null
  max_uses?: number
  note?: string
}): Promise<AdminIssueRedeemKeysResponse> {
  const { data } = await http.post<AdminIssueRedeemKeysResponse>('/admin/subscription/keys/batch', payload)
  return data
}

export async function fetchAdminRedeemKeys(params?: {
  batch_id?: string
  limit?: number
}): Promise<AdminRedeemKeyListResponse> {
  const { data } = await http.get<AdminRedeemKeyListResponse>('/admin/subscription/keys', { params })
  return data
}

export async function disableAdminRedeemKey(keyId: number): Promise<{ ok: boolean }> {
  const { data } = await http.patch<{ ok: boolean }>(`/admin/subscription/keys/${keyId}/disable`)
  return data
}

// ---------------------------------------------------------------------------
// Pipeline API
// ---------------------------------------------------------------------------

export async function runPipeline(params: {
  pipeline?: string
  date?: string
  sllm?: number | null
  zo?: string
  force?: boolean
  /** 多用户编排模式：shared + per_user（含所有自定义配置用户） */
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
  // Arxiv 检索参数
  days?: number | null
  categories?: string | null
  extra_query?: string | null
  max_papers?: number | null
  anchor_tz?: string | null
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/run', params)
  return data
}

export async function getPipelineRunStatus(): Promise<PipelineRunStatus> {
  const { data } = await http.get<PipelineRunStatus>('/admin/pipeline/status')
  return data
}

export async function stopPipeline(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/stop')
  return data
}

export async function getScheduleConfig(): Promise<ScheduleConfig> {
  const { data } = await http.get<ScheduleConfig>('/admin/schedule')
  return data
}

export async function updateScheduleConfig(config: {
  enabled: boolean
  hour: number
  minute: number
  pipeline?: string
  sllm?: number | null
  zo?: string
  user_id?: number | null
  multi_user?: boolean
  max_concurrent_user_pipelines?: number
}): Promise<{ ok: boolean; schedule: ScheduleConfig }> {
  const { data } = await http.post<{ ok: boolean; schedule: ScheduleConfig }>('/admin/schedule', config)
  return data
}

export interface ScheduleHistoryRecord {
  run_id: string
  trigger: string
  date_str: string
  started_at: string
  finished_at: string | null
  user_count: number
  user_ids: number[]
  exit_code: number | null
  success: boolean
  pipeline?: string
}

export async function getScheduleHistory(limit = 50): Promise<ScheduleHistoryRecord[]> {
  const { data } = await http.get<{ records: ScheduleHistoryRecord[]; total: number }>(
    '/admin/schedule/history',
    { params: { limit } },
  )
  return data.records
}

// ---------------------------------------------------------------------------
// User Settings API
// ---------------------------------------------------------------------------

export interface UserSettingsResponse {
  ok: boolean
  feature: string
  settings: Record<string, any>
  defaults: Record<string, any>
}

/** 获取指定功能的用户设置（含默认值） */
export async function fetchUserSettings(feature: string): Promise<UserSettingsResponse> {
  const { data } = await http.get<UserSettingsResponse>(`/user/settings/${feature}`)
  return data
}

/** 保存指定功能的用户设置 */
export async function saveUserSettings(feature: string, settings: Record<string, any>): Promise<UserSettingsResponse> {
  const { data } = await http.put<UserSettingsResponse>(`/user/settings/${feature}`, { settings })
  return data
}

// ---------------------------------------------------------------------------
// System Config API
// ---------------------------------------------------------------------------

/** 获取系统配置 */
export async function getSystemConfig(): Promise<SystemConfigResponse> {
  const { data } = await http.get<SystemConfigResponse>('/admin/config')
  return data
}

/** 更新系统配置 */
export async function updateSystemConfig(config: Record<string, any>): Promise<SystemConfigUpdateResponse> {
  const { data } = await http.post<SystemConfigUpdateResponse>('/admin/config', { config })
  return data
}

/** 重置系统配置为默认值 */
export async function resetSystemConfig(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/config/reset')
  return data
}

// ---------------------------------------------------------------------------
// LLM Config API
// ---------------------------------------------------------------------------

export interface LlmConfig {
  id: number
  name: string
  remark?: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number
  temperature?: number
  concurrency?: number
  input_hard_limit?: number
  input_safety_margin?: number
  endpoint?: string
  completion_window?: string
  out_root?: string
  jsonl_root?: string
  created_at: string
  updated_at: string
}

export interface LlmConfigsResponse {
  ok: boolean
  configs: LlmConfig[]
}

export interface LlmConfigResponse {
  ok: boolean
  config: LlmConfig
}

export interface ApplyLlmConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有模型配置 */
export async function fetchLlmConfigs(): Promise<LlmConfigsResponse> {
  const { data } = await http.get<LlmConfigsResponse>('/admin/llm-configs')
  return data
}

/** 获取单个模型配置 */
export async function fetchLlmConfig(configId: number): Promise<LlmConfigResponse> {
  const { data } = await http.get<LlmConfigResponse>(`/admin/llm-configs/${configId}`)
  return data
}

/** 创建模型配置 */
export async function createLlmConfig(config: Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>): Promise<LlmConfigResponse> {
  const { data } = await http.post<LlmConfigResponse>('/admin/llm-configs', config)
  return data
}

/** 更新模型配置 */
export async function updateLlmConfig(configId: number, config: Partial<LlmConfig>): Promise<LlmConfigResponse> {
  const { data } = await http.put<LlmConfigResponse>(`/admin/llm-configs/${configId}`, config)
  return data
}

/** 删除模型配置 */
export async function deleteLlmConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/llm-configs/${configId}`)
  return data
}

/** 应用模型配置到config.py */
export async function applyLlmConfig(configId: number, usagePrefix: string): Promise<ApplyLlmConfigResponse> {
  const { data } = await http.post<ApplyLlmConfigResponse>(`/admin/llm-configs/${configId}/apply`, {
    usage_prefix: usagePrefix,
  })
  return data
}

// ---------------------------------------------------------------------------
// Prompt Config API
// ---------------------------------------------------------------------------

export interface PromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
  created_at: string
  updated_at: string
}

export interface PromptConfigsResponse {
  ok: boolean
  configs: PromptConfig[]
}

export interface PromptConfigResponse {
  ok: boolean
  config: PromptConfig
}

export interface ApplyPromptConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有提示词配置 */
export async function fetchPromptConfigs(): Promise<PromptConfigsResponse> {
  const { data } = await http.get<PromptConfigsResponse>('/admin/prompt-configs')
  return data
}

/** 获取单个提示词配置 */
export async function fetchPromptConfig(configId: number): Promise<PromptConfigResponse> {
  const { data } = await http.get<PromptConfigResponse>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 创建提示词配置 */
export async function createPromptConfig(config: Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>): Promise<PromptConfigResponse> {
  const { data } = await http.post<PromptConfigResponse>('/admin/prompt-configs', config)
  return data
}

/** 更新提示词配置 */
export async function updatePromptConfig(configId: number, config: Partial<PromptConfig>): Promise<PromptConfigResponse> {
  const { data } = await http.put<PromptConfigResponse>(`/admin/prompt-configs/${configId}`, config)
  return data
}

/** 删除提示词配置 */
export async function deletePromptConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 应用提示词配置到config.py */
export async function applyPromptConfig(configId: number, variableName: string): Promise<ApplyPromptConfigResponse> {
  const { data } = await http.post<ApplyPromptConfigResponse>(`/admin/prompt-configs/${configId}/apply`, {
    variable_name: variableName,
  })
  return data
}

export interface BatchApplyItem_Llm {
  config_id: number
  prefix: string
}

export interface BatchApplyItem_Prompt {
  config_id: number
  variable: string
}

export interface BatchApplyConfigResponse {
  ok: boolean
  message: string
  applied_count: number
  errors: string[]
  config: Record<string, any>
}

/** 批量应用模型配置和提示词配置（一次性写入） */
export async function batchApplyConfigs(
  llmApplies: BatchApplyItem_Llm[],
  promptApplies: BatchApplyItem_Prompt[],
): Promise<BatchApplyConfigResponse> {
  const { data } = await http.post<BatchApplyConfigResponse>('/admin/config/batch-apply', {
    llm_applies: llmApplies,
    prompt_applies: promptApplies,
  })
  return data
}

// ---------------------------------------------------------------------------
// User LLM Presets API
// ---------------------------------------------------------------------------

import type { UserLlmPreset, UserPromptPreset } from '../types/paper'

export interface UserLlmPresetsResponse {
  ok: boolean
  presets: UserLlmPreset[]
}

export interface UserLlmPresetResponse {
  ok: boolean
  preset: UserLlmPreset
}

/** 获取用户的所有模型预设 */
export async function fetchUserLlmPresets(): Promise<UserLlmPresetsResponse> {
  const { data } = await http.get<UserLlmPresetsResponse>('/user/llm-presets')
  return data
}

/** 创建模型预设 */
export async function createUserLlmPreset(preset: Omit<UserLlmPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserLlmPresetResponse> {
  const { data } = await http.post<UserLlmPresetResponse>('/user/llm-presets', preset)
  return data
}

/** 更新模型预设 */
export async function updateUserLlmPreset(presetId: number, preset: Partial<UserLlmPreset>): Promise<UserLlmPresetResponse> {
  const { data } = await http.put<UserLlmPresetResponse>(`/user/llm-presets/${presetId}`, preset)
  return data
}

/** 删除模型预设 */
export async function deleteUserLlmPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/llm-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// User Prompt Presets API
// ---------------------------------------------------------------------------

export interface UserPromptPresetsResponse {
  ok: boolean
  presets: UserPromptPreset[]
}

export interface UserPromptPresetResponse {
  ok: boolean
  preset: UserPromptPreset
}

/** 获取用户的所有提示词预设 */
export async function fetchUserPromptPresets(): Promise<UserPromptPresetsResponse> {
  const { data } = await http.get<UserPromptPresetsResponse>('/user/prompt-presets')
  return data
}

/** 创建提示词预设 */
export async function createUserPromptPreset(preset: Omit<UserPromptPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserPromptPresetResponse> {
  const { data } = await http.post<UserPromptPresetResponse>('/user/prompt-presets', preset)
  return data
}

/** 更新提示词预设 */
export async function updateUserPromptPreset(presetId: number, preset: Partial<UserPromptPreset>): Promise<UserPromptPresetResponse> {
  const { data } = await http.put<UserPromptPresetResponse>(`/user/prompt-presets/${presetId}`, preset)
  return data
}

/** 删除提示词预设 */
export async function deleteUserPromptPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/prompt-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// Idea Generation v2 API (灵感生成)
// ---------------------------------------------------------------------------

import type {
  IdeaAtom,
  IdeaCandidate,
  IdeaPlan,
  IdeaFeedback,
  IdeaExemplar,
  IdeaBenchmark,
  IdeaPromptVersion,
  Announcement,
  AnnouncementsResponse,
  AnnouncementResponse,
  SubscriptionHistoryResponse,
} from '../types/paper'

// -- Atoms --

export interface IdeaAtomsResponse { ok: boolean; atoms: IdeaAtom[] }
export interface IdeaAtomResponse { ok: boolean; atom: IdeaAtom }

export async function fetchIdeaAtoms(params?: {
  paper_id?: string; atom_type?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaAtomsResponse> {
  const { data } = await http.get<IdeaAtomsResponse>('/idea/atoms', { params })
  return data
}

export async function fetchIdeaAtom(atomId: number): Promise<IdeaAtomResponse> {
  const { data } = await http.get<IdeaAtomResponse>(`/idea/atoms/${atomId}`)
  return data
}

export async function updateIdeaAtom(atomId: number, payload: Partial<IdeaAtom>): Promise<IdeaAtomResponse> {
  const { data } = await http.patch<IdeaAtomResponse>(`/idea/atoms/${atomId}`, payload)
  return data
}

export async function deleteIdeaAtom(atomId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/atoms/${atomId}`)
  return data
}

export async function extractIdeaAtoms(paperId: string, dateStr?: string): Promise<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }> {
  const { data } = await http.post<{ ok: boolean; atoms_created: number; atoms: IdeaAtom[] }>('/idea/atoms/extract', {
    paper_id: paperId,
    date_str: dateStr ?? '',
  }, { timeout: 300000 })
  return data
}

// -- Candidates --

export interface IdeaCandidatesResponse { ok: boolean; candidates: IdeaCandidate[] }
export interface IdeaCandidateResponse { ok: boolean; candidate: IdeaCandidate }

export async function fetchIdeaCandidates(params?: {
  status?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaCandidatesResponse> {
  const { data } = await http.get<IdeaCandidatesResponse>('/idea/candidates', { params })
  return data
}

export async function fetchIdeaCandidate(candidateId: number): Promise<IdeaCandidateResponse> {
  const { data } = await http.get<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`)
  return data
}

export async function updateIdeaCandidate(candidateId: number, payload: Partial<IdeaCandidate>): Promise<IdeaCandidateResponse> {
  const { data } = await http.patch<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`, payload)
  return data
}

export async function deleteIdeaCandidate(candidateId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/candidates/${candidateId}`)
  return data
}

export interface GenerateForPaperResponse { candidates: IdeaCandidate[]; count: number }

export async function generateCandidatesForPaper(paperId: string, force = false): Promise<GenerateForPaperResponse> {
  const { data } = await http.post<GenerateForPaperResponse>('/idea/candidates/generate-for-paper', { paper_id: paperId, force }, { timeout: 300000 })
  return data
}

/**
 * Generate idea candidates via SSE stream.
 * Backend returns text/event-stream; use onChunk to receive progressive output.
 */
export async function generateIdeasStream(
  payload: { question_id?: number; custom_question?: string; strategies?: string[] },
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getSessionToken()
  const hdrs: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  let response: Response
  if (IS_TAURI && _tauriInvoke !== null) {
    response = tauriStreamResponse(
      'POST',
      `${API_ORIGIN}/api/idea/candidates/generate`,
      hdrs,
      JSON.stringify(payload),
    )
  } else {
    response = await fetch(`${API_ORIGIN}/api/idea/candidates/generate`, {
      method: 'POST',
      headers: hdrs,
      credentials: API_ORIGIN ? 'omit' : 'include',
      body: JSON.stringify(payload),
      signal,
    })
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`生成失败 (${response.status}): ${text}`)
  }
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const ssePayload = line.slice(6).trim()
      if (ssePayload === '[DONE]') return
      try {
        onChunk(JSON.parse(ssePayload) as string)
      } catch {
        onChunk(ssePayload)
      }
    }
  }
}

export async function reviewIdeaCandidate(candidateId: number, payload: {
  action: 'approve' | 'reject' | 'revise'; feedback?: string; scores?: Record<string, number>
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/idea/candidates/${candidateId}/review`, payload)
  return data
}

// -- Plans --

export interface IdeaPlanResponse { ok: boolean; plan: IdeaPlan }

export async function fetchIdeaPlan(candidateId: number): Promise<IdeaPlanResponse> {
  const { data } = await http.get<IdeaPlanResponse>(`/idea/plans/${candidateId}`)
  return data
}

export async function createIdeaPlan(candidateId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.post<IdeaPlanResponse>(`/idea/plans`, { candidate_id: candidateId, ...payload })
  return data
}

export function streamGeneratePlan(candidateId: number): EventSource {
  // Returns a fetch-based SSE stream for plan generation
  // Caller should use fetch() directly for SSE with POST
  throw new Error('Use fetchGeneratePlanStream instead')
}

export async function fetchGeneratePlanStream(
  candidateId: number,
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getSessionToken()
  const hdrs: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  let response: Response
  if (IS_TAURI && _tauriInvoke !== null) {
    response = tauriStreamResponse(
      'POST',
      `${API_ORIGIN}/api/idea/plans/generate`,
      hdrs,
      JSON.stringify({ candidate_id: candidateId }),
    )
  } else {
    response = await fetch(`${API_ORIGIN}/api/idea/plans/generate`, {
      method: 'POST',
      headers: hdrs,
      credentials: API_ORIGIN ? 'omit' : 'include',
      body: JSON.stringify({ candidate_id: candidateId }),
      signal,
    })
  }
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`生成失败 (${response.status}): ${text}`)
  }
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') return
      try {
        onChunk(JSON.parse(payload) as string)
      } catch {
        onChunk(payload)
      }
    }
  }
}

export async function updateIdeaPlan(planId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.patch<IdeaPlanResponse>(`/idea/plans/${planId}`, payload)
  return data
}

export async function deleteIdeaPlan(planId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/plans/${planId}`)
  return data
}

// -- Feedback --

export interface IdeaFeedbackResponse { ok: boolean; feedback: IdeaFeedback }
export interface IdeaFeedbackListResponse { ok: boolean; feedback_events: IdeaFeedback[] }

export async function createIdeaFeedback(payload: {
  candidate_id?: number; atom_id?: number; action: string; context?: Record<string, any>
}): Promise<IdeaFeedbackResponse> {
  const { data } = await http.post<IdeaFeedbackResponse>('/idea/feedback', payload)
  return data
}


export async function fetchIdeaFeedback(params?: {
  event_type?: string; candidate_id?: number; atom_id?: number; limit?: number; offset?: number
}): Promise<IdeaFeedbackListResponse> {
  const { data } = await http.get<IdeaFeedbackListResponse>('/idea/feedback', { params })
  return data
}

// -- Exemplars --

export interface IdeaExemplarsResponse { ok: boolean; exemplars: IdeaExemplar[] }
export interface IdeaExemplarResponse { ok: boolean; exemplar: IdeaExemplar }

export async function fetchIdeaExemplars(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaExemplarsResponse> {
  const { data } = await http.get<IdeaExemplarsResponse>('/idea/exemplars', { params })
  return data
}

export async function fetchIdeaExemplar(exemplarId: number): Promise<IdeaExemplarResponse> {
  const { data } = await http.get<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`)
  return data
}

export async function createIdeaExemplar(payload: {
  candidate_id: number; name: string; description?: string; tags?: string[]
}): Promise<IdeaExemplarResponse> {
  const { data } = await http.post<IdeaExemplarResponse>('/idea/exemplars', payload)
  return data
}

export async function updateIdeaExemplar(exemplarId: number, payload: Partial<IdeaExemplar>): Promise<IdeaExemplarResponse> {
  const { data } = await http.patch<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`, payload)
  return data
}

export async function deleteIdeaExemplar(exemplarId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/exemplars/${exemplarId}`)
  return data
}

// -- Benchmarks --

export interface IdeaBenchmarksResponse { ok: boolean; benchmarks: IdeaBenchmark[] }
export interface IdeaBenchmarkResponse { ok: boolean; benchmark: IdeaBenchmark }

export async function fetchIdeaBenchmarks(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaBenchmarksResponse> {
  const { data } = await http.get<IdeaBenchmarksResponse>('/idea/benchmarks', { params })
  return data
}

export async function fetchIdeaBenchmark(benchmarkId: number): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.get<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

export async function createIdeaBenchmark(payload: {
  name: string; description?: string; questions?: string[]; expected_outputs?: string[]
}): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.post<IdeaBenchmarkResponse>('/idea/benchmarks', payload)
  return data
}

export async function updateIdeaBenchmark(benchmarkId: number, payload: Partial<IdeaBenchmark>): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.patch<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`, payload)
  return data
}

export async function deleteIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

// -- Prompt Templates --

export interface IdeaPromptVersionsResponse { ok: boolean; templates: IdeaPromptVersion[] }
export interface IdeaPromptVersionResponse { ok: boolean; template: IdeaPromptVersion }

export async function fetchIdeaPromptVersions(params?: {
  stage?: string; name?: string; is_active?: boolean; limit?: number; offset?: number
}): Promise<IdeaPromptVersionsResponse> {
  const { data } = await http.get<IdeaPromptVersionsResponse>('/idea/prompt-versions', { params })
  return data
}

export async function fetchIdeaPromptVersion(versionId: number): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.get<IdeaPromptVersionResponse>(`/idea/prompt-versions/${versionId}`)
  return data
}

export async function createIdeaPromptVersion(payload: {
  name: string; stage: string; content: string; version?: number; is_active?: boolean
}): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.post<IdeaPromptVersionResponse>('/idea/prompt-versions', payload)
  return data
}

export async function updateIdeaPromptVersion(versionId: number, payload: Partial<IdeaPromptVersion>): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.patch<IdeaPromptVersionResponse>(`/idea/prompt-versions/${versionId}`, payload)
  return data
}

export async function deleteIdeaPromptVersion(versionId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/prompt-versions/${versionId}`)
  return data
}

// -- Stats --

export interface IdeaStatsResponse {
  ok: boolean
  stats: {
    total_atoms: number
    total_candidates: number
    total_approved: number
    total_archived: number
    total_plans: number
    total_exemplars: number
    total_benchmarks: number
    atoms_by_type: Record<string, number>
    candidates_by_status: Record<string, number>
  }
}

export async function fetchIdeaStats(): Promise<IdeaStatsResponse> {
  const { data } = await http.get<IdeaStatsResponse>('/idea/stats')
  return data
}

// -- Idea Digest (permission-filtered, date-scoped) --

export interface IdeaDigestResponse {
  ok: boolean
  candidates: import('../types/paper').IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}

/** 获取指定日期的灵感推荐（按用户配额过滤来源论文） */
export async function fetchIdeaDigest(date: string): Promise<IdeaDigestResponse> {
  const { data } = await http.get<IdeaDigestResponse>(`/idea/digest/${date}`)
  return data
}

// ---------------------------------------------------------------------------
// Announcement API (公告)
// ---------------------------------------------------------------------------

/** 获取公告列表 */
export async function fetchAnnouncements(params?: {
  limit?: number
  offset?: number
}): Promise<AnnouncementsResponse> {
  const { data } = await http.get<AnnouncementsResponse>('/announcements', { params })
  return data
}

/** 管理员创建公告 */
export async function createAnnouncement(payload: {
  title: string
  content: string
  tag?: string
  is_pinned?: boolean
}): Promise<AnnouncementResponse> {
  const { data } = await http.post<AnnouncementResponse>('/admin/announcements', payload)
  return data
}

/** 管理员更新公告 */
export async function updateAnnouncement(
  id: number,
  payload: {
    title?: string
    content?: string
    tag?: string
    is_pinned?: boolean
  },
): Promise<AnnouncementResponse> {
  const { data } = await http.put<AnnouncementResponse>(`/admin/announcements/${id}`, payload)
  return data
}

/** 管理员删除公告 */
export async function deleteAnnouncement(id: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/admin/announcements/${id}`)
  return data
}

/** 获取当前用户未读公告数量 */
export async function fetchUnreadAnnouncementCount(): Promise<{ ok: boolean; count: number }> {
  const { data } = await http.get<{ ok: boolean; count: number }>('/announcements/unread-count')
  return data
}

/** 将指定公告标记为已读 */
export async function markAnnouncementsRead(ids: number[]): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-read', {
    announcement_ids: ids,
  })
  return data
}

/** 将全部公告标记为已读 */
export async function markAllAnnouncementsRead(): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/announcements/mark-read', { all: true })
  return data
}

// ---------------------------------------------------------------------------
// Subscription History API (订阅记录)
// ---------------------------------------------------------------------------

/** 获取当前用户订阅变更历史 */
export async function fetchSubscriptionHistory(): Promise<SubscriptionHistoryResponse> {
  const { data } = await http.get<SubscriptionHistoryResponse>('/subscription/history')
  return data
}

// ---------------------------------------------------------------------------
// Admin Analytics API (管理员数据统计分析)
// ---------------------------------------------------------------------------

import type {
  AnalyticsOverviewResponse,
  AnalyticsUsersResponse,
  AnalyticsPapersResponse,
  AnalyticsTrendsResponse,
  AnalyticsFeaturesResponse,
  AnalyticsRetentionResponse,
} from '../types/paper'

/** 获取平台总览统计 */
export async function fetchAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  const { data } = await http.get<AnalyticsOverviewResponse>('/admin/analytics/overview')
  return data
}

/** 获取用户活跃度排行 */
export async function fetchAnalyticsUsers(params?: {
  limit?: number
  offset?: number
}): Promise<AnalyticsUsersResponse> {
  const { data } = await http.get<AnalyticsUsersResponse>('/admin/analytics/users', { params })
  return data
}

/** 获取论文热度排行 */
export async function fetchAnalyticsPapers(params?: {
  limit?: number
}): Promise<AnalyticsPapersResponse> {
  const { data } = await http.get<AnalyticsPapersResponse>('/admin/analytics/papers', { params })
  return data
}

/** 获取趋势数据 */
export async function fetchAnalyticsTrends(params?: {
  days?: number
}): Promise<AnalyticsTrendsResponse> {
  const { data } = await http.get<AnalyticsTrendsResponse>('/admin/analytics/trends', { params })
  return data
}

/** 获取功能使用统计 */
export async function fetchAnalyticsFeatures(): Promise<AnalyticsFeaturesResponse> {
  const { data } = await http.get<AnalyticsFeaturesResponse>('/admin/analytics/features')
  return data
}

/** 获取留存率数据 */
export async function fetchAnalyticsRetention(params?: {
  weeks?: number
}): Promise<AnalyticsRetentionResponse> {
  const { data } = await http.get<AnalyticsRetentionResponse>('/admin/analytics/retention', { params })
  return data
}

/** 获取 Pipeline 各步骤数据量追踪 */
export async function fetchPipelineDataTracking(params?: {
  user_id?: number
  days?: number
}): Promise<import('../types/paper').PipelineDataTrackingResponse> {
  const { data } = await http.get('/admin/pipeline/data-tracking', { params })
  return data
}

// ---------------------------------------------------------------------------
// Analytics Event Tracking (用户行为事件上报)
// ---------------------------------------------------------------------------

/** 上报单个事件 */
export async function reportAnalyticsEvent(event: {
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}): Promise<{ ok: boolean; event_id: number }> {
  const { data } = await http.post<{ ok: boolean; event_id: number }>('/analytics/event', event)
  return data
}

/** 批量上报事件 */
export async function reportAnalyticsEvents(events: Array<{
  event_type: string
  target_type?: string
  target_id?: string
  value?: number
  meta?: Record<string, unknown>
}>): Promise<{ ok: boolean; count: number }> {
  const { data } = await http.post<{ ok: boolean; count: number }>('/analytics/events', { events })
  return data
}

// ---------------------------------------------------------------------------
// User-uploaded papers API
// ---------------------------------------------------------------------------

/** 手动录入论文 */
export async function importUserPaperManual(payload: {
  title: string
  authors?: string[]
  abstract?: string
  institution?: string
  year?: number | null
  external_url?: string
}): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/manual', payload)
  return data
}

/** 通过 arXiv ID 导入 */
export async function importUserPaperArxiv(arxivId: string): Promise<UserPaper> {
  const { data } = await http.post<UserPaper>('/user-papers/import/arxiv', { arxiv_id: arxivId })
  return data
}

/** 上传 PDF 并录入论文 */
export async function importUserPaperPdf(
  file: File,
  meta: {
    title?: string
    authors?: string[]
    abstract?: string
    institution?: string
    year?: number | null
    external_url?: string
  } = {},
): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const params: Record<string, string> = {}
  if (meta.title) params.title = meta.title
  if (meta.authors) params.authors = JSON.stringify(meta.authors)
  if (meta.abstract) params.abstract = meta.abstract
  if (meta.institution) params.institution = meta.institution
  if (meta.year != null) params.year = String(meta.year)
  if (meta.external_url) params.external_url = meta.external_url
  const { data } = await http.post<UserPaper>('/user-papers/import/pdf', form, {
    params,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

function normalizeUserPapersListPayload(data: unknown): UserPapersListResponse {
  let payload = data as any

  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload)
    } catch {
      const preview = (payload as string).slice(0, 120)
      throw new Error(`接口返回非JSON: ${preview}`)
    }
  }

  if (Array.isArray(payload)) {
    return { total: payload.length, papers: payload }
  }

  if (!payload || typeof payload !== 'object') {
    throw new Error(`接口返回类型异常: ${typeof payload}`)
  }

  if (payload.detail) {
    throw new Error(String(payload.detail))
  }

  const papers =
    Array.isArray(payload.papers) ? payload.papers
      : Array.isArray(payload.items) ? payload.items
        : Array.isArray(payload.records) ? payload.records
          : null

  if (!Array.isArray(papers)) {
    const keys = Object.keys(payload).join(',')
    throw new Error(`接口返回缺少papers字段 (keys: ${keys})`)
  }

  const total =
    typeof payload.total === 'number' ? payload.total
      : typeof payload.count === 'number' ? payload.count
        : papers.length

  return { total, papers }
}

/** 获取我的上传论文列表 */
export async function fetchUserPapers(opts?: {
  source_type?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<UserPapersListResponse> {
  const { data } = await http.get<UserPapersListResponse>('/user-papers', { params: opts })
  return normalizeUserPapersListPayload(data)
}

/** 获取单篇上传论文详情 */
export async function fetchUserPaperDetail(paperId: string): Promise<UserPaper> {
  const { data } = await http.get<UserPaper>(`/user-papers/${paperId}`)
  return data
}

/** 更新论文元数据 */
export async function updateUserPaper(
  paperId: string,
  payload: Partial<{
    title: string
    authors: string[]
    abstract: string
    institution: string
    year: number | null
    external_url: string
  }>,
): Promise<UserPaper> {
  const { data } = await http.patch<UserPaper>(`/user-papers/${paperId}`, payload)
  return data
}

/** 为已录入论文补传 PDF */
export async function uploadUserPaperPdf(paperId: string, file: File): Promise<UserPaper> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<UserPaper>(`/user-papers/${paperId}/upload-pdf`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 删除上传论文 */
export async function deleteUserPaper(paperId: string): Promise<{ ok: boolean; paper_id: string }> {
  const { data } = await http.delete<{ ok: boolean; paper_id: string }>(`/user-papers/${paperId}`)
  return data
}

/** 触发单篇论文流水线处理 */
export async function processUserPaper(paperId: string): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/process`,
  )
  return data
}

/** 查询单篇论文处理状态 */
export async function fetchUserPaperProcessStatus(paperId: string): Promise<UserPaperProcessStatusResponse> {
  const { data } = await http.get<UserPaperProcessStatusResponse>(
    `/user-papers/${paperId}/process-status`,
  )
  return data
}

/** 获取我的论文文件夹树 */
export async function fetchUserPaperTree(): Promise<UserPaperTree> {
  const { data } = await http.get<UserPaperTree>('/user-papers/tree')
  return data
}

/** 手动触发 MinerU 全文翻译（中文 + 中英对照） */
export async function translateUserPaper(
  paperId: string,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/translate`,
  )
  return data
}

/** 重新触发全文翻译（与 translate 相同，用于删除译稿后重新生成） */
export async function retranslateUserPaper(
  paperId: string,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.post<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/retranslate`,
  )
  return data
}

export type UserPaperDerivativeType = 'mineru' | 'zh' | 'bilingual'

/** 删除 MinerU 解析或翻译产物文件 */
export async function deleteUserPaperDerivative(
  paperId: string,
  derivativeType: UserPaperDerivativeType,
): Promise<{ ok: boolean; message: string; paper_id: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string; paper_id: string }>(
    `/user-papers/${paperId}/derivatives/${derivativeType}`,
  )
  return data
}

/** 查询翻译任务状态 */
export async function fetchUserPaperTranslateStatus(
  paperId: string,
): Promise<UserPaperTranslateStatusResponse> {
  const { data } = await http.get<UserPaperTranslateStatusResponse>(
    `/user-papers/${paperId}/translate-status`,
  )
  return data
}

/** 论文关联文件是否存在及静态 URL */
export async function fetchUserPaperFiles(paperId: string): Promise<UserPaperFilesResponse> {
  const { data } = await http.get<UserPaperFilesResponse>(`/user-papers/${paperId}/files`)
  return data
}

/** 批量移动我的论文到目标文件夹 (null = 根目录) */
export async function moveUserPapers(
  paperIds: string[],
  targetFolderId: number | null,
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/user-papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
  })
  return data
}

/** 步骤名 → 中文展示文案 */
export function userPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '等待处理...',
    starting: '初始化...',
    pdf_prepare: '准备 PDF...',
    pdf_download: '下载 PDF...',
    pdf_mineru: 'MinerU 版面解析中...',
    pdf_extract: '提取文本（PyMuPDF）...',
    pdf_info: '识别机构信息...',
    paper_summary: '生成论文摘要...',
    summary_limit: '精简结构化摘要...',
    paper_assets: '生成结构化分析...',
    done: '处理完成',
    '': '',
  }
  return labels[step] ?? step
}

/** KB 步骤名 → 中文展示文案 */
export function kbPaperStepLabel(step: string): string {
  const labels: Record<string, string> = {
    queued: '等待处理...',
    starting: '初始化...',
    pdf_attach: '查找/复制 PDF...',
    pdf_mineru: 'MinerU 版面解析中...',
    pdf_extract: '提取文本（PyMuPDF）...',
    done: '处理完成',
    '': '',
  }
  return labels[step] ?? step
}

// ---------------------------------------------------------------------------
// KB Paper Process / Translate API
// ---------------------------------------------------------------------------

import type {
  KbPaperProcessStatusResponse,
  KbPaperTranslateStatusResponse,
  KbPaperFilesResponse,
} from '@/types/paper'

/** 触发 KB 论文 MinerU 解析 */
export async function processKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/process`,
    null,
    { params: { scope } },
  )
  return data
}

/** 查询 KB 论文处理状态 */
export async function fetchKbPaperProcessStatus(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperProcessStatusResponse> {
  const { data } = await http.get<KbPaperProcessStatusResponse>(
    `/kb/papers/${paperId}/process-status`,
    { params: { scope } },
  )
  return data
}

/** 触发 KB 论文翻译 */
export async function translateKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/translate`,
    null,
    { params: { scope } },
  )
  return data
}

/** 重新翻译 KB 论文 */
export async function retranslateKbPaper(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(
    `/kb/papers/${paperId}/retranslate`,
    null,
    { params: { scope } },
  )
  return data
}

/** 查询 KB 论文翻译状态 */
export async function fetchKbPaperTranslateStatus(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperTranslateStatusResponse> {
  const { data } = await http.get<KbPaperTranslateStatusResponse>(
    `/kb/papers/${paperId}/translate-status`,
    { params: { scope } },
  )
  return data
}

/** 获取 KB 论文关联文件静态链接 */
export async function fetchKbPaperFiles(
  paperId: string,
  scope: KbScope = 'kb',
): Promise<KbPaperFilesResponse> {
  const { data } = await http.get<KbPaperFilesResponse>(
    `/kb/papers/${paperId}/files`,
    { params: { scope } },
  )
  return data
}

/** 删除 KB 论文衍生文件 */
export async function deleteKbPaperDerivative(
  paperId: string,
  derivativeType: 'mineru' | 'zh' | 'bilingual',
  scope: KbScope = 'kb',
): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(
    `/kb/papers/${paperId}/derivatives/${derivativeType}`,
    { params: { scope } },
  )
  return data
}

// ---------------------------------------------------------------------------
// Download API
// ---------------------------------------------------------------------------

/** 下载单个论文衍生文件（触发浏览器下载）
 *
 * 对于需要服务端转换的格式（pdf/docx 衍生文件），使用 fetch+blob 方式，
 * 使调用方可以 await 并在此期间显示 loading 状态。
 * md 及原始 pdf 仍使用 <a> click（即时返回，无需等待）。
 */
export async function downloadPaperFile(
  paperId: string,
  fileType: 'pdf' | 'mineru' | 'zh' | 'bilingual',
  scope: 'kb' | 'mypapers' = 'kb',
  format: 'md' | 'docx' | 'pdf' = 'md',
): Promise<void> {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  const url = `${base}/download/paper-file?paper_id=${encodeURIComponent(paperId)}&file_type=${fileType}&scope=${scope}&format=${format}`

  // The server sets Content-Disposition: attachment; filename="<paper title>..."
  // which takes precedence over the client hint in both browser and Tauri paths.
  // The fallback below is only used if the server header is absent.
  const ext = fileType === 'pdf' ? 'pdf' : format
  const fallbackName = fileType === 'pdf' ? `${paperId}.pdf` : `${paperId}_${fileType}.${ext}`

  if (IS_TAURI && _tauriInvoke !== null) {
    // 桌面端：WebView2 的 <a href="外部URL"> 无法携带 Auth header，走 Rust 下载
    // Rust 侧优先使用服务器返回的 Content-Disposition filename
    const headers: Record<string, string> = {}
    const token = getSessionToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    await tauriDownloadBinary(url, headers, fallbackName)
    return
  }

  // 统一使用 fetch+blob 方式下载，确保能捕获后端错误（404/500 等）
  const resp = await fetch(url, { credentials: 'include' })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      if (data?.detail) detail = data.detail
    } catch { /* ignore */ }
    throw new Error(`下载失败: ${detail}`)
  }

  // 从 Content-Disposition 提取服务端返回的文件名
  const cd = resp.headers.get('content-disposition') || ''
  const nameMatch = cd.match(/filename="([^"]+)"/)
  const fileName = nameMatch ? nameMatch[1] : fallbackName

  const blob = await resp.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}

/** 下载/导出笔记（触发浏览器下载） */
export function downloadNote(noteId: number): void {
  const base = (http.defaults.baseURL || '/api').replace(/\/$/, '')
  const url = `${base}/download/note/${noteId}`

  if (IS_TAURI && _tauriInvoke !== null) {
    const headers: Record<string, string> = {}
    const token = getSessionToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    tauriDownloadBinary(url, headers, `note_${noteId}.md`).catch((e) =>
      console.error('[download] note failed:', e),
    )
    return
  }

  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export interface BatchDownloadItem {
  paper_id: string
  file_types: ('pdf' | 'mineru' | 'zh' | 'bilingual')[]
  scope: 'kb' | 'mypapers'
  include_notes?: boolean
}

/** 批量下载（返回 zip，触发浏览器保存） */
export async function downloadBatch(items: BatchDownloadItem[]): Promise<void> {
  if (IS_TAURI && _tauriInvoke !== null) {
    // 桌面端：tauriAdapter 不支持 blob responseType，走专用二进制下载命令
    const url = `${API_ORIGIN}/api/download/batch`
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getSessionToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    await tauriDownloadBinary(url, headers, 'papers_export.zip', 'POST', JSON.stringify({ items }))
    return
  }

  const response = await http.post('/download/batch', { items }, { responseType: 'blob' })
  const blob = new Blob([response.data as BlobPart], { type: 'application/zip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'papers_export.zip'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Community API
// ---------------------------------------------------------------------------

export interface CommunityPost {
  id: number
  user_id: number
  username: string | null
  category: string
  title: string
  content?: string
  view_count: number
  reply_count: number
  like_count: number
  is_pinned: boolean
  is_closed: boolean
  last_reply_at: string | null
  created_at: string
  updated_at: string
  user_liked?: boolean
  replies?: CommunityReply[]
}

export interface CommunityReply {
  id: number
  post_id: number
  user_id: number
  username: string | null
  content: string
  like_count: number
  parent_reply_id?: number | null
  created_at: string
  updated_at: string
  user_liked?: boolean
}

export interface CommunityPostsResponse {
  total: number
  page: number
  page_size: number
  posts: CommunityPost[]
}

export async function fetchCommunityPosts(params: {
  category?: string
  page?: number
  page_size?: number
  sort?: string
}): Promise<CommunityPostsResponse> {
  const resp = await http.get('/community/posts', { params })
  return resp.data
}

export async function fetchCommunityPost(id: number): Promise<CommunityPost> {
  const resp = await http.get(`/community/posts/${id}`)
  return resp.data
}

export async function createCommunityPost(data: {
  category: string
  title: string
  content: string
}): Promise<CommunityPost> {
  const resp = await http.post('/community/posts', data)
  return resp.data
}

export async function updateCommunityPost(
  id: number,
  data: { category?: string; title?: string; content?: string },
): Promise<CommunityPost> {
  const resp = await http.put(`/community/posts/${id}`, data)
  return resp.data
}

export async function deleteCommunityPost(id: number): Promise<void> {
  await http.delete(`/community/posts/${id}`)
}

export async function createCommunityReply(
  postId: number,
  data: { content: string; parent_reply_id?: number | null },
): Promise<CommunityReply> {
  const resp = await http.post(`/community/posts/${postId}/replies`, data)
  return resp.data
}

export async function updateCommunityReply(
  replyId: number,
  data: { content: string },
): Promise<CommunityReply> {
  const resp = await http.put(`/community/replies/${replyId}`, data)
  return resp.data
}

export async function deleteCommunityReply(replyId: number): Promise<void> {
  await http.delete(`/community/replies/${replyId}`)
}

export async function toggleCommunityLike(
  targetType: 'post' | 'reply',
  targetId: number,
): Promise<{ liked: boolean; like_count: number }> {
  const resp = await http.post('/community/like', { target_type: targetType, target_id: targetId })
  return resp.data
}

export async function pinCommunityPost(
  postId: number,
  pinned: boolean,
): Promise<{ ok: boolean; is_pinned: boolean }> {
  const resp = await http.put(`/community/posts/${postId}/pin`, { pinned })
  return resp.data
}

export async function closeCommunityPost(
  postId: number,
  closed: boolean,
): Promise<{ ok: boolean; is_closed: boolean }> {
  const resp = await http.put(`/community/posts/${postId}/close`, { closed })
  return resp.data
}