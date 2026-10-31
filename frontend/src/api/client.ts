const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown

  constructor(status: number, data: unknown) {
    super(`API request failed with status ${status}`)
    this.status = status
    this.data = data
  }
}

function getCookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`))
    ?.split('=')[1]
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const method = (options.method ?? 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCookie('csrftoken')
    if (csrfToken) headers.set('X-CSRFToken', csrfToken)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data)
  return data as T
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
}

type ErrorBody = { detail?: unknown; error?: { code?: string; message?: string } } | null

// The API answers errors as {"error": {"code", "message"}} (accounts, support) or {"detail"} (review).
export function apiErrorMessage(err: unknown, fallback = 'Помилка сервера'): string {
  if (!(err instanceof ApiError)) return 'Сервер недоступний'
  const body = err.data as ErrorBody
  return body?.error?.message || (typeof body?.detail === 'string' ? body.detail : '') || fallback
}

// A failed CSRF check is a 403 too, but the session is still fine.
export function isCsrfFailure(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false
  const body = err.data as ErrorBody
  return body?.error?.code === 'csrf_failed' || String(body?.detail).startsWith('CSRF')
}
