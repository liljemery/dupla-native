export type BudgetSectionId = 'presupuesto' | 'cotizaciones' | 'checklist'

const SECTIONS: { id: BudgetSectionId; label: string }[] = [
  { id: 'presupuesto', label: 'Presupuesto' },
  { id: 'cotizaciones', label: 'Cotizaciones' },
  { id: 'checklist', label: 'Checklist' },
]

type BudgetSectionSwitchProps = {
  value: BudgetSectionId
  onChange: (id: BudgetSectionId) => void
}

export function BudgetSectionSwitch({ value, onChange }: BudgetSectionSwitchProps) {
  return (
    <div
      className="grid w-full grid-cols-3 gap-1 rounded-xl border border-black/10 bg-black/4 p-1"
      role="tablist"
      aria-label="Secciones de presupuesto"
    >
      {SECTIONS.map(({ id, label }) => {
        const active = value === id
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors ${
              active
                ? 'bg-white text-ink shadow-sm'
                : 'text-muted hover:bg-white/60 hover:text-ink'
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
