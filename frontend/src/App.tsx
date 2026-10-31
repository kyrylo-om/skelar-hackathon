import { useEffect, useMemo, useState } from 'react'
import { decideReview, listChats, replyToChat } from './api/support'
import { ChatList, type Filter } from './components/ChatList'
import { ChatView } from './components/ChatView'
import { TracePanel } from './components/TracePanel'
import type { Chat, Decision } from './types'

function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listChats().then((data) => {
      setChats(data)
      setSelectedId(data.find((c) => c.status === 'needs_review')?.id ?? data[0]?.id ?? null)
      setLoaded(true)
    })
  }, [])

  const pending = chats.filter((c) => c.review?.status === 'pending').length

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return chats.filter(
      (c) =>
        (filter === 'all' || c.status === filter) &&
        (!q || c.customer.toLowerCase().includes(q) || c.subject.toLowerCase().includes(q)),
    )
  }, [chats, filter, query])

  const selected = chats.find((c) => c.id === selectedId) ?? null

  async function update(action: Promise<Chat>) {
    setBusy(true)
    try {
      const updated = await action
      setChats((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>SupportPilot · Кабінет оператора</h1>
        <span className="muted">На перевірці: {pending}</span>
      </header>
      {!loaded ? (
        <p className="loading">Завантаження…</p>
      ) : (
        <main className="layout">
          <ChatList
            chats={visible}
            selectedId={selectedId}
            filter={filter}
            query={query}
            onFilter={setFilter}
            onQuery={setQuery}
            onSelect={setSelectedId}
          />
          {selected ? (
            <>
              <ChatView
                key={selected.id}
                chat={selected}
                busy={busy}
                onReply={(text) => update(replyToChat(selected.id, text))}
                onDecide={(d: Decision) => update(decideReview(selected.id, d))}
              />
              <TracePanel trace={selected.trace} />
            </>
          ) : (
            <p className="loading">Оберіть чат зі списку</p>
          )}
        </main>
      )}
    </div>
  )
}

export default App
