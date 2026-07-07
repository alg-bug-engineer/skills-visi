import type { ApiError } from './types'

const BASE = '/api/v1'

export function isApiError(x: unknown): x is ApiError {
  return !!x && typeof x === 'object' && (x as ApiError).ok === false
}

/** 统一 POST JSON；非 2xx / 网络错误规整为 ApiError（不抛裸异常）。 */
export async function postJSON<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T | ApiError> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      signal,
    })
    if (!res.ok) {
      let detail: unknown = null
      try {
        detail = await res.json()
      } catch {
        /* ignore */
      }
      return { ok: false, reason: `http_${res.status}`, detail }
    }
    return (await res.json()) as T
  } catch (e) {
    const reason = e instanceof DOMException && e.name === 'AbortError' ? 'aborted' : 'network_error'
    return { ok: false, reason, detail: String(e) }
  }
}

export async function getJSON<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T | ApiError> {
  try {
    const qs = params
      ? '?' +
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== '')
          .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
          .join('&')
      : ''
    const res = await fetch(`${BASE}${path}${qs}`)
    if (!res.ok) return { ok: false, reason: `http_${res.status}` }
    return (await res.json()) as T
  } catch (e) {
    return { ok: false, reason: 'network_error', detail: String(e) }
  }
}
