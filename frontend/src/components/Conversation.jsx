import { useEffect, useRef, useState } from 'react'
import EmptyState from './EmptyState'
import ResourceState from './ResourceState'
import StatusDot from './StatusDot'
import Timestamp from './Timestamp'

const ROLES = { customer: 'Клієнт', assistant: 'AI', ai: 'AI', operator: 'Оператор', system: 'Системна подія' }

function MessageHistory({ messages }) {
  const container = useRef(null)
  const nearBottom = useRef(true)
  const previous = useRef([])
  const [newCount, setNewCount] = useState(0)
  const lastId = messages.at(-1)?.id
  const scrollToNew = () => {
    if (container.current) container.current.scrollTop = container.current.scrollHeight
    nearBottom.current = true
    setNewCount(0)
  }
  useEffect(() => {
    const known = new Set(previous.current)
    const added = messages.filter((message) => !known.has(message.id)).length
    if (nearBottom.current) scrollToNew()
    else if (added) setNewCount((count) => count + added)
    previous.current = messages.map((message) => message.id)
  }, [lastId, messages])

  return <div className="history-wrap">
    <div className="message-history" ref={container} role="region" tabIndex={0} aria-label="Історія повідомлень" onScroll={() => {
      const element = container.current
      nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 64
      if (nearBottom.current) setNewCount(0)
    }}>
      {!messages.length && <EmptyState title="Повідомлень ще немає" />}
      {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}>
        <div className="row spaced small muted"><span>{ROLES[message.role] || message.role}</span><Timestamp value={message.at} /></div>
        <p className="preserve">{message.text}</p>
      </article>)}
    </div>
    {newCount > 0 && <button className="new-messages" onClick={scrollToNew}>Нові повідомлення: {newCount}. Перейти вниз</button>}
  </div>
}

export default function Conversation({ resource, row, user, draft, onDraft, onSend, onClaim, onResolve, busy, uncertain }) {
  const detail = resource.error ? null : resource.data
  const assignmentKnown = Boolean(row && row.assigned_operator_id !== undefined)
  const assignedToMe = assignmentKnown && String(row.assignedOperatorId) === String(user.id)
  const isSupport = detail?.source === 'support'
  const canReply = detail && !busy && !uncertain && detail.status !== 'resolved' && (isSupport ? assignmentKnown && assignedToMe && detail.status === 'operator' : true)
  const canClaim = isSupport && assignmentKnown && detail.status === 'waiting_operator' && row.assignedOperatorId == null

  return <section className="inbox-conversation" aria-label="Звернення">
    <ResourceState resource={resource} />
    {!resource.loading && !resource.error && !detail && <EmptyState title="Оберіть звернення">Історія та доступні операції з’являться тут.</EmptyState>}
    {detail && <>
      <header className="conversation-heading stack">
        <div className="row spaced"><h2>{detail.customer || 'Звернення'}</h2><StatusDot status={detail.status} /></div>
        <div className="mono">#{detail.id}</div>
        {detail.subject && <p>{detail.subject}</p>}
        {isSupport ? <div className="row spaced small"><span className="muted">Оператор: {assignmentKnown ? row.assignedOperatorId == null ? 'Не призначено' : assignedToMe ? user.username : `ID ${row.assignedOperatorId}` : 'Призначення не надано актуальною чергою'}</span>{canClaim && <button className="primary" disabled={busy || uncertain} onClick={onClaim}>Взяти в роботу</button>}</div> : <p className="muted small">AI review: API дозволяє відповідь оператору без claim. Призначення й окреме закриття недоступні.</p>}
        {isSupport && <p className="muted small">Клієнт і його підписка не включені до операторського API.</p>}
      </header>
      <MessageHistory key={detail.key} messages={detail.messages} />
      {detail.pending_action && <div className="notice"><StatusDot status={detail.pending_action.status} /><p>{detail.pending_action.description}</p><p className="small muted">Підтверджує лише клієнт. Оператор не має цієї дії.</p></div>}
      <form className="reply-composer stack" onSubmit={(event) => { event.preventDefault(); if (canReply && draft.trim()) onSend() }}>
        <label htmlFor="operator-reply">Відповідь клієнту</label>
        <textarea id="operator-reply" rows={4} maxLength={isSupport ? 4000 : 2000} placeholder="Відповідь у цьому самому діалозі…" value={draft} onChange={(event) => onDraft(event.target.value)} disabled={!canReply} />
        {!canReply && <p className="small muted">{uncertain ? 'Результат попереднього запиту не визначено. Спочатку звірте стан із сервером.' : detail.status === 'resolved' ? 'Звернення закрите.' : isSupport ? 'Для відповіді потрібні актуальне призначення на вас і стан «В роботі».' : 'Дочекайтеся завершення операції.'}</p>}
        <div className="row spaced"><button className="primary" type="submit" disabled={!canReply || !draft.trim()}>{busy ? 'Обробка…' : 'Надіслати'}</button>{isSupport && <button type="button" disabled={!canReply} onClick={onResolve}>Закрити звернення</button>}</div>
        {/* TODO(api): AI draft endpoint is absent; never generate or send a local substitute. */}
        <span className="small muted">Чернетка від AI недоступна: API не надає цю операцію.</span>
      </form>
    </>}
  </section>
}
