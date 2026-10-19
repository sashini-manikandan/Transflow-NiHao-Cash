# Security Self-Assessment Report

**Product:** Tran$Flow (Transflow · NiHao Cash)  
**Track:** Topic C — Cross-border & Student Finance Assistant  
**Build type:** Hackathon MVP with synthetic sandbox accounts  
**Last updated:** October 2026

This document satisfies submission item **05 — Security self-assessment report**: permission-tier implementation and known-risk list. It also summarises the security design referenced in technical documentation.

---

## 1. Scope and honesty

Tran$Flow is a **demo** financial obligations assistant. It does **not**:

- connect to a live bank or card network  
- move real money  
- provide regulated financial advice  
- implement production identity (OAuth, sessions, MFA)

All balances, transactions, and FX rates are **synthetic** and labelled as such in the UI and API. Security controls below are designed for a **sandbox agent** that must still demonstrate real isolation, tool safety, and least privilege — the behaviours judges evaluate under **Security & compliance (30%)**.

---

## 2. Permission-tier implementation

Access is layered. Higher tiers never expand the model’s power; they only unlock product surfaces for a scoped demo user.

| Tier | Who | What they can do | How it is enforced |
|---|---|---|---|
| **T0 — Public marketing** | Anyone | View landing, FAQ, sign-up / log-in pages | No API financial data; no agent |
| **T1 — Demo session** | Visitor who completed Get started / Log in | Enter the product shell | Frontend session flag (`billwise.demoSession`); deep links without a session redirect to onboarding |
| **T2 — Scoped demo user** | Session + selected persona email | Read that user’s accounts, bills, subscriptions, forecasts, FX views | Every `/api` request sends `X-Demo-User`; backend resolves a single `User` row and **all queries filter by that `user_id`** |
| **T3 — Agent tools** | Assistant chat for the scoped user | Call only the seven allowlisted tools against that user’s data | Tool names allowlisted; arguments validated (`extra="forbid"`); `user_id` / email / account id **rejected** if the model tries to pass them; identity injected from `ToolContext` only |
| **T4 — State-changing actions** | Explicit user confirmation | Create pending reminders; preview cancellations | Mutations require confirmation paths; subscription cancellation is **preview only** — never executed against a real provider |

### 2.1 Why `X-Demo-User` is not “fake security”

The header is a **deliberate sandbox stand-in** for authentication. Its purpose is to force every query through one user scope so isolation rules are real and testable. Production would replace `get_current_user` with session or token auth **without** changing services or tools.

### 2.2 Agent privilege boundary

```
User question
    → LLM (optional) proposes tool names + args
        → Allowlist check
        → Pydantic validation (unknown fields forbidden)
        → ToolContext(user=server-resolved) 
        → Financial services (Decimal math, DB scoped to user)
    → Structured tool result returned to LLM
    → Narrated answer (no independent arithmetic)
```

The model never receives a database handle, connection string, or another user’s records. Offline mode (no API key) uses the **same tools** via keyword routing so the privilege boundary does not disappear when the LLM is absent.

### 2.3 Tool surface (least privilege)

| Tool | Read / write | Notes |
|---|---|---|
| `get_recurring_payments` | Read | Scoped series for current user |
| `get_upcoming_bills` | Read | Windowed bills |
| `forecast_balance` | Read | Projection only |
| `analyze_subscriptions` | Read | Duplicates / price changes |
| `analyze_currency_costs` | Read | FX breakdown + labelled simulated rates |
| `get_savings_options` | Read | Ranked suggestions with caveats |
| `create_reminder` | Write (pending) | Starts **pending**; user must confirm in UI |

Caps: max tool iterations and max tool calls per request (configurable; defaults 4 / 8).

---

## 3. Security controls summary

| Area | Control |
|---|---|
| **Secrets** | Provider API key lives only in backend environment (`.env`). Never exposed to Vite/`VITE_*`, never returned by API responses, never logged in full. |
| **Data classification** | Synthetic demo PII and balances only. No real card numbers, CVVs, or bank passwords in schema or UI. |
| **Input handling** | Imported / stored descriptors treated as untrusted text; sanitized before LLM context. |
| **CORS** | Restricted to local frontend origins in development settings. |
| **Rate limiting** | Sliding-window limiter on assistant endpoints (default 15 req / 60s per client key). |
| **Audit** | Tool name, authorisation decision, and outcome recorded; financial payloads are not dumped into the audit trail. |
| **Provenance** | UI distinguishes calculated vs estimated figures; FX rates marked simulated. |
| **Dependency hygiene** | Third-party SDKs limited; LLM SDK isolated in `llm_provider.py`. |

---

## 4. Compliance posture (hackathon-appropriate)

| Topic | Stance |
|---|---|
| Financial advice | Product disclaimer: not advice; demo projections only |
| Data protection | No live customer data processed; sandbox accounts only |
| Payments / remittance | Simulation and education only; no executable transfers |
| Model transparency | Answers labelled Tran$Flow AI; tool traces available in UI |
| Open source / IP | Team-authored code; dependencies used under their licences |

We do **not** claim PCI-DSS, banking licence, or production SOC2 readiness. Claiming those for a sandbox MVP would itself be a compliance failure.

---

## 5. Known-risk list

| ID | Risk | Likelihood | Impact | Mitigation / residual |
|---|---|---|---|---|
| R1 | Demo header spoofing (anyone can set `X-Demo-User` to another seeded email) | High in open deploy | Low–medium (sandbox data only) | Acceptable for demo; production needs real auth. Documented explicitly. |
| R2 | In-process rate limiter resets on restart; not shared across workers | Medium | Medium (assistant abuse) | Adequate for single-process MVP; move to Redis for multi-instance. |
| R3 | LLM provider sees tool outputs (amounts, merchants) | Medium if key configured | Low (synthetic data) | Sanitize payloads; minimise fields; no secrets in tools. |
| R4 | Prompt injection via transaction descriptions | Low–medium | Medium (manipulated narrative) | Treat descriptors as data; sanitize; tools still return server-calculated numbers. |
| R5 | Model attempts out-of-scope tools or cross-user args | Medium | Low (blocked) | Allowlist + `extra="forbid"` + server-side identity; covered by tests. |
| R6 | Users mistake projections for guarantees or advice | Medium | Medium (trust) | Disclaimers; Calculated vs Estimate tags; “not financial advice”. |
| R7 | Accidental commit of `.env` with real API key | Low | High | `.gitignore` for `.env`; only `.env.example` placeholders in repo. |
| R8 | Forecast / FX accuracy limits | Certain (by design) | Medium if misunderstood | Simulated rates labelled; stale/unavailable rates refused rather than invented. |
| R9 | Action preview misread as completed cancellation | Low | Medium | Preview-only copy; explicit confirm step; no provider API. |
| R10 | Dependency or supply-chain vulnerability | Low–medium | Medium | Pin requirements; keep MVP surface small; review before any public deploy. |

---

## 6. Testing that backs the security claims

Backend tests exercise (non-exhaustive):

- User-scoped queries (no cross-user leakage via tools)  
- Rejection of model-supplied `user_id` / identity fields  
- Allowlist enforcement for unknown tools  
- Rate-limit behaviour on assistant routes  
- Offline vs LLM paths remaining on the same tool boundary  

Frontend tests cover assistant labelling and provenance display without exposing provider model slugs in product chrome.

---

## 7. Deployment guidance (do / don’t)

**Do**

- Run as a local or controlled demo  
- Keep API keys in server env only  
- Submit sandbox logs + demo video as execution evidence  

**Don’t**

- Deploy publicly with the demo header as “login”  
- Connect real bank credentials  
- Remove disclaimers or simulated-rate labels to look “more real”

---

## 8. Summary for reviewers

Tran$Flow implements **clear permission tiers**, a **least-privilege tool-calling agent**, **server-side user scoping**, **secret isolation**, **rate limiting**, **confirm-gated mutations**, and an **honest known-risk list**. Residual risks are dominated by the intentional demo auth model and synthetic data — appropriate for Topic C sandbox execution, and explicitly not claimed as production banking security.
