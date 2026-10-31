import { useState } from 'react'
import { ApiError, api, apiErrorMessage } from './api/client'

export default function Login({ role, onLogin }) {
  const [username, setUsername] = useState('operator')
  const [password, setPassword] = useState('operator123')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.get('/auth/csrf/', { signal: AbortSignal.timeout(10000) })
      onLogin(await api.post('/auth/login/', { username, password }, { signal: AbortSignal.timeout(15000) }))
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? 'Забагато спроб, спробуйте за хвилину'
          : apiErrorMessage(err, 'Не вдалося увійти'),
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-view-wrap">
      <form className="login" onSubmit={submit} noValidate={false}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', marginBottom: '8px' }}>
          <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'var(--brand)', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '12px', boxShadow: 'var(--shadow-sm)' }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <h2>{role === 'operator' ? 'Вхід для менеджерів' : 'Вхід для клієнтів'}</h2>
          <p className="muted small" style={{ marginTop: '4px' }}>Увійдіть для роботи зі зверненнями клієнтів</p>
        </div>

        <label>
          Логін
          <input
            placeholder="Логін"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            required
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            placeholder="Пароль"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <div className="notice error" role="alert">{error}</div>}
        <button className="primary" disabled={busy || !username || !password}>{busy ? 'Вхід…' : 'Увійти'}</button>
      </form>
    </div>
  )
}
