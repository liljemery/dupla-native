export type BudgetJobStatus = 'queued' | 'processing' | 'completed' | 'completed_partial' | 'failed'

export interface BudgetJob {
  id: string
  project_id: string
  job_id: string
  status: BudgetJobStatus
  discipline?: string | null
  error?: string | null
  phase?: string | null
  phase_detail?: string | null
  created_at: string
  updated_at: string
}

export interface BudgetRowProvenanceMetadata {
  source_file?: string
  level_name?: string
  source_layer?: string
  source_discipline?: string
  provenance_suffix?: string
  confidence?: number
  requiere_revision?: boolean
  source_row_indices?: number[]
  subtotal_row_index?: number
  manual_amount?: boolean
}

export interface BudgetRow {
  row_type?: 'chapter' | 'line' | 'subtotal'
  code: string
  nat: string
  unit: string
  summary: string
  quantity: number | null
  unit_price: number
  amount: number
  metadata?: BudgetRowProvenanceMetadata
}

export interface BudgetResult {
  rows: BudgetRow[]
  chapters?: unknown[]
  hybrid_inventory?: unknown[]
  takeoffs?: unknown[]
  lines?: unknown[]
  extraction?: {
    mode?: string
    artifact_key?: string
    artifact_cache_hit?: boolean
    suggested_discipline?: string
  }
  output?: {
    mode?: string
    artifact_key?: string
    run_dir?: string
    disciplines?: string[]
    archive?: string
    artifacts?: Record<string, string>
  }
}
