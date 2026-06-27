/**
 * Pestañas del workspace de proyecto (`ProjectWorkspacePage`).
 * `hub` es la vista de inicio (resumen); `flujo` solo se abre desde resumen.
 */
import { canViewBudget } from '../lib/accessPermissions'

const TAB_DEFS: { id: string; label: string }[] = [
  { id: 'hub', label: 'Resumen' },
  { id: 'pliego', label: 'Pliego' },
  { id: 'presupuesto', label: 'Presupuesto' },
  { id: 'planosHallazgos', label: 'Planos y hallazgos' },
  { id: 'revisiones', label: 'Revisiones y entregas' },
  { id: 'eventos', label: 'Cronología' },
  { id: 'flujo', label: 'Flujo del proyecto' },
]

const BUDGET_ONLY_TAB_IDS = new Set(['presupuesto'])

export function projectWorkspaceTabs(): { id: string; label: string }[] {
  return TAB_DEFS.map(({ id, label }) => ({ id, label }))
}

export function projectWorkspaceTabsForRole(permissions: readonly string[] | null | undefined): { id: string; label: string }[] {
  if (canViewBudget(permissions)) return projectWorkspaceTabs()
  return TAB_DEFS.filter((t) => !BUDGET_ONLY_TAB_IDS.has(t.id)).map(({ id, label }) => ({ id, label }))
}

export function projectWorkspaceSectionTabsForRole(permissions: readonly string[] | null | undefined): { id: string; label: string }[] {
  return projectWorkspaceTabsForRole(permissions).filter((t) => t.id !== 'hub')
}
