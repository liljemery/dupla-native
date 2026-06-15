import { PLIEGO_GA_FO_01_ARQUITECTURA } from '../data/pliegoGaFo01Arquitectura'
import type { PliegoItemEstado, PliegoItemState, PliegoSectionApproval } from '../types/pliegoForm'

export function catalogItemIds(): string[] {
  const ids: string[] = []
  for (const sec of PLIEGO_GA_FO_01_ARQUITECTURA.secciones) {
    for (const it of sec.items) {
      ids.push(it.id)
    }
  }
  return ids
}

export function buildDefaultPliegoItemStates(): Record<string, PliegoItemState> {
  const out: Record<string, PliegoItemState> = {}
  for (const id of catalogItemIds()) {
    out[id] = { estado: 'PENDIENTE', notas: '', file_uuid: null, file_name: null }
  }
  return out
}

function coerceEstado(raw: unknown): PliegoItemEstado {
  const ok: PliegoItemEstado[] = ['PENDIENTE', 'COMPLETO', 'INCOMPLETO', 'EN_REVISION', 'NO_APLICA']
  return typeof raw === 'string' && (ok as string[]).includes(raw) ? (raw as PliegoItemEstado) : 'PENDIENTE'
}

export function mergePliegoItemStates(
  saved: Record<string, unknown> | undefined,
): Record<string, PliegoItemState> {
  const defaults = buildDefaultPliegoItemStates()
  if (!saved || typeof saved !== 'object') return defaults
  for (const id of catalogItemIds()) {
    const row = saved[id]
    if (!row || typeof row !== 'object') continue
    const o = row as Record<string, unknown>
    defaults[id] = {
      estado: coerceEstado(o.estado),
      notas: typeof o.notas === 'string' ? o.notas : '',
      file_uuid: typeof o.file_uuid === 'string' ? o.file_uuid : null,
      file_name: typeof o.file_name === 'string' ? o.file_name : null,
    }
  }
  return defaults
}

export function pliegoProgressPercent(states: Record<string, PliegoItemState>): number {
  const ids = catalogItemIds()
  if (ids.length === 0) return 0
  let done = 0
  for (const id of ids) {
    const e = states[id]?.estado
    if (e === 'COMPLETO' || e === 'NO_APLICA') done += 1
  }
  return Math.round((done / ids.length) * 100)
}

/** Firma estable de estados (para invalidar aprobación si cambió el checklist). */
export function stablePliegoItemStatesSignature(states: Record<string, PliegoItemState>): string {
  const ids = catalogItemIds()
  const payload: Record<string, { estado: PliegoItemEstado; file_uuid: string | null }> = {}
  for (const id of ids) {
    const s = states[id]
    payload[id] = {
      estado: s?.estado ?? 'PENDIENTE',
      file_uuid: s?.file_uuid ?? null,
    }
  }
  return JSON.stringify(payload)
}

export function isGaFoChecklistFullyTerminal(states: Record<string, PliegoItemState>): boolean {
  return pliegoProgressPercent(states) === 100
}

export type GaFoSectionProgressRow = { id: string; titulo: string; done: number; total: number }

export function gaFoSectionProgressRows(states: Record<string, PliegoItemState>): GaFoSectionProgressRow[] {
  return PLIEGO_GA_FO_01_ARQUITECTURA.secciones.map((sec) => {
    let done = 0
    const total = sec.items.length
    for (const it of sec.items) {
      const e = states[it.id]?.estado
      if (e === 'COMPLETO' || e === 'NO_APLICA') done += 1
    }
    return { id: sec.id, titulo: sec.titulo, done, total }
  })
}

export function gaFoSectionIdForItem(itemId: string): string | null {
  for (const sec of PLIEGO_GA_FO_01_ARQUITECTURA.secciones) {
    if (sec.items.some((it) => it.id === itemId)) return sec.id
  }
  return null
}

export function markGaFoSectionItemsComplete(
  states: Record<string, PliegoItemState>,
  sectionId: string,
): Record<string, PliegoItemState> {
  const sec = PLIEGO_GA_FO_01_ARQUITECTURA.secciones.find((s) => s.id === sectionId)
  if (!sec) return states
  const next = { ...states }
  for (const it of sec.items) {
    const prev = next[it.id] ?? { estado: 'PENDIENTE' as const, notas: '', file_uuid: null, file_name: null }
    next[it.id] = { ...prev, estado: 'COMPLETO' }
  }
  return next
}

export function parseGaFoApprovedSections(
  spec: Record<string, unknown> | undefined,
): Record<string, string> {
  if (!spec || typeof spec !== 'object') return {}
  const ga = spec.ga_fo_01_arquitectura
  if (!ga || typeof ga !== 'object') return {}
  const raw = (ga as Record<string, unknown>).approved_sections
  if (!raw || typeof raw !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [key, val] of Object.entries(raw)) {
    if (val && typeof val === 'object' && typeof (val as PliegoSectionApproval).approved_at === 'string') {
      out[key] = (val as PliegoSectionApproval).approved_at
    }
  }
  return out
}

export function serializeGaFoApprovedSections(
  approved: Record<string, string>,
): Record<string, PliegoSectionApproval> {
  const out: Record<string, PliegoSectionApproval> = {}
  for (const [sectionId, approvedAt] of Object.entries(approved)) {
    if (approvedAt) out[sectionId] = { approved_at: approvedAt }
  }
  return out
}
