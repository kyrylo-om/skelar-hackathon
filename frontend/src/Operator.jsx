import { useState } from 'react'
import { useStore, approve, reject, operatorReply, resolve, undo, draftReply, metrics } from './store'
import Trace from './Trace'

const STATUS = { ai_handling: 'AI веде', awaiting_human: 'Чекає людину', in_review: 'У роботі', resolved: 'Вирішено' }
const PRIO = { high: 'Високий', normal: 'Звичайний', low: 'Низький' }
const ago = (ts) => new Date(ts).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function Operator() {
  const s = useStore()
  const [id, setId] = useState(3)
  const [reply, setReply] = useState('')
  const [amount, setAmount] = useState('')
  const [why, setWhy] = useState('')
  const [showAll, setShowAll] = useState(false)
  const t = s.tickets.find((x) => x.id === id)
  const m = metrics(s)
  const queue = s.tickets.filter((x) => showAll || x.status === 'awaiting_human' || x.status === 'in_review')
  const sorted = [...queue].sort((a, b) => (b.priority === 'high') - (a.priority === 'high'))
  const p = t.pending
  const send = () => { operatorReply(t.id, reply); setReply('') }

  return (
    <div className="operator">
      <div className="metrics">
        <div><b>{m.auto}%</b><span>вирішено AI без людини</span></div>
        <div><b>{m.aiDone}</b><span>дій виконано AI</span></div>
        <div><b>{m.human}</b><span>рішень людини</span></div>
        <div><b>{m.pending}</b><span>чекають рев'юверів</span></div>
        <div className="danger"><b>{m.attacks}</b><span>атак заблоковано</span></div>
      </div>
      <div className="cols">
        <aside className="queue">
          <div className="col-head">
            <b>Черга</b>
            <label className="muted"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> усі</label>
          </div>
          {sorted.length === 0 && <div className="muted pad">Черга порожня</div>}
          {sorted.map((x) => (
            <button key={x.id} className={'q-item' + (x.id === id ? ' active' : '')} onClick={() => setId(x.id)}>
              <span><b>{x.customer.name}</b>{x.customer.tier === 'vip' && ' · VIP'}</span>
              <span className="muted">{STATUS[x.status]} · <span className={x.priority === 'high' ? 'prio' : ''}>{PRIO[x.priority]}</span></span>
              {x.reason && <span className="reason">{x.reason}</span>}
            </button>
          ))}
          <div className="col-head"><b>Атаки</b></div>
          {s.security.length === 0 && <div className="muted pad">Подій немає</div>}
          {s.security.map((e, i) => (
            <div key={i} className="sec"><b>{e.customer}</b> · {ago(e.at)}<div className="muted">«{e.text}»</div><div className="tag bad">{e.rule}</div></div>
          ))}
        </aside>

        <section className="dialog">
          <div className="col-head"><b>{t.customer.name}</b><span className="muted">{STATUS[t.status]} · {t.sentiment || 'neutral'}</span></div>
          <div className="chat small">
            {t.messages.map((x, i) => (
              <div key={i} className={'msg ' + x.role}><div className="who">{{ customer: 'Клієнт', ai: 'AI', operator: 'Оператор', system: 'Система' }[x.role]}</div><div className="bubble">{x.text}</div></div>
            ))}
          </div>
          <div className="reply">
            <textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Відповідь клієнту в цьому ж чаті…" rows={3} />
            <div className="row">
              <button className="ghost" onClick={() => setReply(draftReply(t))}>Чернетка від AI</button>
              <button onClick={send} disabled={!reply.trim()}>Відповісти</button>
              <button className="ghost" onClick={() => resolve(t.id)} disabled={t.status === 'resolved'}>Закрити</button>
            </div>
          </div>
        </section>

        <aside className="ai-panel">
          <div className="col-head"><b>Рішення AI</b></div>
          <div className="card">
            <div className="muted">Підсумок</div>
            <p>{t.summary || 'Звернення поки без ескалації.'}</p>
            {t.reason && <div className="tag warn">Чому до людини: {t.reason}</div>}
          </div>
          {p && (
            <div className="card pending">
              <div className="muted">Дія очікує рішення</div>
              <div><b>{p.name}</b> <code>{JSON.stringify(p.params)}</code></div>
              {p.params.amount !== undefined && (
                <label className="amt">Сума, грн <input type="number" defaultValue={p.params.amount} onChange={(e) => setAmount(e.target.value)} /></label>
              )}
              <input className="why" placeholder="Причина (для відхилення)" value={why} onChange={(e) => setWhy(e.target.value)} />
              <div className="row">
                <button onClick={() => { approve(t.id, amount); setAmount('') }}>Схвалити</button>
                <button className="danger-btn" onClick={() => { reject(t.id, why); setWhy('') }}>Відхилити</button>
              </div>
              <div className="muted">Після схвалення Policy Engine перевіряє дію ще раз.</div>
            </div>
          )}
          <div className="card"><div className="muted">Trace агентів</div><Trace steps={t.lastTrace} compact /></div>
          <div className="card">
            <div className="muted">Дії по зверненню</div>
            {t.actions.length === 0 && <div className="muted">—</div>}
            {t.actions.map((a) => (
              <div key={a.id} className="log"><span><b>{a.name}</b> <code>{JSON.stringify(a.params)}</code></span>
                <span className={'tag ' + (a.status === 'executed' ? 'good' : a.status === 'pending_review' ? 'warn' : 'bad')}>{a.status}</span>
                {a.status === 'executed' && <button className="ghost sm" onClick={() => undo(t.id, a.id)}>Скасувати дію</button>}
              </div>
            ))}
          </div>
        </aside>
      </div>
      <details className="audit"><summary>Аудит-лог ({s.audit.length})</summary>
        {s.audit.map((a, i) => <div key={i} className="muted">{ago(a.at)} · #{a.ticket} · {a.by} · {a.text}</div>)}
      </details>
    </div>
  )
}
