import { useState, type ComponentType, type ReactNode, type SVGProps } from 'react'
import { NavLink, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom'

import {
  api,
  getDemoUser,
  hasDemoSession,
  leaveDemoSession,
  setDemoUser,
} from './lib/api'
import { useApi } from './hooks/useApi'
import {
  AssistantIcon,
  BillsIcon,
  CrossBorderIcon,
  OverviewIcon,
  SubscriptionsIcon,
} from './components/NavIcons'
import Landing from './pages/Landing'
import GetStarted from './pages/GetStarted'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Subscriptions from './pages/Subscriptions'
import BillsAndForecasts from './pages/BillsAndForecasts'
import CrossBorder from './pages/CrossBorder'
import Assistant from './pages/Assistant'

const NAV: {
  to: string
  label: string
  Icon: ComponentType<SVGProps<SVGSVGElement>>
}[] = [
  { to: '/dashboard', label: 'Overview', Icon: OverviewIcon },
  { to: '/subscriptions', label: 'Subscriptions', Icon: SubscriptionsIcon },
  { to: '/bills', label: 'Bills & forecast', Icon: BillsIcon },
  { to: '/cross-border', label: 'Cross-border', Icon: CrossBorderIcon },
  { to: '/assistant', label: 'Assistant', Icon: AssistantIcon },
]

function RequireDemo({ children }: { children: ReactNode }) {
  if (!hasDemoSession()) {
    return <Navigate to="/get-started" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={hasDemoSession() ? <Navigate to="/dashboard" replace /> : <Landing />}
      />
      <Route path="/get-started" element={<GetStarted />} />
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireDemo>
            <AppShell />
          </RequireDemo>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/subscriptions" element={<Subscriptions />} />
        <Route path="/bills" element={<BillsAndForecasts />} />
        <Route path="/cross-border" element={<CrossBorder />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}

function AppShell() {
  const navigate = useNavigate()
  const [navOpen, setNavOpen] = useState(false)
  const [personaEmail, setPersonaEmail] = useState(getDemoUser)
  const profile = useApi(() => api.profile(), [personaEmail])
  const personas = useApi(() => api.personas(), [])

  function switchPersona(email: string) {
    if (email === personaEmail) return
    setDemoUser(email)
    setPersonaEmail(email)
    window.location.assign('/dashboard')
  }

  function leaveDemo() {
    leaveDemoSession()
    navigate('/', { replace: true })
  }

  const activePersona = personas.data?.personas.find((p) => p.email === personaEmail)

  return (
    <div className="flex min-h-screen">
      {navOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-canvas/70 backdrop-blur-sm lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[15.5rem] shrink-0 flex-col
                    overflow-y-auto border-r border-line/80 bg-surface/95 transition-transform
                    lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 lg:self-start
                    ${navOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="px-5 pb-2 pt-6">
          <p className="font-display text-[1.65rem] leading-none text-ink">BillWise</p>
          <p className="mt-1.5 text-[11px] leading-snug text-ink-faint">
            Obligations for students abroad
          </p>
        </div>

        <nav className="mt-6 flex-1 space-y-0.5 px-3" aria-label="Main">
          {NAV.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setNavOpen(false)}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-4 border-t border-line/80 p-4">
          <div>
            <p className="label-xs">Assistant</p>
            <p className="mt-1.5 flex items-center gap-2 text-sm text-ink">
              <AssistantIcon className="h-4 w-4 shrink-0 text-accent" />
              BillWise AI
            </p>
          </div>

          {personas.data && personas.data.personas.length > 0 && (
            <label className="block space-y-1.5">
              <span className="label-xs">Demo student</span>
              <select
                className="input py-2 text-xs"
                value={personaEmail}
                onChange={(event) => switchPersona(event.target.value)}
                aria-label="Switch demo student persona"
              >
                {personas.data.personas.map((persona) => (
                  <option key={persona.email} value={persona.email}>
                    {persona.full_name}
                  </option>
                ))}
              </select>
              {activePersona && (
                <p className="text-[11px] leading-relaxed text-ink-faint">
                  {activePersona.tagline}
                </p>
              )}
            </label>
          )}

          {profile.data && (
            <div className="border-t border-line/60 pt-3">
              <p className="truncate text-sm font-medium text-ink">{profile.data.full_name}</p>
              <p className="mt-0.5 text-[11px] text-ink-faint">
                {profile.data.home_country} → {profile.data.study_country}
              </p>
            </div>
          )}

          <button
            type="button"
            onClick={leaveDemo}
            className="btn-ghost w-full justify-start px-3 py-2 text-xs font-medium text-ink-muted"
          >
            Leave demo
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line/80
                     bg-canvas/90 px-4 backdrop-blur-md lg:hidden"
        >
          <button
            type="button"
            className="btn-ghost px-3 py-2"
            aria-label="Open navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            Menu
          </button>
          <span className="font-display text-lg">BillWise</span>
        </header>

        <main className="min-w-0 flex-1 px-4 py-7 sm:px-7 lg:px-10 lg:py-9">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
