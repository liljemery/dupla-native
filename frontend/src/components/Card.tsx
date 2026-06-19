import type { HTMLAttributes, ReactNode } from 'react'

type Props = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  elevated?: boolean
  rounded2xl?: boolean
}

export function Card({ children, className = '', elevated = false, rounded2xl = false, ...rest }: Props) {
  const radius = rounded2xl ? 'rounded-2xl' : 'rounded-xl'
  const shadow = elevated ? 'shadow-[var(--shadow-elevated)]' : 'shadow-[var(--shadow-card)]'
  return (
    <div
      className={`${radius} border border-black/10 bg-white ${shadow} transition-shadow duration-150 ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
