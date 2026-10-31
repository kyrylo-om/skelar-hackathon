import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from './api/client'
import Trace from './Trace'

const STATUS = { needs_review: 'Чекає людину', ai_handling: 'AI веде', resolved: 'Вирішено' }
const PRIO = { high: 'Високий', normal: 'Звичайний', low: 'Низький' }
const ROLE = { customer: 'Клієнт', ai: 'AI', operator: 'Оператор', system: 'Система' }
const RISK = { high: 'високий', medium: 'середній', low: 'низький' }
const POLL_MS = 5000

const clock = (iso) =>
  new Date(iso).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

function errorText(err) {
  return err instanceof ApiError ? err.data?.detail || 'Помилка сервера' : 'Сервер недоступний'
}

export default function Operator({ onSessionExpired }) {
  const [chats, setChats] = useState([])
  const [audit, setAudit] = useState([])
  const [id, setId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [reply, setReply] = useState('')
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Until the operator picks a chat, show the first one that needs a human.
  const activeId = id ?? (chats.find((c) => c.status === 'needs_review') ?? chats[0])?.id ?? null

  // A 403 means the session is gone or the user lost operator rights; a failed CSRF check is
  // also a 403, but the session is fine, so only report it.
  const fail = useCallback(
    (err) => {
      const csrf = String(err instanceof ApiError ? err.data?.detail : '').startsWith('CSRF')
      if (err instanceof ApiError && err.status === 403 && !csrf) onSessionExpired?.()
      else setError(errorText(err))
    },
    [onSessionExpired],
  )

  const refresh = useCallback(() => {
    Promise.all([api.get('/chats/'), api.get('/audit/')])
      .then(([list, log]) => {
        setChats(list)
        setAudit(log)
        setError('')
      })
      .catch(fail)
    if (activeId !== null) api.get(`/chats/${activeId}/`).then(setDetail).catch(fail)
  }, [activeId, fail])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  const run = async (request) => {
    setBusy(true)
    setError('')
    try {
      setDetail(await request())
      refresh()
      return true
    } catch (err) {
      fail(err)
      return false
    } finally {
      setBusy(false)
    }
  }

  const send = async () => {
    if (await run(() => api.post(`/chats/${activeId}/reply/`, { text: reply }))) setReply('')
  }
  const decide = async (decision) => {
    if (await run(() => api.post(`/reviews/${detail.review.id}/decision/`, { decision, note: why }))) setWhy('')
  }

  const q = query.trim().toLowerCase()
  const queue = chats
    .filter((c) => showAll || c.status === 'needs_review')
    .filter((c) => !q || c.customer.toLowerCase().includes(q) || c.subject.toLowerCase().includes(q))
    .sort((a, b) => (b.priority === 'high') - (a.priority === 'high'))

  const count = (status) => chats.filter((c) => c.status === status).length
  const review = detail?.review
  const pending = review?.status === 'pending'

  return (
    <div className="operator">
      <div className="metrics">
        <div><b>{chats.length}</b><span>усього чатів</span></div>
        <div className={count('needs_review') ? 'danger' : ''}><b>{count('needs_review')}</b><span>чекають перевірки</span></div>
        <div><b>{count('ai_handling')}</b><span>веде AI</span></div>
        <div><b>{count('resolved')}</b><span>вирішено</span></div>
        <div><b>{audit.filter((a) => a.event.startsWith('review_')).length}</b><span>рішень людини</span></div>
      </div>
      {error && <div className="tag bad">{error}</div>}
      <div className="cols">
        <aside className="queue">
          <div className="col-head">
            <b>Черга</b>
            <label className="muted"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> усі чати</label>
          </div>
          <div className="pad">
            <input placeholder="Пошук за клієнтом або темою" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Пошук" />
          </div>
          {queue.length === 0 && <div className="muted pad">Нічого немає</div>}
          {queue.map((c) => (
            <button key={c.id} className={'q-item' + (c.id === activeId ? ' active' : '')} onClick={() => { setId(c.id); setDetail(null) }}>
              <span><b>{c.customer}</b></span>
              <span className="muted">{c.subject}</span>
              <span className="muted">{STATUS[c.status]} · <span className={c.priority === 'high' ? 'prio' : ''}>{PRIO[c.priority]}</span></span>
            </button>
          ))}
        </aside>

        <section className="dialog">
          {!detail ? (
            <div className="muted pad">Оберіть чат</div>
          ) : (
            <>
              <div className="col-head"><b>{detail.customer}</b><span className="muted">{STATUS[detail.status]}</span></div>
              <div className="chat small">
                {detail.messages.map((m) => (
                  <div key={m.id} className={'msg ' + m.role}>
                    <div className="who">{ROLE[m.role]} · {clock(m.at)}</div>
                    <div className="bubble">{m.text}</div>
                  </div>
                ))}
              </div>
              <div className="reply">
                <textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Відповідь клієнту в цьому ж чаті…" rows={3} aria-label="Відповідь клієнту" />
                <div className="row">
                  <button onClick={send} disabled={busy || !reply.trim()}>Відповісти</button>
                </div>
              </div>
            </>
          )}
        </section>

        <aside className="ai-panel">
          <div className="col-head"><b>Рішення AI</b></div>
          {detail && (
            <>
              <div className="card">
                <div className="muted">Підсумок</div>
                <p>{detail.summary || 'Звернення поки без ескалації.'}</p>
                {pending && <div className="tag warn">Чому до людини: {review.reason}</div>}
              </div>
              {review && (
                <div className={'card' + (pending ? ' pending' : '')}>
                  <div className="muted">{pending ? 'Дія очікує рішення' : review.status === 'approved' ? 'Схвалено' : 'Відхилено'}{review.decidedBy && ` · ${review.decidedBy}`}</div>
                  <div><b>{review.action}</b> <code>{JSON.stringify(review.params)}</code></div>
                  <div className="muted">Ризик: {RISK[review.risk]}</div>
                  {pending && (
                    <>
                      <input className="why" placeholder="Коментар до рішення" value={why} onChange={(e) => setWhy(e.target.value)} aria-label="Коментар" />
                      <div className="row">
                        <button disabled={busy} onClick={() => decide('approved')}>Схвалити</button>
                        <button className="danger-btn" disabled={busy} onClick={() => decide('rejected')}>Відхилити</button>
                      </div>
                    </>
                  )}
                </div>
              )}
              <div className="card"><div className="muted">Trace агентів</div><Trace steps={detail.trace} compact /></div>
            </>
          )}
        </aside>
      </div>
      <details className="audit"><summary>Аудит-лог ({audit.length})</summary>
        {audit.map((a) => <div key={a.id} className="muted">{clock(a.at)} · {a.chat ? `#${a.chat} · ` : ''}{a.actor ?? 'система'} · {a.event}</div>)}
      </details>
    </div>
  )
}
