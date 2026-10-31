import { useState } from 'react'
import { ApiError, api } from './api/client'

export default function Login({ role, onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin(await api.post('/auth/login/', { username, password, role }))
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 429 ? 'Забагато спроб, спробуйте за хвилину' : err.data?.detail || 'Не вдалося увійти')
      } else {
        setError('Сервер недоступний')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h2>{role === 'operator' ? 'Вхід для менеджерів' : 'Вхід для клієнтів'}</h2>
      <input
        placeholder="Логін"
        autoComplete="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoFocus
      />
      <input
        type="password"
        placeholder="Пароль"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {error && <div className="tag bad">{error}</div>}
      <button disabled={busy || !username || !password}>Увійти</button>
    </form>
  )
}
