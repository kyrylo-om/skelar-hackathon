import { useCallback, useEffect, useState } from 'react'
import { api, apiErrorMessage, isSessionExpired } from './api/client'
import AppShell from './components/AppShell'
import { Skeleton } from './components/EmptyState'
import Login from './Login'
import Operator from './Operator'

export default function App() {
  const [page, setPage] = useState('inbox')
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const sessionExpired = useCallback(() => { setUser(null); setError('Сесія завершилася. Увійдіть знову.') }, [])

  useEffect(() => {
    const controller = new AbortController()
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)])
    api.get('/auth/csrf/', { signal }).then(() => api.get('/me/', { signal })).then((profile) => {
      if (!controller.signal.aborted) setUser(profile)
    }).catch((err) => {
      if (!controller.signal.aborted && !isSessionExpired(err)) setError(apiErrorMessage(err))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  const logout = async () => {
    if (busy) return
    setBusy(true)
    try { await api.post('/auth/logout/', {}, { signal: AbortSignal.timeout(15000) }); setUser(null); setError('') }
    catch (err) { if (isSessionExpired(err)) sessionExpired(); else setError(apiErrorMessage(err)) }
    finally { setBusy(false) }
  }

  return (
    <AppShell page={page} onNavigate={setPage} user={user} onLogout={logout} busy={busy}>
      {error && <div className="notice error" role="alert">{error}</div>}
      {loading ? <Skeleton label="Перевірка сесії" /> : !user ? <Login role="operator" onLogin={(profile) => { setUser(profile); setError('') }} /> : <Operator user={user} page={page} onNavigate={setPage} onSessionExpired={sessionExpired} />}
    </AppShell>
  )
}
