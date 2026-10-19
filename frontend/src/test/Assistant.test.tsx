import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Assistant from '../pages/Assistant'
import { ApiError, api } from '../lib/api'
import { chatResponse } from './fixtures'

describe('AI assistant', () => {
  beforeEach(() => {
    vi.spyOn(api, 'suggestions').mockResolvedValue({
      suggestions: ['What bills do I have coming up in the next 30 days?'],
      base_currency: 'AED',
    })
  })

  it('shows a short how-it-works panel instead of raw tool schemas', async () => {
    render(<Assistant />)
    expect(await screen.findByText('How Tran$Flow AI works')).toBeInTheDocument()
    expect(screen.getByText(/not free database access/i)).toBeInTheDocument()
    expect(screen.getByText(/drafts until you confirm/i)).toBeInTheDocument()
    expect(screen.queryByText('get_upcoming_bills')).not.toBeInTheDocument()
    expect(screen.queryByText(/what the assistant can call/i)).not.toBeInTheDocument()
  })

  it('answers a question and shows the tool calls behind the answer', async () => {
    const chat = vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)

    await user.type(screen.getByLabelText(/ask the assistant/i), 'What bills are due?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByText(/you have 4 bills due/i)).toBeInTheDocument()
    expect(chat).toHaveBeenCalledWith('What bills are due?', [])
    expect(screen.getByText('1 tool call')).toBeInTheDocument()

    await user.click(screen.getByText(/show how this was calculated/i))
    expect(await screen.findByText('{"days_ahead":30}')).toBeInTheDocument()
    expect(screen.getByText(/total due: aed 11250.4/i)).toBeInTheDocument()
    expect(screen.getByText('get_upcoming_bills')).toBeInTheDocument()
  })

  it('separates calculated figures from estimates in the answer panel', async () => {
    vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)

    await user.type(screen.getByLabelText(/ask the assistant/i), 'bills?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText(/figures used/i)

    expect(screen.getByText('Total due')).toBeInTheDocument()
    expect(screen.getByText('AED 11,250.40')).toBeInTheDocument()
    expect(screen.getByText('Projected closing balance')).toBeInTheDocument()

    // Both provenance labels must be visible side by side.
    expect(screen.getAllByText('Calculated').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estimate').length).toBeGreaterThan(0)
  })

  it('labels replies as Tran$Flow AI without exposing the underlying model', async () => {
    vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)

    await user.click(
      await screen.findByRole('button', { name: /what bills do i have coming up/i }),
    )
    expect(await screen.findByText('Tran$Flow AI')).toBeInTheDocument()
    expect(screen.queryByText(/deterministic/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/gpt/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(/not financial advice/i).length).toBeGreaterThan(0)
  })

  it('explains a rate limit instead of failing silently', async () => {
    vi.spyOn(api, 'chat').mockRejectedValue(
      new ApiError('Too many assistant requests. Limit is 15 per 60s.', 429),
    )
    const user = userEvent.setup()
    render(<Assistant />)

    await user.type(screen.getByLabelText(/ask the assistant/i), 'hello')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/too many assistant requests/i),
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/wait a moment before asking again/i)
  })

  it('warns the user never to share credentials', async () => {
    render(<Assistant />)
    expect(
      await screen.findByText(/never share bank passwords or card details/i),
    ).toBeInTheDocument()
  })

  it('sends prior turns as history so follow-ups have context', async () => {
    const chat = vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)
    const input = screen.getByLabelText(/ask the assistant/i)

    await user.type(input, 'first question')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText(/you have 4 bills due/i)

    await user.type(input, 'and after that?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2))
    const [, history] = chat.mock.calls[1]
    expect(history).toHaveLength(2)
    expect(history[0]).toEqual({ role: 'user', content: 'first question' })
    expect(history[1].role).toBe('assistant')
  })
})
