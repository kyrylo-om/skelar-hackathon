import { useState } from 'react'
import { PRIORITY, SOURCES } from '../api/operator'
import ResourceState from './ResourceState'
import StatusDot from './StatusDot'
import Timestamp from './Timestamp'

export default function Queue({ source, onSource, resource, selectedId, onSelect, user }) {
  const [tab, setTab] = useState('all')
  const [query, setQuery] = useState('')
  const [high, setHigh] = useState(false)
  const list = resource.data || []
  const tabs = source === 'support' ? [['all', 'Усі відкриті'], ['mine', 'Мої']] : [['all', 'Усі'], ['resolved', 'Вирішені']]
  const currentTab = tabs.some(([key]) => key === tab) ? tab : 'all'
  const belongs = (row, target) => target === 'all' || (target === 'mine' ? String(row.assignedOperatorId) === String(user.id) : row.status === 'resolved')
  const visible = list.filter((row) => belongs(row, currentTab))
    .filter((row) => !high || source !== 'review' || row.priority === 'high')
    .filter((row) => [row.id, row.customer, row.subject, row.summary].filter(Boolean).join(' ').toLocaleLowerCase('uk-UA').includes(query.trim().toLocaleLowerCase('uk-UA')))

  return (
    <aside className="inbox-queue" aria-label="Черга звернень">
      <div className="panel-heading"><h2>Черга</h2><button className="ghost" onClick={resource.refresh}>Оновити</button></div>
      <div className="queue-controls stack">
        <label className="stack small">Джерело<select aria-label="Джерело звернень" value={source} onChange={(event) => { onSource(event.target.value); setTab('all'); setHigh(false) }}>
          {Object.entries(SOURCES).map(([key, label]) => <option value={key} key={key} disabled={key === 'support' && !user.is_staff}>{label}{key === 'support' && !user.is_staff ? ' · лише staff' : ''}</option>)}
        </select></label>
        <div className="tabs" aria-label="Фільтр черги">{tabs.map(([key, label]) => <button className="ghost" aria-pressed={currentTab === key} key={key} onClick={() => setTab(key)}>{label}{resource.data && !resource.error ? ` (${list.filter((row) => belongs(row, key)).length})` : ''}</button>)}</div>
        <label className="stack small">Пошук<input placeholder="ID, клієнт або текст" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        {source === 'review' && <label className="row small"><input type="checkbox" checked={high} onChange={(event) => setHigh(event.target.checked)} />Високий пріоритет</label>}
      </div>
      <ResourceState resource={resource} empty={resource.data && !visible.length}>За вибраними фільтрами звернень немає.</ResourceState>
      {!resource.error && visible.map((row) => <button className={`queue-item ${row.priority === 'high' ? 'priority-high' : ''}`} key={row.key} aria-current={String(selectedId) === String(row.id) ? 'true' : undefined} onClick={() => onSelect(row.id)}>
        <span className="row spaced"><strong>{row.customer || 'Клієнт: дані не надано'}</strong>{row.priority && <span className="label">{PRIORITY[row.priority] || row.priority}</span>}</span>
        <span className="queue-subject">{row.subject || row.summary || `Звернення ${row.id}`}</span>
        <span><StatusDot status={row.status} /></span>
        <span className="label">{source === 'support' ? 'Створено' : 'Оновлено'}: <Timestamp value={row.created_at || row.updatedAt} /></span>
        <span className="mono label">#{row.id}</span>
      </button>)}
      <div className="queue-footnote muted small">{source === 'support' ? 'API повертає лише відкриті звернення. Дані клієнта й час початку очікування недоступні.' : 'Це окремий набір AI review. Призначення оператора та час очікування API не надає.'}</div>
    </aside>
  )
}
