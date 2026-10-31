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
  'GET /health/': () => json({ status: 'ok' }),
  'GET /auth/me/': () => json({ username: 'op', isOperator: true }),
  'GET /chats/': () => json([chatItem]),
  'GET /chats/1/': () => json(chatDetail),
  'GET /audit/': () => json([]),
}

afterEach(() => {
  vi.unstubAllGlobals()
})

test('customer chat is shown by default', () => {
  stubApi({ 'GET /health/': () => json({ status: 'ok' }) })
  render(<App />)

  expect(screen.getByText('AI-підтримка · вирішує, а не просто відповідає')).toBeInTheDocument()
})

test('reviewer tab asks for a login when there is no session', async () => {
  stubApi({ 'GET /health/': () => json({ status: 'ok' }) })
  render(<App />)

  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  expect(await screen.findByText('Вхід для менеджерів')).toBeInTheDocument()
})

test('wrong credentials show the server error', async () => {
  stubApi({
    'GET /health/': () => json({ status: 'ok' }),
    'POST /auth/login/': () => json({ detail: 'Невірний логін або пароль' }, 400),
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
  const fetchMock = stubApi({ ...operatorRoutes, 'POST /reviews/9/decision/': decision })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.click(await screen.findByRole('button', { name: 'Схвалити' }))

  await waitFor(() => expect(decision).toHaveBeenCalled())
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/reviews/9/decision/'))
  expect(JSON.parse(call![1]!.body as string)).toEqual({ decision: 'approved', note: '' })
})

test('an expired session sends the operator back to the login', async () => {
  stubApi({
    ...operatorRoutes,
    'GET /chats/': () => json({ detail: 'forbidden' }, 403),
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  await waitFor(() => expect(screen.getByText('Вхід для менеджерів')).toBeInTheDocument())
})
