import { useCallback, useRef, useState } from 'react'
import { api, ApiError } from './api/client'
import { describeError, readDetail, readQueue } from './api/operator'
import usePolling from './api/usePolling'
import Queue from './components/Queue'
import Conversation from './components/Conversation'
import DecisionPanel from './components/DecisionPanel'
import Approvals from './pages/Approvals'
import ActionsLog, { ConversationAudit } from './pages/ActionsLog'
import ApiCalls from './pages/ApiCalls'
import Security from './pages/Security'
import Analytics from './pages/Analytics'
import Integration from './pages/Integration'
import './styles/inbox.css'

export default function Operator({ user, page = 'inbox', onNavigate, onSessionExpired }) {
  const [source, setSource] = useState(user.is_staff ? 'support' : 'review')
  const [selections, setSelections] = useState({})
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [uncertain, setUncertain] = useState({})
  const [panel, setPanel] = useState('queue')
  const lock = useRef(false)
  const messageAttempts = useRef({})
  const unknownRequests = useRef({})
  const loadQueue = useCallback(async (signal) => {
    const rows = await readQueue(source, signal)
    if (!signal.aborted && rows.length) {
      setSelections((previous) => previous[source] != null ? previous : { ...previous, [source]: rows[0].id })
    }
    return rows
  }, [source])
  const queue = usePolling(loadQueue, 10000, onSessionExpired, page === 'inbox')
  const activeId = selections[source] ?? queue.data?.[0]?.id ?? null
  const activeKey = activeId == null ? null : `${source}:${activeId}`
  const loadDetail = useCallback((signal) => activeId == null ? Promise.resolve(null) : readDetail(source, activeId, signal), [source, activeId])
  const detail = usePolling(loadDetail, 5000, onSessionExpired, activeId != null && page === 'inbox')
  const row = queue.error ? null : queue.data?.find((item) => String(item.id) === String(activeId))

  const reconcile = async () => {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    const key = activeKey
    const pending = uncertain[key]
    try {
      const [snapshot, rows] = await Promise.all([detail.refresh(), queue.refresh()])
      if (snapshot?.key !== key || !Array.isArray(rows)) {
        setNotice({ key, kind: 'error', text: 'Не вдалося звірити стан. Повтор операції залишається заблокованим.' })
        return
      }
      const freshRow = rows.find((item) => item.key === key)
      const knownResult = (pending?.kind === 'claim' && snapshot.status === 'operator' && String(freshRow?.assignedOperatorId) === String(user.id))
        || (pending?.kind === 'resolve' && snapshot.status === 'resolved')
        || (pending?.kind === 'decision' && snapshot.review?.id === pending.reviewId && ['approved', 'rejected'].includes(snapshot.review.status))
      if (knownResult) {
        setUncertain((previous) => ({ ...previous, [key]: null }))
        delete unknownRequests.current[key]
        setNotice({ key, kind: 'success', text: 'Серверний стан звірено. Актуальний результат показано в діалозі.' })
      } else {
        const retryable = source === 'support' || pending?.kind === 'decision'
        setUncertain((previous) => ({ ...previous, [key]: { ...previous[key], checked: retryable } }))
        setNotice({ key, kind: 'warning', text: retryable ? 'Стан звірено. Автоматичного повтору немає. За потреби повторіть той самий запит з незмінним ID.' : 'Стан звірено. API відповіді AI review не підтримує ідемпотентність або перевірку результату за ID; автоматичний і ручний повтор запиту заблоковані. Потрібна перевірка командою.' })
      }
    } finally { lock.current = false; setBusy(false) }
  }

  const run = async (kind, request, afterSuccess, replay = false) => {
    if (lock.current || (uncertain[activeKey] && !replay)) return
    lock.current = true
    setBusy(true)
    const operationKey = activeKey
    let mutationSent = kind !== 'decision'
    setNotice(null)
    try {
      await request(AbortSignal.timeout(20000), () => { mutationSent = true })
      afterSuccess?.()
      setUncertain((previous) => ({ ...previous, [operationKey]: null }))
      delete unknownRequests.current[operationKey]
      setNotice({ key: operationKey, kind: 'success', text: kind === 'reply' ? 'Відповідь збережено сервером.' : kind === 'claim' ? 'Звернення прийнято в роботу.' : kind === 'decision' ? 'Рішення review збережено сервером. Перевірте оновлений стан.' : 'Звернення закрито.' })
    } catch (error) {
      const failure = await describeError(error, onSessionExpired)
      const unknown = mutationSent && (!(error instanceof ApiError) || error.status >= 500)
      if (unknown) {
        unknownRequests.current[operationKey] = { kind, request, afterSuccess }
        setUncertain((previous) => ({ ...previous, [operationKey]: { kind, checked: false, reviewId: detail.data?.review?.id } }))
      } else if (replay) setUncertain((previous) => ({ ...previous, [operationKey]: null }))
      setNotice({ key: operationKey, kind: failure.kind, text: error instanceof ApiError && error.status === 409 ? 'Стан звернення змінився. Дані оновлено; перевірте призначення й повторіть доступну дію.' : `${failure.message}${unknown ? ' Результат операції невідомий; повтор заблоковано до звірки.' : ''}` })
    } finally {
      await Promise.all([detail.refresh(), queue.refresh()])
      lock.current = false
      setBusy(false)
    }
  }

  const send = () => {
    const text = (drafts[activeKey] || '').trim()
    if (!text) return
    let attempt = messageAttempts.current[activeKey]
    if (!attempt || attempt.text !== text) {
      attempt = { text, client_message_id: crypto.randomUUID() }
      messageAttempts.current[activeKey] = attempt
    }
    const key = activeKey
    const path = source === 'support' ? `/operator/conversations/${activeId}/messages/` : `/review/chats/${activeId}/reply/`
    const body = source === 'support' ? attempt : { text }
    void run('reply', (signal) => api.post(path, body, { signal }), () => {
      setDrafts((previous) => ({ ...previous, [key]: '' }))
      delete messageAttempts.current[key]
    })
  }

  const decide = (decision, note) => {
    const proposal = detail.data?.review
    if (source !== 'review' || proposal?.status !== 'pending' || (decision === 'rejected' && !note.trim())) return
    const sameProposal = (review) => JSON.stringify([review?.id, review?.action, review?.params, review?.risk, review?.reason])
    void run('decision', async (signal, markSent) => {
      const fresh = await detail.refresh()
      if (!fresh || fresh.key !== activeKey) throw new Error('Не вдалося перечитати пропозицію. Рішення не надіслано.')
      if (fresh.review?.status !== 'pending' || sameProposal(fresh.review) !== sameProposal(proposal)) {
        throw new ApiError(409, { detail: 'Пропозиція змінилася. Перегляньте актуальні параметри.' })
      }
      markSent()
      return api.post(`/review/reviews/${proposal.id}/decision/`, { decision, note: note.trim() }, { signal })
    })
  }

  const openReview = (id) => {
    setSource('review')
    setSelections((previous) => ({ ...previous, review: id }))
    setPanel('decision')
    onNavigate?.('inbox')
  }

  if (page === 'approvals') return <Approvals onOpen={openReview} onSessionExpired={onSessionExpired} />
  if (page === 'actions') return <ActionsLog onOpen={openReview} onSessionExpired={onSessionExpired} />
  if (page === 'calls') return <ApiCalls />
  if (page === 'security') return <Security />
  if (page === 'analytics') return <Analytics />
  if (page === 'integration') return <Integration />

  return <div className="inbox-workspace">
    <div className="source-notice small muted">Операторські звернення та AI review — окремі серверні діалоги без спільного ID.</div>
    {(notice?.key === activeKey || uncertain[activeKey]) && <div className={`notice ${notice?.key === activeKey ? notice.kind : 'warning'}`} role="status">
      {notice?.key === activeKey ? notice.text : 'Результат попередньої операції невідомий. Звірте стан із сервером.'}
      {uncertain[activeKey] && <div className="row">
        <button className="ghost" disabled={busy} onClick={reconcile}>Звірити стан</button>
        {uncertain[activeKey].checked && <button disabled={busy} onClick={() => {
          const pending = unknownRequests.current[activeKey]
          if (pending) void run(pending.kind, pending.request, pending.afterSuccess, true)
        }}>Повторити з тим самим ID</button>}
      </div>}
    </div>}
    <nav className="mobile-panels tabs" aria-label="Панелі звернення">{[['queue', 'Черга'], ['conversation', 'Звернення'], ['decision', 'Рішення']].map(([key, title]) => <button className="ghost" key={key} aria-pressed={panel === key} onClick={() => setPanel(key)}>{title}</button>)}</nav>
    <div className="inbox-columns" data-panel={panel}>
      <Queue source={source} onSource={setSource} resource={queue} selectedId={activeId} user={user} onSelect={(id) => { setSelections((previous) => ({ ...previous, [source]: id })); setPanel('conversation') }} />
      <Conversation resource={detail} row={row} user={user} draft={drafts[activeKey] || ''} onDraft={(text) => setDrafts((previous) => ({ ...previous, [activeKey]: text }))} onSend={send} busy={busy} uncertain={uncertain[activeKey]}
        onClaim={() => run('claim', (signal) => api.post(`/operator/conversations/${activeId}/claim/`, {}, { signal }))}
        onResolve={() => run('resolve', (signal) => api.post(`/operator/conversations/${activeId}/resolve/`, {}, { signal }))} />
      <DecisionPanel key={activeKey} resource={detail} busy={busy} uncertain={uncertain[activeKey]} onDecide={decide} history={source === 'review' && activeId != null ? <ConversationAudit chatId={activeId} onSessionExpired={onSessionExpired} /> : null} />
    </div>
  </div>
}
