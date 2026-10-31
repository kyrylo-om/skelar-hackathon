import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'

// Synthetic API fixtures are confined to tests. The product has no mock data path.
const json = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status })
type Handler = (init?: RequestInit) => Response | Promise<Response>
type Routes = Record<string, Handler>
const profile = { id: '7', username: 'operator', is_staff: true }
const conversationId = '00000000-0000-4000-8000-000000000001'
const base = `/operator/conversations/${conversationId}`
const queueItem = { id: conversationId, status: 'waiting_operator', summary: 'Потрібна допомога', version: 1, assigned_operator_id: null, created_at: '2026-10-31T10:00:00Z' }
const detail = { id: conversationId, status: 'waiting_operator', version: 1, summary: 'Потрібна допомога', pending_action: null, messages: [{ id: 'message-1', sender: 'customer', text: 'Перевірте мій платіж', created_at: '2026-10-31T10:00:00Z' }] }
const chat = { id: 11, customer: 'Клієнт для тесту', subject: 'Запит підтримки', status: 'needs_review', priority: 'high', updatedAt: '2026-10-31T10:00:00Z', summary: 'Підсумок із сервера' }
const chatDetail = { ...chat, messages: [{ id: 1, role: 'customer', text: 'Потрібна консультація', at: '2026-10-31T10:00:00Z' }], trace: [{ agent: 'policy', verdict: 'needs_review', detail: 'Потрібен оператор' }], review: { id: 19, action: 'escalate_to_human', params: { reason: 'Запит клієнта' }, risk: 'low', reason: 'Клієнт просить оператора', status: 'pending', note: '', decidedBy: null } }

function stubApi(extra: Routes = {}) {
  const routes: Routes = {
    'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }),
    'GET /me/': () => json(profile),
    'GET /operator/conversations/': () => json({ results: [queueItem] }),
    [`GET ${base}/`]: () => json(detail),
    'GET /review/chats/': () => json([chat]),
    'GET /review/chats/11/': () => json(chatDetail),
    'GET /review/audit/': () => json([]),
    ...extra,
  }
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const path = String(url).replace(/^\/api/, '')
    const handler = routes[`${init?.method ?? 'GET'} ${path}`]
    return Promise.resolve(handler ? handler(init) : json({ error: { code: 'not_found', message: 'Не знайдено' } }, 404))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function openReview() {
  fireEvent.change(await screen.findByRole('combobox', { name: 'Джерело звернень' }), { target: { value: 'review' } })
  await screen.findByText('Потрібна консультація')
}

beforeEach(() => {
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
})
afterEach(() => { vi.unstubAllGlobals() })

test('the app offers operator login and never mounts the customer cabinet', async () => {
  stubApi({ 'GET /me/': () => json({ error: { code: 'not_authenticated', message: 'Потрібен вхід' } }, 403) })
  render(<App />)
  expect(await screen.findByText('Вхід для менеджерів')).toBeInTheDocument()
  expect(screen.queryByText('Вхід для клієнтів')).not.toBeInTheDocument()
  expect(screen.queryByPlaceholderText('Напишіть повідомлення…')).not.toBeInTheDocument()
})

test('claim is required before a support reply; a second click cannot post twice', async () => {
  let claimed = false
  let finish: (value: Response) => void = () => {}
  const claim = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve }))
  stubApi({
    'GET /operator/conversations/': () => json({ results: [{ ...queueItem, status: claimed ? 'operator' : 'waiting_operator', assigned_operator_id: claimed ? 7 : null }] }),
    [`GET ${base}/`]: () => json({ ...detail, status: claimed ? 'operator' : 'waiting_operator' }),
    [`POST ${base}/claim/`]: claim,
  })
  render(<App />)
  const button = await screen.findByRole('button', { name: 'Взяти в роботу' })
  expect(screen.getByLabelText('Відповідь клієнту')).toBeDisabled()
  fireEvent.click(button)
  fireEvent.click(button)
  expect(claim).toHaveBeenCalledTimes(1)
  claimed = true
  finish(json({ ...detail, status: 'operator' }))
  await waitFor(() => expect(screen.getByLabelText('Відповідь клієнту')).toBeEnabled())
})

test('support reply sends a stable client ID and resolve refreshes persisted state', async () => {
  let current = { ...detail, status: 'operator' }
  const reply = vi.fn((init?: RequestInit) => {
    const body = JSON.parse(init!.body as string)
    const message = { id: 'message-2', sender: 'operator', text: body.text, created_at: '2026-10-31T10:05:00Z' }
    current = { ...current, messages: [...current.messages, message] }
    return json(message, 201)
  })
  const resolve = vi.fn(() => { current = { ...current, status: 'resolved' }; return json(current) })
  stubApi({
    'GET /operator/conversations/': () => json({ results: current.status === 'resolved' ? [] : [{ ...queueItem, status: 'operator', assigned_operator_id: 7 }] }),
    [`GET ${base}/`]: () => json(current), [`POST ${base}/messages/`]: reply, [`POST ${base}/resolve/`]: resolve,
  })
  render(<App />)
  const input = await screen.findByLabelText('Відповідь клієнту')
  fireEvent.change(input, { target: { value: 'Перевіряю оплату' } })
  fireEvent.click(screen.getByRole('button', { name: 'Надіслати' }))
  expect(await screen.findByText('Перевіряю оплату')).toBeInTheDocument()
  expect(JSON.parse(reply.mock.calls[0][0]!.body as string)).toEqual({ text: 'Перевіряю оплату', client_message_id: expect.any(String) })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Закрити звернення' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Закрити звернення' }))
  expect((await screen.findAllByText('Звернення закрито.')).length).toBeGreaterThan(0)
  expect(resolve).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText('Відповідь клієнту')).toBeDisabled()
})

test('claim conflict refreshes assignment and disables replying', async () => {
  let taken = false
  const claim = vi.fn(() => { taken = true; return json({ error: { code: 'state_conflict', message: 'Зайнято' } }, 409) })
  stubApi({
    'GET /operator/conversations/': () => json({ results: [{ ...queueItem, status: taken ? 'operator' : 'waiting_operator', assigned_operator_id: taken ? 8 : null }] }),
    [`GET ${base}/`]: () => taken ? json({ error: { code: 'permission_denied', message: 'Призначено іншому оператору' } }, 403) : json(detail),
    [`POST ${base}/claim/`]: claim,
  })
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Взяти в роботу' }))
  expect(await screen.findByText(/Стан звернення змінився/)).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Надіслати' })).not.toBeInTheDocument())
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
})

test('a permission 403 retains the valid session and a 404 is never an empty queue', async () => {
  stubApi({ 'GET /operator/conversations/': () => json({ error: { code: 'permission_denied', message: 'Немає прав' } }, 403), 'GET /review/chats/': () => json({ detail: 'Маршрут не знайдено' }, 404) })
  render(<App />)
  expect(await screen.findByText('Недостатньо прав')).toBeInTheDocument()
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Джерело звернень' }), { target: { value: 'review' } })
  expect(await screen.findByText('Маршрут не знайдено')).toBeInTheDocument()
  expect(screen.queryByText('Даних немає')).not.toBeInTheDocument()
})

test('an expired Django session returns to login', async () => {
  stubApi({ 'GET /operator/conversations/': () => json({ error: { code: 'not_authenticated', message: 'Сесія завершилася' } }, 403) })
  render(<App />)
  expect(await screen.findByText('Вхід для менеджерів')).toBeInTheDocument()
})

test('a server-authorized operators group user can use review without a staff flag', async () => {
  stubApi({ 'GET /me/': () => json({ ...profile, is_staff: false }) })
  render(<App />)
  expect(await screen.findByText('Потрібна консультація')).toBeInTheDocument()
  expect(screen.getByRole('option', { name: /Операторські звернення/ })).toBeDisabled()
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
})

test('a failed logout keeps the current session visible', async () => {
  stubApi({ 'POST /auth/logout/': () => json({ error: { code: 'csrf_failed', message: 'CSRF failure' } }, 403) })
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Вийти' }))
  expect(await screen.findByText('CSRF failure')).toBeInTheDocument()
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
})

test('review rejection requires a reason and submits only the server review ID', async () => {
  let current = chatDetail
  const decision = vi.fn((init?: RequestInit) => { const body = JSON.parse(init!.body as string); current = { ...current, review: { ...current.review, status: body.decision, note: body.note } }; return json(current) })
  stubApi({ 'GET /review/chats/11/': () => json(current), 'POST /review/reviews/19/decision/': decision })
  render(<App />)
  await openReview()
  expect(screen.getByRole('button', { name: 'Відхилити' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Причина відхилення / коментар'), { target: { value: 'Потрібне уточнення' } })
  fireEvent.click(screen.getByRole('button', { name: 'Відхилити' }))
  await waitFor(() => expect(decision).toHaveBeenCalledTimes(1))
  expect(JSON.parse(decision.mock.calls[0][0]!.body as string)).toEqual({ decision: 'rejected', note: 'Потрібне уточнення' })
})

test('a changed proposal is refreshed and never posted with the old approval', async () => {
  let reads = 0
  const post = vi.fn(() => json(chatDetail))
  stubApi({ 'GET /review/chats/11/': () => json(reads++ === 0 ? chatDetail : { ...chatDetail, review: { ...chatDetail.review, params: { reason: 'Змінена пропозиція' } } }), 'POST /review/reviews/19/decision/': post })
  render(<App />)
  await openReview()
  fireEvent.click(screen.getByRole('button', { name: 'Схвалити' }))
  expect(await screen.findByText(/Стан звернення змінився/)).toBeInTheDocument()
  expect(post).not.toHaveBeenCalled()
})

test('CSRF failure reports the error without logging the operator out', async () => {
  stubApi({ 'POST /review/reviews/19/decision/': () => json({ error: { code: 'csrf_failed', message: 'Потрібен коректний CSRF-токен.' } }, 403) })
  render(<App />)
  await openReview()
  fireEvent.click(screen.getByRole('button', { name: 'Схвалити' }))
  expect(await screen.findByText('Потрібен коректний CSRF-токен.')).toBeInTheDocument()
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
})

test('login bootstraps CSRF and subsequent mutations read the rotated cookie', async () => {
  let loggedIn = false
  const claim = vi.fn<Handler>(() => json({ ...detail, status: 'operator' }))
  const login = vi.fn<Handler>(() => { loggedIn = true; document.cookie = 'csrftoken=rotated; path=/'; return json(profile) })
  stubApi({
    'GET /auth/csrf/': () => { if (!loggedIn) document.cookie = 'csrftoken=initial; path=/'; return json({ detail: 'set' }) },
    'GET /me/': () => loggedIn ? json(profile) : json({ error: { code: 'not_authenticated' } }, 403),
    'POST /auth/login/': login, [`POST ${base}/claim/`]: claim,
  })
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Логін'), { target: { value: 'operator' } })
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Увійти' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Взяти в роботу' }))
  await waitFor(() => expect(claim).toHaveBeenCalledTimes(1))
  expect(new Headers(login.mock.calls[0][0]?.headers).get('X-CSRFToken')).toBe('initial')
  expect(new Headers(claim.mock.calls[0][0]?.headers).get('X-CSRFToken')).toBe('rotated')
  expect(claim.mock.calls[0][0]?.credentials).toBe('include')
})

test('a timed-out support reply is never automatically repeated; explicit replay reuses its ID', async () => {
  const bodies: Array<{ text: string; client_message_id: string }> = []
  let current = { ...detail, status: 'operator' }
  const reply = vi.fn((init?: RequestInit) => {
    const body = JSON.parse(init!.body as string)
    bodies.push(body)
    if (bodies.length === 1) return Promise.reject(new DOMException('Timeout', 'TimeoutError'))
    const message = { id: 'reply-1', sender: 'operator', text: body.text, created_at: '2026-10-31T10:10:00Z' }
    current = { ...current, messages: [...current.messages, message] }
    return Promise.resolve(json(message, 201))
  })
  stubApi({ 'GET /operator/conversations/': () => json({ results: [{ ...queueItem, status: 'operator', assigned_operator_id: 7 }] }), [`GET ${base}/`]: () => json(current), [`POST ${base}/messages/`]: reply })
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Відповідь клієнту'), { target: { value: 'Перевіряю' } })
  fireEvent.click(screen.getByRole('button', { name: 'Надіслати' }))
  const reconcile = await screen.findByRole('button', { name: 'Звірити стан' })
  await waitFor(() => expect(reconcile).toBeEnabled())
  expect(reply).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Надіслати' })).toBeDisabled()
  fireEvent.click(reconcile)
  fireEvent.click(await screen.findByRole('button', { name: 'Повторити з тим самим ID' }))
  await waitFor(() => expect(reply).toHaveBeenCalledTimes(2))
  expect(bodies[1]).toEqual(bodies[0])
})

test('drafts survive switching conversations and navigating to another page', async () => {
  const secondId = '00000000-0000-4000-8000-000000000002'
  stubApi({ 'GET /operator/conversations/': () => json({ results: [{ ...queueItem, status: 'operator', assigned_operator_id: 7 }, { ...queueItem, id: secondId, summary: 'Інший діалог', status: 'operator', assigned_operator_id: 7 }] }), [`GET ${base}/`]: () => json({ ...detail, status: 'operator' }), [`GET /operator/conversations/${secondId}/`]: () => json({ ...detail, id: secondId, status: 'operator', messages: [] }) })
  render(<App />)
  fireEvent.change(await screen.findByLabelText('Відповідь клієнту'), { target: { value: 'Перша чернетка' } })
  fireEvent.click(screen.getByRole('button', { name: /Інший діалог/ }))
  const second = await screen.findByLabelText('Відповідь клієнту')
  expect(second).toHaveValue('')
  fireEvent.change(second, { target: { value: 'Друга чернетка' } })
  fireEvent.click(screen.getByRole('button', { name: 'Аналітика' }))
  fireEvent.click(screen.getByRole('button', { name: 'Вхідні' }))
  expect(await screen.findByLabelText('Відповідь клієнту')).toHaveValue('Друга чернетка')
  fireEvent.click(screen.getByRole('button', { name: /Потрібна допомога/ }))
  expect(await screen.findByLabelText('Відповідь клієнту')).toHaveValue('Перша чернетка')
})

test('missing integration pages never fetch invented endpoints or show zero KPIs', async () => {
  const fetchMock = stubApi()
  render(<App />)
  await screen.findByRole('combobox', { name: 'Джерело звернень' })
  for (const name of ['API calls', 'Безпека', 'Аналітика', 'Інтеграція']) fireEvent.click(screen.getByRole('button', { name }))
  expect(screen.getByText('Контекст інтеграції недоступний')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Аналітика' }))
  expect(screen.getAllByText('Недостатньо даних')).toHaveLength(4)
  expect(screen.queryByText('0%')).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.some(([url]) => /\/api\/(analytics|integration|security|calls)/.test(url))).toBe(false)
})
