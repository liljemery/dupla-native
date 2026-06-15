import type { ClashStatus, Priority, ReviewerDecision, Severity } from '../types/clashWorkflow'

export const STATUS_LABELS: Record<ClashStatus, string> = {
  detected: 'Detectado',
  needs_review: 'Requiere revisión',
  correction_required: 'Corrección requerida',
  correction_uploaded: 'Corrección cargada',
  pending_reanalysis: 'Pendiente de reanálisis',
  resolved: 'Resuelto',
  still_present: 'Persiste tras reanálisis',
  false_positive: 'Falso positivo',
  closed: 'Cerrado',
}

export const DECISION_LABELS: Record<ReviewerDecision, string> = {
  correct_dwg_a: 'Corregir DWG A',
  correct_dwg_b: 'Corregir DWG B',
  correct_both: 'Corregir ambos',
  false_positive: 'Falso positivo',
  design_decision_needed: 'Decisión de diseño requerida',
  external_discipline_required: 'Disciplina externa requerida',
  keep_pending: 'Mantener pendiente',
}

export const DECISION_ORDER: ReviewerDecision[] = [
  'correct_dwg_a',
  'correct_dwg_b',
  'correct_both',
  'false_positive',
  'design_decision_needed',
  'external_discipline_required',
  'keep_pending',
]

export const STATUS_TRANSITIONS: Record<ClashStatus, ClashStatus[]> = {
  detected: ['needs_review', 'false_positive'],
  needs_review: ['correction_required', 'false_positive', 'detected'],
  correction_required: ['correction_uploaded', 'needs_review'],
  correction_uploaded: ['pending_reanalysis', 'correction_required'],
  pending_reanalysis: ['resolved', 'still_present'],
  still_present: ['correction_required', 'needs_review'],
  resolved: ['closed', 'still_present'],
  false_positive: ['closed', 'needs_review'],
  closed: ['needs_review'],
}

export const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: 'bg-primary/15 text-primary border border-primary/30',
  high: 'bg-orange-500/12 text-orange-900 border border-orange-500/30',
  medium: 'bg-amber-500/12 text-amber-900 border border-amber-500/30',
  low: 'bg-black/[0.06] text-muted border border-black/10',
}

export const PRIORITY_CLASSES: Record<Priority, string> = {
  P1: 'bg-primary text-white',
  P2: 'bg-amber-600 text-white',
  P3: 'bg-black/30 text-white',
}

export const STATUS_CLASSES: Record<ClashStatus, string> = {
  detected: 'bg-black/[0.06] text-ink',
  needs_review: 'bg-primary/10 text-primary',
  correction_required: 'bg-orange-500/12 text-orange-900',
  correction_uploaded: 'bg-indigo-500/12 text-indigo-900',
  pending_reanalysis: 'bg-purple-500/12 text-purple-900',
  resolved: 'bg-emerald-600/12 text-emerald-900',
  still_present: 'bg-primary/15 text-primary',
  false_positive: 'bg-black/[0.08] text-muted',
  closed: 'bg-ink text-white',
}
