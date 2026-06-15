import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
}

export function PrimaryButton({ children, className = '', ...rest }: Props) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-base font-semibold uppercase tracking-wide text-white shadow-sm outline-none transition-[opacity,transform,box-shadow] duration-150 hover:opacity-[0.92] active:translate-y-px active:opacity-100 active:shadow-inner disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0 focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-offset-2 focus-visible:ring-offset-white ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
