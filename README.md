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
> exchange rates are a simulated series, not live market quotes. 
---

## Contents

- [Quick start](#quick-start)
- [What it does](#what-it-does)
- [The AI agent](#the-ai-agent)
- [Security model](#security-model)
- [API reference](#api-reference)
- [Running the tests](#running-the-tests)

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



The important boundary is between the agent and the financial services. The agent
can only reach the data through seven typed functions; the services are plain Python
that know nothing about the model and are unit-tested on their own.



### Money handling

Amounts are stored as `Numeric(18,4)` and exchange rates as `Numeric(18,8)`; all
arithmetic uses `Decimal`. A transaction row always holds the amount in the currency
the charge actually occurred in. Reporting-currency equivalents are derived when
read, never written back as if they were facts.

---

## The AI agent

The model receives a question and a list of tool schemas.
### Offline mode is a fallback, not a second assistant



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
lable data" rather than an improvised answer. It is not financial
advice.
>>>>>>> fbb3cf0 (Initial Commit : backend,frontend ,and landing flow)
