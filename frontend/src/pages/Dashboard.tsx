import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api } from '../lib/api'
import type { Recommendation } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { longDate, money, percent, shortDate, titleCase } from '../lib/format'
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

const HORIZONS = [30, 60, 90]

export default function Dashboard() {
  const [horizon, setHorizon] = useState(30)
  const dashboard = useApi(() => api.dashboard(horizon), [horizon])
  const recommendations = useApi(() => api.recommendations(6), [])

  if (dashboard.loading && !dashboard.data) return <LoadingPanel label="Loading dashboard" />
  if (dashboard.error)
    return <ErrorPanel message={dashboard.error} onRetry={dashboard.reload} />
  if (!dashboard.data) return null

  const d = dashboard.data
  const currency = d.user.base_currency
  const flow = d.cash_flow
  const flowEnd =
    flow.period?.end ??
    flow.series?.[flow.series.length - 1]?.date ??
    d.as_of
  const flowSeries = flow.series ?? []
  const excluded = flow.excluded_from_projection ?? []

  const chartData = flowSeries.map((point) => ({
    date: point.date,
    balance: point.balance,
    label: shortDate(point.date),
  }))

  const categories = d.spend_by_category_30d
    .filter((row) => row.amount_base !== null)
    .slice(0, 7)
    .map((row) => ({ name: titleCase(row.category), amount: row.amount_base as number }))

  return (
    <div className="space-y-8">
      <PageHeader
        title="Overview"
        lede={`${d.user.name} · ${d.user.study_country} · ${currency} · ${longDate(d.as_of)}`}
      >
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

      <DemoDataBanner label={d.data_source.label} />

      {(flow.shortfall_detected ||
        d.upcoming_bills.total_base > d.available_balance.amount) && (
        <div
          role="alert"
          className="border border-rose/30 border-l-[3px] border-l-rose bg-rose/[0.07] px-5 py-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 max-w-3xl">
              <p className="label-xs text-rose">Cash-flow alert</p>
              <p className="mt-2 font-display text-xl text-ink sm:text-2xl">
                {flow.shortfall_detected
                  ? `Shortfall of ${money(flow.largest_shortfall, currency)} on ${longDate(flow.first_shortfall_date)}`
                  : `Bills of ${money(d.upcoming_bills.total_base, currency)} exceed cash on hand`}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                {flow.shortfall_detected
                  ? `Projected low of ${money(flow.minimum_balance, currency)}. Cut a duplicate subscription and time remittances after local bills clear.`
                  : `Obligations in the next ${d.upcoming_bills.window_days} days outrun available balance. Hold or resize cross-border transfers until the gap closes.`}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link to="/bills" className="btn-primary text-sm">
                Review bills
              </Link>
              <Link to="/assistant" className="btn-ghost text-sm">
                Ask assistant
              </Link>
              <Link to="/cross-border" className="btn-ghost text-sm">
                Remittance routes
              </Link>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Available balance"
          value={money(d.available_balance.amount, currency)}
          sublabel={`Across ${d.available_balance.accounts.length} demo accounts`}
          basis={d.available_balance.basis}
          note={
            d.available_balance.excluded.length > 0
              ? `${d.available_balance.excluded.length} account balance(s) excluded: no exchange rate.`
              : undefined
          }
        />
        <StatCard
          label={`Bills due in ${d.upcoming_bills.window_days} days`}
          value={money(d.upcoming_bills.total_base, currency)}
          sublabel={`${d.upcoming_bills.count} scheduled obligations`}
          basis={d.upcoming_bills.basis}
          tone={d.upcoming_bills.total_base > d.available_balance.amount ? 'warn' : 'neutral'}
        />
        <StatCard
          label="Recurring per month"
          value={money(d.recurring_monthly.amount, currency)}
          sublabel={`${d.recurring_monthly.likely_count} likely · ${d.recurring_monthly.possible_count} possible`}
          basis={d.recurring_monthly.basis}
          note={d.recurring_monthly.note}
        />
        <StatCard
          label="Potential savings"
          value={money(d.potential_savings.amount, currency)}
          sublabel={`${d.potential_savings.option_count} options to review`}
          basis={d.potential_savings.basis}
          tone="good"
          note={d.potential_savings.note}
        />
      </div>

      {/* ------------------------------------------------------ cash flow */}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Projected cash flow"
          subtitle={`Day-by-day balance to ${longDate(flowEnd)}, combining confirmed bills, projected subscription charges and expected income.`}
          action={<BasisTag basis="estimate" />}
        >
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <defs>
                  <linearGradient id="balanceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3DCF9A" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#3DCF9A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#243830" vertical={false} strokeOpacity={0.7} />
                <XAxis
                  dataKey="label"
                  stroke="#73857C"
                  tick={{ fontSize: 11, fill: '#73857C' }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={28}
                />
                <YAxis
                  stroke="#73857C"
                  tick={{ fontSize: 11, fill: '#73857C' }}
                  tickLine={false}
                  axisLine={false}
                  width={64}
                  tickFormatter={(value: number) => money(value, undefined, { compact: true })}
                />
                <Tooltip content={<FlowTooltip currency={currency} />} />
                <ReferenceLine y={0} stroke="#E8898F" strokeDasharray="3 5" />
                <Area
                  type="monotone"
                  dataKey="balance"
                  stroke="#3DCF9A"
                  strokeWidth={1.75}
                  fill="url(#balanceFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-4">
            {[
              ['Opening', money(flow.opening_balance, currency)],
              ['Expected in', money(flow.total_inflow, currency)],
              ['Expected out', money(flow.total_outflow, currency)],
              ['Projected close', money(flow.closing_balance, currency)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="label-xs">{label}</dt>
                <dd className="num mt-1 text-sm font-semibold">{value}</dd>
              </div>
            ))}
          </dl>

          <EvidenceDisclosure summary="forecast assumptions">
            <ul className="space-y-1.5 text-xs leading-relaxed text-ink-muted">
              {flow.assumptions.map((assumption) => (
                <li key={assumption}>• {assumption}</li>
              ))}
            </ul>
            {excluded.length > 0 && (
              <div className="mt-3 border-t border-line pt-3">
                <p className="text-xs font-semibold text-amber">
                  Excluded from the running balance
                </p>
                <ul className="mt-1.5 space-y-1 text-xs text-ink-muted">
                  {excluded.map((item, index) => (
                    <li key={`${item.item}-${index}`}>
                      • {item.item}
                      {item.amount_original != null
                        ? ` — ${money(item.amount_original, item.currency)}.`
                        : '.'}{' '}
                      {item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </EvidenceDisclosure>
        </Card>

        <div className="space-y-6">
          <Card
            title="Next obligations"
            subtitle="Confirmed bills with a known due date."
            action={<BasisTag basis="calculated" />}
          >
            {d.upcoming_bills.next.length === 0 ? (
              <EmptyState
                title="Nothing due in this window"
                description="No bills fall inside the selected horizon."
              />
            ) : (
              <ul className="divide-y divide-line">
                {d.upcoming_bills.next.map((bill) => (
                  <li key={bill.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{bill.name}</p>
                      <p className="mt-0.5 text-xs text-ink-faint">
                        {longDate(bill.due_date)} · in {bill.days_until_due} days
                        {bill.autopay && ' · autopay'}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="num text-sm font-semibold">
                        {money(bill.amount, bill.currency)}
                      </p>
                      {bill.currency !== currency && (
                        <p className="num text-xs text-ink-faint">
                          ≈ {money(bill.amount_base, currency)}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Link
              to="/bills"
              className="mt-4 inline-block text-xs font-semibold text-accent hover:underline"
            >
              View all bills and forecasts →
            </Link>
          </Card>

          <Card
            title="Price change alerts"
            subtitle="Detected shifts in recurring charge amounts."
            action={<BasisTag basis="calculated" />}
          >
            {d.price_change_alerts.length === 0 ? (
              <EmptyState
                title="No price changes detected"
                description="Every detected subscription has been charging a steady amount."
              />
            ) : (
              <ul className="space-y-3">
                {d.price_change_alerts.slice(0, 4).map((alert, index) => (
                  <li
                    key={`${alert.merchant}-${alert.effective_date}-${index}`}
                    className="rounded-xl border border-line bg-surface-2/60 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-medium">{alert.merchant}</p>
                      <Pill tone={alert.direction === 'increase' ? 'bad' : 'good'}>
                        {alert.change_pct > 0 ? '+' : ''}
                        {percent(alert.change_pct, 1)}
                      </Pill>
                    </div>
                    <p className="num mt-1 text-xs text-ink-muted">
                      {money(alert.previous_amount, alert.currency)} →{' '}
                      {money(alert.new_amount, alert.currency)} on{' '}
                      {longDate(alert.effective_date)}
                    </p>
                    <p className="mt-1 text-[11px] text-ink-faint">
                      {alert.confirmed_by_later_charge
                        ? 'Confirmed by a later charge at the new amount.'
                        : 'Seen once so far, so this may not be permanent.'}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {/* ------------------------------------------- spend + suggestions */}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card
          title="Spending by category"
          subtitle="Last 30 days, converted to your reporting currency."
          action={<BasisTag basis="calculated" />}
        >
          {categories.length === 0 ? (
            <EmptyState
              title="No categorised spending"
              description="Import a statement to see where your money goes."
            />
          ) : (
            <div className="h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={categories}
                  layout="vertical"
                  margin={{ top: 0, right: 12, bottom: 0, left: 8 }}
                >
                  <CartesianGrid stroke="#243830" horizontal={false} />
                  <XAxis
                    type="number"
                    stroke="#73857C"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value: number) =>
                      money(value, undefined, { compact: true })
                    }
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#93AFA4"
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={86}
                  />
                  <Tooltip
                    cursor={{ fill: '#10241D' }}
                    contentStyle={TOOLTIP_STYLE}
                    formatter={(value: number) => [money(value, currency), 'Spent']}
                  />
                  <Bar dataKey="amount" radius={[0, 6, 6, 0]}>
                    {categories.map((entry, index) => (
                      <Cell
                        key={entry.name}
                        fill={index % 2 === 0 ? '#3DCF9A' : '#C9B8A0'}
                        fillOpacity={0.85}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card
          className="xl:col-span-2"
          title="Ranked recommendations"
          subtitle="Ordered by urgency, estimated impact, confidence and your stated priorities."
        >
          {recommendations.loading && <LoadingPanel label="Loading recommendations" />}
          {recommendations.error && (
            <ErrorPanel message={recommendations.error} onRetry={recommendations.reload} />
          )}
          {recommendations.data && recommendations.data.count === 0 && (
            <EmptyState
              title="Nothing needs your attention"
              description="No shortfalls, duplicates or price rises were found in the current data."
            />
          )}
          {recommendations.data && recommendations.data.count > 0 && (
            <ul className="space-y-3">
              {recommendations.data.recommendations.map((item) => (
                <RecommendationRow key={item.key} item={item} />
              ))}
            </ul>
          )}
        </Card>
      </div>
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

function FlowTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean
  payload?: { payload: { date: string; balance: number } }[]
  currency: string
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-xs">
      <p className="font-semibold text-ink">{longDate(point.date)}</p>
      <p className={`num mt-0.5 ${point.balance < 0 ? 'text-rose' : 'text-accent'}`}>
        {money(point.balance, currency)}
      </p>
    </div>
  )
}

function RecommendationRow({ item }: { item: Recommendation }) {
  const tone =
    item.category === 'cash_flow_risk'
      ? 'bad'
      : item.category === 'bill_due_soon'
        ? 'warn'
        : 'info'

  return (
    <li className="rounded-xl border border-line bg-surface-2/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{item.title}</h3>
            <BasisTag basis={item.basis} />
            <Pill tone={tone}>{titleCase(item.category)}</Pill>
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{item.summary}</p>
        </div>
        {item.estimated_impact_base !== null && (
          <div className="shrink-0 text-right">
            <p className="num text-base font-semibold text-accent">
              {money(item.estimated_impact_base, item.currency)}
            </p>
            <p className="text-[11px] text-ink-faint">
              {item.category === 'cash_flow_risk' ? 'shortfall' : 'per month'}
            </p>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-ink-faint">
        <span>Urgency {Math.round(item.urgency * 100)}%</span>
        <span>Confidence {Math.round(item.confidence * 100)}%</span>
        {item.priority_alignment > 0 && (
          <span className="text-accent">Matches a stated priority</span>
        )}
        {item.suggested_action && <span>Needs your approval before anything happens</span>}
      </div>

      <EvidenceDisclosure summary="basis and caveats">
        <p className="text-xs leading-relaxed text-ink-muted">
          <span className="font-semibold text-ink">How this figure is derived: </span>
          {item.impact_basis}
        </p>
        {item.caveats.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs leading-relaxed text-amber">
            {item.caveats.map((caveat) => (
              <li key={caveat}>• {caveat}</li>
            ))}
          </ul>
        )}
      </EvidenceDisclosure>
    </li>
  )
}
