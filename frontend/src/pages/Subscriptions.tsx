import { useState } from 'react'

import { api, ApiError } from '../lib/api'
import type { ActionPreview, DuplicateFinding, Subscription } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { longDate, money, percent, titleCase } from '../lib/format'
import { PageHeader } from '../components/PageHeader'
import {
  BasisTag,
  Card,
  ConfidenceMeter,
  EmptyState,
  ErrorPanel,
  EvidenceDisclosure,
  LoadingPanel,
  Pill,
  StatCard,
  VerdictBadge,
} from '../components/primitives'

type Filter = 'all' | 'likely' | 'possible' | 'dormant'

export default function Subscriptions() {
  const [filter, setFilter] = useState<Filter>('all')
  const [preview, setPreview] = useState<ActionPreview | null>(null)
  const analysis = useApi(() => api.subscriptions(0, true), [])

  if (analysis.loading && !analysis.data)
    return <LoadingPanel label="Analysing subscriptions" />
  if (analysis.error) return <ErrorPanel message={analysis.error} onRetry={analysis.reload} />
  if (!analysis.data) return null

  const { summary, subscriptions, duplicate_findings, methodology, base_currency } =
    analysis.data

  const filtered = subscriptions.filter((sub) => {
    if (filter === 'all') return true
    if (filter === 'dormant') return sub.status === 'dormant'
    if (filter === 'likely') return sub.verdict === 'likely_recurring'
    return sub.verdict === 'possible_recurring'
  })

  const counts: Record<Filter, number> = {
    all: subscriptions.length,
    likely: subscriptions.filter((s) => s.verdict === 'likely_recurring').length,
    possible: subscriptions.filter((s) => s.verdict === 'possible_recurring').length,
    dormant: subscriptions.filter((s) => s.status === 'dormant').length,
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Subscriptions"
        lede="Recurring charges inferred from history — each series shows the evidence and how confident the detection is."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Estimated monthly cost"
          value={money(summary.estimated_monthly_total_base, base_currency)}
          sublabel={`${money(summary.estimated_annual_total_base, base_currency)} a year`}
          basis="estimate"
        />
        <StatCard
          label="Active subscriptions"
          value={String(summary.active_count)}
          sublabel={`${summary.likely_count} likely · ${summary.possible_count} possible`}
          basis="calculated"
        />
        <StatCard
          label="Duplicate & overlap findings"
          value={String(summary.duplicate_findings)}
          sublabel="Review before cancelling anything"
          basis="calculated"
          tone={summary.duplicate_findings > 0 ? 'warn' : 'neutral'}
        />
        <StatCard
          label="Price changes detected"
          value={String(summary.price_changes_detected)}
          sublabel="Across all detected series"
          basis="calculated"
        />
      </div>

      {duplicate_findings.length > 0 && (
        <Card
          title="Duplicates and overlaps"
          subtitle="Grouped by what the signal actually means. Only the first group is treated as a probable mistake."
        >
          <ul className="space-y-3">
            {duplicate_findings.map((finding, index) => (
              <DuplicateCard
                key={`${finding.finding_type}-${finding.merchants.join()}-${index}`}
                finding={finding}
                baseCurrency={base_currency}
                onPreview={setPreview}
              />
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Detected recurring payments"
        subtitle={methodology}
        action={
          <div
            className="flex flex-wrap gap-1 rounded-xl border border-line bg-surface-2 p-1"
            role="group"
            aria-label="Filter subscriptions"
          >
            {(['all', 'likely', 'possible', 'dormant'] as Filter[]).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={filter === option}
                onClick={() => setFilter(option)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                  filter === option
                    ? 'bg-accent-dim text-accent'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {option} ({counts[option]})
              </button>
            ))}
          </div>
        }
      >
        {filtered.length === 0 ? (
          <EmptyState
            title="Nothing matches this filter"
            description="Try a different filter, or import more transaction history so the detector has more to work with."
          />
        ) : (
          <ul className="space-y-3">
            {filtered.map((sub) => (
              <SubscriptionRow
                key={`${sub.merchant}-${sub.account_id}-${sub.currency}`}
                sub={sub}
                baseCurrency={base_currency}
                onPreview={setPreview}
              />
            ))}
          </ul>
        )}

        {summary.amounts_excluded_for_missing_rates.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber/25 bg-amber/5 p-3 text-xs text-amber">
            <p className="font-semibold">Excluded from the monthly total</p>
            <ul className="mt-1 space-y-1">
              {summary.amounts_excluded_for_missing_rates.map((item) => (
                <li key={item.merchant}>
                  • {item.merchant}: {item.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {preview && (
        <CancellationDialog
          preview={preview}
          onClose={() => setPreview(null)}
          onDone={() => {
            setPreview(null)
            analysis.reload()
          }}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ rows */

function SubscriptionRow({
  sub,
  baseCurrency,
  onPreview,
}: {
  sub: Subscription
  baseCurrency: string
  onPreview: (preview: ActionPreview) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestChange = sub.price_changes.at(-1)

  async function startPreview() {
    setBusy(true)
    setError(null)
    try {
      onPreview(await api.previewAction('cancel_subscription', sub.merchant))
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not build a preview.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="rounded-xl border border-line bg-surface-2/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{sub.merchant}</h3>
            <VerdictBadge verdict={sub.verdict} />
            {sub.status === 'dormant' && <Pill>Appears cancelled</Pill>}
            {sub.service_family && <Pill>{titleCase(sub.service_family)}</Pill>}
          </div>
          <p className="mt-1.5 text-xs text-ink-muted">
            {titleCase(sub.cadence)} · {sub.occurrence_count} charges observed ·{' '}
            {sub.next_expected_date
              ? `next expected ${longDate(sub.next_expected_date)}`
              : `last charged ${longDate(sub.last_seen)}`}
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="num text-sm font-semibold">
              {money(sub.latest_amount, sub.currency)}
            </p>
            <p className="num text-xs text-ink-faint">
              ≈ {money(sub.monthly_equivalent_base, baseCurrency)}/mo
            </p>
          </div>
          <button
            type="button"
            className="btn-ghost px-3 py-1.5 text-xs"
            onClick={startPreview}
            disabled={busy}
          >
            {busy ? 'Preparing…' : 'Preview cancellation'}
          </button>
        </div>
      </div>

      {latestChange && (
        <p className="num mt-2 text-xs text-amber">
          Price {latestChange.direction}: {money(latestChange.previous_amount, latestChange.currency)}{' '}
          → {money(latestChange.new_amount, latestChange.currency)} on{' '}
          {longDate(latestChange.effective_date)} ({percent(latestChange.change_pct, 1)})
        </p>
      )}

      {error && (
        <p role="alert" className="mt-2 text-xs text-rose">
          {error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-4">
        <ConfidenceMeter value={sub.confidence} />
        <span className="text-[11px] text-ink-faint">
          Timing regularity {Math.round(sub.interval_regularity * 100)}% · amount stability{' '}
          {Math.round(sub.amount_stability * 100)}%
        </span>
      </div>

      <EvidenceDisclosure summary={`the ${sub.evidence.length} charges behind this`}>
        <ul className="mb-3 space-y-1 text-xs text-ink-muted">
          {sub.reasons.map((reason) => (
            <li key={reason}>• {reason}</li>
          ))}
        </ul>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-faint">
              <tr>
                <th className="pb-2 pr-4 font-medium">Date</th>
                <th className="pb-2 pr-4 font-medium">Amount</th>
                <th className="pb-2 font-medium">Statement description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sub.evidence.map((row) => (
                <tr key={row.transaction_id}>
                  <td className="py-1.5 pr-4 whitespace-nowrap">{longDate(row.date)}</td>
                  <td className="num py-1.5 pr-4 whitespace-nowrap">
                    {money(row.amount, row.currency)}
                  </td>
                  <td className="py-1.5 text-ink-faint">{row.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sub.conversion.rate_date && (
          <p className="mt-3 border-t border-line pt-2 text-[11px] text-ink-faint">
            Monthly equivalent converted at {sub.conversion.rate} ({sub.currency}→
            {baseCurrency}) dated {longDate(sub.conversion.rate_date)}, source{' '}
            {sub.conversion.rate_source}
            {sub.conversion.is_simulated_rate && ' — simulated demo rate'}.
          </p>
        )}
      </EvidenceDisclosure>
    </li>
  )
}

function DuplicateCard({
  finding,
  baseCurrency,
  onPreview,
}: {
  finding: DuplicateFinding
  baseCurrency: string
  onPreview: (preview: ActionPreview) => void
}) {
  const [busy, setBusy] = useState(false)

  async function startPreview() {
    setBusy(true)
    try {
      onPreview(await api.previewAction('cancel_subscription', finding.merchants[0]))
    } catch {
      /* surfaced by the row-level control instead */
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="rounded-xl border border-line bg-surface-2/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">{finding.title}</h3>
            <VerdictBadge verdict={finding.verdict} />
            <Pill>{titleCase(finding.finding_type)}</Pill>
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{finding.detail}</p>
        </div>
        {finding.estimated_redundant_monthly !== null && (
          <div className="shrink-0 text-right">
            <p className="num text-sm font-semibold text-accent">
              {money(finding.estimated_redundant_monthly, finding.currency)}
            </p>
            <p className="text-[11px] text-ink-faint">potential overlap / month</p>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4">
        <ConfidenceMeter value={finding.confidence} />
        {finding.finding_type !== 'double_charge_in_cycle' && (
          <button
            type="button"
            className="btn-ghost px-3 py-1.5 text-xs"
            onClick={startPreview}
            disabled={busy}
          >
            {busy ? 'Preparing…' : `Preview cancelling ${finding.merchants[0]}`}
          </button>
        )}
      </div>

      <p className="mt-3 rounded-lg border border-amber/20 bg-amber/5 px-3 py-2 text-xs leading-relaxed text-amber">
        {finding.caveat}
      </p>

      <EvidenceDisclosure summary="the charges behind this finding">
        <pre className="overflow-x-auto text-[11px] leading-relaxed text-ink-muted">
          {JSON.stringify(finding.evidence, null, 2)}
        </pre>
        <p className="mt-2 text-[11px] text-ink-faint">
          Amounts shown in {finding.currency}; reporting currency is {baseCurrency}.
        </p>
      </EvidenceDisclosure>
    </li>
  )
}

/* ---------------------------------------------------- authorization flow */

function CancellationDialog({
  preview,
  onClose,
  onDone,
}: {
  preview: ActionPreview
  onClose: () => void
  onDone: () => void
}) {
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function decide(decision: 'approve' | 'decline') {
    setBusy(true)
    setError(null)
    try {
      const updated = await api.decideAction(preview.id, decision, confirmation)
      setResult(updated.status)
      setTimeout(onDone, 1400)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not record a decision.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cancel-dialog-title"
    >
      <div className="w-full max-w-lg rounded-2xl border border-line bg-surface p-6">
        <h2 id="cancel-dialog-title" className="text-lg font-semibold">
          Review before anything happens
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          This is a preview of cancelling <strong>{preview.target_label}</strong>.
        </p>

        <pre className="mt-4 whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-3 text-xs leading-relaxed text-ink-muted">
          {preview.summary}
        </pre>

        {preview.estimated_monthly_impact && (
          <p className="num mt-3 text-sm">
            Estimated monthly impact:{' '}
            <span className="font-semibold text-accent">
              {money(preview.estimated_monthly_impact, preview.currency)}
            </span>{' '}
            <BasisTag basis="estimate" className="ml-1" />
          </p>
        )}

        {result ? (
          <p role="status" className="mt-5 text-sm font-medium text-accent">
            Recorded: {titleCase(result)}. No cancellation has been sent to the merchant.
          </p>
        ) : (
          <>
            <label
              htmlFor="confirm-input"
              className="mt-5 block text-xs font-medium text-ink-muted"
            >
              To approve, type <strong className="text-ink">{preview.target_label}</strong>{' '}
              exactly.
            </label>
            <input
              id="confirm-input"
              className="input mt-2"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder={preview.target_label}
              autoComplete="off"
            />

            {error && (
              <p role="alert" className="mt-2 text-xs text-rose">
                {error}
              </p>
            )}

            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
                Close
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => decide('decline')}
                disabled={busy}
              >
                Decline
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={() => decide('approve')}
                disabled={busy || confirmation.trim() === ''}
              >
                Approve cancellation plan
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
