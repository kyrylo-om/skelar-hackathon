import { useState } from 'react'
import { ApiError, api, apiErrorMessage } from './api/client'

export default function Login({ role, onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
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
    <form className="login" onSubmit={submit}>
      <h2>{role === 'operator' ? 'Вхід для менеджерів' : 'Вхід для клієнтів'}</h2>
      <label>Логін<input
        placeholder="Логін"
        autoComplete="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoFocus
        required
      /></label>
      <label>Пароль<input
        type="password"
        placeholder="Пароль"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      /></label>
      {error && <div className="notice error" role="alert">{error}</div>}
      <button className="primary" disabled={busy || !username || !password}>{busy ? 'Вхід…' : 'Увійти'}</button>
    </form>
  )
}
