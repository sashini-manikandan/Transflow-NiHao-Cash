import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Assistant from '../pages/Assistant'
import { ApiError, api } from '../lib/api'
import { chatResponse } from './fixtures'

const TOOLS = {
  mode: 'offline_deterministic',
  max_tool_iterations: 4,
  tools: [
    {
      name: 'get_upcoming_bills',
      description: 'List bills due within a window.',
      mutates_state: false,
    },
    {
      name: 'create_reminder',
      description: 'Draft a reminder for the user.',
      mutates_state: true,
    },
  ],
  notes: ['The model has no database access and performs no arithmetic.'],
}

describe('AI assistant', () => {
  beforeEach(() => {
    vi.spyOn(api, 'suggestions').mockResolvedValue({
      suggestions: ['What bills do I have coming up in the next 30 days?'],
      base_currency: 'AED',
    })
    vi.spyOn(api, 'agentTools').mockResolvedValue(TOOLS)
  })

  it('documents the tool allowlist and flags the one that needs approval', async () => {
    render(<Assistant />)
    expect(await screen.findByText('get_upcoming_bills')).toBeInTheDocument()
    expect(screen.getByText('create_reminder')).toBeInTheDocument()
    expect(screen.getByText('Needs approval')).toBeInTheDocument()
    expect(screen.getByText(/no database access/i)).toBeInTheDocument()
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

    await user.click(screen.getByText(/show the backend calls behind this answer/i))
    // The tool name also appears in the allowlist sidebar, so scope to the trace.
    expect(await screen.findByText('{"days_ahead":30}')).toBeInTheDocument()
    expect(screen.getByText(/total due: aed 11250.4/i)).toBeInTheDocument()
    expect(screen.getAllByText('get_upcoming_bills').length).toBe(2)
  })

  it('separates calculated figures from estimates in the answer panel', async () => {
    vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)

    await user.type(screen.getByLabelText(/ask the assistant/i), 'bills?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByText(/figures behind this answer/i)

    expect(screen.getByText('Total due')).toBeInTheDocument()
    expect(screen.getByText('AED 11,250.40')).toBeInTheDocument()
    expect(screen.getByText('Projected closing balance')).toBeInTheDocument()

    // Both provenance labels must be visible side by side.
    expect(screen.getAllByText('Calculated').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estimate').length).toBeGreaterThan(0)
  })

  it('labels replies as BillWise AI without exposing the underlying model', async () => {
    vi.spyOn(api, 'chat').mockResolvedValue(chatResponse)
    const user = userEvent.setup()
    render(<Assistant />)

    await user.click(
      await screen.findByRole('button', { name: /what bills do i have coming up/i }),
    )
    expect(await screen.findByText('BillWise AI')).toBeInTheDocument()
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
      await screen.findByText(/never share bank passwords, pins or card security codes/i),
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
