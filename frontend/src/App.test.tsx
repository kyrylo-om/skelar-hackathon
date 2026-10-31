import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows backend health status', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), { status: 200 })),
  )

  render(<App />)

  expect(await screen.findByText('Backend: ok')).toBeInTheDocument()
})

test('shows unreachable when backend fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))

  render(<App />)

  expect(await screen.findByText('Backend: unreachable')).toBeInTheDocument()
})
