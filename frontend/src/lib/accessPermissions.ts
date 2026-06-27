import type { UserRole } from '../constants/userRoles'
import { WORKFLOW_PHASE_LABELS } from '../constants/workflowPhases'

export const BUDGET_WORKSPACE_TAB_IDS = ['presupuesto'] as const

export const BUDGET_WORKFLOW_PHASES = new Set([
  'BUDGETING_PIPELINE',
  'MANAGEMENT_APPROVAL',
  'BUDGET_APPROVED',
])

export function hasPermission(permissions: readonly string[] | null | undefined, key: string): boolean {
  return (permissions ?? []).includes(key)
}

export function canViewBudget(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'budget.view')
}

export function isBudgetWorkspaceTab(tabId: string): boolean {
  return (BUDGET_WORKSPACE_TAB_IDS as readonly string[]).includes(tabId)
}

export function workflowPhaseLabelForRole(phase: string, permissions: readonly string[] | null | undefined): string {
  if (canViewBudget(permissions) || !BUDGET_WORKFLOW_PHASES.has(phase)) {
    return WORKFLOW_PHASE_LABELS[phase as keyof typeof WORKFLOW_PHASE_LABELS] ?? phase
  }
  return 'Etapa operativa'
}

export function isBudgetWorkflowPhase(phase: string): boolean {
  return BUDGET_WORKFLOW_PHASES.has(phase)
}

export function workflowStepTitleForRole(title: string, permissions: readonly string[] | null | undefined): string {
  if (canViewBudget(permissions)) return title
  if (/presupuesto/i.test(title)) return 'Etapa operativa'
  return title
}

export function hasElevatedAccess(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'admin.access')
}

export function canCreateUsers(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'admin.users.create')
}

export function canManagePermissions(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'admin.permissions.manage')
}

export function canEditTaskBoard(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'tasks.board.edit')
}

export function canViewAllTasks(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'tasks.board.view_all')
}

export function canAssignTasks(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'tasks.board.assign')
}

export function canManageTaskBoard(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'tasks.board.manage')
}

export function canMarkControlReview(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'lifecycle.control_review')
}

export function canMarkManagementReview(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'lifecycle.management_review')
}

export function canArchiveProjects(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'projects.archive')
}

export function canViewArchivedProjects(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'projects.view_archived')
}

export function canDeleteProjects(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'projects.delete')
}

export function canApproveSpecifications(permissions: readonly string[] | null | undefined): boolean {
  return hasPermission(permissions, 'lifecycle.approve_specs')
}

export function isFieldRole(role: UserRole | null): boolean {
  return role === 'PRESUPUESTO' || role === 'ARQUITECTURA'
}
