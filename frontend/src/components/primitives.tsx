import type { ReactNode } from 'react'

import type { Basis } from '../lib/api'
import { VERDICT_LABEL, confidenceLabel } from '../lib/format'

/* ------------------------------------------------------------------ card */

export function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
  padded = true,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section className={`card ${padded ? 'card-pad' : ''} animate-fade-up ${className}`}>
      {(title || action) && (
        <header className="mb-5 flex items-start justify-between gap-4 border-b border-line/70 pb-4">
          <div className="min-w-0">
            {title && (
              <h2 className="font-display text-[1.35rem] leading-snug text-ink sm:text-[1.5rem]">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-1.5 text-[0.95rem] leading-relaxed text-ink-muted">{subtitle}</p>
            )}
          </div>
          {action && <div className="shrink-0 pt-1">{action}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

/* ------------------------------------------------------- basis / verdicts */

const BASIS_STYLE: Record<Basis, { label: string; className: string; title: string }> = {
  calculated: {
    label: 'Calculated',
    className: 'bg-accent-dim text-accent border-accent/25',
    title: 'Computed by the backend from recorded amounts and dates.',
  },
  estimate: {
    label: 'Estimate',
    className: 'bg-mist-dim text-mist border-mist/25',
    title:
      'A projection or converted figure. Depends on assumptions listed alongside it.',
  },
  suggestion: {
    label: 'Suggestion',
    className: 'bg-amber/10 text-amber border-amber/25',
    title: 'A recommendation for you to review. Nothing happens automatically.',
  },
  action: {
    label: 'Action',
    className: 'bg-sky/10 text-sky border-sky/25',
    title: 'A draft action awaiting your confirmation.',
  },
}

export function BasisTag({ basis, className = '' }: { basis: Basis; className?: string }) {
  const style = BASIS_STYLE[basis] ?? BASIS_STYLE.estimate
  return (
    <span
      title={style.title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px]
                  font-semibold uppercase tracking-[0.08em] ${style.className} ${className}`}
    >
      {style.label}
    </span>
  )
}

const VERDICT_STYLE: Record<string, string> = {
  likely_recurring: 'bg-accent-dim text-accent border-accent/25',
  possible_recurring: 'bg-amber/10 text-amber border-amber/25',
  insufficient_evidence: 'bg-surface-3 text-ink-faint border-line',
  likely: 'bg-rose/10 text-rose border-rose/25',
  possible: 'bg-amber/10 text-amber border-amber/25',
  informational: 'bg-sky/10 text-sky border-sky/25',
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs
                  font-medium ${VERDICT_STYLE[verdict] ?? VERDICT_STYLE.informational}`}
    >
      {VERDICT_LABEL[verdict] ?? verdict}
    </span>
  )
}

export function ConfidenceMeter({
  value,
  showLabel = true,
}: {
  value: number
  showLabel?: boolean
}) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100)
  const tone = pct >= 80 ? 'bg-accent' : pct >= 55 ? 'bg-amber' : 'bg-rose'
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1 w-14 overflow-hidden rounded-sm bg-surface-3"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Detection confidence ${pct}%`}
      >
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      {showLabel && (
        <span className="num text-xs text-ink-muted" title={confidenceLabel(value)}>
          {pct}%
        </span>
      )}
    </div>
  )
}

export function Pill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'
}) {
  const tones = {
    neutral: 'bg-surface-3 text-ink-muted border-line',
    good: 'bg-accent-dim text-accent border-accent/25',
    warn: 'bg-amber/10 text-amber border-amber/25',
    bad: 'bg-rose/10 text-rose border-rose/25',
    info: 'bg-sky/10 text-sky border-sky/25',
  }
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs
                  font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

/* ------------------------------------------------------------- app states */

export function Skeleton({ className = 'h-24' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />
}

export function LoadingPanel({ label = 'Loading' }: { label?: string }) {
  return (
    <div
      className="space-y-3"
      role="status"
      aria-label={label}
      aria-live="polite"
      aria-busy="true"
    >
      <span className="sr-only">{label}…</span>
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-28" />
      <Skeleton className="h-28" />
    </div>
  )
}

export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div role="alert" className="card card-pad border-rose/30 bg-rose/5 text-sm text-ink">
      <p className="font-semibold text-rose">Could not load this view</p>
      <p className="mt-1 text-ink-muted">{message}</p>
      {onRetry && (
        <button type="button" className="btn-ghost mt-4" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="rounded-xl border border-dashed border-line/80 bg-surface-2/30 px-6 py-12 text-center">
      <p className="font-display text-lg text-ink">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-muted">
        {description}
      </p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

/* ------------------------------------------------------------- stat card */

export function StatCard({
  label,
  value,
  sublabel,
  basis,
  tone = 'neutral',
  note,
  footer,
}: {
  label: string
  value: string
  sublabel?: string
  basis?: Basis
  tone?: 'neutral' | 'good' | 'warn' | 'bad'
  note?: string
  footer?: ReactNode
}) {
  const valueTone = {
    neutral: 'text-ink',
    good: 'text-accent',
    warn: 'text-amber',
    bad: 'text-rose',
  }[tone]

  return (
    <div className="relative overflow-hidden rounded-xl border border-line/80 bg-surface/80 p-5 animate-fade-up">
      <div
        className="pointer-events-none absolute inset-y-0 left-0 w-0.5 bg-accent/70"
        aria-hidden="true"
      />
      <div className="flex items-start justify-between gap-3 pl-2">
        <span className="label-xs">{label}</span>
        {basis && <BasisTag basis={basis} />}
      </div>
      <p className={`num mt-3 pl-2 text-[1.85rem] font-semibold leading-none sm:text-[2.05rem] ${valueTone}`}>
        {value}
      </p>
      {sublabel && <p className="mt-2 pl-2 text-[0.95rem] text-ink-muted">{sublabel}</p>}
      {note && <p className="mt-2 pl-2 text-sm leading-relaxed text-ink-faint">{note}</p>}
      {footer && <div className="mt-3 pl-2">{footer}</div>}
    </div>
  )
}

/* ------------------------------------------------------- evidence details */

export function EvidenceDisclosure({
  summary,
  children,
}: {
  summary: string
  children: ReactNode
}) {
  return (
    <details className="group mt-3">
      <summary
        className="cursor-pointer list-none text-sm font-semibold text-accent
                   hover:underline focus-visible:underline"
      >
        <span className="group-open:hidden">Show {summary}</span>
        <span className="hidden group-open:inline">Hide {summary}</span>
      </summary>
      <div className="mt-3 rounded-lg border border-line bg-surface-2/50 p-3">{children}</div>
    </details>
  )
}

export function DemoDataBanner({ label }: { label?: string }) {
  return (
    <p className="text-xs text-ink-faint">
      <span className="font-medium text-mist">Demo</span>
      {' · '}
      {label?.trim() || 'Synthetic data · not a live bank connection'}
    </p>
  )
}
