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
  const tools = useApi(() => api.agentTools(), [])

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

  const mode = tools.data?.mode

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="flex min-h-[70vh] flex-col xl:col-span-2">
        <PageHeader
          title="Assistant"
          lede="Ask about obligations. Every figure comes from a backend tool — shown under each reply. The model never does the arithmetic."
        />

        <DemoDataBanner
          label={
            mode === 'llm'
              ? 'Answers are written by a language model from backend tool results, over synthetic demo data. Not financial advice.'
              : 'No model API key is configured, so replies are assembled directly from backend calculations. Clearly marked as such on each reply.'
          }
        />

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
              <div className="flex items-center gap-2 text-sm text-ink-muted">
                <span className="flex gap-1" aria-hidden="true">
                  {[0, 1, 2].map((index) => (
                    <span
                      key={index}
                      className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent"
                      style={{ animationDelay: `${index * 160}ms` }}
                    />
                  ))}
                </span>
                <span role="status">Running backend tools…</span>
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
              Never share bank passwords, PINs or card security codes. BillWise does not
              ask for them and cannot move money.
            </p>
          </form>
        </div>
      </div>

      <aside className="space-y-6">
        <Card
          title="What the assistant can call"
          subtitle="A fixed allowlist. Anything outside it is refused before it runs."
        >
          {tools.loading && <Skeleton className="h-40" />}
          {tools.data && (
            <>
              <ul className="space-y-2.5">
                {tools.data.tools.map((tool) => (
                  <li key={tool.name} className="rounded-xl border border-line bg-surface-2/50 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <code className="text-xs font-semibold text-accent">{tool.name}</code>
                      {tool.mutates_state && <Pill tone="warn">Needs approval</Pill>}
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
                      {tool.description}
                    </p>
                  </li>
                ))}
              </ul>
              <ul className="mt-4 space-y-1.5 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-faint">
                {tools.data.notes.map((note) => (
                  <li key={note}>• {note}</li>
                ))}
                <li>
                  • Up to {tools.data.max_tool_iterations} tool rounds per question, then
                  the assistant must answer with what it has.
                </li>
              </ul>
            </>
          )}
        </Card>

        <Card
          title="How to read the answers"
          subtitle="The assistant separates these three things, and so does this interface."
        >
          <dl className="space-y-3 text-xs leading-relaxed">
            <div>
              <dt>
                <BasisTag basis="calculated" />
              </dt>
              <dd className="mt-1.5 text-ink-muted">
                A confirmed figure: a billed amount, a due date, a past transaction.
              </dd>
            </div>
            <div>
              <dt>
                <BasisTag basis="estimate" />
              </dt>
              <dd className="mt-1.5 text-ink-muted">
                A projection, a normalised monthly total, or anything converted between
                currencies. Depends on stated assumptions.
              </dd>
            </div>
            <div>
              <dt>
                <BasisTag basis="suggestion" />
              </dt>
              <dd className="mt-1.5 text-ink-muted">
                Something to review. Nothing is actioned without your explicit approval.
              </dd>
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
              <Pill tone="info">BillWise AI</Pill>
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
            <p className="label-xs mb-2.5">Figures behind this answer</p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {response.facts.map((fact, index) => (
                <FactChip key={`${fact.label}-${index}`} fact={fact} />
              ))}
            </ul>
          </div>
        )}

        {response && response.tool_calls.length > 0 && (
          <EvidenceDisclosure summary="the backend calls behind this answer">
            <ul className="space-y-2">
              {response.tool_calls.map((call, index) => (
                <ToolTraceRow key={`${call.tool}-${index}`} call={call} />
              ))}
            </ul>
          </EvidenceDisclosure>
        )}

        {response && (
          <p className="text-[11px] leading-relaxed text-ink-faint">
            {response.disclaimer}
          </p>
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
