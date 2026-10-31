export default function EmptyState({ kind = 'empty', title, children, onRetry }) {
  return (
    <div className={`state ${kind}`} role={kind === 'error' || kind === 'forbidden' ? 'alert' : 'status'}>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {onRetry && <button className="ghost" onClick={onRetry}>Спробувати ще раз</button>}
    </div>
  )
}

export function Skeleton({ rows = 5, label = 'Завантаження даних' }) {
  return <div className="skeleton-list" role="status" aria-label={label}>{Array.from({ length: rows }, (_, i) => <div className="skeleton" key={i} aria-hidden="true" />)}</div>
}
