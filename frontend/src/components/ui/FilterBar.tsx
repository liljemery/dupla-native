import type { ReactNode } from 'react'

type FilterBarProps = {
  children: ReactNode
  search?: ReactNode
  className?: string
}

export function FilterBar({ children, search, className = '' }: FilterBarProps) {
  return (
    <div className={`du-filter-bar ${className}`}>
      <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
      {search ? <div className="w-full sm:w-auto sm:min-w-56 sm:max-w-xs">{search}</div> : null}
    </div>
  )
}

type FilterChipProps = {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}

export function FilterChip({ label, count, active, onClick }: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3.5 py-1.5 text-xs font-semibold transition ${
        active
          ? 'border-primary bg-primary text-white shadow-[0_2px_8px_rgba(193,13,18,0.35)]'
          : 'border-slate-200 bg-slate-50 text-muted hover:border-slate-300 hover:bg-white hover:text-ink'
      }`}
    >
      {label}
      {count !== undefined ? (
        <span className={`ml-1.5 tabular-nums ${active ? 'text-white/90' : 'text-muted'}`}>
          ({count})
        </span>
      ) : null}
    </button>
  )
}
