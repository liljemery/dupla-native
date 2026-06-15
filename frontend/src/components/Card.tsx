import type { HTMLAttributes, ReactNode } from 'react'

type Props = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
}

export function Card({ children, className = '', ...rest }: Props) {
  return (
    <div
      className={`rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)] transition-shadow duration-150 ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
