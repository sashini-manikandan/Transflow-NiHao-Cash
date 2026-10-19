import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Dashboard from '../pages/Dashboard'
import { api } from '../lib/api'
import { dashboard, recommendations } from './fixtures'

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.spyOn(api, 'dashboard').mockResolvedValue(dashboard)
    vi.spyOn(api, 'recommendations').mockResolvedValue(recommendations)
  })

  it('shows a loading state before the data arrives', () => {
    renderDashboard()
    expect(screen.getByRole('status', { name: /loading dashboard/i })).toBeInTheDocument()
  })

  it('renders figures returned by the backend rather than placeholders', async () => {
    renderDashboard()
    // The opening balance appears both as a headline stat and in the chart footer.
    expect((await screen.findAllByText('AED 7,300.25')).length).toBeGreaterThan(0)
    expect(screen.getByText('AED 11,250.40')).toBeInTheDocument()
    expect(screen.getByText('AED 742.18')).toBeInTheDocument()
    expect(screen.getByText('AED 188.40')).toBeInTheDocument()
  })

  it('labels each headline figure as calculated or estimated', async () => {
    renderDashboard()
    await screen.findAllByText('AED 7,300.25')

    expect(screen.getAllByText('Calculated').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estimate').length).toBeGreaterThan(0)
  })

  it('raises a shortfall alert with the projected gap', async () => {
    renderDashboard()
    const alerts = await screen.findAllByRole('alert')
    const shortfall = alerts.find((node) => /shortfall of/i.test(node.textContent ?? ''))

    expect(shortfall).toBeDefined()
    expect(shortfall).toHaveTextContent('AED 2,310.40')
    expect(shortfall).toHaveTextContent('31 Oct 2026')
  })

  it('always states that the data is synthetic', async () => {
    renderDashboard()
    expect(
      await screen.findByText(/no bank account is connected/i),
    ).toBeInTheDocument()
  })

  it('ranks recommendations and explains the basis of each impact figure', async () => {
    renderDashboard()
    await screen.findByText(/projected shortfall on 2026-10-31/i)

    expect(
      screen.getByText(/cancel the duplicate netflix subscription/i),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/matches a stated priority/i).length).toBe(2)
    expect(screen.getAllByText(/needs your approval/i).length).toBeGreaterThan(0)
  })

  it('surfaces an error with a retry affordance when the API fails', async () => {
    vi.spyOn(api, 'dashboard').mockRejectedValue(new Error('backend down'))
    renderDashboard()

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/could not load this view/i),
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('refetches with a new horizon when the range is changed', async () => {
    const spy = vi.spyOn(api, 'dashboard').mockResolvedValue(dashboard)
    const { default: userEvent } = await import('@testing-library/user-event')
    renderDashboard()
    await screen.findAllByText('AED 7,300.25')

    await userEvent.setup().click(screen.getByRole('button', { name: '90d' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith(90))
  })
})
