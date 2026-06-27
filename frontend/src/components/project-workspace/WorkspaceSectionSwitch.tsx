type Section = { id: string; label: string }

const GRID_COLS: Record<number, string> = {
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-4',
}

type WorkspaceSectionSwitchProps = {
  sections: Section[]
  value: string
  onChange: (id: string) => void
  ariaLabel: string
}

export function WorkspaceSectionSwitch({ sections, value, onChange, ariaLabel }: WorkspaceSectionSwitchProps) {
  const gridClass = GRID_COLS[sections.length] ?? 'grid-cols-2'

  return (
    <div
      className={`grid w-full ${gridClass} gap-1 rounded-xl border border-black/10 bg-black/4 p-1`}
      role="tablist"
      aria-label={ariaLabel}
    >
      {sections.map(({ id, label }) => {
        const active = value === id
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors ${
              active ? 'bg-white text-ink shadow-sm' : 'text-muted hover:bg-white/60 hover:text-ink'
            }`}
            onClick={() => onChange(id)}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
