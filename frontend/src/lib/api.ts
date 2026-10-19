/**
 * Backend client.
 *
 * The browser never holds an API key or a database credential. Every figure
 * rendered by the app is fetched from these endpoints; nothing is calculated
 * here beyond formatting.
 */

const DEMO_USER_STORAGE_KEY = 'billwise.demoUser'
const DEMO_SESSION_KEY = 'billwise.demoSession'
const DEFAULT_DEMO_USER = import.meta.env.VITE_DEMO_USER ?? 'amina@demo.billwise.ai'

/** Active demo persona email. Stored in localStorage so the sidebar switcher sticks. */
export function getDemoUser(): string {
  try {
    return localStorage.getItem(DEMO_USER_STORAGE_KEY) || DEFAULT_DEMO_USER
  } catch {
    return DEFAULT_DEMO_USER
  }
}

export function setDemoUser(email: string): void {
  localStorage.setItem(DEMO_USER_STORAGE_KEY, email)
}

/** Whether the visitor has entered the product from the landing flow. */
export function hasDemoSession(): boolean {
  try {
    return localStorage.getItem(DEMO_SESSION_KEY) === '1'
  } catch {
    return false
  }
}

export function enterDemoSession(email?: string): void {
  if (email) setDemoUser(email)
  localStorage.setItem(DEMO_SESSION_KEY, '1')
}

export function leaveDemoSession(): void {
  localStorage.removeItem(DEMO_SESSION_KEY)
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fieldErrors: { field: string; message: string }[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        'X-Demo-User': getDemoUser(),
        ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init.headers,
      },
    })
  } catch {
    throw new ApiError(
      'Could not reach the Tran$Flow backend. Is it running on port 8000?',
      0,
    )
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const body = text ? safeParse(text) : null

  if (!response.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? `Request failed (${response.status}).`
    const fieldErrors =
      body && typeof body === 'object' && 'errors' in body
        ? ((body as { errors: { field: string; message: string }[] }).errors ?? [])
        : []
    throw new ApiError(detail, response.status, fieldErrors)
  }
  return body as T
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/* ------------------------------------------------------------------ types */

export type Basis = 'calculated' | 'estimate' | 'suggestion' | 'action'

export interface Health {
  status: string
  environment: string
  assistant_mode: 'llm' | 'offline_deterministic'
  model: string | null
  demo_data: boolean
}

export interface Account {
  id: number
  name: string
  institution: string
  account_type: string
  currency: string
  current_balance: string
  is_synthetic: boolean
}

export interface Profile {
  id: number
  full_name: string
  email: string
  base_currency: string
  home_country: string
  study_country: string
  priorities: string[]
  accounts: Account[]
  is_demo_data: boolean
}

export interface DemoPersona {
  email: string
  full_name: string
  home_country: string
  study_country: string
  base_currency: string
  tagline: string
  story: string
}

export interface Conversion {
  amount_converted: number | null
  rate: number | null
  rate_date: string | null
  rate_source: string | null
  is_simulated_rate: boolean
  is_stale: boolean
  staleness_days: number
  status: string
  note: string
}

export interface EvidenceRow {
  transaction_id: number
  date: string
  amount: number
  currency: string
  description?: string
}

export interface PriceChange {
  merchant: string
  currency: string
  previous_amount: number
  new_amount: number
  change_amount: number
  change_pct: number
  direction: 'increase' | 'decrease'
  effective_date: string
  confidence: number
  confirmed_by_later_charge: boolean
  change_amount_base?: number | null
  cadence?: string
}

export interface Subscription {
  merchant: string
  currency: string
  account_id: number
  service_family: string | null
  cadence: string
  occurrence_count: number
  typical_amount: number
  latest_amount: number
  monthly_equivalent: number
  monthly_equivalent_base: number | null
  annual_equivalent: number
  first_seen: string
  last_seen: string
  next_expected_date: string | null
  status: 'active' | 'dormant'
  confidence: number
  verdict: 'likely_recurring' | 'possible_recurring' | 'insufficient_evidence'
  interval_regularity: number
  amount_stability: number
  reasons: string[]
  price_changes: PriceChange[]
  evidence: EvidenceRow[]
  conversion: Conversion
}

export interface DuplicateFinding {
  finding_type:
    | 'same_service_duplicate'
    | 'double_charge_in_cycle'
    | 'overlapping_service_family'
  title: string
  detail: string
  merchants: string[]
  currency: string
  estimated_redundant_monthly: number | null
  confidence: number
  verdict: 'likely' | 'possible' | 'informational'
  evidence: Record<string, unknown>[]
  caveat: string
}

export interface SubscriptionAnalysis {
  as_of: string
  base_currency: string
  summary: {
    series_detected: number
    active_count: number
    likely_count: number
    possible_count: number
    dormant_count: number
    estimated_monthly_total_base: number
    estimated_annual_total_base: number
    duplicate_findings: number
    price_changes_detected: number
    amounts_excluded_for_missing_rates: { merchant: string; reason: string }[]
  }
  subscriptions: Subscription[]
  duplicate_findings: DuplicateFinding[]
  price_changes: PriceChange[]
  methodology: string
}

export interface Bill {
  id: number
  name: string
  merchant: string
  category: string
  due_date: string
  days_until_due: number
  amount: number
  currency: string
  amount_base: number | null
  base_currency: string
  status: string
  is_recurring: boolean
  autopay: boolean
  notes: string
  conversion: Conversion
}

export interface BillsResponse {
  as_of: string
  base_currency: string
  window_days: number
  count: number
  total_due_base: number
  amounts_excluded_for_missing_rates: { name: string; reason: string }[]
  bills: Bill[]
}

export interface ForecastEvent {
  date: string
  label: string
  kind: 'bill' | 'recurring_charge' | 'income'
  direction: 'inflow' | 'outflow'
  amount_original: number
  currency_original: string
  amount_base: number | null
  conversion_status: string
  certainty: 'confirmed' | 'projected' | 'estimated'
  confidence: number
  source_note: string
  fx_note: string
}

export interface DailyPoint {
  date: string
  balance: number
  inflow: number
  outflow: number
  events: string[]
}

export interface Forecast {
  base_currency: string
  period: { start: string; end: string; horizon_days: number }
  opening_balance: number
  closing_balance: number
  total_inflow: number
  total_outflow: number
  net_change: number
  minimum_balance: number
  minimum_balance_date: string
  shortfall_detected: boolean
  first_shortfall_date: string | null
  largest_shortfall: number | null
  daily: DailyPoint[]
  events: ForecastEvent[]
  excluded_from_projection: {
    item: string
    amount_original?: number
    currency?: string
    reason: string
    due_date?: string
  }[]
  assumptions: string[]
  opening_balance_breakdown: {
    account_id: number
    name: string
    institution: string
    currency: string
    balance_original: number
    balance_base: number | null
    conversion: Conversion
  }[]
}

export interface Dashboard {
  as_of: string
  user: {
    name: string
    base_currency: string
    home_country: string
    study_country: string
    priorities: string[]
  }
  data_source: { is_demo_data: boolean; label: string }
  available_balance: {
    amount: number
    currency: string
    basis: Basis
    accounts: Forecast['opening_balance_breakdown']
    excluded: { item: string; reason: string }[]
  }
  upcoming_bills: {
    count: number
    total_base: number
    currency: string
    window_days: number
    basis: Basis
    next: Bill[]
  }
  recurring_monthly: {
    amount: number
    currency: string
    active_count: number
    likely_count: number
    possible_count: number
    basis: Basis
    note: string
  }
  potential_savings: {
    amount: number
    currency: string
    option_count: number
    basis: Basis
    note: string
  }
  price_change_alerts: PriceChange[]
  cash_flow: Forecast & { series: DailyPoint[]; basis: Basis; currency: string }
  spend_by_category_30d: { category: string; amount_base: number | null; note?: string }[]
  duplicate_findings_count: number
}

export interface CurrencyRow {
  currency: string
  transaction_count: number
  total_original: number
  total_base: number
  disclosed_fees_original: number
  disclosed_fees_base: number
  converted_count: number
  unconverted_count: number
  latest_rate: number | null
  rate_date: string | null
  rate_source: string | null
  is_simulated_rate: boolean | null
  is_base_currency: boolean
}

export interface RemittanceRoute {
  route: string
  label: string
  fee_base: number
  amount_received_dest: number | null
  destination_currency: string
  total_cost_base: number | null
  eta_business_days: string
  notes: string[]
}

export interface RemittanceSim {
  as_of: string
  simulation: boolean
  disclaimer: string
  send: { amount: number; currency: string; destination_currency: string }
  routes: RemittanceRoute[]
  fee_savings_base_if_stablecoin: number | null
  reporting_currency: string
  recommendation: string
  requires_user_authorization: true
  executable: false
}

export interface CurrencyAnalysis {
  as_of: string
  base_currency: string
  period: { start: string; end: string; months: number }
  summary: {
    currencies_used: number
    foreign_currency_spend_base: number
    foreign_spend_monthly_average_base: number
    disclosed_fees_base: number
    disclosed_fee_transaction_count: number
    unconvertible_transaction_count: number
  }
  by_currency: CurrencyRow[]
  fx_sensitivity_whatif: { scenario: string; monthly_impact_base: number }[]
  unconvertible_transactions: {
    transaction_id: number
    date: string
    merchant: string
    amount: number
    currency: string
    reason: string
  }[]
  notes: string[]
}

export interface RateRow {
  pair: string
  base_currency: string
  quote_currency: string
  rate: number
  as_of_date: string
  source: string
  is_simulated: boolean
}

export interface Recommendation {
  key: string
  title: string
  summary: string
  category: string
  basis: Basis
  rank_score: number
  urgency: number
  confidence: number
  impact_normalised: number
  priority_alignment: number
  estimated_impact_base: number | null
  estimated_annual_impact_base: number | null
  currency: string
  impact_basis: string
  suggested_action: {
    type: string
    target: string
    requires_user_authorization: boolean
    executes_immediately: boolean
  } | null
  evidence: Record<string, unknown>[]
  caveats: string[]
}

export interface RecommendationsResponse {
  count: number
  base_currency: string
  ranking: { weights: Record<string, number>; user_priorities: string[] }
  recommendations: Recommendation[]
}

export interface AgentFact {
  label: string
  value: string | number
  currency: string | null
  basis: Basis
  period: string | null
  confidence: number | null
  note: string
}

export interface ToolCallTrace {
  tool: string
  arguments: Record<string, unknown>
  status: string
  duration_ms: number
  summary: string
  error: string | null
}

export interface ChatResponse {
  answer: string
  mode: 'llm' | 'offline_deterministic'
  model: string | null
  tool_calls: ToolCallTrace[]
  facts: AgentFact[]
  iterations: number
  truncated: boolean
  disclaimer: string
}

export interface ActionPreview {
  id: number
  action_type: string
  target_label: string
  summary: string
  estimated_monthly_impact: string | null
  currency: string | null
  status: string
  requires_authorization: boolean
}

export interface Reminder {
  id: number
  title: string
  due_date: string
  note: string
  related_kind: string | null
  related_ref: string | null
  created_by: string
  status: string
}

export interface ImportResult {
  imported: number
  skipped: number
  total_rows: number
  errors: { row: number; error: string }[]
  new_merchants: string[]
  warning: string
}

export interface Transaction {
  id: number
  account_id: number
  posted_date: string
  description_raw: string
  merchant_normalized: string
  category: string
  direction: 'debit' | 'credit'
  amount_original: string
  currency_original: string
  fee_amount: string | null
  fee_currency: string | null
  is_synthetic: boolean
  source: string
}

/* ---------------------------------------------------------------- methods */

export const api = {
  health: () => request<Health>('/api/health'),
  personas: () => request<{ personas: DemoPersona[]; note: string }>('/api/personas'),
  profile: () => request<Profile>('/api/me'),
  dashboard: (horizonDays = 30) =>
    request<Dashboard>(`/api/dashboard?horizon_days=${horizonDays}`),
  subscriptions: (minConfidence = 0, includeDormant = true) =>
    request<SubscriptionAnalysis>(
      `/api/subscriptions?min_confidence=${minConfidence}&include_dormant=${includeDormant}`,
    ),
  bills: (daysAhead = 30) => request<BillsResponse>(`/api/bills?days_ahead=${daysAhead}`),
  forecast: (horizonDays = 30, includeProjected = true) =>
    request<Forecast>(
      `/api/forecast?horizon_days=${horizonDays}&include_projected_recurring=${includeProjected}`,
    ),
  currency: (months = 6) => request<CurrencyAnalysis>(`/api/currency?months=${months}`),
  remittanceSim: (amount: number, destinationCurrency = 'GHS', sourceCurrency?: string) =>
    request<RemittanceSim>(
      `/api/currency/remittance-sim?amount=${amount}&destination_currency=${destinationCurrency}${
        sourceCurrency ? `&source_currency=${sourceCurrency}` : ''
      }`,
    ),
  rates: (quote?: string, limit = 60) =>
    request<{ count: number; all_rates_simulated: boolean; rates: RateRow[] }>(
      `/api/currency/rates?limit=${limit}${quote ? `&quote=${quote}` : ''}`,
    ),
  recommendations: (limit = 10) =>
    request<RecommendationsResponse>(`/api/recommendations?limit=${limit}`),
  transactions: (params: { limit?: number; offset?: number; merchant?: string } = {}) => {
    const query = new URLSearchParams({
      limit: String(params.limit ?? 50),
      offset: String(params.offset ?? 0),
      ...(params.merchant ? { merchant: params.merchant } : {}),
    })
    return request<{ items: Transaction[]; total: number; limit: number; offset: number }>(
      `/api/transactions?${query}`,
    )
  },
  importCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportResult>('/api/transactions/import', {
      method: 'POST',
      body: form,
    })
  },
  sampleCsvUrl: '/api/transactions/sample-csv',

  chat: (message: string, history: { role: 'user' | 'assistant'; content: string }[]) =>
    request<ChatResponse>('/api/assistant/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history: history.slice(-12) }),
    }),
  suggestions: () =>
    request<{ suggestions: string[]; base_currency: string }>('/api/assistant/suggestions'),
  agentTools: () =>
    request<{
      mode: string
      max_tool_iterations: number
      tools: { name: string; description: string; mutates_state: boolean }[]
      notes: string[]
    }>('/api/assistant/tools'),

  previewAction: (actionType: string, targetLabel: string) =>
    request<ActionPreview>('/api/actions/preview', {
      method: 'POST',
      body: JSON.stringify({ action_type: actionType, target_label: targetLabel }),
    }),
  decideAction: (id: number, decision: 'approve' | 'decline', confirmationText = '') =>
    request<ActionPreview>(`/api/actions/${id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, confirmation_text: confirmationText }),
    }),
  actions: () => request<ActionPreview[]>('/api/actions'),

  reminders: () => request<Reminder[]>('/api/reminders'),
  createReminder: (title: string, dueDate: string, note = '') =>
    request<Reminder>('/api/reminders', {
      method: 'POST',
      body: JSON.stringify({ title, due_date: dueDate, note }),
    }),
  confirmReminder: (id: number) =>
    request<Reminder>(`/api/reminders/${id}/confirm`, { method: 'POST' }),
  dismissReminder: (id: number) =>
    request<void>(`/api/reminders/${id}`, { method: 'DELETE' }),
}
