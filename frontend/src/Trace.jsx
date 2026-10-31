const NAMES = { guard: 'Guard', triage: 'Triage', actor: 'Actor', critic: 'Critic', policy: 'Policy Engine', executor: 'Executor', human: 'Людина', qa: 'QA' }
const tone = (v) => (['pass', 'ok', 'approve', 'allow', 'done', 'proposed'].includes(v) ? 'good' : ['block', 'reject', 'deny'].includes(v) ? 'bad' : 'warn')

export default function Trace({ steps, compact }) {
  if (!steps?.length) return <div className="muted">Ще немає даних</div>
  return (
    <ol className={'trace' + (compact ? ' compact' : '')}>
      {steps.map((s, i) => (
        <li key={i} className={'tone-' + tone(s.verdict)}>
          <span className="dot" />
          <div>
            <b>{NAMES[s.agent] || s.agent}</b> <span className="badge">{s.verdict}</span>
            <div className="detail">{s.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  )
}
