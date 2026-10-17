import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, ApiError, getDemoUser } from '../lib/api'
import type { ForecastEvent } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { longDate, money, relativeDays, shortDate, titleCase } from '../lib/format'
import { PageHeader } from '../components/PageHeader'
import {
  BasisTag,
  Card,
  EmptyState,
  ErrorPanel,
  EvidenceDisclosure,
  LoadingPanel,
  Pill,
  StatCard,
} from '../components/primitives'

const HORIZONS = [30, 60, 90, 180]

export default function BillsAndForecasts() {
  const [horizon, setHorizon] = useState(60)
  const [includeProjected, setIncludeProjected] = useState(true)

  const bills = useApi(() => api.bills(horizon), [horizon])
  const forecast = useApi(
    () => api.forecast(horizon, includeProjected),
    [horizon, includeProjected],
  )

  const chartData = useMemo(
    () =>
      (forecast.data?.daily ?? []).map((point) => ({
        date: point.date,
        label: shortDate(point.date),
        balance: point.balance,
        inflow: point.inflow,
        outflow: -point.outflow,
      })),
    [forecast.data],
  )

  if (bills.loading && !bills.data) return <LoadingPanel label="Loading bills" />
  if (bills.error) return <ErrorPanel message={bills.error} onRetry={bills.reload} />
  if (!bills.data) return null

  const currency = bills.data.base_currency
  const f = forecast.data

  return (
    <div className="space-y-8">
      <PageHeader
        title="Bills & forecast"
        lede="Confirmed bills and projected charges against expected income — so you can see whether each obligation is covered."
      >
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-line bg-surface-2 accent-emerald-400"
            checked={includeProjected}
            onChange={(event) => setIncludeProjected(event.target.checked)}
          />
          Include projected subscriptions
        </label>
        <div
          className="flex items-center gap-0.5 rounded-lg border border-line/80 bg-surface/80 p-1"
          role="group"
          aria-label="Forecast horizon"
        >
          {HORIZONS.map((days) => (
            <button
              key={days}
              type="button"
              aria-pressed={horizon === days}
              onClick={() => setHorizon(days)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                horizon === days
                  ? 'bg-accent-dim text-accent'
                  : 'text-ink-muted hover:text-ink'
              }`}
            >
              {days}d
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label={`Total due in ${horizon} days`}
          value={money(bills.data.total_due_base, currency)}
          sublabel={`${bills.data.count} confirmed bills`}
          basis="calculated"
        />
        <StatCard
          label="Projected closing balance"
          value={money(f?.closing_balance, currency)}
          sublabel={f ? `on ${longDate(f.period.end)}` : undefined}
          basis="estimate"
          tone={f && f.closing_balance < 0 ? 'bad' : 'neutral'}
        />
        <StatCard
          label="Lowest projected point"
          value={money(f?.minimum_balance, currency)}
          sublabel={f ? `on ${longDate(f.minimum_balance_date)}` : undefined}
          basis="estimate"
          tone={f && f.minimum_balance < 0 ? 'bad' : 'good'}
        />
        <StatCard
          label="Shortfall risk"
          value={f?.shortfall_detected ? money(f.largest_shortfall, currency) : 'None'}
          sublabel={
            f?.shortfall_detected
              ? `first on ${longDate(f.first_shortfall_date)}`
              : 'Balance stays positive across the horizon'
          }
          basis="estimate"
          tone={f?.shortfall_detected ? 'bad' : 'good'}
        />
      </div>

      {f?.shortfall_detected && (
        <div role="alert" className="card card-pad border-rose/30 bg-rose/5">
          <h2 className="text-sm font-semibold text-rose">
            You are projected to run short on {longDate(f.first_shortfall_date)}
          </h2>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-muted">
            The projection dips to {money(f.minimum_balance, currency)} on{' '}
            {longDate(f.minimum_balance_date)}, a gap of{' '}
            {money(f.largest_shortfall, currency)}. This combines confirmed bills with
            projected subscription charges, so the exact date can move if a subscription
            bills earlier or later than its usual day.
          </p>
        </div>
      )}

      <Card
        title="Balance projection"
        subtitle="Line is the running balance. Bars show money in and out on each day."
        action={<BasisTag basis="estimate" />}
      >
        {forecast.loading && !f && <LoadingPanel label="Projecting balance" />}
        {forecast.error && (
          <ErrorPanel message={forecast.error} onRetry={forecast.reload} />
        )}
        {f && (
          <>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chartData}
                  margin={{ top: 8, right: 8, bottom: 0, left: -12 }}
                >
                  <CartesianGrid stroke="#243830" vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke="#73857C"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={32}
                  />
                  <YAxis
                    stroke="#73857C"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={64}
                    tickFormatter={(value: number) =>
                      money(value, undefined, { compact: true })
                    }
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    labelFormatter={(_label, payload) =>
                      payload?.[0] ? longDate(payload[0].payload.date) : ''
                    }
                    formatter={(value: number, name: string) => [
                      money(Math.abs(value), currency),
                      titleCase(name),
                    ]}
                  />
                  <ReferenceLine y={0} stroke="#E8898F" strokeDasharray="4 4" />
                  <Bar dataKey="inflow" fill="#3DCF9A" fillOpacity={0.5} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="outflow" fill="#E8898F" fillOpacity={0.5} radius={[0, 0, 3, 3]} />
                  <Line
                    type="monotone"
                    dataKey="balance"
                    stroke="#C9B8A0"
                    strokeWidth={2.2}
                    dot={false}
                  />
                  {f.first_shortfall_date && (
                    <ReferenceDot
                      x={shortDate(f.first_shortfall_date)}
                      y={0}
                      r={5}
                      fill="#E8898F"
                      stroke="#06100D"
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <EvidenceDisclosure summary={`all ${f.events.length} projected events`}>
              <ul className="space-y-2">
                {f.events.map((event, index) => (
                  <EventRow
                    key={`${event.label}-${event.date}-${index}`}
                    event={event}
                    currency={currency}
                  />
                ))}
              </ul>
            </EvidenceDisclosure>

            {f.excluded_from_projection.length > 0 && (
              <div className="mt-4 rounded-xl border border-amber/25 bg-amber/5 p-3">
                <p className="text-xs font-semibold text-amber">
                  Excluded from the running balance
                </p>
                <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-ink-muted">
                  {f.excluded_from_projection.map((item, index) => (
                    <li key={`${item.item}-${index}`}>
                      • {item.item} — {money(item.amount_original, item.currency)}.{' '}
                      {item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Card>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Upcoming bills"
          subtitle={`Confirmed obligations in the next ${horizon} days.`}
          action={<BasisTag basis="calculated" />}
        >
          {bills.data.count === 0 ? (
            <EmptyState
              title="No bills in this window"
              description="Widen the horizon, or add a bill to track it here."
            />
          ) : (
            <ul className="divide-y divide-line">
              {bills.data.bills.map((bill) => (
                <li key={bill.id} className="py-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium">{bill.name}</p>
                        <Pill>{titleCase(bill.category)}</Pill>
                        {bill.autopay && <Pill tone="info">Autopay</Pill>}
                        {bill.days_until_due <= 7 && <Pill tone="warn">Due soon</Pill>}
                      </div>
                      <p className="mt-1 text-xs text-ink-faint">
                        {longDate(bill.due_date)} · {relativeDays(bill.days_until_due)}
                        {bill.notes && ` · ${bill.notes}`}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="num text-sm font-semibold">
                        {money(bill.amount, bill.currency)}
                      </p>
                      {bill.currency !== currency && (
                        <p className="num text-xs text-ink-faint">
                          {bill.amount_base === null
                            ? 'no rate available'
                            : `≈ ${money(bill.amount_base, currency)}`}
                        </p>
                      )}
                    </div>
                  </div>

                  {bill.currency !== currency && bill.conversion.rate_date && (
                    <p className="mt-1.5 text-[11px] text-ink-faint">
                      Converted at {bill.conversion.rate} dated{' '}
                      {longDate(bill.conversion.rate_date)} ({bill.conversion.rate_source}
                      {bill.conversion.is_simulated_rate && ', simulated'}).
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Where the money sits"
          subtitle="Opening position by account."
          action={<BasisTag basis="calculated" />}
        >
          {!f ? (
            <LoadingPanel label="Loading accounts" />
          ) : (
            <>
              <ul className="space-y-3">
                {f.opening_balance_breakdown.map((account) => (
                  <li
                    key={account.account_id}
                    className="rounded-xl border border-line bg-surface-2/60 p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{account.name}</p>
                        <p className="text-xs text-ink-faint">{account.institution}</p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="num text-sm font-semibold">
                          {money(account.balance_original, account.currency)}
                        </p>
                        {account.currency !== currency && (
                          <p className="num text-xs text-ink-faint">
                            ≈ {money(account.balance_base, currency)}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-4 h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={f.opening_balance_breakdown.map((account) => ({
                      name: account.name.split(' ')[0],
                      value: account.balance_base ?? 0,
                    }))}
                    margin={{ top: 4, right: 8, bottom: 0, left: -16 }}
                  >
                    <CartesianGrid stroke="#243830" vertical={false} />
                    <XAxis
                      dataKey="name"
                      stroke="#73857C"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      stroke="#73857C"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={56}
                      tickFormatter={(value: number) =>
                        money(value, undefined, { compact: true })
                      }
                    />
                    <Tooltip
                      cursor={{ fill: '#10241D' }}
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(value: number) => [money(value, currency), 'Balance']}
                    />
                    <Bar dataKey="value" fill="#3DCF9A" fillOpacity={0.8} radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </Card>
      </div>

      <AddBillCard
        onCreated={() => {
          bills.reload()
          forecast.reload()
        }}
      />
    </div>
  )
}

const TOOLTIP_STYLE = {
  background: '#0B1A15',
  border: '1px solid #243830',
  borderRadius: 12,
  fontSize: 12,
  color: '#E8F3EE',
}

function EventRow({ event, currency }: { event: ForecastEvent; currency: string }) {
  const tone = event.direction === 'inflow' ? 'text-accent' : 'text-rose'
  return (
    <li className="flex items-start justify-between gap-3 text-xs">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium text-ink">{event.label}</span>
          <Pill tone={event.certainty === 'confirmed' ? 'good' : 'warn'}>
            {titleCase(event.certainty)}
          </Pill>
        </div>
        <p className="mt-0.5 text-ink-faint">
          {longDate(event.date)} · {event.source_note}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className={`num font-semibold ${tone}`}>
          {event.direction === 'inflow' ? '+' : '−'}
          {money(event.amount_original, event.currency_original)}
        </p>
        {event.currency_original !== currency && (
          <p className="num text-ink-faint">
            {event.amount_base === null
              ? 'no rate'
              : `≈ ${money(event.amount_base, currency)}`}
          </p>
        )}
      </div>
    </li>
  )
}

function AddBillCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('AED')
  const [dueDate, setDueDate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const response = await fetch('/api/bills', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Demo-User': getDemoUser(),
        },
        body: JSON.stringify({
          name,
          amount,
          currency,
          due_date: dueDate,
          category: 'uncategorized',
        }),
      })
      if (!response.ok) {
        const body = await response.json()
        throw new ApiError(
          body.errors?.[0]
            ? `${body.errors[0].field}: ${body.errors[0].message}`
            : (body.detail ?? 'Could not save the bill.'),
          response.status,
        )
      }
      setName('')
      setAmount('')
      setDueDate('')
      setSaved(true)
      onCreated()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not save the bill.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title="Track another bill"
      subtitle="Add an obligation the statement does not show yet, such as a fee you have been told about."
    >
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-5">
        <div className="sm:col-span-2">
          <label htmlFor="bill-name" className="label-xs">
            Name
          </label>
          <input
            id="bill-name"
            className="input mt-1.5"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Visa renewal fee"
            required
            maxLength={160}
          />
        </div>
        <div>
          <label htmlFor="bill-amount" className="label-xs">
            Amount
          </label>
          <input
            id="bill-amount"
            className="input mt-1.5"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="1200.00"
            inputMode="decimal"
            required
          />
        </div>
        <div>
          <label htmlFor="bill-currency" className="label-xs">
            Currency
          </label>
          <select
            id="bill-currency"
            className="input mt-1.5"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {['AED', 'USD', 'EUR', 'GBP', 'GHS', 'INR'].map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="bill-date" className="label-xs">
            Due date
          </label>
          <input
            id="bill-date"
            type="date"
            className="input mt-1.5"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
            required
          />
        </div>
        <div className="sm:col-span-5 flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Add bill'}
          </button>
          {saved && (
            <span role="status" className="text-xs text-accent">
              Bill added and the forecast has been refreshed.
            </span>
          )}
          {error && (
            <span role="alert" className="text-xs text-rose">
              {error}
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}
