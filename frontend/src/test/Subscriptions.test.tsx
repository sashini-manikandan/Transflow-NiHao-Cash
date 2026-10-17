import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Subscriptions from '../pages/Subscriptions'
import { api } from '../lib/api'
import { subscriptionAnalysis } from './fixtures'

describe('Subscriptions', () => {
  beforeEach(() => {
    vi.spyOn(api, 'subscriptions').mockResolvedValue(subscriptionAnalysis)
  })

  it('never presents an uncertain series as a confirmed subscription', async () => {
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    expect(screen.getByText('Likely subscription')).toBeInTheDocument()
    expect(screen.getByText('Possible subscription')).toBeInTheDocument()
  })

  it('exposes the transactions that justify a detection', async () => {
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    // Netflix and Notion each have one evidence row in the fixture.
    const disclosures = screen.getAllByText(/show the 1 charges behind this/i)
    await userEvent.setup().click(disclosures[0])
    expect(await screen.findByText('NETFLIX.COM*4471 AMSTERDAM NL')).toBeInTheDocument()
  })

  it('shows a confidence meter for every detection', async () => {
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    const meters = screen.getAllByRole('meter')
    expect(meters.length).toBeGreaterThanOrEqual(2)
    expect(
      meters.some((meter) => meter.getAttribute('aria-valuenow') === '94'),
    ).toBe(true)
    expect(
      meters.some((meter) => meter.getAttribute('aria-valuenow') === '55'),
    ).toBe(true)
  })

  it('distinguishes a probable duplicate from an intentional overlap', async () => {
    render(<Subscriptions />)
    await screen.findByText(/netflix looks like it is being billed twice/i)

    expect(screen.getByText('Likely')).toBeInTheDocument()
    expect(screen.getByText('Worth reviewing')).toBeInTheDocument()
    expect(screen.getByText(/often deliberate/i)).toBeInTheDocument()
  })

  it('filters the list without refetching', async () => {
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    await userEvent.setup().click(screen.getByRole('button', { name: /possible \(1\)/i }))
    await waitFor(() => expect(screen.queryByText('Netflix')).not.toBeInTheDocument())
    expect(screen.getByText('Notion')).toBeInTheDocument()
  })

  it('shows an empty state when a filter matches nothing', async () => {
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    await userEvent.setup().click(screen.getByRole('button', { name: /dormant \(0\)/i }))
    expect(await screen.findByText(/nothing matches this filter/i)).toBeInTheDocument()
  })

  it('requires typing the exact service name before a cancellation can be approved', async () => {
    const preview = {
      id: 7,
      action_type: 'cancel_subscription',
      target_label: 'Netflix',
      summary: 'Preview only — nothing has been cancelled.',
      estimated_monthly_impact: '61.75',
      currency: 'AED',
      status: 'pending_review',
      requires_authorization: true,
    }
    vi.spyOn(api, 'previewAction').mockResolvedValue(preview)
    const decide = vi
      .spyOn(api, 'decideAction')
      .mockResolvedValue({ ...preview, status: 'approved_by_user' })

    const user = userEvent.setup()
    render(<Subscriptions />)
    await screen.findByText('Netflix')

    await user.click(screen.getAllByRole('button', { name: /preview cancellation/i })[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/nothing has been cancelled/i)).toBeInTheDocument()

    const approve = within(dialog).getByRole('button', { name: /approve cancellation plan/i })
    expect(approve).toBeDisabled()

    await user.type(within(dialog).getByLabelText(/type/i), 'Netflix')
    expect(approve).toBeEnabled()

    await user.click(approve)
    await waitFor(() => expect(decide).toHaveBeenCalledWith(7, 'approve', 'Netflix'))
    expect(
      await within(dialog).findByText(/no cancellation has been sent to the merchant/i),
    ).toBeInTheDocument()
  })
})
