export type ClashExtractionProgress = {
  processed: number
  total: number
  current_files?: string[]
  elapsed_s?: number
  phase?: 'extraction' | 'clash' | string
}

export type ClashJob = {
  id: string
  project_id: string
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  coordination_profile: string | null
  error: string | null
  progress?: ClashExtractionProgress | null
  created_at: string
  updated_at: string
}
