import { useState, type FormEvent } from 'react'
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, ApiError } from '../lib/api'
import type { ImportResult, RemittanceSim } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { longDate, money, shortDate } from '../lib/format'
import { PageHeader } from '../components/PageHeader'
import {
  BasisTag,
  Card,
  DemoDataBanner,
  EmptyState,
  ErrorPanel,
  EvidenceDisclosure,
  LoadingPanel,
  Pill,
  StatCard,
} from '../components/primitives'

const SLICE_COLORS = ['#3DCF9A', '#C9B8A0', '#7EB8C9', '#E0A84A', '#E8898F', '#5E9E8A']
const PERIODS = [3, 6, 12]

export default function CrossBorder() {
  const [months, setMonths] = useState(6)
  const [rateQuote, setRateQuote] = useState('GHS')

  const analysis = useApi(() => api.currency(months), [months])
  const rates = useApi(() => api.rates(rateQuote, 24), [rateQuote])

  if (analysis.loading && !analysis.data)
    return <LoadingPanel label="Analysing currency costs" />
  if (analysis.error) return <ErrorPanel message={analysis.error} onRetry={analysis.reload} />
  if (!analysis.data) return null

  const a = analysis.data
  const base = a.base_currency
  const foreign = a.by_currency.filter((row) => !row.is_base_currency && row.total_base > 0)

  const rateSeries = [...(rates.data?.rates ?? [])]
    .reverse()
    .map((row) => ({ date: row.as_of_date, label: shortDate(row.as_of_date), rate: row.rate }))

  return (
    <div className="space-y-8">
      <PageHeader
        title="Cross-border"
        lede="Amounts stay in the currency they happened in. Reporting figures use a dated rate, shown beside every conversion."
      >
        <div
          className="flex items-center gap-0.5 rounded-lg border border-line/80 bg-surface/80 p-1"
          role="group"
          aria-label="Analysis period"
        >
          {PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={months === value}
              onClick={() => setMonths(value)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                months === value ? 'bg-accent-dim text-accent' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {value}m
            </button>
          ))}
        </div>
      </PageHeader>

      <DemoDataBanner label="All exchange rates in this demo are simulated and labelled as such. They are not live market quotes." />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Foreign-currency spend"
          value={money(a.summary.foreign_currency_spend_base, base)}
          sublabel={`over ${months} months`}
          basis="estimate"
          note="Converted with dated simulated rates."
        />
        <StatCard
          label="Monthly average"
          value={money(a.summary.foreign_spend_monthly_average_base, base)}
          sublabel="foreign-currency outflow"
          basis="estimate"
        />
        <StatCard
          label="Disclosed transfer fees"
          value={money(a.summary.disclosed_fees_base, base)}
          sublabel={`${a.summary.disclosed_fee_transaction_count} transfers with a stated fee`}
          basis="calculated"
          tone="warn"
        />
        <StatCard
          label="Could not convert"
          value={String(a.summary.unconvertible_transaction_count)}
          sublabel="transactions with no stored rate"
          basis="calculated"
          tone={a.summary.unconvertible_transaction_count > 0 ? 'warn' : 'good'}
          note="Left out of totals rather than estimated."
        />
      </div>

      <RemittanceSimPanel baseCurrency={base} />

      <div className="grid gap-6 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title="Spending by currency"
          subtitle="Each row shows the exact rate, date and source used for the conversion."
          action={<BasisTag basis="calculated" />}
        >
          {a.by_currency.length === 0 ? (
            <EmptyState
              title="No spending in this period"
              description="Widen the period or import a statement."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-ink-faint">
                    <th className="pb-2.5 pr-4 text-xs font-medium">Currency</th>
                    <th className="pb-2.5 pr-4 text-xs font-medium">Spent</th>
                    <th className="pb-2.5 pr-4 text-xs font-medium">In {base}</th>
                    <th className="pb-2.5 pr-4 text-xs font-medium">Fees</th>
                    <th className="pb-2.5 text-xs font-medium">Rate used</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {a.by_currency.map((row) => (
                    <tr key={row.currency}>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{row.currency}</span>
                          {row.is_base_currency && <Pill tone="good">Base</Pill>}
                          {row.unconverted_count > 0 && (
                            <Pill tone="warn">{row.unconverted_count} unconverted</Pill>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-ink-faint">
                          {row.transaction_count} transactions
                        </p>
                      </td>
                      <td className="num py-3 pr-4">
                        {money(row.total_original, row.currency)}
                      </td>
                      <td className="num py-3 pr-4">
                        {row.converted_count === 0 ? '—' : money(row.total_base, base)}
                      </td>
                      <td className="num py-3 pr-4">
                        {row.disclosed_fees_original > 0
                          ? money(row.disclosed_fees_original, row.currency)
                          : '—'}
                      </td>
                      <td className="py-3 text-xs text-ink-muted">
                        {row.is_base_currency ? (
                          'no conversion needed'
                        ) : row.latest_rate === null ? (
                          <span className="text-amber">no rate stored</span>
                        ) : (
                          <>
                            <span className="num">{row.latest_rate}</span>
                            <br />
                            <span className="text-ink-faint">
                              {longDate(row.rate_date)} ·{' '}
                              {row.is_simulated_rate ? 'simulated' : 'live'}
                            </span>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {a.unconvertible_transactions.length > 0 && (
            <div className="mt-4 rounded-xl border border-amber/25 bg-amber/5 p-3">
              <p className="text-xs font-semibold text-amber">
                Transactions left out of every total
              </p>
              <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-ink-muted">
                {a.unconvertible_transactions.map((item) => (
                  <li key={item.transaction_id}>
                    • {longDate(item.date)} · {item.merchant} ·{' '}
                    {money(item.amount, item.currency)} — {item.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card
          className="xl:col-span-2"
          title="Share of foreign spend"
          subtitle="Converted amounts only."
          action={<BasisTag basis="estimate" />}
        >
          {foreign.length === 0 ? (
            <EmptyState
              title="No foreign-currency spending"
              description="Everything in this period was in your reporting currency."
            />
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={foreign.map((row) => ({
                      name: row.currency,
                      value: row.total_base,
                    }))}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={56}
                    outerRadius={92}
                    paddingAngle={3}
                    stroke="none"
                  >
                    {foreign.map((row, index) => (
                      <Cell
                        key={row.currency}
                        fill={SLICE_COLORS[index % SLICE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(value: number, name: string) => [money(value, base), name]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <ul className="mt-2 space-y-1.5">
            {foreign.map((row, index) => (
              <li key={row.currency} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: SLICE_COLORS[index % SLICE_COLORS.length] }}
                    aria-hidden="true"
                  />
                  {row.currency}
                </span>
                <span className="num text-ink-muted">{money(row.total_base, base)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title="Rate history"
          subtitle="The exact stored rates this app used, so any figure can be traced back."
          action={
            <select
              className="input w-28 py-1.5 text-xs"
              value={rateQuote}
              onChange={(event) => setRateQuote(event.target.value)}
              aria-label="Currency pair"
            >
              {['GHS', 'AED', 'EUR', 'GBP', 'INR'].map((code) => (
                <option key={code} value={code}>
                  USD/{code}
                </option>
              ))}
            </select>
          }
        >
          {rates.loading && <LoadingPanel label="Loading rates" />}
          {rates.error && <ErrorPanel message={rates.error} onRetry={rates.reload} />}
          {rateSeries.length > 0 && (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={rateSeries}
                  margin={{ top: 8, right: 8, bottom: 0, left: -8 }}
                >
                  <CartesianGrid stroke="#243830" vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke="#73857C"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={28}
                  />
                  <YAxis
                    stroke="#73857C"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    labelFormatter={(_l, payload) =>
                      payload?.[0] ? longDate(payload[0].payload.date) : ''
                    }
                    formatter={(value: number) => [value, `USD/${rateQuote}`]}
                  />
                  <Line
                    type="monotone"
                    dataKey="rate"
                    stroke="#C9B8A0"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-2 text-[11px] text-ink-faint">
            {rates.data?.all_rates_simulated
              ? 'Every rate shown is simulated demo data.'
              : 'Mixed rate sources.'}
          </p>
        </Card>

        <Card
          className="xl:col-span-2"
          title="Rate sensitivity"
          subtitle="A what-if on past spending, not a prediction of future rates."
          action={<BasisTag basis="estimate" />}
        >
          <ul className="space-y-2.5">
            {a.fx_sensitivity_whatif.map((scenario) => (
              <li
                key={scenario.scenario}
                className="flex items-center justify-between rounded-xl border border-line bg-surface-2/60 px-3 py-2.5 text-sm"
              >
                <span className="text-ink-muted">{scenario.scenario}</span>
                <span
                  className={`num font-semibold ${
                    scenario.monthly_impact_base > 0 ? 'text-rose' : 'text-accent'
                  }`}
                >
                  {money(scenario.monthly_impact_base, base, { signed: true })}/mo
                </span>
              </li>
            ))}
          </ul>
          <EvidenceDisclosure summary="how these figures are limited">
            <ul className="space-y-1.5 text-xs leading-relaxed text-ink-muted">
              {a.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          </EvidenceDisclosure>
        </Card>
      </div>

      <ImportCard onImported={analysis.reload} />
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

function ImportCard({ onImported }: { onImported: () => void }) {
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const imported = await api.importCsv(file)
      setResult(imported)
      onImported()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Import failed.')
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  return (
    <Card
      title="Import transactions"
      subtitle="Upload a CSV with date, description, amount and currency columns. Rows that fail validation are reported individually; the rest still import."
      action={
        <a href={api.sampleCsvUrl} download="billwise-sample.csv" className="btn-ghost text-xs">
          Download sample CSV
        </a>
      }
    >
      <label
        htmlFor="csv-input"
        className="flex cursor-pointer flex-col items-center justify-center rounded-xl
                   border border-dashed border-line bg-surface-2/40 px-6 py-8 text-center
                   transition-colors hover:border-accent/40 hover:bg-surface-2"
      >
        <span className="text-sm font-medium text-ink">
          {busy ? 'Importing…' : 'Choose a CSV file'}
        </span>
        <span className="mt-1 text-xs text-ink-faint">
          Up to 2 MB and 2,000 rows. Descriptions are stored as text only.
        </span>
        <input
          id="csv-input"
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={handleFile}
          disabled={busy}
        />
      </label>

      {error && (
        <p role="alert" className="mt-3 rounded-xl border border-rose/30 bg-rose/5 p-3 text-xs text-rose">
          {error}
        </p>
      )}

      {result && (
        <div role="status" className="mt-3 rounded-xl border border-line bg-surface-2/60 p-3">
          <p className="text-sm font-medium text-accent">
            Imported {result.imported} of {result.total_rows} rows
            {result.skipped > 0 && `, skipped ${result.skipped}`}.
          </p>
          {result.new_merchants.length > 0 && (
            <p className="mt-1 text-xs text-ink-muted">
              New merchants recognised: {result.new_merchants.join(', ')}.
            </p>
          )}
          {result.errors.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-amber">
              {result.errors.map((item) => (
                <li key={item.row}>
                  • Row {item.row}: {item.error}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-ink-faint">{result.warning}</p>
        </div>
      )}
    </Card>
  )
}

function RemittanceSimPanel({ baseCurrency }: { baseCurrency: string }) {
  const [amount, setAmount] = useState('1100')
  const [destination, setDestination] = useState('GHS')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [quote, setQuote] = useState<RemittanceSim | null>(null)

  async function runCompare(event: FormEvent) {
    event.preventDefault()
    const parsed = Number(amount)
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setError('Enter a positive send amount.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api.remittanceSim(parsed, destination, baseCurrency)
      setQuote(result)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Simulation failed.')
      setQuote(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title="Remittance route simulation"
      subtitle="Compare a traditional remittance rail with a USDC stablecoin path. Neither route executes a transfer."
      action={<BasisTag basis="estimate" />}
    >
      <form
        onSubmit={runCompare}
        className="flex flex-wrap items-end gap-3 border-b border-line pb-4"
      >
        <label className="space-y-1">
          <span className="label-xs">Send amount ({baseCurrency})</span>
          <input
            className="w-36 rounded-lg border border-line bg-canvas px-3 py-2 text-sm"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
          />
        </label>
        <label className="space-y-1">
          <span className="label-xs">Destination</span>
          <select
            className="rounded-lg border border-line bg-canvas px-3 py-2 text-sm"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
          >
            <option value="GHS">GHS (Ghana)</option>
            <option value="INR">INR (India)</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Simulating…' : 'Compare routes'}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-3 text-sm text-rose">
          {error}
        </p>
      )}

      {quote && (
        <div className="mt-4 space-y-4">
          <p className="rounded-xl border border-amber/30 bg-amber/5 px-3 py-2 text-xs text-amber">
            {quote.disclaimer}
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {quote.routes.map((route) => (
              <div
                key={route.route}
                className={`rounded-xl border p-4 ${
                  route.route === 'stablecoin_usdc'
                    ? 'border-violet/40 bg-violet/5'
                    : 'border-line bg-surface-2/40'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-ink">{route.label}</p>
                  {route.route === 'stablecoin_usdc' && (
                    <Pill tone="info">USDC sim</Pill>
                  )}
                </div>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-ink-muted">Fee ({quote.reporting_currency})</dt>
                    <dd className="num font-medium">{money(route.fee_base, quote.reporting_currency)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-ink-muted">Recipient gets</dt>
                    <dd className="num font-medium">
                      {route.amount_received_dest == null
                        ? 'rate unavailable'
                        : money(route.amount_received_dest, route.destination_currency)}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-ink-muted">ETA</dt>
                    <dd>{route.eta_business_days} business days</dd>
                  </div>
                </dl>
                <ul className="mt-3 space-y-1 text-[11px] leading-relaxed text-ink-faint">
                  {route.notes.map((note) => (
                    <li key={note}>• {note}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          {quote.fee_savings_base_if_stablecoin != null && (
            <p className="text-sm text-ink-muted">
              Fee difference if choosing the USDC simulation:{' '}
              <span className="num font-semibold text-accent">
                {money(quote.fee_savings_base_if_stablecoin, quote.reporting_currency)}
              </span>{' '}
              (positive means the stablecoin route looks cheaper on fees in this demo).
              Nothing is executable — review only.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
