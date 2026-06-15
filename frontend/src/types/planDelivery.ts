export type PlanDeliveryRow = {
  uuid: string
  request_number: string
  sequence_number: number
  request_date: string | null
  description: string
  delivery_date: string | null
  days_count: number | null
  days_resolved: number | null
  status: string
  created_at: string
  updated_at: string
}
