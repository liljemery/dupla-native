import type { BootstrapCriterion } from '../types/project'

/** Alineado con `backend/app/domain/bootstrap_defaults.py` (IDs estables para fallback en cliente). */
export function defaultBootstrapCriteria(): BootstrapCriterion[] {
  return [
    {
      id: 'dupla-bootstrap-estructural',
      label: 'Planos estructurales (cimentaciones, zapatas, columnas y vigas)',
      required: true,
      done: false,
    },
    {
      id: 'dupla-bootstrap-tecnicos',
      label: 'Planos técnicos',
      required: true,
      done: false,
    },
    {
      id: 'dupla-bootstrap-elementos',
      label: 'Planos con información completa por cada elemento',
      required: true,
      done: false,
    },
  ]
}
