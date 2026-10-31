import { useState } from 'react'
import { formatMoney, safeJson } from '../api/operator'
import EmptyState from './EmptyState'
import ResourceState from './ResourceState'
import StatusDot from './StatusDot'
import TraceDetailed from './TraceDetailed'

export default function DecisionPanel({ resource, busy, uncertain, onDecide, history }) {
  const [note, setNote] = useState('')
  const detail = resource.error ? null : resource.data
  const review = detail?.review
  const pending = review?.status === 'pending'
  // Current backend has no review expiry or version. Refresh the immutable proposal before POST;
  // backend locks the review and rejects a second decision. Never edit params locally.
  return <aside className="inbox-decision" aria-label="Рішення AI">
    <h2 className="panel-heading">Рішення AI</h2>
    <ResourceState resource={resource} />
    {!resource.loading && !resource.error && !detail && <EmptyState title="Оберіть звернення" />}
    {detail && <>
      <section className="decision-section stack"><h3>AI-підсумок</h3>{detail.summary ? <p className="preserve">{detail.summary}</p> : <EmptyState title="Підсумок не надано" />}</section>
      <section className="decision-section stack"><h3>Передача людині</h3>{review?.reason ? <p className="preserve">{review.reason}</p> : <p className="muted small">Окрему причину передачі API не надає.</p>}</section>
      <section className="decision-section stack"><h3>Пропозиція дії</h3>
        {detail.source !== 'review' ? <EmptyState kind="unavailable" title="Human review недоступний">Цей API не надає пропозиції для схвалення оператором.</EmptyState> : !review ? <EmptyState title="Пропозиції немає">API не повернув human review для цього діалогу.</EmptyState> : <>
          <div className="row spaced"><code>{review.action}</code><StatusDot status={review.status} /></div>
          <dl><dt>Рішення</dt><dd className="mono">#{review.id}</dd><dt>Ризик</dt><dd>{{ low: 'Низький', medium: 'Середній', high: 'Високий' }[review.risk] || review.risk}</dd><dt>Сума / валюта</dt><dd>{formatMoney(review.params)}</dd><dt>Хто вирішив</dt><dd>{review.decidedBy || 'Не надано'}</dd></dl>
          <pre aria-label="Параметри рішення">{safeJson(review.params)}</pre>
          <p className="muted small">Параметри незмінні. Наслідки, строк дії, версію та окремий результат виконання API не повертає. Статус review не підтверджує зміну білінгу.</p>
          {review.note && <p className="preserve small">Коментар: {review.note}</p>}
          {pending && <>
            <label className="stack small" htmlFor="decision-note">Причина відхилення / коментар<textarea id="decision-note" rows={3} maxLength={500} value={note} disabled={busy || uncertain} onChange={(event) => setNote(event.target.value)} /></label>
            <div className="row"><button disabled={busy || uncertain} onClick={() => onDecide('approved', note)}>Схвалити</button><button className="danger" disabled={busy || uncertain || !note.trim()} onClick={() => onDecide('rejected', note)}>Відхилити</button></div>
            <p className="small muted">Відхилення потребує причини. Рішення застосовується до серверного review #{review.id}; підтвердження клієнта — окрема дія.</p>
          </>}
        </>}
      </section>
      <section className="decision-section stack"><h3>TraceDetailed</h3><TraceDetailed key={detail.key} available={detail.source === 'review'} steps={detail.trace} /></section>
      <section className="decision-section stack"><h3>Історія операцій</h3>{history || <EmptyState kind="unavailable" title="Журнал недоступний">Для цього джерела немає API журналу операцій.</EmptyState>}</section>
    </>}
  </aside>
}
