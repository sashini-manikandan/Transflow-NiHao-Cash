/** Display helpers. No financial logic lives here — only formatting. */

export function money(
  amount: number | string | null | undefined,
  currency?: string | null,
  options: { compact?: boolean; signed?: boolean } = {},
): string {
  if (amount === null || amount === undefined || amount === '') return '—'
  const value = typeof amount === 'string' ? Number(amount) : amount
  if (Number.isNaN(value)) return '—'

  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: options.compact ? 0 : 2,
    maximumFractionDigits: options.compact ? 0 : 2,
    notation: options.compact && Math.abs(value) >= 10000 ? 'compact' : 'standard',
  }).format(Math.abs(value))

  // The sign belongs with the number, not in front of the currency code.
  const sign = value < 0 ? '−' : options.signed && value > 0 ? '+' : ''
  return `${currency ? `${currency} ` : ''}${sign}${formatted}`
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(digits)}%`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function relativeDays(days: number): string {
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days < 0) return `${Math.abs(days)} days ago`
  return `in ${days} days`
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

/** Verdict vocabulary shared by the detector and the UI. */
export const VERDICT_LABEL: Record<string, string> = {
  likely_recurring: 'Likely subscription',
  possible_recurring: 'Possible subscription',
  insufficient_evidence: 'Not enough evidence',
  likely: 'Likely',
  possible: 'Possible',
  informational: 'Worth reviewing',
}

export function confidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return 'High confidence'
  if (confidence >= 0.6) return 'Moderate confidence'
  if (confidence >= 0.4) return 'Low confidence'
  return 'Very low confidence'
}
