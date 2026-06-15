/** Orden lineal del flujo (para indicadores visuales). */
export const WORKFLOW_PHASE_ORDER = [
  'BOOTSTRAPPING',
  'AWAITING_FILES',
  'ARCHITECTURE_REVIEW',
  'SPECIFICATIONS',
  'BUDGETING_PIPELINE',
  'MANAGEMENT_APPROVAL',
  'BUDGET_APPROVED',
  'COMPLETE',
] as const

export const WORKFLOW_PHASE_LABELS: Record<string, string> = {
  BOOTSTRAPPING: 'Criterios de arranque',
  AWAITING_FILES: 'Esperando archivos CAD',
  /** Legado / tareas creadas antes del cambio de flujo */
  FILES_INGESTED: 'Archivos ingresados',
  ARCHITECTURE_REVIEW: 'Revisión de arquitectura',
  SPECIFICATIONS: 'Pliego de condiciones',
  BUDGETING_PIPELINE: 'Presupuesto (cotización / volumetría / costo)',
  MANAGEMENT_APPROVAL: 'Aprobación de gerencia',
  BUDGET_APPROVED: 'Presupuesto aprobado por cliente',
  COMPLETE: 'Completo',
  CUSTOM_AUTOMATION: 'Automatización',
}

/** Siguiente fase en el flujo lineal (ISO). */
export const NEXT_WORKFLOW_PHASE: Record<string, string | undefined> = {
  BOOTSTRAPPING: 'AWAITING_FILES',
  AWAITING_FILES: 'ARCHITECTURE_REVIEW',
  ARCHITECTURE_REVIEW: 'SPECIFICATIONS',
  SPECIFICATIONS: 'BUDGETING_PIPELINE',
  BUDGETING_PIPELINE: 'MANAGEMENT_APPROVAL',
  MANAGEMENT_APPROVAL: 'BUDGET_APPROVED',
  BUDGET_APPROVED: 'COMPLETE',
  COMPLETE: undefined,
}

/** Fase anterior inmediata (retroceso de un paso). */
export const PREV_WORKFLOW_PHASE: Record<string, string | undefined> = {
  AWAITING_FILES: 'BOOTSTRAPPING',
  ARCHITECTURE_REVIEW: 'AWAITING_FILES',
  SPECIFICATIONS: 'ARCHITECTURE_REVIEW',
  BUDGETING_PIPELINE: 'SPECIFICATIONS',
  MANAGEMENT_APPROVAL: 'BUDGETING_PIPELINE',
  BUDGET_APPROVED: 'MANAGEMENT_APPROVAL',
  COMPLETE: 'BUDGET_APPROVED',
}

/** Licitación (TENDER): no se permite retroceder por debajo de esta fase. */
export const TENDER_MIN_BACKWARD_PHASE = 'ARCHITECTURE_REVIEW' as const

/** Fase inmediatamente anterior permitida según tipo de proyecto (TENDER acotado). */
export function effectivePrevWorkflowPhase(
  projectKind: string | undefined | null,
  currentPhase: string,
): string | undefined {
  const prev = PREV_WORKFLOW_PHASE[currentPhase]
  if (!prev) return undefined
  if (projectKind === 'TENDER') {
    const order = WORKFLOW_PHASE_ORDER as readonly string[]
    const floorIdx = order.indexOf(TENDER_MIN_BACKWARD_PHASE)
    const prevIdx = order.indexOf(prev)
    if (prevIdx < floorIdx) return undefined
  }
  return prev
}

/** Transición de un paso (adelante o atrás) permitida para la tarjeta del tablero. */
export function isAdjacentWorkflowTransitionAllowed(
  projectKind: string | undefined | null,
  currentPhase: string,
  targetPhase: string,
): boolean {
  const next = NEXT_WORKFLOW_PHASE[currentPhase]
  const prev = effectivePrevWorkflowPhase(projectKind, currentPhase)
  return next === targetPhase || prev === targetPhase
}
