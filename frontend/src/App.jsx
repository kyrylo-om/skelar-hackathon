import { useEffect, useState } from 'react'
import { api } from './api/client'
import Client from './Client'
import Login from './Login'
import Operator from './Operator'

export default function App() {
  const [role, setRole] = useState('customer')
  const [user, setUser] = useState(null)

  // /health/ hands out the CSRF cookie; /auth/me/ restores an existing session.
  useEffect(() => {
    api
      .get('/health/')
      .then(() => api.get('/auth/me/'))
      .then(setUser)
      .catch(() => {})
  }, [])

  const logout = () => {
    api.post('/auth/logout/').finally(() => setUser(null))
  }

  return (
    <div className="app">
      <header>
        <div className="brand">SupportPilot</div>
        <nav>
          <button className={role === 'customer' ? 'on' : ''} onClick={() => setRole('customer')}>
            Клієнт
          </button>
          <button className={role === 'reviewer' ? 'on' : ''} onClick={() => setRole('reviewer')}>
            Оператор
          </button>
          {user && role === 'reviewer' && (
            <button className="ghost" onClick={logout}>
              Вийти ({user.username})
            </button>
          )}
        </nav>
      </header>
      <main>
        {role === 'customer' && <Client />}
        {role === 'reviewer' && (user ? <Operator onSessionExpired={() => setUser(null)} /> : <Login onLogin={setUser} />)}
      </main>
    </div>
  )
}
