export type ClashJob = {
  id: string
  project_id: string
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'failed'
  coordination_profile: string | null
  error: string | null
  created_at: string
  updated_at: string
}
