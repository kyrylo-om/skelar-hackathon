import { statusLabel } from '../labels'
import type { Chat, ChatStatus } from '../types'

export type Filter = 'all' | ChatStatus

const filters: { value: Filter; label: string }[] = [
  { value: 'all', label: 'Усі' },
  { value: 'needs_review', label: 'Перевірка' },
  { value: 'ai_handling', label: 'AI' },
  { value: 'resolved', label: 'Вирішені' },
]

type Props = {
  chats: Chat[]
  selectedId: number | null
  filter: Filter
  query: string
  onFilter: (filter: Filter) => void
  onQuery: (query: string) => void
  onSelect: (id: number) => void
}

export function ChatList({ chats, selectedId, filter, query, onFilter, onQuery, onSelect }: Props) {
  return (
    <aside className="panel list">
      <h2>Усі чати</h2>
      <input
        type="search"
        placeholder="Пошук за клієнтом або темою"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        aria-label="Пошук"
      />
      <div className="filters" role="group" aria-label="Фільтр за статусом">
        {filters.map((f) => (
          <button
            key={f.value}
            className={filter === f.value ? 'chip active' : 'chip'}
            onClick={() => onFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <ul>
        {chats.map((chat) => (
          <li key={chat.id}>
            <button
              className={chat.id === selectedId ? 'item selected' : 'item'}
              onClick={() => onSelect(chat.id)}
            >
              <span className="item-top">
                <strong>{chat.customer}</strong>
                <span className={`badge ${chat.status}`}>{statusLabel[chat.status]}</span>
              </span>
              <span className="item-subject">{chat.subject}</span>
              <span className="item-meta">
                {chat.priority === 'high' && <span className="prio">● високий</span>}
                {new Date(chat.updatedAt).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </button>
          </li>
        ))}
        {chats.length === 0 && <li className="empty">Нічого не знайдено</li>}
      </ul>
    </aside>
  )
}
