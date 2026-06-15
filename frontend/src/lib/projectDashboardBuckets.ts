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
  const order = WORKFLOW_PHASE_ORDER as readonly string[]
  const i = order.indexOf(phase)
  if (i < 0) return 8
  const denom = Math.max(1, order.length - 1)
  return Math.min(100, Math.round((i / denom) * 100))
}
