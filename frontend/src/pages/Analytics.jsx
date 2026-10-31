const METRICS = [
  ['Частка вирішених без людини', 'Потрібні визначення AI-вирішення, чисельник і знаменник за одним періодом.'],
  ['Кількість звернень', 'Потрібна кількість за період із визначенням, які діалоги враховано.'],
  ['Кількість ескалацій', 'Потрібні визначення ескалації та кількість за період.'],
  ['Кількість заблокованих атак', 'Потрібне серверне визначення атаки; warning і policy-відмова не дорівнюють атаці.'],
]

export default function Analytics() {
  // TODO(api): metrics need period, definition, source, numerator/denominator and issue categories.
  // Neither the open support queue nor the latest 100 audit records is a complete metric source.
  return <div className="page stack">
    <div><h2>Аналітика підтримки</h2><p className="muted small">Інтеграція недоступна: агрегованих метрик у чинному API немає.</p></div>
    <div className="analytics-grid">{METRICS.map(([title, description]) => <section className="metric-card stack" key={title}><h3>{title}</h3><p>Недостатньо даних</p><p className="muted small">{description}</p><dl><dt>Період</dt><dd>Не надано</dd><dt>Джерело</dt><dd>API відсутнє</dd></dl></section>)}</div>
    <section className="stack"><h3>Топ-5 проблем</h3><p className="muted">Недостатньо даних. API не повертає категорій проблем і кількостей за період.</p></section>
  </div>
}
