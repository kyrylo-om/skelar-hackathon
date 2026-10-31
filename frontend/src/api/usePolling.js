import { useCallback, useEffect, useRef, useState } from 'react'
import { describeError } from './operator'

export default function usePolling(load, interval, onSessionExpired, enabled = true) {
  const [resource, setResource] = useState({ load, enabled, data: null, loading: enabled, error: null, updatedAt: null })
  const refreshRef = useRef(async () => {})
  const refresh = useCallback(() => refreshRef.current(), [])

  // Reset when the requested resource changes, before rendering its consumers.
  if (resource.load !== load || resource.enabled !== enabled) {
    setResource({ load, enabled, data: null, loading: enabled, error: null, updatedAt: null })
  }

  useEffect(() => {
    let disposed = false
    let inFlight = null
    let controller = null
    let timer
    let requestTimeout
    let failures = 0
    let generation = 0

    const run = () => {
      if (disposed || !enabled || document.hidden) return Promise.resolve()
      if (inFlight) return inFlight
      clearTimeout(timer)
      controller = new AbortController()
      const activeController = controller
      const requestGeneration = ++generation
      const timeout = setTimeout(() => activeController.abort(new DOMException('Перевищено час очікування.', 'TimeoutError')), 15000)
      requestTimeout = timeout
      inFlight = (async () => {
        try {
          const data = await load(activeController.signal)
          if (disposed || activeController.signal.aborted || requestGeneration !== generation) return
          failures = 0
          setResource({ load, enabled, data, loading: false, error: null, updatedAt: new Date().toISOString() })
          return data
        } catch (error) {
          if (disposed || requestGeneration !== generation || (activeController.signal.aborted && activeController.signal.reason?.name !== 'TimeoutError')) return
          failures += 1
          const failure = await describeError(activeController.signal.reason?.name === 'TimeoutError' ? activeController.signal.reason : error, () => {
            if (!disposed && requestGeneration === generation) onSessionExpired?.()
          })
          if (!disposed && requestGeneration === generation) setResource((previous) => ({ ...previous, loading: false, error: failure }))
        } finally {
          clearTimeout(timeout)
          inFlight = null
          if (!disposed && enabled && !document.hidden) timer = setTimeout(run, Math.min(interval * 2 ** failures, 60000))
        }
      })()
      return inFlight
    }

    const force = async () => {
      clearTimeout(timer)
      generation += 1
      controller?.abort()
      if (inFlight) await inFlight
      if (!disposed) return run()
    }
    refreshRef.current = force
    const visibility = () => {
      clearTimeout(timer)
      if (document.hidden) controller?.abort()
      else void force()
    }
    document.addEventListener('visibilitychange', visibility)
    if (enabled) void run()
    return () => {
      disposed = true
      generation += 1
      clearTimeout(timer)
      clearTimeout(requestTimeout)
      controller?.abort()
      document.removeEventListener('visibilitychange', visibility)
      refreshRef.current = async () => {}
    }
  }, [load, interval, enabled, onSessionExpired])

  return { ...(resource.load === load && resource.enabled === enabled ? resource : { data: null, loading: enabled, error: null, updatedAt: null }), refresh }
}
