import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, enterDemoSession } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { ErrorPanel, LoadingPanel } from '../components/primitives'
import { MarketingChrome } from '../components/MarketingChrome'

/** Resume a demo session by selecting a seeded student. */
export default function Login() {
  const navigate = useNavigate()
  const personas = useApi(() => api.personas(), [])
  const [selected, setSelected] = useState<string | null>(null)

  if (personas.loading && !personas.data) {
    return (
      <MarketingChrome>
        <div className="flex min-h-[60vh] items-center justify-center px-5">
          <LoadingPanel label="Loading demo students" />
        </div>
      </MarketingChrome>
    )
  }

  if (personas.error) {
    return (
      <MarketingChrome>
        <div className="flex min-h-[60vh] items-center justify-center px-5">
          <ErrorPanel message={personas.error} onRetry={personas.reload} />
        </div>
      </MarketingChrome>
    )
  }

  const list = personas.data?.personas ?? []
  const active = selected ?? list[0]?.email ?? null

  function continueToApp() {
    if (!active) return
    enterDemoSession(active)
    navigate('/dashboard', { replace: true })
  }

  return (
    <MarketingChrome>
      <div className="mx-auto max-w-3xl px-5 py-14 sm:px-8 lg:px-12">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-800/70">
          Log in
        </p>
        <h1 className="mt-3 font-display text-4xl text-stone-900 sm:text-5xl">
          Continue as a demo student
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-stone-600">
          No password — this build uses seeded personas. Choose who you were exploring,
          or <Link to="/get-started" className="font-medium text-emerald-800 underline-offset-2 hover:underline">create a new demo account</Link>.
        </p>

        <ul className="mt-10 space-y-3" role="listbox" aria-label="Demo student">
          {list.map((persona) => {
            const isActive = persona.email === active
            return (
              <li key={persona.email}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  onClick={() => setSelected(persona.email)}
                  className={`w-full rounded-2xl border px-5 py-4 text-left transition-colors ${
                    isActive
                      ? 'border-emerald-700 bg-emerald-50'
                      : 'border-stone-200 bg-white hover:border-stone-300'
                  }`}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-base font-semibold text-stone-900">{persona.full_name}</p>
                    <p className="text-xs text-stone-500">
                      {persona.home_country} → {persona.study_country}
                    </p>
                  </div>
                  <p className="mt-1.5 text-sm text-emerald-800">{persona.tagline}</p>
                </button>
              </li>
            )
          })}
        </ul>

        <div className="mt-8 flex flex-wrap gap-3">
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-full bg-emerald-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-40"
            disabled={!active}
            onClick={continueToApp}
          >
            Enter Tran$Flow
          </button>
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-full border border-stone-300 px-6 py-2.5 text-sm font-semibold text-stone-800 hover:bg-stone-50"
          >
            Back
          </Link>
        </div>
      </div>
    </MarketingChrome>
  )
}
