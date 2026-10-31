const PAGES = {
  inbox: 'Вхідні', approvals: 'Схвалення', actions: 'Журнал дій', calls: 'API calls',
  security: 'Безпека', analytics: 'Аналітика', integration: 'Інтеграція',
}

export default function AppShell({ page, onNavigate, user, onLogout, busy, children }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">SupportPilot</div>
        <p className="sidebar-caption label">Панель команди підтримки</p>
        <nav aria-label="Основна навігація">
          {Object.entries(PAGES).map(([key, title]) => <button key={key} aria-current={page === key ? 'page' : undefined} onClick={() => onNavigate(key)}>{title}</button>)}
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <h1>{PAGES[page]}</h1>
          <div className="row"><span className="muted">{user ? user.username : 'Команда підтримки'}</span>{user && <button disabled={busy} onClick={onLogout}>{busy ? 'Вихід…' : 'Вийти'}</button>}</div>
        </header>
        <main id="main-content">{children}</main>
      </div>
    </div>
  )
}
