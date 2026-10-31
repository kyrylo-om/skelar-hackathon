import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(url, init))),
  )
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

beforeEach(() => {
  stubFetch((url) => (url.endsWith('/health/') ? json({ status: 'ok' }) : json({}, 403)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('customer chat is shown by default', () => {
  render(<App />)

  expect(screen.getByText('AI-підтримка · вирішує, а не просто відповідає')).toBeInTheDocument()
})

test('reviewer tab asks for a login', async () => {
  render(<App />)

  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  expect(await screen.findByText('Вхід для менеджерів')).toBeInTheDocument()
})

test('successful login opens the operator cabinet', async () => {
  stubFetch((url) => {
    if (url.endsWith('/auth/login/')) return json({ username: 'op', isOperator: true })
    return url.endsWith('/health/') ? json({ status: 'ok' }) : json({}, 403)
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.change(await screen.findByPlaceholderText('Логін'), { target: { value: 'op' } })
  fireEvent.change(screen.getByPlaceholderText('Пароль'), { target: { value: 'secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Увійти' }))

  expect(await screen.findByText('Черга')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Вийти (op)' })).toBeInTheDocument()
})

test('wrong credentials show the server error', async () => {
  stubFetch((url) => {
    if (url.endsWith('/auth/login/')) return json({ detail: 'Невірний логін або пароль' }, 400)
    return url.endsWith('/health/') ? json({ status: 'ok' }) : json({}, 403)
  })
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: 'Оператор' }))

  fireEvent.change(await screen.findByPlaceholderText('Логін'), { target: { value: 'op' } })
  fireEvent.change(screen.getByPlaceholderText('Пароль'), { target: { value: 'bad' } })
  fireEvent.click(screen.getByRole('button', { name: 'Увійти' }))

  expect(await screen.findByText('Невірний логін або пароль')).toBeInTheDocument()
})
