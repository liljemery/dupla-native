/**
 * Pestañas del workspace de proyecto (`ProjectWorkspacePage`).
 * `hub` es la vista de inicio (rejilla); no tiene formulario propio.
 */
import { BUDGET_WORKSPACE_TAB_IDS, canViewBudget } from '../lib/accessPermissions'
import type { UserRole } from './userRoles'

const TAB_DEFS: { id: string; label: string }[] = [
  { id: 'hub', label: 'Inicio' },
  { id: 'detalles', label: 'Detalles' },
  { id: 'flujo', label: 'Arranque y flujo' },
  { id: 'archivos', label: 'Archivos' },
  { id: 'basePrecios', label: 'Base de precios' },
  { id: 'entregaPlanos', label: 'Control de entregas' },
  { id: 'revisiones', label: 'Revisiones' },
  { id: 'hallazgos', label: 'Hallazgos' },
  { id: 'pliego', label: 'Pliego' },
  { id: 'presupuestoMaestro', label: 'Presupuesto maestro' },
  { id: 'eventos', label: 'Eventos' },
]

export function projectWorkspaceTabs(): { id: string; label: string }[] {
  return TAB_DEFS.map(({ id, label }) => ({ id, label }))
}

export function projectWorkspaceTabsForRole(role: UserRole | null): { id: string; label: string }[] {
  if (canViewBudget(role)) return projectWorkspaceTabs()
  const hidden = new Set<string>(BUDGET_WORKSPACE_TAB_IDS)
  return TAB_DEFS.filter((t) => !hidden.has(t.id)).map(({ id, label }) => ({ id, label }))
}

/** Pestañas con panel de contenido (excluye inicio). */
export function projectWorkspaceSectionTabs(): { id: string; label: string }[] {
  return TAB_DEFS.filter((t) => t.id !== 'hub').map(({ id, label }) => ({ id, label }))
}

export function projectWorkspaceSectionTabsForRole(role: UserRole | null): { id: string; label: string }[] {
  return projectWorkspaceTabsForRole(role).filter((t) => t.id !== 'hub')
}
