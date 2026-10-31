import { useEffect, useState } from 'react'
import { api } from './api/client'

type Health = { status: string }

function App() {
  const [status, setStatus] = useState<string>('checking…')

  useEffect(() => {
    api
      .get<Health>('/health/')
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main style={{ padding: '2rem' }}>
      <h1>App</h1>
      <p>Backend: {status}</p>
    </main>
  )
}

export default App
