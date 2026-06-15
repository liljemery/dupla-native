export type ClashStatus =
  | 'detected'
  | 'needs_review'
  | 'correction_required'
  | 'correction_uploaded'
  | 'pending_reanalysis'
  | 'resolved'
  | 'still_present'
  | 'false_positive'
  | 'closed'

export type ReviewerDecision =
  | 'correct_dwg_a'
  | 'correct_dwg_b'
  | 'correct_both'
  | 'false_positive'
  | 'design_decision_needed'
  | 'external_discipline_required'
  | 'keep_pending'

export type Priority = 'P1' | 'P2' | 'P3'
export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type ClashRow = {
  id: string
  clash_code: string
  job_id: string
  priority: Priority
  severity: Severity
  report_confidence: string
  status: ClashStatus
  status_label: string
  reviewer_decision: ReviewerDecision | null
  decision_label: string | null
  dwg_a: string | null
  dwg_b: string | null
  level_id: string | null
  discipline_a: string | null
  discipline_b: string | null
  discipline_pair: string
  layer_a: string | null
  layer_b: string | null
  layers_involved: string
  observation: string | null
  recommended_action: string | null
  action_owner: string | null
  assigned_to: string | null
  member_count: number | null
  area_mm2: number | null
  overlap_depth_mm: number | null
  location: {
    unit: string
    model_centroid: { x: number; y: number; space: string }
    world_centroid: { x: number; y: number; space: string }
    world_bounds: { min: { x: number; y: number }; max: { x: number; y: number } }
    alignment_offset_mm: number[] | null
    autocad_zoom_window_command: string
  }
  updated_at: string | null
  created_at: string | null
}

export type ClashEvent = {
  id: string
  event_type: string
  actor: string
  actor_role: string | null
  previous_status: ClashStatus | null
  new_status: ClashStatus | null
  decision: ReviewerDecision | null
  comment: string | null
  created_at: string | null
}

export type CorrectionTarget = 'dwg_a' | 'dwg_b' | 'both'
export type CorrectionResult = 'resolved' | 'still_present'

export type ClashCorrection = {
  id: string
  target: CorrectionTarget
  target_label: string
  revision_name: string
  original_dwg: string | null
  file_name: string | null
  uploaded_by: string
  uploaded_at: string | null
  result: CorrectionResult | null
  result_label: string | null
  reanalysis_run_id: string | null
}

export type ClashDetail = ClashRow & {
  audit_trail: ClashEvent[]
  corrections: ClashCorrection[]
  visual_preview?: {
    available: boolean
    annotated_url: string | null
    plain_url: string | null
    default_url: string | null
    format: string
    description: string
  }
  dwg_comparison?: {
    dwg_a: { file_name: string | null; discipline: string | null; layer: string | null }
    dwg_b: { file_name: string | null; discipline: string | null; layer: string | null }
  }
}

export type DashboardMetrics = {
  job_id: string
  total_clashes: number
  by_severity: { critical: number; high: number; medium: number; low: number }
  by_priority: Record<string, number>
  by_status: Record<string, number>
  pending_reviewer_decisions: number
  correction_uploaded: number
  pending_reanalysis: number
  resolved: number
  false_positives: number
  still_present_after_reanalysis: number
}

export type FilterOptions = {
  priorities: Priority[]
  statuses: ClashStatus[]
  severities: Severity[]
  levels: string[]
  disciplines: string[]
  reviewers: string[]
  dwgs: string[]
}

export type ClashFilters = {
  priority?: string
  severity?: string
  status?: string
  level_id?: string
  discipline?: string
  assigned_to?: string
  dwg?: string
}
