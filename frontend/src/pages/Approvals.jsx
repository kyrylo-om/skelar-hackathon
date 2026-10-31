import { useCallback } from 'react'
import { formatMoney, readApprovals, safeJson } from '../api/operator'
import usePolling from '../api/usePolling'
import ResourceState from '../components/ResourceState'
import StatusDot from '../components/StatusDot'
import Timestamp from '../components/Timestamp'

export default function Approvals({ onOpen, onSessionExpired }) {
  const load = useCallback((signal) => readApprovals(signal), [])
  const resource = usePolling(load, 10000, onSessionExpired)
  return <div className="page">
    <div className="page-heading"><div><h2>Рішення, що чекають оператора</h2><p className="muted small">Лише серверні review зі статусом pending. Підтвердження клієнта сюди не входять.</p></div><button onClick={resource.refresh}>Оновити</button></div>
    <div className="notice small">API не повертає час створення review, початок очікування, expiry або версію. Показаний час — останнє оновлення діалогу. Черга формується з деталей звернень needs_review.</div>
    <ResourceState resource={resource} empty={resource.data?.length === 0}>Сервер не повернув рішень, що потребують human review.</ResourceState>
    {resource.data && !resource.error && resource.data.length > 0 && <>
      <p className="small muted">Отримано рішень: {resource.data.length}</p>
      <div className="table-wrap"><table><caption className="table-caption">Черга human review · AI review</caption><thead><tr><th>Оновлено</th><th>Звернення / клієнт</th><th>Дія / параметри</th><th>Сума / валюта</th><th>Причина</th><th>Стан / очікування</th></tr></thead><tbody>
        {resource.data.map((chat) => <tr key={chat.review.id}><td><Timestamp value={chat.updatedAt} /></td><td><button className="table-link mono" onClick={() => onOpen(chat.id)}>#{chat.id}</button><p>{chat.customer}</p></td><td><code>{chat.review.action}</code><pre>{safeJson(chat.review.params)}</pre></td><td>{formatMoney(chat.review.params)}</td><td className="preserve">{chat.review.reason}</td><td><StatusDot status={chat.review.status} /><p className="muted small">Час очікування не надано</p></td></tr>)}
      </tbody></table></div>
    </>}
  </div>
}
