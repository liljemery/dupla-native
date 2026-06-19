import { WORKFLOW_PHASE_ORDER } from '../constants/workflowPhases'

/** Filtros del panel de control (resumen). */
export type DashboardStatusFilter = 'todos' | 'proceso' | 'revision' | 'cerrado'

export function projectDashboardBucket(phase: string): Exclude<DashboardStatusFilter, 'todos'> {
  if (phase === 'COMPLETE') return 'cerrado'
  if (phase === 'ARCHITECTURE_REVIEW' || phase === 'AWAITING_FILES' || phase === 'FILES_INGESTED') {
    return 'revision'
  }
  return 'proceso'
}

export function dashboardBucketLabel(bucket: Exclude<DashboardStatusFilter, 'todos'>): string {
  if (bucket === 'cerrado') return 'Cerrado'
  if (bucket === 'revision') return 'En revisión'
  return 'En proceso'
}

/** Progreso aproximado del flujo ISO (0–100) para la barra del listado. */
export function workflowPhaseProgressPct(phase: string): number {
  if (phase === 'COMPLETE') return 100
  const order = WORKFLOW_PHASE_ORDER as readonly string[]
  const i = order.indexOf(phase)
  if (i < 0) return 8
  // Punto medio del tramo de la fase, así la primera fase no queda en 0%.
  return Math.min(100, Math.max(0, Math.round(((i + 0.5) / order.length) * 100)))
}
