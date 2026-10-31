import { useCallback } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ApiError } from './client'
import usePolling from './usePolling'

beforeEach(() => {
  vi.useFakeTimers()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

test('polling waits for a read to finish before scheduling the next one', async () => {
  let complete
  const load = vi.fn(() => new Promise((resolve) => { complete = resolve }))
  const { result, unmount } = renderHook(() => usePolling(load, 5000))
  expect(load).toHaveBeenCalledTimes(1)
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(load).toHaveBeenCalledTimes(1)
  await act(async () => { complete(['first']) })
  expect(result.current.data).toEqual(['first'])
  await act(() => vi.advanceTimersByTimeAsync(5000))
  expect(load).toHaveBeenCalledTimes(2)
  unmount()
})

test('late responses from a previously selected resource cannot replace the new resource', async () => {
  let finishOld
  const old = new Promise((resolve) => { finishOld = resolve })
  const { result, rerender, unmount } = renderHook(({ id }) => {
    const load = useCallback(() => id === 'old' ? old : Promise.resolve('new data'), [id])
    return usePolling(load, 5000)
  }, { initialProps: { id: 'old' } })
  await act(async () => { rerender({ id: 'new' }) })
  expect(result.current.data).toBe('new data')
  await act(async () => { finishOld('stale data') })
  expect(result.current.data).toBe('new data')
  unmount()
})

test('polling pauses in hidden tabs and refreshes on return', async () => {
  const load = vi.fn(() => Promise.resolve([]))
  const { unmount } = renderHook(() => usePolling(load, 5000))
  await act(async () => {})
  await act(async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(30000)
  })
  expect(load).toHaveBeenCalledTimes(1)
  await act(async () => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  expect(load).toHaveBeenCalledTimes(2)
  unmount()
})

test('errors apply backoff and a successful read restores the regular interval', async () => {
  const load = vi.fn().mockRejectedValueOnce(new ApiError(503, { detail: 'Unavailable' })).mockResolvedValue([])
  const { result, unmount } = renderHook(() => usePolling(load, 5000))
  await act(async () => {})
  expect(result.current.error).not.toBeNull()
  await act(() => vi.advanceTimersByTimeAsync(9999))
  expect(load).toHaveBeenCalledTimes(1)
  await act(() => vi.advanceTimersByTimeAsync(1))
  expect(load).toHaveBeenCalledTimes(2)
  expect(result.current.error).toBeNull()
  await act(() => vi.advanceTimersByTimeAsync(5000))
  expect(load).toHaveBeenCalledTimes(3)
  unmount()
})
