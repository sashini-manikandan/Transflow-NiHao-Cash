import { useState } from 'react'
import { Link } from 'react-router-dom'

import { MarketingChrome } from '../components/MarketingChrome'

const TRUST = ['NYU Abu Dhabi', 'International students', 'Multi-currency', 'Remittance-aware']

const FEATURES = [
  {
    title: 'Shortfall alerts',
    body: 'See the day your balance crosses zero — before rent or tuition clears.',
    tint: 'bg-[#E8F2EC]',
    widget: 'alert',
  },
  {
    title: 'BillWise AI',
    body: 'Ask in plain language. Every figure is pulled from a backend tool, not invented.',
    tint: 'bg-[#E7EEF2]',
    widget: 'ai',
  },
  {
    title: 'Cross-border clarity',
    body: 'Foreign spend and remittance routes with dated rates, clearly labelled.',
    tint: 'bg-[#EDF3E8]',
    widget: 'fx',
  },
]

const FAQ = [
  {
    q: 'Can I create a real bank account here?',
    a: 'Not in this hackathon build. Sign up opens a demo account backed by synthetic student data — no passwords, no live banking.',
  },
  {
    q: 'Is BillWise AI giving financial advice?',
    a: 'No. Replies are grounded on calculated demo figures. Treat them as product exploration, not advice.',
  },
  {
    q: 'What currencies are covered?',
    a: 'Demo personas use AED, USD, and GBP bases, with foreign spend and remittance flows (including GHS) shown with dated simulated rates.',
  },
  {
    q: 'Can I switch students after signing up?',
    a: 'Yes. Use the demo student control in the sidebar, or leave the demo and start again from Sign up.',
  },
]

/**
 * Marketing landing guided by fintech inspo (nav, hero, trust, features, FAQ)
 * but BillWise-branded: brand leads the hero, light shell, honest demo CTAs.
 */
export default function Landing() {
  const [openFaq, setOpenFaq] = useState<number | null>(0)

  return (
    <MarketingChrome>
      {/* —— Hero —— */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_480px_at_85%_20%,rgba(16,85,60,0.12),transparent_55%),radial-gradient(700px_400px_at_10%_90%,rgba(180,160,120,0.10),transparent_50%)]"
        />
        <div className="relative mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center gap-12 px-5 py-16 sm:px-8 lg:grid-cols-2 lg:gap-8 lg:px-10 lg:py-20">
          <div className="animate-hero-fade">
            <p className="inline-flex rounded-full border border-emerald-900/15 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-900">
              For students abroad
            </p>
            <p className="mt-6 font-display text-[clamp(3rem,8vw,4.75rem)] leading-[0.92] tracking-[-0.02em] text-stone-900">
              BillWise
            </p>
            <h1 className="mt-5 max-w-md font-sans text-xl font-medium leading-snug text-stone-800 sm:text-2xl">
              See every obligation{' '}
              <span className="font-display italic text-emerald-900">before</span> it hits
              your account.
            </h1>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-stone-600 sm:text-[0.95rem]">
              Bills, subscriptions, and remittances in one place — with BillWise AI
              grounded on the numbers.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to="/get-started"
                className="inline-flex rounded-full bg-emerald-900 px-6 py-3 text-sm font-semibold text-white transition hover:bg-emerald-800"
              >
                Get started
              </Link>
              <Link
                to="/login"
                className="inline-flex rounded-full border border-stone-300 bg-white/80 px-6 py-3 text-sm font-semibold text-stone-800 hover:bg-white"
              >
                Log in
              </Link>
            </div>
            <div className="mt-10 flex items-center gap-3">
              <div className="flex -space-x-2" aria-hidden="true">
                {['AO', 'JL', 'MC'].map((initials) => (
                  <span
                    key={initials}
                    className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-[#F7F8F5] bg-emerald-900 text-[10px] font-semibold text-white"
                  >
                    {initials}
                  </span>
                ))}
              </div>
              <p className="text-sm text-stone-600">
                <span className="font-semibold text-stone-900">3</span> seeded student
                stories ready to explore
              </p>
            </div>
          </div>

          <div
            aria-hidden="true"
            className="relative hidden min-h-[28rem] animate-hero-drift lg:block"
          >
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* —— Trust strip —— */}
      <section className="border-y border-stone-200 bg-white/60 py-8">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 sm:px-8 lg:flex-row lg:items-center lg:gap-10 lg:px-10">
          <p className="shrink-0 text-xs font-medium text-stone-500">Built around</p>
          <ul className="flex flex-wrap items-center gap-x-8 gap-y-3">
            {TRUST.map((label) => (
              <li
                key={label}
                className="text-sm font-semibold tracking-tight text-stone-400"
              >
                {label}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* —— Why —— */}
      <section id="why" className="scroll-mt-20 px-5 py-20 sm:px-8 lg:px-10">
        <div className="mx-auto max-w-6xl text-center">
          <p className="inline-flex rounded-full border border-stone-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">
            Why BillWise
          </p>
          <h2 className="mt-4 font-display text-3xl text-stone-900 sm:text-4xl">
            Obligations for students abroad, simplified.
          </h2>
          <ul className="mt-12 grid gap-5 text-left md:grid-cols-3">
            {FEATURES.map((feature) => (
              <li
                key={feature.title}
                className={`rounded-[1.75rem] p-6 ${feature.tint}`}
              >
                <FeatureWidget kind={feature.widget} />
                <h3 className="mt-5 text-lg font-semibold text-stone-900">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-stone-600">{feature.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* —— Product deep dives —— */}
      <section id="product" className="scroll-mt-20 space-y-24 px-5 pb-20 sm:px-8 lg:px-10">
        <FeatureRow
          eyebrow="Bills & forecast"
          title="Know if tuition and rent are covered this month."
          body="Confirmed bills sit against projected cash flow so you can see the shortfall date — not just a static balance."
          align="left"
          visual="forecast"
        />
        <FeatureRow
          eyebrow="Subscriptions"
          title="Catch duplicates before they renew."
          body="Recurring series show evidence and confidence. Overlaps are flagged so you review before cancelling anything."
          align="right"
          visual="subs"
        />
        <FeatureRow
          eyebrow="BillWise AI"
          title="Ask the question. See the tools behind the answer."
          body="Every assistant reply is labelled BillWise AI. Figures come from backend tools — the model never does the arithmetic."
          align="left"
          visual="assistant"
        />
      </section>

      {/* —— Testimonial —— */}
      <section className="px-5 pb-20 sm:px-8 lg:px-10">
        <div className="mx-auto max-w-6xl rounded-[2rem] bg-[#DCE8E0] px-8 py-12 sm:px-12">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-900/70">
            From the demo
          </p>
          <blockquote className="mt-4 max-w-3xl font-display text-2xl leading-snug text-stone-900 sm:text-3xl">
            “I finally saw the remittance and the rent on the same timeline — the
            shortfall wasn’t a surprise anymore.”
          </blockquote>
          <div className="mt-8 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-900 text-sm font-semibold text-white">
              AO
            </span>
            <div>
              <p className="text-sm font-semibold text-stone-900">Amina Osei</p>
              <p className="text-xs text-stone-600">Demo student · Ghana → UAE</p>
            </div>
          </div>
        </div>
      </section>

      {/* —— FAQ —— */}
      <section id="faq" className="scroll-mt-20 border-t border-stone-200 bg-white px-5 py-20 sm:px-8 lg:px-10">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">
              FAQ
            </p>
            <h2 className="mt-3 font-display text-3xl text-stone-900 sm:text-4xl">
              Questions before you start
            </h2>
          </div>
          <ul className="divide-y divide-stone-200">
            {FAQ.map((item, index) => {
              const open = openFaq === index
              return (
                <li key={item.q}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-4 py-5 text-left"
                    aria-expanded={open}
                    onClick={() => setOpenFaq(open ? null : index)}
                  >
                    <span className="text-sm font-semibold text-stone-900 sm:text-base">
                      {item.q}
                    </span>
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-stone-300 text-lg leading-none text-stone-600 transition ${
                        open ? 'rotate-45 bg-stone-100' : ''
                      }`}
                      aria-hidden="true"
                    >
                      +
                    </span>
                  </button>
                  {open && (
                    <p className="pb-5 pr-12 text-sm leading-relaxed text-stone-600">
                      {item.a}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      </section>

      {/* —— Footer CTA —— */}
      <section className="border-t border-stone-200 px-5 py-16 sm:px-8 lg:px-10">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 sm:flex-row sm:items-end">
          <div className="max-w-lg">
            <p className="font-display text-3xl text-stone-900 sm:text-4xl">
              Create your demo account
            </p>
            <p className="mt-3 text-sm text-stone-600">
              Pick a student story and open the full product — Overview through BillWise AI.
            </p>
          </div>
          <Link
            to="/get-started"
            className="inline-flex rounded-full bg-emerald-900 px-6 py-3 text-sm font-semibold text-white hover:bg-emerald-800"
          >
            Sign up
          </Link>
        </div>
      </section>

      <footer className="border-t border-stone-200 px-5 py-10 sm:px-8 lg:px-10">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 sm:flex-row sm:justify-between">
          <div>
            <p className="font-display text-xl text-stone-900">BillWise</p>
            <p className="mt-2 max-w-xs text-xs leading-relaxed text-stone-500">
              Obligations for students abroad. Demo product · synthetic data · not
              financial advice.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8 text-sm sm:grid-cols-3">
            <div>
              <p className="font-semibold text-stone-900">Product</p>
              <ul className="mt-3 space-y-2 text-stone-500">
                <li>
                  <a href="/#product" className="hover:text-stone-800">
                    Features
                  </a>
                </li>
                <li>
                  <a href="/#why" className="hover:text-stone-800">
                    Why BillWise
                  </a>
                </li>
                <li>
                  <Link to="/get-started" className="hover:text-stone-800">
                    Sign up
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-stone-900">Account</p>
              <ul className="mt-3 space-y-2 text-stone-500">
                <li>
                  <Link to="/login" className="hover:text-stone-800">
                    Log in
                  </Link>
                </li>
                <li>
                  <Link to="/get-started" className="hover:text-stone-800">
                    Create demo
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-stone-900">Trust</p>
              <ul className="mt-3 space-y-2 text-stone-500">
                <li>
                  <a href="/#faq" className="hover:text-stone-800">
                    FAQ
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </footer>
    </MarketingChrome>
  )
}

function FeatureRow({
  eyebrow,
  title,
  body,
  align,
  visual,
}: {
  eyebrow: string
  title: string
  body: string
  align: 'left' | 'right'
  visual: 'forecast' | 'subs' | 'assistant'
}) {
  const copy = (
    <div className="max-w-md">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-800/80">
        {eyebrow}
      </p>
      <h3 className="mt-3 font-display text-3xl text-stone-900">{title}</h3>
      <p className="mt-3 text-sm leading-relaxed text-stone-600">{body}</p>
      <Link
        to="/get-started"
        className="mt-6 inline-flex rounded-full border border-stone-300 bg-white px-5 py-2.5 text-sm font-semibold text-stone-800 hover:bg-stone-50"
      >
        Learn more
      </Link>
    </div>
  )

  const panel = (
    <div className="relative overflow-hidden rounded-[1.75rem] border border-stone-200 bg-white p-6 shadow-[0_20px_50px_-30px_rgba(0,0,0,0.25)]">
      <ProductMock kind={visual} />
    </div>
  )

  return (
    <div
      className={`mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-2 ${
        align === 'right' ? '' : ''
      }`}
    >
      <div className={align === 'right' ? 'lg:order-2' : ''}>{copy}</div>
      <div className={align === 'right' ? 'lg:order-1' : ''}>{panel}</div>
    </div>
  )
}

function FeatureWidget({ kind }: { kind: string }) {
  if (kind === 'alert') {
    return (
      <div className="rounded-2xl border border-rose-200/80 bg-white/80 p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-500">
          Cash-flow alert
        </p>
        <p className="mt-2 font-display text-xl text-stone-900">Shortfall · 1 Nov</p>
        <p className="mt-1 text-xs text-stone-500">AED 3,716 projected low</p>
      </div>
    )
  }
  if (kind === 'ai') {
    return (
      <div className="rounded-2xl border border-sky-200/80 bg-white/80 p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-sky-700">
          BillWise AI
        </p>
        <p className="mt-2 text-sm text-stone-800">“What bills hit before my remittance?”</p>
        <div className="mt-3 h-2 w-full rounded-full bg-stone-100">
          <div className="h-2 w-2/3 rounded-full bg-emerald-700/80" />
        </div>
      </div>
    )
  }
  return (
    <div className="rounded-2xl border border-emerald-200/80 bg-white/80 p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
        Remittance
      </p>
      <p className="mt-2 font-display text-xl text-stone-900">GHS 2,800</p>
      <p className="mt-1 text-xs text-stone-500">Dated simulated rate · Accra</p>
    </div>
  )
}

function ProductMock({ kind }: { kind: 'forecast' | 'subs' | 'assistant' }) {
  if (kind === 'forecast') {
    return (
      <div>
        <p className="text-xs font-medium text-stone-500">Projected balance</p>
        <p className="mt-1 font-display text-3xl text-stone-900">AED −852</p>
        <div className="mt-6 flex h-28 items-end gap-1.5">
          {[40, 55, 48, 62, 50, 35, 28, 22, 30, 18, 25, 15].map((h, i) => (
            <div
              key={i}
              className="flex-1 rounded-t-md bg-emerald-800/80"
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
      </div>
    )
  }
  if (kind === 'subs') {
    return (
      <div className="space-y-3">
        {[
          ['Spotify Duo', 'Likely · AED 37'],
          ['Netflix', 'Possible duplicate'],
          ['Adobe CC', 'Price change'],
        ].map(([name, meta]) => (
          <div
            key={name}
            className="flex items-center justify-between rounded-xl border border-stone-100 bg-stone-50 px-4 py-3"
          >
            <p className="text-sm font-medium text-stone-900">{name}</p>
            <p className="text-xs text-stone-500">{meta}</p>
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="rounded-2xl rounded-bl-md bg-emerald-900 px-4 py-3 text-sm text-emerald-50">
        Which obligations clear before my next remittance?
      </div>
      <div className="rounded-2xl rounded-br-md border border-stone-200 bg-stone-50 px-4 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-800">
          BillWise AI
        </p>
        <p className="mt-2 text-sm text-stone-700">
          Rent and tuition clear first. Remittance is safer after the 5th.
        </p>
      </div>
    </div>
  )
}

function HeroVisual() {
  return (
    <div className="absolute inset-0 flex items-center justify-end">
      <div className="relative h-full w-[92%] overflow-hidden rounded-l-[2.5rem] border border-r-0 border-stone-200 bg-gradient-to-br from-[#0B3D2E] via-[#0F4A38] to-[#163C32] p-8 text-white shadow-[0_30px_80px_-40px_rgba(11,61,46,0.8)]">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-200/80">
          Upcoming
        </p>
        <ul className="mt-8 space-y-6">
          {[
            { label: 'Tuition instalment', when: '1 Nov', amount: 'AED 8,400' },
            { label: 'Rent · Dubai Marina', when: '3 Nov', amount: 'AED 4,200' },
            { label: 'Remittance · Accra', when: '5 Nov', amount: 'GHS 2,800' },
            { label: 'Netflix · review', when: '12 Nov', amount: 'AED 56' },
          ].map((row, index) => (
            <li
              key={row.label}
              className="animate-line-draw origin-left border-b border-white/10 pb-5"
              style={{ animationDelay: `${160 + index * 120}ms` }}
            >
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">{row.label}</p>
                  <p className="mt-1 text-[11px] uppercase tracking-[0.14em] text-emerald-100/50">
                    {row.when}
                  </p>
                </div>
                <p className="font-sans text-lg tabular-nums tracking-tight">{row.amount}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
