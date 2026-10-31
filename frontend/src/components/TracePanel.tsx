import type { TraceStep } from '../types'

const agentLabel: Record<TraceStep['agent'], string> = {
  guard: 'Guard',
  triage: 'Triage',
  actor: 'Actor',
  critic: 'Critic',
  policy: 'Policy',
  executor: 'Executor',
  qa: 'QA',
}

const mark = { pass: '✓', block: '✗', info: '•' }

export function TracePanel({ trace }: { trace: TraceStep[] }) {
  return (
    <aside className="panel trace">
      <h2>Кроки агентів</h2>
      <ol>
        {trace.map((step, i) => (
          <li key={i} className={step.verdict}>
            <span className="mark" aria-hidden="true">
              {mark[step.verdict]}
            </span>
            <div>
              <strong>{agentLabel[step.agent]}</strong>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  )
}
