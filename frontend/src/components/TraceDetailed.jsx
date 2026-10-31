import { useMemo, useState } from 'react'
import EmptyState from './EmptyState'
import './TraceDetailed.css'

const NAMES = { guard: 'Guard', triage: 'Triage', actor: 'Actor', critic: 'Critic', policy: 'Policy', human: 'Human review', executor: 'Executor', qa: 'QA' }
const GROUPS = { pass: 'Пройдено', warn: 'Попередження', fail: 'Помилки', skip: 'Пропущено', na: 'Не застосовується', unknown: 'Інформація / інше' }
const SYMBOLS = { pass: '✓', fail: '✕', warn: 'WARN', skip: '–', na: '–', unknown: '·' }

// Current TraceStepSerializer exposes only agent/verdict/detail. No check list or duration.
function adaptTrace(steps) {
  const occurrences = {}
  return (Array.isArray(steps) ? steps : []).map((step) => {
    const stage = step.agent
    occurrences[stage] = (occurrences[stage] || 0) + 1
    const verdict = step.verdict
    const status = ['pass', 'approve', 'allow', 'done'].includes(verdict) ? 'pass'
      : ['block', 'reject', 'deny', 'failed', 'fail'].includes(verdict) ? 'fail'
        : ['needs_review', 'needs_human', 'warn'].includes(verdict) ? 'warn'
          : verdict === 'skip' ? 'skip' : verdict === 'na' ? 'na' : 'unknown'
    return { id: `${stage}:${occurrences[stage]}`, name: NAMES[stage] || stage, stage, verdict, status, detail: step.detail }
  })
}

export default function TraceDetailed({ steps, available = true }) {
  const trace = useMemo(() => adaptTrace(steps), [steps])
  const [expanded, setExpanded] = useState({})
  if (!available) return <EmptyState kind="unavailable" title="Trace недоступний">Операторський API не повертає етапи обробки.</EmptyState>
  if (!trace.length) return <EmptyState title="Записів trace немає">Відсутня інформація про виконані етапи. Це не означає успішну перевірку.</EmptyState>
  const counts = Object.fromEntries(Object.keys(GROUPS).map((group) => [group, trace.filter((step) => step.status === group).length]))

  return <div className="stack">
    <p className="small muted">Записи trace, включно з повторними етапами. Детальні checks і тривалість API не надає.</p>
    <dl className="trace-counts">{Object.entries(GROUPS).map(([group, name]) => <div key={group}><dt>{name}</dt><dd>{counts[group]}</dd></div>)}</dl>
    <ol className="trace-detailed">
      {trace.map((step) => {
        const open = expanded[step.id] ?? ['fail', 'warn'].includes(step.status)
        return <li key={step.id} className={`trace-entry trace-${step.status}`}>
          <button className="trace-toggle" aria-expanded={open} onClick={() => setExpanded((previous) => ({ ...previous, [step.id]: !open }))}>
            <span className="trace-name">{step.name}</span><span className="trace-verdict">{SYMBOLS[step.status]} {step.verdict}</span>
          </button>
          {open && <div className="trace-detail"><p className="preserve">{step.detail || 'Пояснення не надано.'}</p>{step.stage === 'policy' && <p className="muted small">Детерміновані правила, без LLM.</p>}</div>}
        </li>
      })}
    </ol>
  </div>
}
