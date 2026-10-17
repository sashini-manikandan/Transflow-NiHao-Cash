import type { ReactNode, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, className, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className ?? 'h-[1.125rem] w-[1.125rem] shrink-0'}
      {...props}
    >
      {children}
    </svg>
  )
}

export function OverviewIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Icon>
  )
}

export function SubscriptionsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 12a8 8 0 0 1 13.5-5.8" />
      <path d="M17.5 4v2.5H15" />
      <path d="M20 12a8 8 0 0 1-13.5 5.8" />
      <path d="M6.5 20v-2.5H9" />
      <circle cx="12" cy="12" r="2.25" />
    </Icon>
  )
}

export function BillsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M8 3h8a2 2 0 0 1 2 2v14l-3-1.5L12 19l-3-1.5L6 19V5a2 2 0 0 1 2-2z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h3" />
    </Icon>
  )
}

export function CrossBorderIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18" />
      <path d="M12 3a14 14 0 0 0 0 18" />
    </Icon>
  )
}

export function AssistantIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7.5 18.5 5 21v-4.2A7.5 7.5 0 1 1 12 19.5" />
      <path d="M9.5 10.5h.01" />
      <path d="M12 10.5h.01" />
      <path d="M14.5 10.5h.01" />
    </Icon>
  )
}
