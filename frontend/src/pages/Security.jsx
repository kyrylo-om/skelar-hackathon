import EmptyState from '../components/EmptyState'

export default function Security() {
  // TODO(api): expose SecurityEvent through a staff endpoint with redacted excerpts, severity,
  // rule, component, verdict and a conversation link. Guard fallback is not necessarily an attack.
  return <div className="page"><h2>Події безпеки</h2><EmptyState kind="unavailable" title="Security events недоступні">У backend є модель SecurityEvent, але немає endpoint для панелі. Правило, безпечний фрагмент, час, компонент і вердикт недоступні. Policy-відмови не зараховуються до атак.</EmptyState><p className="muted small pad">Лічильники блокувань і попереджень не обчислюються без серверних визначень та джерела подій.</p></div>
}
