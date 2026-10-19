import { Link } from 'react-router-dom'

type Tone = 'light' | 'dark'

/**
 * Tran$Flow mark + wordmark. SVG stays crisp in sidebar and marketing chrome.
 */
export function BrandLogo({
  to = '/',
  tone = 'dark',
  showWordmark = true,
  size = 'md',
}: {
  to?: string
  tone?: Tone
  showWordmark?: boolean
  size?: 'sm' | 'md' | 'lg'
}) {
  const box = size === 'lg' ? 'h-10 w-10' : size === 'sm' ? 'h-7 w-7' : 'h-8 w-8'
  const type =
    size === 'lg'
      ? 'text-[1.65rem]'
      : size === 'sm'
        ? 'text-lg'
        : 'text-2xl'
  const ink = tone === 'light' ? 'text-stone-900' : 'text-ink'

  return (
    <Link to={to} className={`inline-flex items-center gap-2.5 ${ink}`}>
      <img
        src="/logo.svg"
        alt=""
        width={40}
        height={40}
        className={`${box} shrink-0 rounded-[0.55rem]`}
        aria-hidden="true"
      />
      {showWordmark && (
        <span className={`font-display leading-none ${type}`}>Tran$Flow</span>
      )}
      <span className="sr-only">Tran$Flow home</span>
    </Link>
  )
}

/** Icon-only mark for tight spots (favicon-sized usages in UI). */
export function BrandMark({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <img
      src="/logo.svg"
      alt="Tran$Flow"
      width={32}
      height={32}
      className={`shrink-0 rounded-lg ${className}`}
    />
  )
}
