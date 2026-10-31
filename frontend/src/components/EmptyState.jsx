export default function EmptyState({ kind = 'empty', title, children, onRetry }) {
  const isAlert = kind === 'error' || kind === 'forbidden'

  return (
    <div className={`state ${kind}`} role={isAlert ? 'alert' : 'status'}>
      <div
        style={{
          width: '42px',
          height: '42px',
          borderRadius: '50%',
          background: isAlert ? 'var(--danger-border)' : 'var(--neutral-bg)',
          color: isAlert ? 'var(--danger-text)' : 'var(--text-3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '6px',
        }}
        aria-hidden="true"
      >
        {isAlert ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" x2="12" y1="8" y2="12" />
            <line x1="12" x2="12.01" y1="16" y2="16" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
            <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
          </svg>
        )}
      </div>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {onRetry && (
        <button
          className="ghost"
          style={{ border: '1px solid var(--control-border)', marginTop: '8px' }}
          onClick={onRetry}
        >
          Спробувати ще раз
        </button>
      )}
    </div>
  )
}

export function Skeleton({ rows = 5, label = 'Завантаження даних' }) {
  return (
    <div className="skeleton-list" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton" key={i} aria-hidden="true" />
      ))}
    </div>
  )
}
