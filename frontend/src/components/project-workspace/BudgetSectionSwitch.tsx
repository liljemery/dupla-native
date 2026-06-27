import type { PresupuestoSectionId } from '../../lib/workspaceNavigation'
import { WorkspaceSectionSwitch } from './WorkspaceSectionSwitch'

const SECTIONS = [
  { id: 'presupuesto', label: 'Presupuesto' },
  { id: 'cotizaciones', label: 'Cotizaciones' },
  { id: 'checklist', label: 'Checklist' },
  { id: 'basePrecios', label: 'Base de precios' },
]

type BudgetSectionSwitchProps = {
  value: PresupuestoSectionId
  onChange: (id: PresupuestoSectionId) => void
}

export function BudgetSectionSwitch({ value, onChange }: BudgetSectionSwitchProps) {
  return (
    <WorkspaceSectionSwitch
      sections={SECTIONS}
      value={value}
      onChange={(id) => onChange(id as PresupuestoSectionId)}
      ariaLabel="Secciones de presupuesto"
    />
  )
}

export type { PresupuestoSectionId as BudgetSectionId }
