import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import TraceDetailed from './TraceDetailed'

test('failed stages expand by default and manual collapse survives polling', () => {
  const steps = [{ agent: 'policy', verdict: 'deny', detail: 'Перевірка відхилила дію' }]
  const { rerender } = render(<TraceDetailed steps={steps} />)
  expect(screen.getByText('Перевірка відхилила дію')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Policy/ }))
  expect(screen.queryByText('Перевірка відхилила дію')).not.toBeInTheDocument()
  rerender(<TraceDetailed steps={steps.map((step) => ({ ...step }))} />)
  expect(screen.getByRole('button', { name: /Policy/ })).toHaveAttribute('aria-expanded', 'false')
})

test('an unknown verdict is neutral and missing checks never become passed checks', () => {
  render(<TraceDetailed steps={[{ agent: 'actor', verdict: 'new_verdict', detail: 'Пояснення' }]} />)
  const button = screen.getByRole('button', { name: /new_verdict/ })
  expect(button.closest('li')).toHaveClass('trace-unknown')
  expect(screen.getByText(/Детальні checks і тривалість API не надає/)).toBeInTheDocument()
  expect(screen.queryByText('13/13')).not.toBeInTheDocument()
})
