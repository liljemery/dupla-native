import type { UserRole } from '../constants/userRoles'
import { WORKFLOW_PHASE_LABELS } from '../constants/workflowPhases'

export const BUDGET_WORKSPACE_TAB_IDS = ['presupuestoMaestro', 'basePrecios'] as const

export const BUDGET_WORKFLOW_PHASES = new Set([
  'BUDGETING_PIPELINE',
  'MANAGEMENT_APPROVAL',
  'BUDGET_APPROVED',
])

export function canViewBudget(role: UserRole | null): boolean {
  return role !== 'ARQUITECTURA'
}

export function isBudgetWorkspaceTab(tabId: string): boolean {
  return (BUDGET_WORKSPACE_TAB_IDS as readonly string[]).includes(tabId)
}

/** Etiqueta de fase sin exponer presupuesto a Arquitectura. */
export function workflowPhaseLabelForRole(phase: string, role: UserRole | null): string {
  if (canViewBudget(role) || !BUDGET_WORKFLOW_PHASES.has(phase)) {
    return WORKFLOW_PHASE_LABELS[phase as keyof typeof WORKFLOW_PHASE_LABELS] ?? phase
  }
  return 'Etapa operativa'
}

export function isBudgetWorkflowPhase(phase: string): boolean {
  return BUDGET_WORKFLOW_PHASES.has(phase)
}

export function workflowStepTitleForRole(title: string, role: UserRole | null): string {
  if (canViewBudget(role)) return title
  if (/presupuesto/i.test(title)) return 'Etapa operativa'
  return title
}

export function hasElevatedAccess(role: UserRole | null, isTeamLeader: boolean): boolean {
  return role === 'GERENCIA' || isTeamLeader
}

export function canCreateUsers(role: UserRole | null): boolean {
  return role === 'GERENCIA'
}

export function canAssignTeamLeader(role: UserRole | null): boolean {
  return role === 'GERENCIA'
}

export function canMarkControlReview(role: UserRole | null, isTeamLeader: boolean): boolean {
  return role === 'CONTROL' || hasElevatedAccess(role, isTeamLeader)
}

export function canApproveSpecifications(role: UserRole | null, isTeamLeader: boolean): boolean {
  return role === 'ARQUITECTURA' || hasElevatedAccess(role, isTeamLeader)
}
