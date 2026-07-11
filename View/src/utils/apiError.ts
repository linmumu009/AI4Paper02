interface ValidationIssue {
  loc?: Array<string | number>
  msg?: string
}

interface ErrorSnapshot {
  context: string
  message: string
  status?: number
  code?: string
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object'
    ? value as Record<string, unknown>
    : null
}

function validationDetail(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (!Array.isArray(detail)) return null

  const messages = detail
    .map((item) => {
      const issue = asRecord(item) as ValidationIssue | null
      if (!issue?.msg) return null
      const field = issue.loc?.filter(part => part !== 'body').join('.')
      return field ? `${field}: ${issue.msg}` : issue.msg
    })
    .filter((message): message is string => Boolean(message))

  return messages.length > 0 ? messages.join('；') : null
}

export function getApiErrorStatus(error: unknown): number | undefined {
  const response = asRecord(asRecord(error)?.response)
  return typeof response?.status === 'number' ? response.status : undefined
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const errorRecord = asRecord(error)
  const response = asRecord(errorRecord?.response)
  const data = asRecord(response?.data)
  const detail = validationDetail(data?.detail)
  if (detail) return detail

  if (typeof errorRecord?.message === 'string' && errorRecord.message.trim()) {
    return errorRecord.message
  }

  const status = getApiErrorStatus(error)
  return status ? `服务器错误 (HTTP ${status})` : fallback
}

/**
 * Emit a sanitized client-error signal without logging request headers,
 * payloads, session tokens, or the raw Axios error object.
 */
export function reportClientError(context: string, error: unknown, fallback = '操作失败'): ErrorSnapshot {
  const errorRecord = asRecord(error)
  const snapshot: ErrorSnapshot = {
    context,
    message: getApiErrorMessage(error, fallback),
    status: getApiErrorStatus(error),
    code: typeof errorRecord?.code === 'string' ? errorRecord.code : undefined,
  }

  console.error(`[AI4Papers] ${context}`, snapshot)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<ErrorSnapshot>('ai4papers:client-error', { detail: snapshot }))
  }
  return snapshot
}
