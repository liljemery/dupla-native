import type { BootstrapCriterion } from '../types/project'

export function bootstrapRequiredPercent(criteria: BootstrapCriterion[]): {
  pct: number | null
  label: string
  done: number
  required: number
} {
  const required = criteria.filter((c) => c.required)
  if (required.length === 0) {
    return { pct: null, label: 'Sin ítems obligatorios en el checklist.', done: 0, required: 0 }
  }
  const done = required.filter((c) => c.done).length
  return {
    pct: Math.round((done / required.length) * 100),
    label: `${done} de ${required.length} ítems obligatorios cumplidos`,
    done,
    required: required.length,
  }
}

export function isBootstrapComplete(criteria: BootstrapCriterion[]): boolean {
  const { required, done } = bootstrapRequiredPercent(criteria)
  return required === 0 || done >= required
}
