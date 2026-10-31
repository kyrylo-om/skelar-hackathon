import { useCallback, useState } from 'react'
import { readAudit, safeJson } from '../api/operator'
import usePolling from '../api/usePolling'
import ResourceState from '../components/ResourceState'
import StatusDot from '../components/StatusDot'
import Timestamp from '../components/Timestamp'

const EVENTS = { operator_reply: 'Відповідь оператора', review_approved: 'Review схвалено', review_rejected: 'Review відхилено' }
const statusOf = (event) => event === 'review_approved' ? 'approved' : event === 'review_rejected' ? 'rejected' : event

export function ConversationAudit({ chatId, onSessionExpired }) {
  const load = useCallback((signal) => readAudit(signal), [])
  const resource = usePolling(load, 10000, onSessionExpired)
  const records = resource.data?.filter((record) => String(record.chat) === String(chatId)) || []
  return <div className="stack">
    <p className="small muted">Збіги серед останніх 100 подій AI review; це не повна історія виконання.</p>
    <ResourceState resource={resource} empty={resource.data && !records.length}>У доступній вибірці подій для цього звернення немає.</ResourceState>
    {!resource.error && records.map((record) => <div className="audit-entry stack" key={record.id}><Timestamp className="small muted" value={record.at} /><p>{EVENTS[record.event] || record.event} · {record.actor ?? 'Ініціатор не наданий'}</p><pre>{safeJson(record.payload)}</pre></div>)}
  </div>
}

export default function ActionsLog({ onOpen, onSessionExpired }) {
  const load = useCallback((signal) => readAudit(signal), [])
  const resource = usePolling(load, 10000, onSessionExpired)
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [status, setStatus] = useState('')
  const records = resource.data || []
  const unique = (select) => [...new Set(records.map(select).filter((value) => value != null && value !== ''))]
  const visible = records.filter((record) => (!action || record.payload?.action === action) && (!actor || record.actor === actor) && (!status || record.event === status))
  return <div className="page">
    <div className="page-heading"><div><h2>Журнал рішень і відповідей</h2><p className="muted small">API повертає до 100 останніх audit-подій AI review. Схвалення не є підтвердженням виконаної бізнес-операції.</p></div><button onClick={resource.refresh}>Оновити</button></div>
    <div className="filters row">
      <label>Дія<select value={action} onChange={(event) => setAction(event.target.value)}><option value="">Усі дії</option>{unique((record) => record.payload?.action).map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Ініціатор<select value={actor} onChange={(event) => setActor(event.target.value)}><option value="">Усі ініціатори</option>{unique((record) => record.actor).map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Подія / стан<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Усі події</option>{unique((record) => record.event).map((value) => <option key={value} value={value}>{EVENTS[value] || value}</option>)}</select></label>
    </div>
    <ResourceState resource={resource} empty={resource.data && !visible.length}>У поточній вибірці подій за цими фільтрами немає.</ResourceState>
    {resource.data && !resource.error && visible.length > 0 && <>
      <p className="small muted">Показано {visible.length} із {records.length} отриманих подій; не загальна кількість операцій.</p>
      <div className="table-wrap"><table><caption className="table-caption">Аудит AI review</caption><thead><tr><th>Час</th><th>Звернення</th><th>Дія / параметри</th><th>Ініціатор</th><th>Хто схвалив</th><th>Подія / стан</th><th>Результат / undo</th></tr></thead><tbody>
        {visible.map((record) => <tr key={record.id}><td><Timestamp value={record.at} /></td><td>{record.chat != null ? <button className="table-link mono" onClick={() => onOpen(record.chat)}>#{record.chat}</button> : 'Не надано'}</td><td><code>{record.payload?.action || (record.event === 'operator_reply' ? 'operator_reply' : 'Не надано')}</code><pre>{safeJson(record.payload)}</pre></td><td>{record.actor ?? 'Не надано'}</td><td>{record.event === 'review_approved' ? record.actor ?? 'Не надано' : 'Не надано'}</td><td><StatusDot status={statusOf(record.event)}>{EVENTS[record.event] || record.event}</StatusDot></td><td className="muted">Результат виконання й undo API не надає.</td></tr>)}
      </tbody></table></div>
    </>}
    {/* TODO(api): execution log needs action status/result/error, initiator, approval and can_undo/undo_expires_at. */}
  </div>
}
