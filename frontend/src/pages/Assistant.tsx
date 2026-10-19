import { useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../lib/api'
import type { AgentFact, ChatResponse, ToolCallTrace } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { money, titleCase } from '../lib/format'
import { PageHeader } from '../components/PageHeader'
import {
  BasisTag,
  Card,
  DemoDataBanner,
  EvidenceDisclosure,
  Pill,
  Skeleton,
} from '../components/primitives'

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  response?: ChatResponse
  failed?: boolean
}

export default function Assistant() {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const nextId = useRef(1)
  const endRef = useRef<HTMLDivElement>(null)

  const suggestions = useApi(() => api.suggestions(), [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  async function send(text: string) {
    const question = text.trim()
    if (!question || busy) return

    const history = messages.map((message) => ({
      role: message.role,
      content: message.content,
    }))

    setMessages((current) => [
      ...current,
      { id: nextId.current++, role: 'user', content: question },
    ])
    setDraft('')
    setBusy(true)

    try {
      const response = await api.chat(question, history)
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: 'assistant',
          content: response.answer,
          response,
        },
      ])
    } catch (caught) {
      const message =
        caught instanceof ApiError
          ? caught.status === 429
            ? `${caught.message} Wait a moment before asking again.`
            : caught.message
          : 'The assistant could not answer that.'
      setMessages((current) => [
        ...current,
        { id: nextId.current++, role: 'assistant', content: message, failed: true },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="flex min-h-[70vh] flex-col xl:col-span-2">
        <PageHeader title="Assistant" lede="Ask about bills, subscriptions, forecasts, or FX." />

        <DemoDataBanner label="Synthetic data · not financial advice." />

        <div className="card mt-4 flex min-h-0 flex-1 flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
            {messages.length === 0 && (
              <div className="py-6">
                <p className="text-sm font-medium text-ink">
                  Try one of these to start
                </p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {(suggestions.data?.suggestions ?? []).map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => send(suggestion)}
                      className="rounded-lg border border-line/80 bg-transparent px-3.5 py-3
                                 text-left text-sm text-ink-muted transition-colors
                                 hover:border-accent/35 hover:bg-surface-2/50 hover:text-ink"
                    >
                      {suggestion}
                    </button>
                  ))}
                  {suggestions.loading &&
                    Array.from({ length: 6 }).map((_, index) => (
                      <Skeleton key={index} className="h-14" />
                    ))}
                </div>
              </div>
            )}

            {messages.map((message) =>
              message.role === 'user' ? (
                <div key={message.id} className="flex justify-end">
                  <p className="max-w-[85%] rounded-lg rounded-br-sm border border-accent/25 bg-accent-dim px-4 py-2.5 text-sm text-ink">
                    {message.content}
                  </p>
                </div>
              ) : (
                <AssistantMessage key={message.id} message={message} />
              ),
            )}

            {busy && (
              <div className="flex items-center gap-2.5 text-sm text-ink-muted">
                <span
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full
                             bg-accent-dim text-accent animate-pulse"
                  aria-hidden="true"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-4 w-4"
                  >
                    <circle cx="12" cy="12" r="3" />
                    <path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21" />
                    <path d="m5.6 5.6 1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" />
                  </svg>
                </span>
                <span role="status">Tran$Flow AI is thinking…</span>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            className="border-t border-line p-3 sm:p-4"
            onSubmit={(event) => {
              event.preventDefault()
              send(draft)
            }}
          >
            <div className="flex gap-2">
              <label htmlFor="chat-input" className="sr-only">
                Ask the assistant a question
              </label>
              <input
                id="chat-input"
                className="input"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="e.g. Can I cover my tuition instalment this month?"
                maxLength={2000}
                disabled={busy}
                autoComplete="off"
              />
              <button type="submit" className="btn-primary" disabled={busy || !draft.trim()}>
                Ask
              </button>
            </div>
            <p className="mt-2 text-[11px] text-ink-faint">
              Never share bank passwords or card details. Tran$Flow cannot move money.
            </p>
          </form>
        </div>
      </div>

      <aside className="space-y-6">
        <Card title="How Tran$Flow AI works">
          <ul className="space-y-2.5 text-sm leading-relaxed text-ink-muted">
            <li>
              Uses a <span className="text-ink">fixed tool set</span> — not free database
              access.
            </li>
            <li>
              <span className="text-ink">Numbers come from those tools</span>, not model
              arithmetic.
            </li>
            <li>
              Actions stay as <span className="text-ink">drafts until you confirm</span>.
            </li>
          </ul>
        </Card>

        <Card title="Tags">
          <dl className="space-y-3 text-xs leading-relaxed">
            <div className="flex items-center gap-2">
              <BasisTag basis="calculated" />
              <dd className="text-ink-muted">Confirmed</dd>
            </div>
            <div className="flex items-center gap-2">
              <BasisTag basis="estimate" />
              <dd className="text-ink-muted">Projection / FX</dd>
            </div>
            <div className="flex items-center gap-2">
              <BasisTag basis="suggestion" />
              <dd className="text-ink-muted">Needs your OK</dd>
            </div>
          </dl>
        </Card>
      </aside>
    </div>
  )
}

function AssistantMessage({ message }: { message: Message }) {
  const response = message.response

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[95%] space-y-3">
        <div
          role={message.failed ? 'alert' : undefined}
          className={`rounded-2xl rounded-bl-md border px-4 py-3 ${
            message.failed
              ? 'border-rose/30 bg-rose/5'
              : 'border-line bg-surface-2/60'
          }`}
        >
          {response && (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Pill tone="info">Tran$Flow AI</Pill>
              {response.tool_calls.length > 0 && (
                <Pill tone="good">
                  {response.tool_calls.length} tool call
                  {response.tool_calls.length === 1 ? '' : 's'}
                </Pill>
              )}
              {response.truncated && <Pill tone="warn">Tool limit reached</Pill>}
            </div>
          )}

          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
            {message.content}
          </p>
        </div>

        {response && response.facts.length > 0 && (
          <div className="rounded-xl border border-line bg-surface p-3">
            <p className="label-xs mb-2.5">Figures used</p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {response.facts.map((fact, index) => (
                <FactChip key={`${fact.label}-${index}`} fact={fact} />
              ))}
            </ul>
          </div>
        )}

        {response && response.tool_calls.length > 0 && (
          <EvidenceDisclosure summary="how this was calculated">
            <ul className="space-y-2">
              {response.tool_calls.map((call, index) => (
                <ToolTraceRow key={`${call.tool}-${index}`} call={call} />
              ))}
            </ul>
          </EvidenceDisclosure>
        )}
      </div>
    </div>
  )
}

function FactChip({ fact }: { fact: AgentFact }) {
  const value =
    typeof fact.value === 'number' && fact.currency
      ? money(fact.value, fact.currency)
      : String(fact.value)

  return (
    <li className="rounded-lg border border-line bg-surface-2/60 px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-medium text-ink-muted">{fact.label}</span>
        <BasisTag basis={fact.basis} />
      </div>
      <p className="num mt-1 text-sm font-semibold text-ink">{value}</p>
      {fact.period && <p className="text-[11px] text-ink-faint">{fact.period}</p>}
      {fact.note && <p className="mt-1 text-[11px] leading-relaxed text-amber">{fact.note}</p>}
    </li>
  )
}

function ToolTraceRow({ call }: { call: ToolCallTrace }) {
  const ok = call.status === 'ok'
  return (
    <li className="rounded-lg border border-line bg-surface px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <code className={ok ? 'text-accent' : 'text-rose'}>{call.tool}</code>
        <span className="flex items-center gap-2">
          <Pill tone={ok ? 'good' : 'bad'}>{titleCase(call.status)}</Pill>
          <span className="num text-ink-faint">{call.duration_ms} ms</span>
        </span>
      </div>
      {Object.keys(call.arguments).length > 0 && (
        <p className="mt-1 font-mono text-[11px] text-ink-faint">
          {JSON.stringify(call.arguments)}
        </p>
      )}
      <p className={`mt-1 ${ok ? 'text-ink-muted' : 'text-rose'}`}>
        {call.error ?? call.summary}
      </p>
    </li>
  )
}
