# Transflow-NiHao-Cash
An agentic financial copilot built for international students. The system integrates domestic transaction parsing, subscription lifecycle management, predictive cash flow forecasting, and cross-border remittance/FX optimization into a single privacy-centric workflow.
=======
# BillWise AI

An AI-powered financial obligations assistant for international students: it finds
the recurring payments hiding in a transaction history, forecasts whether the next
tuition instalment will actually clear, and explains the cost of living across
several currencies at once.

Every figure on screen comes from a backend calculation. The language model chooses
which questions to ask of the data and writes the prose; it never does the arithmetic
and never touches the database.

> **All data in this project is synthetic.** There is no bank integration, and the
> exchange rates are a simulated series, not live market quotes. The UI labels this
> everywhere it matters.

---

## Contents

- [Quick start](#quick-start)
- [What it does](#what-it-does)
- [Architecture](#architecture)
- [The AI agent](#the-ai-agent)
- [Security model](#security-model)
- [Environment variables](#environment-variables)
- [API reference](#api-reference)
- [Running the tests](#running-the-tests)
- [Demo script](#demo-script)
- [Known limitations](#known-limitations)

---

## Quick start

Requires Python 3.11+ and Node 18+. No database server is needed: the default
configuration uses SQLite and seeds itself on first boot.

**Three demo students** ship with the seed: Amina (tuition shortfall + Accra
remittance), Jordan (rent covered — remittance timing), and Mei (FX / foreign
spend). Switch them from the sidebar; the header is `X-Demo-User`. If you only
see Amina from an older database, delete `backend/billwise.db` and restart.

The dashboard shows a **cash-flow alert** when near-term bills exceed cash or a
shortfall is projected. Cross-Border includes a **USDC vs traditional remittance
simulation** (`GET /api/currency/remittance-sim`) — demo fees only, never
executable.

### Backend

```bash
cd backend
python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env            # Windows: Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

The API is now on <http://127.0.0.1:8000>, with interactive docs at
<http://127.0.0.1:8000/docs>. On first start it creates `billwise.db` and seeds
roughly a year of demo transactions anchored to today's date.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend on port 8000, so
no CORS configuration is needed for local development.

### Enabling the language model (optional)

Without an API key the assistant still answers, but through a deterministic
fallback rather than a model: it keyword-matches the question to tools and formats
their output from templates. That is reliable and reproducible for the questions in
the [demo script](#demo-script), and it means the app is never a dead screen — but
it is not a conversational assistant. See
[offline mode](#offline-mode-is-a-fallback-not-a-second-assistant) for what it
cannot do. **Use a real key to demo the assistant properly.**

To use a real model, put your key in `backend/.env`:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Restart the backend. The assistant's response includes a `mode` field so you can
always tell which path produced an answer (`llm` or `offline_deterministic`).

### Resetting the demo data

Stop the server, delete `backend/billwise.db`, and start it again.

---

## What it does

**Dashboard** — available balance across accounts, bills due in the next 30 days,
committed recurring spend per month, ranked savings options, price-change alerts,
and a day-by-day cash-flow projection that flags the date the balance first goes
negative.

**Subscription intelligence** — normalises messy merchant descriptors
(`SQ *NETFLIX.COM AMS NL` → `Netflix`), then decides whether a series of charges is
recurring using the regularity of the gaps, the stability of the amounts, and how
many charges have been observed. Each series carries a verdict
(`likely_recurring` / `possible_recurring` / `insufficient_evidence`), a confidence
score, and the individual transactions that justify it. Nothing is asserted as a
subscription on thin evidence.

It also flags the same service billed to two different cards, overlapping services
in one category (two video streaming plans), and genuine price changes.

**Bills and forecasting** — projects the balance forward day by day from confirmed
bills, projected subscription charges and expected income, separating what is
confirmed from what is estimated. Items that cannot be converted to the reporting
currency are listed as explicitly excluded rather than silently guessed at.

**Cross-border finance** — every transaction stores the amount in the currency it
actually occurred in. Reporting-currency equivalents are derived at read time from a
dated rate, which may be direct, inverted, or triangulated through USD. The
derivation path, the age of the rate, and the fact that the rate is simulated are all
returned with the number. Where no rate exists at all, the API returns
`rate_unavailable` with an explanation instead of an estimate.

**AI assistant** — answers questions about the user's own data by calling backend
tools, and shows which tools ran and what they returned.

**Recommendations** — ranked by urgency, estimated financial impact, detection
confidence and the user's stated priorities, each with its evidence and caveats
attached.

### Detection in a bit more detail

Recurrence confidence is a weighted combination of four signals: how regular the
intervals are (mean absolute deviation relative to the median interval), how stable
the amounts are (coefficient of variation), how many occurrences there are, and how
cleanly the median interval maps onto a known cadence (weekly, monthly, quarterly,
annual).

Price-change detection is deliberately conservative, because the expensive mistake
is telling someone their groceries got more expensive. A level shift is reported
only when all of the following hold:

- the series is classified as recurring at all;
- its amounts are normally stable (metered utility bills are excluded by this);
- the move is larger than four times the series' own typical charge-to-charge
  variation, so jitter in a near-fixed bill does not read as a repricing;
- the new level is confirmed by a later charge, or the shift is on the most recent
  charge, in which case it is shown but marked unconfirmed.

On the seeded dataset this reports exactly the two real price rises (Netflix and
Adobe) out of roughly 25 detected series.

---

## Architecture

```
┌──────────────────────────────┐
│ React + Vite + TypeScript    │   Dashboard · Subscriptions · Bills &
│ Tailwind · Recharts          │   Forecasts · Cross-Border · Assistant
└──────────────┬───────────────┘
               │  /api  (JSON, X-Demo-User header)
┌──────────────▼───────────────┐
│ FastAPI routers              │   validation, rate limiting, audit logging
├──────────────────────────────┤
│ Agent service                │   tool allowlist, argument validation,
│   └─ llm_provider            │   iteration budget, offline fallback
├──────────────────────────────┤
│ Financial services           │   merchants · recurring · duplicates · fx
│                              │   forecast · analysis · recommendations
├──────────────────────────────┤
│ SQLAlchemy models            │   SQLite (default) or PostgreSQL
└──────────────────────────────┘
```

The important boundary is between the agent and the financial services. The agent
can only reach the data through seven typed functions; the services are plain Python
that know nothing about the model and are unit-tested on their own.

```
backend/app/
  config.py            pydantic-settings, cached
  database.py          engine, session, create_all
  models.py            9 tables
  deps.py              demo user resolution, rate limiter, audit helper
  schemas.py           request/response models
  routers/             meta · transactions · insights · actions · assistant
  services/
    merchants.py       descriptor normalisation, service families
    recurring.py       cadence classification, confidence, price changes
    duplicates.py      same-service, double-charge and category overlaps
    fx.py              dated conversion with derivation path and staleness
    forecast.py        day-by-day balance projection
    analysis.py        orchestration across the above
    recommendations.py multi-signal ranking
    dashboard.py       dashboard composition
    importer.py        CSV import with per-row error reporting
  agent/
    llm_provider.py    the only module that imports the OpenAI SDK
    tools.py           the seven tools, their schemas and handlers
    service.py         the tool-calling loop and the offline fallback
  seed/seed_data.py    deterministic synthetic data

frontend/src/
  lib/api.ts           typed client for every endpoint
  lib/format.ts        money, dates, percentages
  hooks/useApi.ts      fetch/loading/error state
  components/          shared primitives, including the provenance tags
  pages/               the five screens
```

### Money handling

Amounts are stored as `Numeric(18,4)` and exchange rates as `Numeric(18,8)`; all
arithmetic uses `Decimal`. A transaction row always holds the amount in the currency
the charge actually occurred in. Reporting-currency equivalents are derived when
read, never written back as if they were facts.

---

## The AI agent

The model receives a question and a list of tool schemas. It cannot query the
database, and it is instructed not to perform arithmetic — every number in an answer
originates from one of these seven functions:

| Tool | Returns |
|---|---|
| `get_recurring_payments` | detected series with cadence, amount, next expected date, confidence, verdict |
| `get_upcoming_bills` | bills due in a window, original and reporting currency |
| `forecast_balance` | projected balance over a horizon, with shortfall dates |
| `analyze_subscriptions` | totals, duplicates, overlaps, price changes, with evidence |
| `analyze_currency_costs` | spend by currency, rates used, disclosed fees |
| `get_savings_options` | ranked savings with estimated impact and caveats |
| `create_reminder` | drafts a reminder in a **pending** state |

Each tool result is an envelope carrying the value, its currency, the time period it
covers, whether it is calculated or estimated, and any caveats. When the data cannot
answer a question, the tool says so rather than returning a plausible number.

Payloads are trimmed to what the model can actually reason with. Raw transaction ids
are withheld — it cannot verify one, and the charge count plus date range say more —
and a series that failed to qualify as recurring is reduced to a stub, since the only
honest thing to say about it is that the evidence is thin. Caveats that would
otherwise repeat on every row, such as the simulated-rate notice, are stated once in
the envelope. The full evidence still reaches the UI through the REST endpoints.

The loop is bounded: at most `AGENT_MAX_TOOL_ITERATIONS` round trips and
`AGENT_MAX_TOOL_CALLS` calls per request. Tool names are checked against an
allowlist, arguments are parsed into Pydantic models with `extra="forbid"`, and any
attempt to pass `user_id`, `user`, `email` or `account_id` is rejected outright —
identity is injected server-side from the authenticated request, never taken from the
model. Provider errors and timeouts are translated into safe messages that do not
leak internals.

### Offline mode is a fallback, not a second assistant

With no API key, the service matches the question against a keyword table, runs up
to three tools, and formats their output from templates. The figures it prints are
real — they come from the same tools and the same calculations, so nothing is
fabricated. Matching is done on word stems rather than raw substrings, so
"wasting" reaches the keyword `waste` and "renewals" reaches `renewal`.

It also handles the two cases where a naive router would mislead you. A short
back-referential turn ("and what about the one after that?") reuses the previous
question's tools and says that is what it did. A question it cannot match says so
plainly and labels what follows as a general overview, rather than presenting an
unrelated dump as if it were an answer.

It is still a graceful degradation, not parity:

- **It cannot answer anything compositional.** Combining or contrasting two tool
  results is exactly the work the model does, and templates cannot do it. "Compare
  my spending this month with last month" is honestly declined.
- **Follow-ups are shallow.** It reuses the previous plan but cannot tell *which*
  item you meant by "that one", and it says so rather than guessing.
- **Keyword routing has a ceiling.** Stemming widens it; it does not make it
  understand language.

So: it guarantees the demo never dies on a missing key, and it is useful for
testing the tool layer without burning tokens. It is not a substitute for the model.

---

## Security model

- The OpenAI key is read from the backend environment only. It is never sent to the
  browser, returned by an endpoint, or written to a log.
- `backend/.env.example` and `frontend/.env.example` contain placeholders only.
  Anything prefixed `VITE_` is compiled into the browser bundle and is treated as
  public by definition.
- Every query is scoped to the resolved user. Cross-user access is covered by tests.
- No bank passwords, card numbers or CVVs are collected anywhere in the schema or
  the UI.
- Imported transaction descriptions are handled as untrusted text. They are passed to
  the model as data, never as instructions, and a test asserts that an injection
  string embedded in a CSV description is stored and displayed verbatim without
  influencing agent behaviour.
- State-changing actions require explicit confirmation. Subscription cancellation
  produces a **preview only** — a description of what would happen, which the user
  must approve. The MVP cannot and does not cancel anything with a real provider.
- The audit log records the tool name, the authorisation decision and the outcome.
  It deliberately does not record the financial detail of each call.
- AI endpoints are rate-limited with a sliding window, 15 requests per minute by
  default.

### What this is not

Authentication is a demo stand-in: the frontend sends an `X-Demo-User` header that
selects the seeded user. There are no passwords, sessions or tokens. **Do not deploy
this as-is.** A real deployment needs proper authentication, a managed secret store,
and a shared rate limiter rather than the in-process one.

---

## Environment variables

All backend variables live in `backend/.env` (template in `backend/.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./billwise.db` | SQLAlchemy URL. For PostgreSQL: `postgresql+psycopg://user:pass@localhost:5432/billwise` |
| `OPENAI_API_KEY` | *(blank)* | Blank runs the assistant in deterministic offline mode |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for the Responses API |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Per-request provider timeout |
| `AGENT_MAX_TOOL_ITERATIONS` | `4` | Maximum model↔tool round trips per request |
| `AGENT_MAX_TOOL_CALLS` | `8` | Maximum total tool invocations per request |
| `AI_RATE_LIMIT_REQUESTS` | `15` | Requests allowed per window on AI endpoints |
| `AI_RATE_LIMIT_WINDOW_SECONDS` | `60` | Length of the rate-limit window |
| `APP_ENV` | `development` | Environment label |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins |
| `DEMO_USER_EMAIL` | `amina@demo.billwise.ai` | Seeded user selected by the demo header |
| `SEED_ON_STARTUP` | `true` | Seed synthetic data when the database is empty |

Frontend (`frontend/.env`, optional):

| Variable | Default | Purpose |
|---|---|---|
| `VITE_DEMO_USER` | `amina@demo.billwise.ai` | Value sent in the `X-Demo-User` header |

### Using PostgreSQL instead

```bash
createdb billwise
# in backend/.env:
DATABASE_URL=postgresql+psycopg://billwise:yourpassword@localhost:5432/billwise
```

Tables are created on startup; no migration tool is wired up for the MVP.

---

## API reference

Base URL `http://127.0.0.1:8000`. All `/api` routes require an `X-Demo-User` header.
Full generated documentation is at `/docs`.

### Meta

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness, plus whether an LLM is configured |
| `GET` | `/api/me` | Demo user profile, base currency, stated priorities |

### Transactions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/transactions` | Paginated list; filter by account, category, currency, date range, search |
| `POST` | `/api/transactions` | Add a single transaction |
| `GET` | `/api/transactions/categories` | Category totals |
| `GET` | `/api/transactions/sample-csv` | Download a correctly-shaped sample CSV |
| `POST` | `/api/transactions/import` | Import a CSV; returns per-row errors without aborting the batch |

### Insights

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Everything the dashboard renders, in one call |
| `GET` | `/api/subscriptions` | Detected series, duplicates, price changes, methodology |
| `GET` | `/api/savings` | Ranked savings options with impact and confidence |
| `GET` | `/api/bills` | Upcoming and past bills |
| `POST` | `/api/bills` | Create a bill |
| `GET` | `/api/forecast?horizon_days=30` | Day-by-day projection, events, exclusions, assumptions |
| `GET` | `/api/currency` | Spend by currency, FX sensitivity, unconvertible items |
| `GET` | `/api/currency/rates` | The dated rates held, with their age |

### Actions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/recommendations` | Ranked recommendations with evidence and caveats |
| `GET` | `/api/reminders` | List reminders |
| `POST` | `/api/reminders` | Create a reminder (starts pending) |
| `POST` | `/api/reminders/{id}/confirm` | Explicitly activate a pending reminder |
| `DELETE` | `/api/reminders/{id}` | Dismiss a reminder |
| `GET` | `/api/actions` | List action previews |
| `POST` | `/api/actions/preview` | Generate a preview — **never executes anything** |
| `POST` | `/api/actions/{id}/decision` | Approve or reject a previewed action |

### Assistant

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/assistant/tools` | The tool allowlist and schemas the model is given |
| `GET` | `/api/assistant/suggestions` | Starter questions grounded in the current data |
| `POST` | `/api/assistant/chat` | Ask a question; rate-limited |

`POST /api/assistant/chat` takes `{"message": "...", "history": [...]}` and returns:

```jsonc
{
  "answer":  "...",
  "mode":    "llm" | "offline_deterministic",
  "model":   "gpt-4o-mini",
  "tool_calls": [
    { "tool": "forecast_balance", "arguments": {...},
      "status": "ok", "duration_ms": 49, "summary": "Opening balance: AED 6979.14" }
  ],
  "facts": [
    { "label": "Projected shortfall", "value": 2699.56, "currency": "AED",
      "basis": "estimate", "period": "first on 2026-10-31", "note": "..." }
  ],
  "iterations": 1,
  "truncated": false,
  "disclaimer": "..."
}
```

`facts` is what the UI uses to distinguish calculated figures from estimates; the
frontend tags each one as Calculated, Estimate, Suggestion or Action.

---

## Running the tests

Backend — 164 tests covering merchant normalisation, recurrence detection, FX
derivation and staleness, duplicate detection, forecasting, the seeded dataset's
analytical properties, every API route, the agent's security boundary, its tool-call
cost, offline routing, and rate limiting:

```bash
cd backend
.venv/Scripts/python -m pytest -q      # Windows
.venv/bin/python -m pytest -q          # macOS / Linux
```

Frontend — 32 tests covering formatting, the three main screens, loading and error
states, and the assistant's tool trace:

```bash
cd frontend
npm test
npm run lint      # tsc --noEmit
```

Both suites run offline and never call the OpenAI API; the provider is stubbed.

A note on the test data: the engine tests pin "today" to a fixed date so detection
results are deterministic, while the API tests seed relative to the real current date
so that route behaviour is exercised the way the running server experiences it.

---

## Demo script

Roughly four minutes, using the seeded data as-is.

1. **Dashboard.** Balance, bills due, committed monthly spend. Point at the cash-flow
   chart: the projection goes negative before the tuition instalment clears, and the
   warning names the date.
2. **Subscriptions.** Show a high-confidence series and expand its evidence — the
   actual charges behind the verdict. Then show a series marked
   `insufficient_evidence` and note that the app declines to call it a subscription.
3. **Duplicates.** Netflix is billed to two different cards; two video streaming
   services and two music services overlap. Three findings, each with its reasoning.
4. **Price changes.** Netflix and Adobe, both confirmed by later charges. Mention
   that the grocery and utility series are *not* flagged, and why that is the harder
   problem.
5. **Cross-border.** Open the currency page: spend in AED, USD, GHS and TRY. Show
   that each converted figure names the rate date, the derivation path (the Ghana
   school fees are triangulated through USD), and that the rate is simulated. Then
   show the Turkish lira hotel booking, which has no stored rate and is reported as
   unavailable rather than estimated.
6. **Assistant.** Ask *"Can I afford my tuition instalment next month?"* Open the tool
   trace to show `get_upcoming_bills` and `forecast_balance` running, then the facts
   panel showing which figures are calculated and which are projections.
7. **Action safety.** Trigger a cancellation preview and show that it produces a
   description awaiting approval, not an executed cancellation.

The seeded data is generated from a fixed random seed, so every run of the demo
produces the same numbers.

---

## Known limitations

**Not production software.** The demo header is not authentication. The rate limiter
is in-process and resets on restart, so it would not hold across multiple workers.
There is no migration tooling — tables are created from the models at startup.

**The data is synthetic.** There is no bank or card integration. Exchange rates are a
generated series labelled as simulated throughout the UI and the API responses. The
"fees" are the ones recorded in the demo data, not a fee schedule scraped from real
providers.

**Detection has real limits.** A subscription needs several charges before it can be
identified with any confidence; a new one is invisible. Merchant normalisation is
rule-based, so an unfamiliar descriptor format can split one service into two series.
Quarterly and annual plans are detected but rest on very few data points, and their
confidence scores reflect that. The price-change threshold is calibrated rather than
derived, and errs toward silence: a genuine increase smaller than the series' own
routine variation will not be reported, because it could not be evidenced.

**Forecasting is a projection, not a prediction.** It assumes observed recurring
charges continue at their observed cadence and amount, and that expected income
arrives as scheduled. It does not model variable discretionary spending, so the
projected balance is optimistic relative to a typical month.

**Currency conversion is as good as the stored rates.** Rates are daily; intraday
movement is not modelled, and neither are the spreads a bank would actually charge.
Conversions older than seven days are flagged as stale, and pairs with no stored rate
are refused rather than estimated.

**The agent is correct before it is cheap.** The conversation resends every prior
tool result on each iteration, so a three-tool question costs roughly 14,700 input
tokens — down from about 19,500 before the payloads were trimmed, but still
dominated by that resending. The remaining lever is caching or summarising earlier
turns rather than replaying them verbatim, which was not worth the complexity for
an MVP. Recurrence detection now runs once per request and is shared by every tool
that needs it, so a three-tool answer costs one detection pass rather than four.
Tests pin both the per-tool token budgets and the single-detection guarantee.

**The assistant is bounded by its tools.** It can only answer what the seven
functions expose. Questions outside that surface get an honest "I can't determine
that from the available data" rather than an improvised answer. It is not financial
advice.
>>>>>>> fbb3cf0 (Initial Commit : backend,frontend ,and landing flow)
