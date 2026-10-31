import { afterEach, expect, test, vi } from 'vitest'
import { ApiError } from './client'
import { adaptQueue, describeError, formatMoney, readApprovals, safeJson } from './operator'

afterEach(() => { vi.unstubAllGlobals() })

test('credential fields are excluded recursively from displayed JSON', () => {
  const output = safeJson({ action: 'read', params: { password: 'password-value', api_key: 'key-value', headers: { Authorization: 'Bearer secret-value', Cookie: 'session-value' }, nested: [{ access_token: 'token-value' }] } })
  for (const secret of ['password-value', 'key-value', 'secret-value', 'session-value', 'token-value']) expect(output).not.toContain(secret)
  expect(output).toContain('read')
})

test('missing currency is disclosed instead of assumed and absent money is never zero', () => {
  expect(formatMoney({ amount: 12 })).toContain('валюту не надано')
  expect(formatMoney({})).toBe('Не надано')
  expect(formatMoney({ amount: 12, currency: 'USD' })).toBe(new Intl.NumberFormat('uk-UA', { style: 'currency', currency: 'USD' }).format(12))
})

test('a paginated or malformed list cannot silently masquerade as a complete queue', () => {
  expect(() => adaptQueue('review', { results: [], count: 100 })).toThrow()
  expect(() => adaptQueue('support', null)).toThrow()
})

test('ambiguous 403 checks the session before calling it expired', async () => {
  const expired = vi.fn()
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ id: '7', username: 'op', is_staff: true })))))
  const failure = await describeError(new ApiError(403, { detail: 'Forbidden' }), expired)
  expect(failure.kind).toBe('forbidden')
  expect(expired).not.toHaveBeenCalled()
})

test('one failed candidate read prevents a false empty approvals queue', async () => {
  vi.stubGlobal('fetch', vi.fn((url) => Promise.resolve(new Response(JSON.stringify(String(url).endsWith('/review/chats/') ? [{ id: 1, status: 'needs_review' }] : { detail: 'Not found' }), { status: String(url).endsWith('/review/chats/') ? 200 : 404 }))))
  await expect(readApprovals(new AbortController().signal)).rejects.toBeInstanceOf(ApiError)
})
