import type { ButtonHTMLAttributes, ReactNode } from 'react'

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  label: string
  variant?: 'default' | 'ghost'
}

export function IconButton({
  children,
  label,
  variant = 'default',
  className = '',
  ...rest
}: IconButtonProps) {
  const base =
    variant === 'ghost'
      ? 'rounded-xl p-2 text-muted transition-colors hover:bg-black/[0.04] hover:text-ink'
      : 'rounded-xl border border-black/10 bg-white p-2 text-ink shadow-sm transition-colors hover:bg-black/[0.03]'
  return (
    <button
      type="button"
      className={`${base} outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 ${className}`}
      aria-label={label}
      {...rest}
    >
      {children}
    </button>
  )
}
