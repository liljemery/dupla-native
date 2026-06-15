import { canViewBudget, isBudgetWorkflowPhase } from '../lib/accessPermissions'
import type { UserRole } from './userRoles'

export type PhaseHint = {
  title: string
  body: string
  tabId: 'resumen' | 'flujo' | 'documentos' | 'revisiones' | 'historial' | 'pliego' | 'hub'
  cta: string
}

export const PHASE_WORKSPACE_HINTS: Record<string, PhaseHint> = {
  BOOTSTRAPPING: {
    title: 'Checklist de arranque',
    body: 'Marca los documentos obligatorios del checklist y guarda. Solo podrás avanzar cuando estén cumplidos.',
    tabId: 'flujo',
    cta: 'Abrir checklist de arranque',
  },
  AWAITING_FILES: {
    title: 'Subir archivos',
    body: 'Carga planos (DWG/DXF), PDF, IFC u otros adjuntos permitidos en Archivos. Con al menos un archivo cargado, puedes avanzar a revisión de arquitectura.',
    tabId: 'documentos',
    cta: 'Ir a Archivos',
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
    body: 'Con el pliego de condiciones cerrado, trabaja cotizaciones, volumetría y análisis; registra subcontratos si aplica.',
    tabId: 'flujo',
    cta: 'Ir a Flujo — presupuesto',
  },
  MANAGEMENT_APPROVAL: {
    title: 'Aprobación de gerencia',
    body: 'El presupuesto interno está listo: validación formal de gerencia antes de registrar la versión aprobada por el cliente.',
    tabId: 'flujo',
    cta: 'Ir a Flujo',
  },
  BUDGET_APPROVED: {
    title: 'Presupuesto aprobado',
    body: 'Continúa con archivos, el pliego y el control de entregas; cuando el proyecto esté cerrado, avanza a la fase final «Completo».',
    tabId: 'documentos',
    cta: 'Ir a Archivos',
  },
  COMPLETE: {
    title: 'Proyecto completo',
    body: 'Fase final. Puedes consultar archivos, exportaciones e historial del proyecto.',
    tabId: 'flujo',
    cta: 'Ir a Flujo',
  },
}

export function phaseWorkspaceHintForRole(
  phase: string,
  role: UserRole | null,
): PhaseHint | undefined {
  if (!canViewBudget(role) && isBudgetWorkflowPhase(phase)) return undefined
  return PHASE_WORKSPACE_HINTS[phase]
}
