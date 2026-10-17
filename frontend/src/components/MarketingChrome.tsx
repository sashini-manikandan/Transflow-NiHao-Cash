import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Light marketing shell shared by landing, sign-up, and log-in. */
export function MarketingChrome({
  children,
  bare = false,
}: {
  children: ReactNode
  bare?: boolean
}) {
  return (
    <div className="landing-shell min-h-screen bg-[#F7F8F5] text-stone-900">
      {!bare && (
        <header className="sticky top-0 z-30 border-b border-stone-200/80 bg-[#F7F8F5]/90 backdrop-blur-md">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8 lg:px-10">
            <Link to="/" className="font-display text-2xl leading-none text-stone-900">
              BillWise
            </Link>
            <nav className="hidden items-center gap-7 text-sm text-stone-600 md:flex" aria-label="Marketing">
              <a href="/#product" className="hover:text-stone-900">
                Product
              </a>
              <a href="/#why" className="hover:text-stone-900">
                Why BillWise
              </a>
              <a href="/#faq" className="hover:text-stone-900">
                FAQ
              </a>
            </nav>
            <div className="flex items-center gap-2 sm:gap-3">
              <Link
                to="/login"
                className="rounded-full px-3.5 py-2 text-sm font-medium text-stone-700 hover:bg-stone-200/60"
              >
                Log in
              </Link>
              <Link
                to="/get-started"
                className="rounded-full bg-emerald-900 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800"
              >
                Sign up
              </Link>
            </div>
          </div>
        </header>
      )}
      {children}
    </div>
  )
}
