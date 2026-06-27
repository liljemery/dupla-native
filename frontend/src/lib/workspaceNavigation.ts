export type WorkspacePrimaryTabId =
  | 'hub'
  | 'pliego'
  | 'presupuesto'
  | 'planosHallazgos'
  | 'revisiones'
  | 'eventos'
  | 'flujo'

export type PresupuestoSectionId = 'presupuesto' | 'cotizaciones' | 'checklist' | 'basePrecios'
export type PlanosHallazgosSectionId = 'planos' | 'hallazgos'
export type RevisionesSectionId = 'revisiones' | 'entregas'

const LEGACY_TAB_MAP: Record<string, { tab: string; section?: string }> = {
  especificaciones: { tab: 'pliego' },
  pliegos: { tab: 'hub' },
  materiales: { tab: 'hub' },
  detalles: { tab: 'hub' },
  resumen: { tab: 'hub' },
  documentos: { tab: 'planosHallazgos', section: 'planos' },
  historial: { tab: 'eventos' },
  presupuestoMaestro: { tab: 'presupuesto', section: 'presupuesto' },
  basePrecios: { tab: 'presupuesto', section: 'basePrecios' },
  archivos: { tab: 'planosHallazgos', section: 'planos' },
  hallazgos: { tab: 'planosHallazgos', section: 'hallazgos' },
  entregaPlanos: { tab: 'revisiones', section: 'entregas' },
}

const CONSOLE_PARENT: Record<string, WorkspacePrimaryTabId> = {
  detalles: 'hub',
  flujo: 'hub',
  presupuestoMaestro: 'presupuesto',
  basePrecios: 'presupuesto',
  archivos: 'planosHallazgos',
  hallazgos: 'planosHallazgos',
  entregaPlanos: 'revisiones',
}

export function resolveConsoleTabId(tab: string): string {
  return CONSOLE_PARENT[tab] ?? tab
}

export function defaultSectionForTab(tab: string): string | null {
  if (tab === 'presupuesto') return 'presupuesto'
  if (tab === 'planosHallazgos') return 'planos'
  if (tab === 'revisiones') return 'revisiones'
  return null
}

export function normalizeWorkspaceRoute(
  rawTab: string | null | undefined,
  rawSection: string | null | undefined,
): { tab: string; section: string | null } {
  const trimmed = rawTab?.trim() ?? ''
  const mapped = trimmed ? LEGACY_TAB_MAP[trimmed] : undefined
  const tab = mapped?.tab ?? (trimmed || 'hub')
  const section = mapped?.section ?? rawSection?.trim() ?? defaultSectionForTab(tab)
  return { tab, section: section || null }
}

export function hintNavigationTarget(hintTabId: string): { tab: string; section?: string } {
  if (hintTabId === 'documentos') return { tab: 'planosHallazgos', section: 'planos' }
  if (hintTabId === 'presupuestoMaestro') return { tab: 'presupuesto', section: 'presupuesto' }
  if (hintTabId === 'historial') return { tab: 'eventos' }
  if (hintTabId === 'resumen' || hintTabId === 'hub') return { tab: 'hub' }
  return { tab: hintTabId }
}
