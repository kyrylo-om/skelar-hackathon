import EmptyState from '../components/EmptyState'

export default function Integration() {
  // TODO(api): read-only integration context needs tenant/product, connection status, a masked
  // key identifier, a server-sanitized manifest, available transports/tools and last successful call.
  return <div className="page stack">
    <h2>Підключений продукт</h2>
    <EmptyState kind="unavailable" title="Контекст інтеграції недоступний">Backend не має endpoint для tenant/product, стану підключення, маскованого ID ключа, manifest, інструментів і останнього успішного виклику. Назви й налаштування не підставляються з локальних прикладів.</EmptyState>
    <section className="stack"><h3>Інструкція підключення</h3><p className="muted small">Це загальні інструкції, а не виконані кроки. Налаштування через цю панель недоступне.</p>
      <ol className="integration-steps"><li>Передайте команді інтеграції опис продукту, підтримуваних операцій та правил доступу.</li><li>Налаштуйте доступ і manifest на сервері продукту. Зберігайте ключі та секрети на сервері.</li><li>Перевірте дозволений виклик і його серверний результат; після появи API стан буде доступний у панелі.</li></ol>
    </section>
  </div>
}
