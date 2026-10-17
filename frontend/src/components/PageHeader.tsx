import type { ReactNode } from 'react'

/**
 * Sticky page chrome shared by every tab.
 * Sits under the mobile top bar; flush to the top on desktop.
 */
export function PageHeader({
  title,
  lede,
  children,
}: {
  title: ReactNode
  lede?: ReactNode
  children?: ReactNode
}) {
  return (
    <header
      className="sticky z-20 mb-6 border-b border-line/70 bg-canvas/90 pb-4 pt-1
                 backdrop-blur-md top-14 lg:top-0"
    >
      <div className="flex flex-wrap items-end justify-between gap-4 pt-3">
        <div className="min-w-0 max-w-3xl">
          <h1 className="page-title">{title}</h1>
          {lede && <p className="page-lede">{lede}</p>}
        </div>
        {children && <div className="flex flex-wrap items-center gap-3">{children}</div>}
      </div>
    </header>
  )
}
