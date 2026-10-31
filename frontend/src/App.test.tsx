import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App.jsx'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const chatItem = {
  id: 1,
  customer: 'Олена Коваль',
  subject: 'Подвійне списання',
  status: 'needs_review',
  priority: 'high',
  updatedAt: '2026-10-31T11:40:00Z',
  summary: 'Двічі списали 240 грн',
}

const chatDetail = {
  ...chatItem,
  messages: [{ id: 1, role: 'customer', text: 'Поверніть гроші', at: '2026-10-31T11:36:00Z' }],
  trace: [{ agent: 'policy', verdict: 'block', detail: 'Сума перевищує ліміт' }],
  review: {
    id: 9,
    action: 'refund',
    params: { amount: 240 },
    risk: 'high',
    reason: 'Policy: ліміт',
    status: 'pending',
    note: '',
    decidedBy: null,
  },
}

type Routes = Record<string, (init?: RequestInit) => Response>

function stubApi(routes: Routes) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const path = url.replace('/api', '')
    const handler = routes[`${init?.method ?? 'GET'} ${path}`]
    return Promise.resolve(handler ? handler(init) : json({}, 403))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const operatorRoutes: Routes = {
  'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }),
  'GET /me/': () => json({ id: '1', username: 'op', is_staff: true }),
  'GET /review/chats/': () => json([chatItem]),
  'GET /review/chats/1/': () => json(chatDetail),
  'GET /review/audit/': () => json([]),
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('customer tab asks for a customer login when there is no session', () => {
  stubApi({ 'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }) })
  render(<App />)

  expect(screen.getByText('Вхід для клієнтів')).toBeInTheDocument()
})

const customerChat = {
  id: 3,
  status: 'ai_handling',
  messages: [{ id: 1, role: 'ai', text: 'Вітаю! Чим допомогти?', at: '2026-10-31T11:00:00Z' }],
}

const customerRoutes: Routes = {
  'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }),
  'GET /me/': () => json({ id: '2', username: 'olena', is_staff: false }),
  'GET /review/my/chat/': () => json(customerChat),
}

test('signed in customer sees their chat from the API', async () => {
  stubApi(customerRoutes)
  render(<App />)

  expect(await screen.findByText('Вітаю! Чим допомогти?')).toBeInTheDocument()
})

test('customer message is posted to the API', async () => {
  const post = vi.fn(() =>
    json({
      ...customerChat,
      status: 'needs_review',
      messages: [
        ...customerChat.messages,
        { id: 2, role: 'customer', text: 'Поверніть гроші', at: '2026-10-31T11:01:00Z' },
      ],
    }),
  )
  stubApi({ ...customerRoutes, 'POST /review/my/chat/messages/': post })
  render(<App />)

  fireEvent.change(await screen.findByPlaceholderText('Напишіть повідомлення…'), {
    target: { value: 'Поверніть гроші' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Надіслати' }))

  expect(await screen.findByText('Ваш запит передано спеціалісту — відповідь прийде тут')).toBeInTheDocument()
  expect(post).toHaveBeenCalled()
})

test('reviewer tab asks for a login when there is no session', async () => {
  stubApi({ 'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }) })
  render(<App />)

  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  expect(await screen.findByText('Вхід для менеджерів')).toBeInTheDocument()
})

test('wrong credentials show the server error', async () => {
  stubApi({
    'GET /auth/csrf/': () => json({ detail: 'CSRF cookie set.' }),
    'POST /auth/login/': () => json({ error: { code: 'permission_denied', message: 'Невірний логін або пароль' } }, 403),
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.change(await screen.findByPlaceholderText('Логін'), { target: { value: 'op' } })
  fireEvent.change(screen.getByPlaceholderText('Пароль'), { target: { value: 'bad' } })
  fireEvent.click(screen.getByRole('button', { name: 'Увійти' }))

  expect(await screen.findByText('Невірний логін або пароль')).toBeInTheDocument()
})

test('logged in operator sees the queue and the selected chat from the API', async () => {
  stubApi(operatorRoutes)
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  expect(await screen.findByText('Поверніть гроші')).toBeInTheDocument()
  expect(screen.getByText('Policy: ліміт', { exact: false })).toBeInTheDocument()
  expect(screen.getByText('Сума перевищує ліміт')).toBeInTheDocument()
})

test('approving posts the decision with the review id', async () => {
  const decision = vi.fn(() =>
    json({ ...chatDetail, status: 'resolved', review: { ...chatDetail.review, status: 'approved' } }),
  )
  const fetchMock = stubApi({ ...operatorRoutes, 'POST /review/reviews/9/decision/': decision })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.click(await screen.findByRole('button', { name: 'Схвалити' }))

  await waitFor(() => expect(decision).toHaveBeenCalled())
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/review/reviews/9/decision/'))
  expect(JSON.parse(call![1]!.body as string)).toEqual({ decision: 'approved', note: '' })
})

test('an expired session sends the operator back to the login', async () => {
  stubApi({
    ...operatorRoutes,
    'GET /review/chats/': () => json({ detail: 'forbidden' }, 403),
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  await waitFor(() => expect(screen.getByText('Вхід для менеджерів')).toBeInTheDocument())
})

test('a failed CSRF check shows an error but keeps the operator signed in', async () => {
  stubApi({
    ...operatorRoutes,
    'POST /review/reviews/9/decision/': () => json({ error: { code: 'csrf_failed', message: 'Потрібен коректний CSRF-токен.' } }, 403),
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.click(await screen.findByRole('button', { name: 'Схвалити' }))

  expect(await screen.findByText('Потрібен коректний CSRF-токен.')).toBeInTheDocument()
  expect(screen.queryByText('Вхід для менеджерів')).not.toBeInTheDocument()
})
