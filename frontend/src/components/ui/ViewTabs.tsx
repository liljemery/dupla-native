type ViewTab = {
  id: string
  label: string
}

type ViewTabsProps = {
  tabs: ViewTab[]
  activeId: string
  onChange: (id: string) => void
  ariaLabel?: string
  className?: string
  'data-tour'?: string
}

export function ViewTabs({
  tabs,
  activeId,
  onChange,
  ariaLabel = 'Vista',
  className = '',
  'data-tour': dataTour,
}: ViewTabsProps) {
  return (
    <div
      data-tour={dataTour}
      className={`flex gap-6 border-b border-slate-200 ${className}`}
      role="tablist"
      aria-label={ariaLabel}
    >
      {tabs.map((t) => {
        const active = activeId === t.id
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
              className={`relative -mb-px border-b-[3px] pb-3 text-sm font-semibold transition-colors ${
              active
                ? 'border-primary text-ink'
                : 'border-transparent text-muted hover:text-ink'
            }`}
            onClick={() => onChange(t.id)}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
