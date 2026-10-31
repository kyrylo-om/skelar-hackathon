import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, test } from 'vitest'
import App from './App'
import { resetStore } from './api/support'

beforeEach(() => {
  resetStore()
})

test('lists all chats and opens the first one needing review', async () => {
  render(<App />)

  expect(await screen.findByText('Підсумок AI')).toBeInTheDocument()
  expect(screen.getByText('Андрій Мельник')).toBeInTheDocument()
  expect(screen.getByText('Ірина Шевченко')).toBeInTheDocument()
  expect(screen.getByText('На перевірці: 3')).toBeInTheDocument()
})

test('filters chats by status', async () => {
  render(<App />)
  await screen.findByText('Підсумок AI')

  fireEvent.click(screen.getByRole('button', { name: 'Вирішені' }))

  expect(screen.queryByText('Андрій Мельник')).not.toBeInTheDocument()
  expect(screen.getByText('Ірина Шевченко')).toBeInTheDocument()
})

test('approving a review resolves the chat', async () => {
  render(<App />)
  await screen.findByText('Підсумок AI')

  fireEvent.click(screen.getByRole('button', { name: 'Схвалити' }))

  expect(await screen.findByText('Схвалено оператором')).toBeInTheDocument()
  expect(screen.getByText('На перевірці: 2')).toBeInTheDocument()
})

test('operator reply appears in the conversation', async () => {
  render(<App />)
  await screen.findByText('Підсумок AI')

  fireEvent.change(screen.getByLabelText('Відповідь клієнту'), { target: { value: 'Вже перевіряю' } })
  fireEvent.click(screen.getByRole('button', { name: 'Надіслати' }))

  expect(await screen.findByText('Вже перевіряю')).toBeInTheDocument()
})
