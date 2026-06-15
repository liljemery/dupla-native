import {
  BUSINESS_PLIEGO_SECTION_KEYS,
  MIN_PLIEGO_SECTION_LEN,
  parseBusinessPliegoFromSpec,
} from '../constants/businessPliego'
import type { ConstructionLineValue } from '../types/constructionPliego'
import type { PliegoItemState } from '../types/pliegoForm'
import {
  isConstructionPliegoFullyComplete,
  isConstructionPliegoSchemaActive,
  parseConstructionPliegoFromSpec,
} from './constructionPliegoState'
import { isGaFoChecklistFullyTerminal, mergePliegoItemStates } from './pliegoFormState'

export function buildPliegoDraftSpec(
  spec: Record<string, unknown> | undefined,
  pliegoItemStates: Record<string, PliegoItemState>,
  constructionLines: Record<string, ConstructionLineValue>,
  includeConstruction: boolean,
): Record<string, unknown> {
  const base = spec ? { ...spec } : {}
  const prevGa = spec?.ga_fo_01_arquitectura
  base.ga_fo_01_arquitectura = {
    ...(typeof prevGa === 'object' && prevGa ? prevGa : {}),
    schema_version: 1,
    item_states: pliegoItemStates,
  }
  if (includeConstruction) {
    base.construction_pliego = {
      schema_version: 1,
      lines: constructionLines,
    }
  }
  return base
}

/** Mirrors backend `pliego_sections_incomplete_message` for UI gating. */
export function pliegoSectionsIncompleteMessage(
  spec: Record<string, unknown> | undefined,
): string | null {
  if (!spec || typeof spec !== 'object') {
    return 'Falta el pliego de condiciones.'
  }
  if (isConstructionPliegoSchemaActive(spec)) {
    const lines = parseConstructionPliegoFromSpec(spec)
    if (!isConstructionPliegoFullyComplete(lines)) {
      return 'Faltan partidas por completar (unidad, cantidad y precio unitario en cada ítem del pliego de obra).'
    }
    return null
  }
  const bp = spec.business_pliego
  if (!bp || typeof bp !== 'object') {
    const ga = spec.ga_fo_01_arquitectura
    if (ga && typeof ga === 'object' && (ga as Record<string, unknown>).schema_version === 1) {
      const rawStates = (ga as { item_states?: Record<string, unknown> }).item_states
      const states = mergePliegoItemStates(rawStates)
      if (!isGaFoChecklistFullyTerminal(states)) {
        return 'Faltan documentos del checklist GA-FO-01 por marcar como Completo o No aplica.'
      }
      return null
    }
    return 'Genera o completa el pliego estructurado antes de aprobar.'
  }
  const parsed = parseBusinessPliegoFromSpec(spec)
  const missing = BUSINESS_PLIEGO_SECTION_KEYS.filter(
    (k) => (parsed.sections[k]?.trim().length ?? 0) < MIN_PLIEGO_SECTION_LEN,
  )
  if (missing.length > 0) {
    return `Faltan secciones o son demasiado cortas: ${missing.join(', ')}`
  }
  return null
}

export function isPliegoReadyForApproval(spec: Record<string, unknown> | undefined): boolean {
  return pliegoSectionsIncompleteMessage(spec) === null
}

const PLIEGO_EDITABLE_WORKFLOW_PHASES = new Set([
  'ARCHITECTURE_REVIEW',
  'SPECIFICATIONS',
  'BUDGETING_PIPELINE',
  'MANAGEMENT_APPROVAL',
  'BUDGET_APPROVED',
  'COMPLETE',
])

export function isPliegoEditablePhase(workflowPhase: string | undefined): boolean {
  return workflowPhase != null && PLIEGO_EDITABLE_WORKFLOW_PHASES.has(workflowPhase)
}

export function pliegoReadOnlyMessage(workflowPhase: string | undefined): string | null {
  if (isPliegoEditablePhase(workflowPhase)) return null
  return 'El pliego de condiciones solo es editable desde revisión de arquitectura hasta proyecto completo.'
}
