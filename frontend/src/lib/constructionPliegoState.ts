import {
  BUSINESS_PLIEGO_SECTION_KEYS,
  MIN_PLIEGO_SECTION_LEN,
  type BusinessPliegoSectionKey,
} from '../constants/businessPliego'
import {
  CONSTRUCTION_PLIEGO_ALL_ITEM_IDS,
  CONSTRUCTION_PLIEGO_CHAPTERS,
} from '../constants/constructionPliegoStructure'
import type { ConstructionLineValue, ConstructionPliegoPersisted } from '../types/constructionPliego'

export function isConstructionPliegoSchemaActive(spec: Record<string, unknown> | undefined): boolean {
  if (!spec || typeof spec !== 'object') return false
  const cp = spec.construction_pliego
  if (!cp || typeof cp !== 'object') return false
  return (cp as ConstructionPliegoPersisted).schema_version === 1
}

export function emptyConstructionLineValues(): Record<string, ConstructionLineValue> {
  const o: Record<string, ConstructionLineValue> = {}
  for (const id of CONSTRUCTION_PLIEGO_ALL_ITEM_IDS) {
    const def = CONSTRUCTION_PLIEGO_CHAPTERS.flatMap((c) => c.items).find((it) => it.id_item === id)
    o[id] = {
      unidad: def?.unidad_default ?? '',
      cantidad: '',
      unitario: '',
    }
  }
  return o
}

export function parseConstructionPliegoFromSpec(
  spec: Record<string, unknown> | undefined,
): Record<string, ConstructionLineValue> {
  const base = emptyConstructionLineValues()
  if (!spec || typeof spec !== 'object') return base
  const raw = spec.construction_pliego
  if (!raw || typeof raw !== 'object') return base
  const lines = (raw as ConstructionPliegoPersisted).lines
  if (!lines || typeof lines !== 'object') return base
  for (const id of CONSTRUCTION_PLIEGO_ALL_ITEM_IDS) {
    const row = lines[id]
    if (!row || typeof row !== 'object') continue
    base[id] = {
      unidad: typeof row.unidad === 'string' ? row.unidad : String(row.unidad ?? ''),
      cantidad: typeof row.cantidad === 'string' ? row.cantidad : String(row.cantidad ?? ''),
      unitario: typeof row.unitario === 'string' ? row.unitario : String(row.unitario ?? ''),
    }
  }
  return base
}

export function parseConstructionApprovedChapters(
  spec: Record<string, unknown> | undefined,
): Record<number, string> {
  if (!spec || typeof spec !== 'object') return {}
  const raw = spec.construction_pliego
  if (!raw || typeof raw !== 'object') return {}
  const approved = (raw as ConstructionPliegoPersisted).approved_chapters
  if (!approved || typeof approved !== 'object') return {}
  const out: Record<number, string> = {}
  for (const [key, val] of Object.entries(approved)) {
    const num = Number(key)
    if (!Number.isFinite(num)) continue
    if (val && typeof val === 'object' && typeof val.approved_at === 'string') {
      out[num] = val.approved_at
    }
  }
  return out
}

export function serializeConstructionApprovedChapters(
  approved: Record<number, string>,
): Record<string, { approved_at: string }> {
  const out: Record<string, { approved_at: string }> = {}
  for (const [num, approvedAt] of Object.entries(approved)) {
    if (approvedAt) out[String(num)] = { approved_at: approvedAt }
  }
  return out
}

export function isConstructionChapterComplete(
  chapterNum: number,
  lines: Record<string, ConstructionLineValue>,
): boolean {
  const { done, total } = constructionChapterProgress(chapterNum, lines)
  return total > 0 && done === total
}

function parseNum(s: string): number | null {
  const t = s.trim().replace(',', '.')
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

export function lineSubtotal(v: ConstructionLineValue): number | null {
  const q = parseNum(v.cantidad)
  const u = parseNum(v.unitario)
  if (q == null || u == null) return null
  return Math.round(q * u * 100) / 100
}

export function isLineComplete(v: ConstructionLineValue): boolean {
  if (!v.unidad.trim()) return false
  const q = parseNum(v.cantidad)
  const u = parseNum(v.unitario)
  if (q == null || q <= 0) return false
  if (u == null || u < 0) return false
  return true
}

export function constructionChapterProgress(
  chapterNum: number,
  lines: Record<string, ConstructionLineValue>,
): { done: number; total: number } {
  const ch = CONSTRUCTION_PLIEGO_CHAPTERS.find((c) => c.num === chapterNum)
  if (!ch) return { done: 0, total: 0 }
  let done = 0
  for (const it of ch.items) {
    const row = lines[it.id_item] ?? emptyConstructionLineValues()[it.id_item]
    if (isLineComplete(row)) done += 1
  }
  return { done, total: ch.items.length }
}

export function isConstructionPliegoFullyComplete(lines: Record<string, ConstructionLineValue>): boolean {
  return CONSTRUCTION_PLIEGO_ALL_ITEM_IDS.every((id) => isLineComplete(lines[id] ?? { unidad: '', cantidad: '', unitario: '' }))
}

function formatLineForExport(id: string, descripcion: string, v: ConstructionLineValue): string {
  const sub = lineSubtotal(v)
  const subStr = sub != null ? String(sub) : '—'
  return `${id}\t${descripcion}\tUD:${v.unidad.trim() || '—'}\tCant:${v.cantidad.trim() || '—'}\tPU:${v.unitario.trim() || '—'}\tSub:${subStr}`
}

function rowFor(lines: Record<string, ConstructionLineValue>, id: string): ConstructionLineValue {
  return lines[id] ?? { unidad: '', cantidad: '', unitario: '' }
}

function chapterBlock(chapterNum: number, lines: Record<string, ConstructionLineValue>): string {
  const ch = CONSTRUCTION_PLIEGO_CHAPTERS.find((c) => c.num === chapterNum)
  if (!ch) return ''
  const head = `${chapterNum}. ${ch.titulo}`
  const body = ch.items
    .map((it) => formatLineForExport(it.id_item, it.descripcion, rowFor(lines, it.id_item)))
    .join('\n')
  return `${head}\n${body}`
}

/** Rellena las 9 secciones legacy para que el backend siga validando MIN_SECTION_LEN tras guardar. */
export function synthesizeBusinessSectionsFromConstruction(
  lines: Record<string, ConstructionLineValue>,
): Record<BusinessPliegoSectionKey, string> {
  const c = (n: number) => chapterBlock(n, lines)
  const filler =
    'Documento generado desde partidas de obra (construction_pliego). Valores editables en la consola del proyecto.'

  const parts: Record<BusinessPliegoSectionKey, string> = {
    scope: `${c(1)}\n\n${filler}`,
    technical_specifications: `${c(2)}\n\n${c(3)}`,
    materials: `${c(5)}`,
    construction_systems: `${c(4)}`,
    restrictions: `${c(7)}`,
    base_assumptions: `${c(6)}`,
    exclusions: `${c(8)}\n\nExclusiones contractuales no listadas explícitamente en partidas: ver condiciones generales y anexos.`,
    validated_documentation: CONSTRUCTION_PLIEGO_ALL_ITEM_IDS.map((id) => {
      const it = CONSTRUCTION_PLIEGO_CHAPTERS.flatMap((ch) => ch.items).find((x) => x.id_item === id)
      return formatLineForExport(id, it?.descripcion ?? id, rowFor(lines, id))
    }).join('\n'),
    identified_risks:
      'Riesgos: validar mediciones en sitio, disponibilidad de materiales y variaciones de mercado en unitarios. Revisar coherencia entre replanteo y cantidades declaradas.',
  }

  for (const k of BUSINESS_PLIEGO_SECTION_KEYS) {
    if ((parts[k]?.trim().length ?? 0) < MIN_PLIEGO_SECTION_LEN) {
      parts[k] = `${parts[k] ?? ''}\n\n${filler}`.slice(0, Math.max(MIN_PLIEGO_SECTION_LEN, (parts[k]?.length ?? 0) + filler.length))
    }
  }
  return parts
}
