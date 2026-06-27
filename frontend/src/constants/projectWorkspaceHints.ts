import { canViewBudget, isBudgetWorkflowPhase } from '../lib/accessPermissions'

export type PhaseHint = {
  title: string
  body: string
  tabId: 'hub' | 'flujo' | 'planosHallazgos' | 'revisiones' | 'eventos' | 'pliego' | 'presupuesto'
  cta: string
}

export const PHASE_WORKSPACE_HINTS: Record<string, PhaseHint> = {
  AWAITING_FILES: {
    title: 'Subir archivos',
    body: 'Carga planos (DWG/DXF), PDF, IFC u otros adjuntos permitidos. Con al menos un archivo cargado, puedes avanzar a revisión de arquitectura.',
    tabId: 'planosHallazgos',
    cta: 'Ir a Planos',
  },
  ARCHITECTURE_REVIEW: {
    title: 'Revisión de arquitectura',
    body: 'Registra la decisión (aprobado / rechazo / parcial) y las notas en Revisiones. Con aprobación, continúa con el pliego de condiciones.',
    tabId: 'revisiones',
    cta: 'Ir a Revisiones',
  },
  SPECIFICATIONS: {
    title: 'Pliego de condiciones',
    body: 'Completa el checklist GA-FO-01 por sección, adjunta documentos y solicita aprobación cuando esté listo.',
    tabId: 'pliego',
    cta: 'Ir al Pliego',
  },
  BUDGETING_PIPELINE: {
    title: 'Pipeline de presupuesto',
    body: 'Cotizaciones, hitos del pipeline y presupuesto maestro en la pestaña Presupuesto.',
    tabId: 'presupuesto',
    cta: 'Ir a Presupuesto',
  },
  MANAGEMENT_APPROVAL: {
    title: 'Aprobación de gerencia',
    body: 'El presupuesto interno está listo: validación formal de gerencia antes de registrar la versión aprobada por el cliente.',
    tabId: 'presupuesto',
    cta: 'Ir a Presupuesto',
  },
  BUDGET_APPROVED: {
    title: 'Presupuesto aprobado',
    body: 'Continúa con planos, el pliego y el control de entregas; cuando el proyecto esté cerrado, avanza a la fase final «Completo».',
    tabId: 'planosHallazgos',
    cta: 'Ir a Planos',
  },
  COMPLETE: {
    title: 'Proyecto completo',
    body: 'Fase final. Puedes consultar planos, exportaciones e historial del proyecto.',
    tabId: 'eventos',
    cta: 'Ir a Cronología',
  },
}

export function phaseWorkspaceHintForRole(
  phase: string,
  permissions: readonly string[] | null | undefined,
): PhaseHint | undefined {
  const key = phase === 'BOOTSTRAPPING' ? 'AWAITING_FILES' : phase
  if (!canViewBudget(permissions) && isBudgetWorkflowPhase(key)) return undefined
  return PHASE_WORKSPACE_HINTS[key]
}
