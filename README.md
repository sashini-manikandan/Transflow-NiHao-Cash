# Tran$Flow

An agentic financial copilot for **international students**.

Students studying abroad juggle tuition, rent, subscriptions, and remittances across currencies. Tran$Flow brings those obligations into one place so you can see what is due, what repeats, and whether cash will cover the next instalment — before the shortfall arrives.

> **Demo build.** All balances, transactions, and exchange rates are synthetic. There is no live bank connection and no real money movement.

---

## What it solves

| Pressure | How Tran$Flow helps |
|---|---|
| Hidden recurring charges | Detects likely subscriptions from history and flags overlaps or duplicates |
| Tuition & rent timing | Projects cash day by day against confirmed bills and expected income |
| Cross-border spend | Keeps amounts in the currency they happened in; reporting uses dated rates |
| “Can I afford this?” | Tran$Flow AI answers from backend tools — the model never invents the numbers |

---

## How it works

1. **Seeded student profiles** — Explore complete demo stories (home country → study country).
2. **Analysis layer** — The backend calculates balances, recurrence, forecasts, and currency costs.
3. **Product UI** — Overview, Subscriptions, Bills & forecast, Cross-border, and Assistant.
4. **Tran$Flow AI** — Chooses tools, reads results, writes the explanation. Arithmetic stays on the server.

```
Landing / demo account
        ↓
React app (Overview · Subscriptions · Bills · Cross-border · Assistant)
        ↓
FastAPI  →  financial services  →  SQLite (demo data)
        ↓
Tran$Flow AI (optional LLM · offline fallback without a key)
```

---

## Quick start

**Requirements:** Python 3.11+, Node 18+

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

API: http://127.0.0.1:8000 · docs: http://127.0.0.1:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

Optional: add a provider key in `backend/.env` for the live assistant. Leave blank for offline tool-based replies. Never commit real secrets.

---

## Stack

- **Frontend** — React, TypeScript, Vite, Tailwind, Recharts
- **Backend** — FastAPI, SQLAlchemy, SQLite
- **Assistant** — Tool-calling agent over typed backend functions

---

## Privacy & honesty

- Synthetic demo data only — not financial advice
- No bank passwords or card details are collected
- API keys stay in the backend environment, never in the browser
- See `SECURITY.md` for the security self-assessment

---

## Team

Built for the Transflow · NiHao Cash track as **Tran$Flow** — obligations clarity for students abroad.
