import type { ReactNode } from 'react'

type MetricCardProps = {
  label: string
  value: string | number
  footer?: ReactNode
  className?: string
  accent?: 'neutral' | 'primary' | 'amber' | 'emerald'
}

const accentStyles = {
  neutral: 'border-slate-200/80 bg-white',
  primary: 'border-primary/15 bg-gradient-to-br from-primary/[0.07] to-white',
  amber: 'border-amber-200/80 bg-gradient-to-br from-amber-50 to-white',
  emerald: 'border-emerald-200/80 bg-gradient-to-br from-emerald-50 to-white',
} as const

const valueStyles = {
  neutral: 'text-ink',
  primary: 'text-primary',
  amber: 'text-amber-700',
  emerald: 'text-emerald-700',
} as const

export function MetricCard({
  label,
  value,
  footer,
  className = '',
  accent = 'neutral',
}: MetricCardProps) {
  return (
    <div
      className={`rounded-2xl border px-5 py-4 shadow-(--shadow-toolbar) transition-all hover:-translate-y-0.5 hover:shadow-(--shadow-elevated) ${accentStyles[accent]} ${className}`}
    >
      <p className="text-[11px] font-bold uppercase tracking-wider text-muted">{label}</p>
      <p className={`du-kpi-value mt-2 ${valueStyles[accent]}`}>{value}</p>
      {footer ? <div className="mt-3">{footer}</div> : null}
    </div>
  )
}
