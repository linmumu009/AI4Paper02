import { describe, expect, it, vi } from 'vitest'
import { getApiErrorMessage, getApiErrorStatus, reportClientError } from '../apiError'

describe('apiError', () => {
  it('prefers a backend detail message', () => {
    const error = { message: 'Request failed', response: { status: 400, data: { detail: '用户名已存在' } } }
    expect(getApiErrorMessage(error, '注册失败')).toBe('用户名已存在')
    expect(getApiErrorStatus(error)).toBe(400)
  })

  it('formats FastAPI validation issues', () => {
    const error = {
      response: {
        status: 422,
        data: { detail: [{ loc: ['body', 'phone'], msg: '手机号格式错误' }] },
      },
    }
    expect(getApiErrorMessage(error, '提交失败')).toBe('phone: 手机号格式错误')
  })

  it('falls back to a normal Error message', () => {
    expect(getApiErrorMessage(new Error('网络连接中断'), '加载失败')).toBe('网络连接中断')
  })

  it('uses the supplied fallback for unknown values', () => {
    expect(getApiErrorMessage(null, '加载失败')).toBe('加载失败')
  })

  it('reports only a sanitized error snapshot', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const eventSpy = vi.fn()
    window.addEventListener('ai4papers:client-error', eventSpy)

    const snapshot = reportClientError('auth.login', {
      code: 'ECONNABORTED',
      config: { headers: { Authorization: 'Bearer secret' } },
      response: { status: 503, data: { detail: '服务暂不可用' } },
    })

    expect(snapshot).toEqual({
      context: 'auth.login',
      message: '服务暂不可用',
      status: 503,
      code: 'ECONNABORTED',
    })
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain('Bearer secret')
    expect(eventSpy).toHaveBeenCalledOnce()

    window.removeEventListener('ai4papers:client-error', eventSpy)
    consoleSpy.mockRestore()
  })
})
