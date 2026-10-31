import { api, ApiError, apiErrorMessage, isCsrfFailure, isSessionExpired } from './client'

export const SOURCES = { support: 'Операторські звернення', review: 'AI review' }
export const STATUS = {
  waiting_operator: 'Чекає оператора', operator: 'В роботі', resolved: 'Вирішено', ai: 'AI веде',
  needs_review: 'Передано людині', ai_handling: 'AI веде', pending: 'Чекає схвалення',
  approved: 'Схвалено', rejected: 'Відхилено', awaiting_confirmation: 'Чекає підтвердження клієнта',
  succeeded: 'Виконано', failed: 'Помилка', expired: 'Строк минув',
}
export const PRIORITY = { high: 'Високий', normal: 'Звичайний', low: 'Низький' }

export function adaptQueue(source, data) {
  const list = source === 'support' ? data?.results : data
  if (!Array.isArray(list) || list.some((row) => row?.id == null || typeof row.status !== 'string')) throw new Error('Сервер повернув неочікуваний формат черги.')
  return list.map((row) => ({
    ...row, source, key: `${source}:${row.id}`,
    assignedOperatorId: source === 'support' ? row.assigned_operator_id : undefined,
  }))
}

export async function readQueue(source, signal) {
  return adaptQueue(source, await api.get(source === 'support' ? '/operator/conversations/' : '/review/chats/', { signal }))
}

export function detailPath(source, id) {
  return source === 'support' ? `/operator/conversations/${encodeURIComponent(id)}/` : `/review/chats/${encodeURIComponent(id)}/`
}

export function adaptDetail(source, data) {
  if (!data?.id || !Array.isArray(data.messages)) throw new Error('Сервер повернув неочікуваний формат звернення.')
  return {
    ...data, source, key: `${source}:${data.id}`,
    messages: data.messages.map((message) => ({
      id: message.id, role: source === 'support' ? message.sender : message.role,
      text: message.text, at: source === 'support' ? message.created_at : message.at,
    })),
  }
}

export async function readDetail(source, id, signal) {
  const detail = adaptDetail(source, await api.get(detailPath(source, id), { signal }))
  if (String(detail.id) !== String(id)) throw new Error('Відповідь API не відповідає вибраному зверненню.')
  return detail
}

export async function describeError(error, onSessionExpired) {
  if (isSessionExpired(error)) onSessionExpired?.()
  if (error instanceof ApiError && error.status === 403 && !isCsrfFailure(error) && !isSessionExpired(error)) {
    // Permissions and expired Django sessions may both be 403. Check the session itself.
    try { await api.get('/me/', { signal: AbortSignal.timeout(10000) }) }
    catch (profileError) { if (isSessionExpired(profileError)) onSessionExpired?.() }
  }
  const kind = error instanceof ApiError && error.status === 403 && !isCsrfFailure(error) ? 'forbidden' : 'error'
  const message = error instanceof Error && !(error instanceof ApiError)
    ? error.name === 'TimeoutError' ? 'Перевищено час очікування відповіді сервера.' : error instanceof TypeError ? 'Сервер недоступний.' : error.message
    : apiErrorMessage(error)
  return { kind, message, status: error instanceof ApiError ? error.status : null }
}

export function formatDate(iso) {
  if (!iso) return 'Не надано'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat('uk-UA', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

export function exactDate(iso) {
  if (!iso) return 'Не надано'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? String(iso) : `${new Intl.DateTimeFormat('uk-UA', { dateStyle: 'full', timeStyle: 'long' }).format(date)} · ${iso}`
}

// Defense in depth only: the backend must redact credentials before sending them.
const credentialKey = /password|passwd|secret|token|authorization|cookie|api[_-]?key|private[_-]?key|connection[_-]?string|database[_-]?url/i
export function safeValue(value) {
  if (Array.isArray(value)) return value.map(safeValue)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, credentialKey.test(key) ? '[приховано]' : safeValue(item)]))
  if (typeof value === 'string') return value.replace(/\bBearer\s+\S+/gi, '[приховано]').replace(/\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/\S+/gi, '[приховано]')
  return value
}

export function safeJson(value) { return JSON.stringify(safeValue(value), null, 2) }

export function formatMoney(params) {
  if (params?.amount == null) return 'Не надано'
  if (!params.currency) return `${params.amount} (валюту не надано)`
  if (!Number.isFinite(Number(params.amount))) return 'Некоректна сума'
  try { return new Intl.NumberFormat('uk-UA', { style: 'currency', currency: params.currency }).format(Number(params.amount)) }
  catch { return `${params.amount} · ${params.currency}` }
}

export async function readApprovals(signal) {
  const chats = await readQueue('review', signal)
  const candidates = chats.filter((chat) => chat.status === 'needs_review')
  const details = []
  // There is no review list endpoint: inspect candidates in bounded batches.
  // Fail the read on any inaccessible detail instead of declaring a partial queue complete.
  for (let offset = 0; offset < candidates.length; offset += 4) {
    if (signal.aborted) throw signal.reason
    const batch = await Promise.allSettled(candidates.slice(offset, offset + 4).map((chat) => readDetail('review', chat.id, signal)))
    const failure = batch.find((result) => result.status === 'rejected')
    if (failure) throw failure.reason
    details.push(...batch.map((result) => result.value))
  }
  return details.filter((chat) => chat.review?.status === 'pending')
}

export async function readAudit(signal) {
  const data = await api.get('/review/audit/', { signal })
  if (!Array.isArray(data)) throw new Error('Сервер повернув неочікуваний формат журналу.')
  return data
}

// TODO(api): operator detail needs customer, subscription, assignment and waiting_since.
// TODO(api): review needs expires_at, version and execution result; no local expiry is invented.
// TODO(api): add one authoritative link between review.Chat and support.Conversation.
