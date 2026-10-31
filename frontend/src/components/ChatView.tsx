import { useState } from 'react'
import type { Chat, Decision, Role } from '../types'
import { statusLabel } from '../labels'

const roleLabel: Record<Role, string> = {
  customer: 'Клієнт',
  ai: 'AI',
  operator: 'Оператор',
  system: 'Система',
}

const riskLabel = { low: 'низький', medium: 'середній', high: 'високий' }

type Props = {
  chat: Chat
  busy: boolean
  onReply: (text: string) => void
  onDecide: (decision: Decision) => void
}

export function ChatView({ chat, busy, onReply, onDecide }: Props) {
  const [text, setText] = useState('')
  const review = chat.review

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return
    onReply(trimmed)
    setText('')
  }

  return (
    <section className="panel view">
      <header>
        <div>
          <h2>{chat.customer}</h2>
          <p className="muted">{chat.subject}</p>
        </div>
        <span className={`badge ${chat.status}`}>{statusLabel[chat.status]}</span>
      </header>

      <div className="summary">
        <strong>Підсумок AI</strong>
        <p>{chat.summary}</p>
      </div>

      {review && (
        <div className={`review ${review.status}`}>
          <div className="review-head">
            <strong>Дія на перевірку: {review.action}</strong>
            <span className={`risk ${review.risk}`}>ризик: {riskLabel[review.risk]}</span>
          </div>
          <p>{review.reason}</p>
          <code>{JSON.stringify(review.params)}</code>
          {review.status === 'pending' ? (
            <div className="actions">
              <button className="approve" disabled={busy} onClick={() => onDecide('approved')}>
                Схвалити
              </button>
              <button className="reject" disabled={busy} onClick={() => onDecide('rejected')}>
                Відхилити
              </button>
            </div>
          ) : (
            <p className="muted">
              {review.status === 'approved' ? 'Схвалено оператором' : 'Відхилено оператором'}
            </p>
          )}
        </div>
      )}

      <ol className="messages" aria-label="Переписка">
        {chat.messages.map((m) => (
          <li key={m.id} className={`msg ${m.role}`}>
            <span className="msg-role">{roleLabel[m.role]}</span>
            <p>{m.text}</p>
            <time>{new Date(m.at).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })}</time>
          </li>
        ))}
      </ol>

      <form className="reply" onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Відповісти клієнту в цьому чаті…"
          aria-label="Відповідь клієнту"
        />
        <button type="submit" disabled={busy || !text.trim()}>
          Надіслати
        </button>
      </form>
    </section>
  )
}
