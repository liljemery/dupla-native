export type BudgetJobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface BudgetJob {
  id: string
  project_id: string
  job_id: string
  status: BudgetJobStatus
  discipline?: string | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface BudgetRow {
  code: string
  nat: string
  unit: string
  summary: string
  quantity: number | null
  unit_price: number
  amount: number
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
