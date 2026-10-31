const PAGES = {
  inbox: 'Вхідні',
  approvals: 'Схвалення',
  actions: 'Журнал дій',
  calls: 'API calls',
  security: 'Безпека',
  analytics: 'Аналітика',
  integration: 'Інтеграція',
}

const PAGE_ICONS = {
  inbox: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  ),
  approvals: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  ),
  actions: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" x2="8" y1="13" y2="13" />
      <line x1="16" x2="8" y1="17" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  ),
  calls: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" x2="20" y1="19" y2="19" />
    </svg>
  ),
  security: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
    </svg>
  ),
  analytics: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 3v18h18" />
      <path d="m19 9-5 5-4-4-3 3" />
    </svg>
  ),
  integration: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2v4" />
      <path d="m6.8 15-3.5 2" />
      <path d="m20.7 17-3.5-2" />
      <path d="M9 22v-4h6v4" />
      <rect width="12" height="12" x="6" y="6" rx="2" />
    </svg>
  ),
}

export default function AppShell({ page, onNavigate, user, onLogout, busy, children }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-wrapper">
          <div className="brand-icon-box" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </div>
          <div>
            <div className="brand">SupportPilot</div>
            <p className="sidebar-caption">Панель команди підтримки</p>
          </div>
        </div>
        <nav aria-label="Основна навігація">
          {Object.entries(PAGES).map(([key, title]) => (
            <button
              key={key}
              aria-current={page === key ? 'page' : undefined}
              onClick={() => onNavigate(key)}
            >
              {PAGE_ICONS[key]}
              <span>{title}</span>
            </button>
          ))}
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <h1>{PAGES[page]}</h1>
          <div className="row">
            {user ? (
              <div className="topbar-user">
                <div className="user-badge">
                  <span className="user-avatar-initial">{(user.username || 'O')[0].toUpperCase()}</span>
                  <span>{user.username}</span>
                  {user.is_staff && <span className="status neutral" style={{ fontSize: '10px', padding: '1px 6px' }}>Staff</span>}
                </div>
                <button disabled={busy} onClick={onLogout} className="ghost" style={{ border: '1px solid var(--control-border)' }}>
                  {busy ? 'Вихід…' : 'Вийти'}
                </button>
              </div>
            ) : (
              <span className="muted">Команда підтримки</span>
            )}
          </div>
        </header>
        <main id="main-content">{children}</main>
      </div>
    </div>
  )
}
