// Імітація бекенду за нашим контрактом (план дій, trace, undo, черга рев'ювера).
// Коли бекенд буде готовий — замінити тіла функцій на fetch до /api/* (форма даних та сама).
import { useSyncExternalStore } from 'react'

const AUTO_REFUND_LIMIT = 50
const UNDO_MS = 10 * 60 * 1000
const listeners = new Set()
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let actionSeq = 100

const ORDER = { number: '#1042', status: 'shipped', tracking: 'NP 20450912345678', items: 'Худі SupportPilot', total: 420 }

function mkAction(name, params, status, trace) {
  return { id: ++actionSeq, name, params, status, trace, undoUntil: status === 'executed' ? Date.now() + UNDO_MS : null }
}

function init() {
  const pending = mkAction('issue_refund', { order: '#1031', amount: 300 }, 'pending_review', [
    { agent: 'guard', verdict: 'pass', detail: 'Ознак injection немає' },
    { agent: 'triage', verdict: 'ok', detail: 'Інтент: refund · сентимент: angry · пріоритет: high' },
    { agent: 'actor', verdict: 'proposed', detail: 'issue_refund(#1031, 300 грн) — товар прийшов пошкодженим' },
    { agent: 'critic', verdict: 'approve', detail: 'План відповідає запиту клієнта' },
    { agent: 'policy', verdict: 'needs_review', detail: `Сума 300 грн > авто-ліміт ${AUTO_REFUND_LIMIT} грн` },
  ])
  return {
    audit: [],
    security: [],
    tickets: [
      { id: 1, customer: { name: 'Іван Коваль', tier: 'standard' }, status: 'ai_handling', priority: 'normal', sentiment: 'neutral',
        reason: null, summary: '', pending: null, busy: false, live: [], lastTrace: [], actions: [],
        messages: [{ role: 'ai', text: 'Вітаю! Я SupportPilot. Можу дізнатись статус замовлення, змінити підписку, оформити повернення. Чим допомогти?' }] },
      { id: 2, customer: { name: 'Марія Литвин', tier: 'vip' }, status: 'ai_handling', priority: 'normal', sentiment: 'neutral',
        reason: null, summary: '', pending: null, busy: false, live: [], lastTrace: [], actions: [],
        messages: [{ role: 'ai', text: 'Вітаю, Маріє! Чим можу допомогти?' }] },
      { id: 3, customer: { name: 'Олена Шевчук', tier: 'standard' }, status: 'awaiting_human', priority: 'high', sentiment: 'angry',
        reason: `Сума 300 грн перевищує авто-ліміт ${AUTO_REFUND_LIMIT} грн`,
        summary: 'Клієнтка отримала пошкоджений товар із замовлення #1031 і вимагає повернення 300 грн. Фото додано. Тон різкий.',
        pending, busy: false, live: [], lastTrace: pending.trace, actions: [pending],
        messages: [
          { role: 'customer', text: 'Товар прийшов зламаний!! Поверніть мої 300 грн, це неприпустимо.' },
          { role: 'ai', text: 'Мені дуже шкода. Така сума потребує підтвердження спеціаліста — я вже передав запит, відповімо тут же.' },
        ] },
    ],
  }
}

let S = init()
const emit = () => { S = { ...S }; listeners.forEach((f) => f()) }
const subscribe = (f) => { listeners.add(f); return () => listeners.delete(f) }
export const useStore = () => useSyncExternalStore(subscribe, () => S)
const get = (id) => S.tickets.find((t) => t.id === id)

// ---------- «мозок»: розбір намірів (заглушка під pipeline агентів) ----------
function plan(text) {
  const t = text.toLowerCase()
  const angry = /!{2,}|жах|обурл|неприпустим|ненавиджу|безлад|зламан/.test(t)
  if (/ігнору|ignore|system prompt|системн\w+ промпт|чуж\w+ (адрес|замовл|дан)/.test(t)) return { kind: 'attack', angry }
  if (/підписк/.test(t) && /остаточно/.test(t)) return { kind: 'sub_cancel', angry }
  if (/підписк/.test(t) && /(скас|дорого|відмов|призуп)/.test(t)) return { kind: 'sub_pause', angry }
  if (/поверн|рефанд|гроші назад/.test(t)) { const m = t.match(/(\d+)/); return { kind: 'refund', amount: m ? +m[1] : 25, angry } }
  if (/(людин|оператор|менеджер|живо)/.test(t)) return { kind: 'human', angry }
  if (/посилк|де моє|замовлен|трек|доставк/.test(t)) return { kind: 'status', angry }
  return { kind: 'clarify', angry }
}

function steps(p) {
  const base = [{ agent: 'guard', verdict: p.kind === 'attack' ? 'block' : 'pass', detail: p.kind === 'attack' ? 'Виявлено спробу prompt injection / доступу до чужих даних' : 'Ознак injection немає, PII замасковано' }]
  if (p.kind === 'attack') return base
  base.push({ agent: 'triage', verdict: 'ok', detail: `Інтент: ${p.kind} · сентимент: ${p.angry ? 'angry' : 'neutral'} · пріоритет: ${p.angry ? 'high' : 'normal'}` })
  const d = {
    status: ['get_order_status(#1042)', 'Читання, ризик низький', 'allow', 'Власник замовлення збігається з сесією'],
    sub_pause: ['pause_subscription(Premium, 30 днів)', 'Клієнт скаржиться на ціну — спершу пропонуємо паузу замість скасування', 'allow', 'Дія оборотна, ризик низький'],
    sub_cancel: ['cancel_subscription(Premium)', 'Клієнт чітко підтвердив скасування', 'allow', 'Дія оборотна (resume протягом 30 днів)'],
    refund: [`issue_refund(#1042, ${p.amount} грн)`, 'Запит на повернення коштів', p.amount > AUTO_REFUND_LIMIT ? 'needs_review' : 'allow', p.amount > AUTO_REFUND_LIMIT ? `Сума ${p.amount} грн > авто-ліміт ${AUTO_REFUND_LIMIT} грн` : `Сума в межах авто-ліміту ${AUTO_REFUND_LIMIT} грн`],
    human: ['escalate_to_human()', 'Клієнт просить живу людину', 'needs_review', 'Пряме прохання клієнта'],
    clarify: ['ask_clarification()', 'Запит неоднозначний', 'allow', '—'],
  }[p.kind]
  base.push({ agent: 'actor', verdict: 'proposed', detail: d[0] })
  base.push({ agent: 'critic', verdict: 'approve', detail: d[1] })
  base.push({ agent: 'policy', verdict: d[2], detail: d[3] })
  if (d[2] === 'allow') base.push({ agent: 'executor', verdict: 'done', detail: p.kind === 'clarify' ? 'Дій не потрібно' : 'Виконано, undo доступний 10 хв' })
  return base
}

// ---------- публічне API ----------
export async function sendMessage(id, text) {
  const t = get(id)
  if (!text.trim() || t.busy) return
  t.messages.push({ role: 'customer', text }); t.busy = true; t.live = []; emit()
  const p = plan(text); const tr = steps(p)
  for (const s of tr) { await sleep(420); t.live.push(s); emit() }
  await sleep(300)
  if (p.angry) { t.sentiment = 'angry'; t.priority = 'high' }
  const done = (name, params, reply) => {
    const a = mkAction(name, params, 'executed', tr)
    t.actions.push(a); S.audit.unshift({ at: Date.now(), ticket: t.id, text: `${name} ${JSON.stringify(params)}`, by: 'AI' })
    t.messages.push({ role: 'ai', text: reply, actionId: a.id })
  }
  const hold = (name, params, reason, summary, reply) => {
    const a = mkAction(name, params, 'pending_review', tr)
    t.actions.push(a); t.pending = a; t.status = 'awaiting_human'; t.reason = reason; t.summary = summary
    t.messages.push({ role: 'ai', text: reply })
  }
  switch (p.kind) {
    case 'attack':
      S.security.unshift({ at: Date.now(), ticket: t.id, customer: t.customer.name, text, rule: 'Guard: prompt injection / чужі дані' })
      t.messages.push({ role: 'ai', text: 'Я не можу виконати цей запит. Якщо вам потрібна допомога із власним замовленням чи підпискою — опишіть ситуацію, і я допоможу.' }); break
    case 'status':
      done('get_order_status', { order: ORDER.number }, `Замовлення ${ORDER.number} («${ORDER.items}») уже в дорозі. Номер відстеження: ${ORDER.tracking}. Очікуйте доставку протягом 1–2 днів.`); break
    case 'sub_pause':
      done('pause_subscription', { plan: 'Premium', days: 30 }, 'Розумію, що ціна може бути завищеною. Замість скасування я призупинив підписку Premium на 30 днів — гроші не списуватимуться. Якщо все ж хочете скасувати, напишіть «скасуйте остаточно». Дію можна відмінити кнопкою нижче.'); break
    case 'sub_cancel':
      done('cancel_subscription', { plan: 'Premium' }, 'Підписку Premium скасовано. Доступ збережеться до кінця оплаченого періоду. Передумали — відновіть кнопкою нижче протягом 30 днів.'); break
    case 'refund':
      if (p.amount > AUTO_REFUND_LIMIT) hold('issue_refund', { order: ORDER.number, amount: p.amount }, `Сума ${p.amount} грн перевищує авто-ліміт ${AUTO_REFUND_LIMIT} грн`, `Клієнт просить повернення ${p.amount} грн за замовлення ${ORDER.number}.${p.angry ? ' Тон різкий.' : ''}`, `Розумію вас. Повернення ${p.amount} грн потребує підтвердження спеціаліста — я вже передав запит, відповімо тут же.`)
      else done('issue_refund', { order: ORDER.number, amount: p.amount }, `Готово: повернення ${p.amount} грн оформлено на вашу картку (1–3 робочі дні). Якщо це помилка — можна відмінити кнопкою нижче.`)
      break
    case 'human':
      hold('escalate_to_human', {}, 'Клієнт просить живу людину', 'Клієнт просить поспілкуватись зі спеціалістом.', 'Звісно, передаю вас спеціалісту. Він відповість у цьому ж чаті.'); break
    default:
      t.messages.push({ role: 'ai', text: 'Уточніть, будь ласка: йдеться про замовлення чи про підписку, і що саме потрібно зробити?' })
  }
  t.busy = false; t.live = []; t.lastTrace = tr; emit()
}

export function undo(ticketId, actionId) {
  const t = get(ticketId); const a = t.actions.find((x) => x.id === actionId)
  if (!a || a.status !== 'executed' || Date.now() > a.undoUntil) return
  a.status = 'undone'
  S.audit.unshift({ at: Date.now(), ticket: t.id, text: `UNDO ${a.name}`, by: 'Клієнт/оператор' })
  t.messages.push({ role: 'system', text: `Дію «${a.name}» скасовано, стан відновлено.` }); emit()
}

export function approve(ticketId, amount) {
  const t = get(ticketId); const a = t.pending; if (!a) return
  if (a.params.amount !== undefined && amount) a.params.amount = +amount
  a.status = 'executed'; a.undoUntil = Date.now() + UNDO_MS
  a.trace = [...a.trace, { agent: 'human', verdict: 'approve', detail: 'Схвалено рев\'ювером' }, { agent: 'policy', verdict: 'allow', detail: 'Повторна перевірка після схвалення пройдена' }, { agent: 'executor', verdict: 'done', detail: 'Виконано, undo доступний 10 хв' }]
  t.pending = null; t.status = 'resolved'; t.lastTrace = a.trace
  S.audit.unshift({ at: Date.now(), ticket: t.id, text: `${a.name} ${JSON.stringify(a.params)}`, by: 'Рев\'ювер' })
  t.messages.push({ role: 'operator', text: `Запит схвалено${a.params.amount ? `: повернення ${a.params.amount} грн оформлено` : ''}. Дякуємо за терпіння!`, actionId: a.id }); emit()
}

export function reject(ticketId, why) {
  const t = get(ticketId); const a = t.pending; if (!a) return
  a.status = 'rejected'; t.pending = null; t.status = 'resolved'
  a.trace = [...a.trace, { agent: 'human', verdict: 'reject', detail: why || 'Відхилено рев\'ювером' }]; t.lastTrace = a.trace
  S.audit.unshift({ at: Date.now(), ticket: t.id, text: `REJECT ${a.name}`, by: 'Рев\'ювер' })
  t.messages.push({ role: 'operator', text: `На жаль, цей запит не може бути виконаний${why ? `: ${why}` : ''}. Готовий запропонувати альтернативу — напишіть, що вам підійде.` }); emit()
}

export function operatorReply(ticketId, text) {
  const t = get(ticketId); if (!text.trim()) return
  t.messages.push({ role: 'operator', text }); if (t.status === 'awaiting_human') t.status = 'in_review'; emit()
}

export function resolve(ticketId) { const t = get(ticketId); t.status = 'resolved'; emit() }

export function draftReply(t) {
  const a = t.pending
  if (a?.name === 'issue_refund') return `Добрий день, ${t.customer.name.split(' ')[0]}! Перепрошуємо за незручності. Ми оформили повернення ${a.params.amount} грн — кошти надійдуть протягом 1–3 робочих днів.`
  return `Добрий день, ${t.customer.name.split(' ')[0]}! Дякуємо за звернення, зараз усе перевірю і повернусь із рішенням.`
}

export function metrics(s) {
  const all = s.tickets.flatMap((t) => t.actions)
  const aiDone = all.filter((a) => a.status === 'executed' && !a.trace.some((x) => x.agent === 'human')).length
  const human = all.filter((a) => a.trace.some((x) => x.agent === 'human')).length
  return { aiDone, human, pending: s.tickets.filter((t) => t.pending).length, attacks: s.security.length, auto: aiDone + human ? Math.round((aiDone / (aiDone + human + s.tickets.filter((t) => t.pending).length)) * 100) : 0 }
}
