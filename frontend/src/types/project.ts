export type BootstrapCriterion = {
  id: string
  label: string
  required?: boolean
  done?: boolean
}

export type Project = {
  uuid: string
  name: string
  client_name: string | null
  /** TENDER = licitación, CLIENT = cliente, DEVELOPMENT = desarrollo */
  project_kind: string
  status: string
  workflow_phase: string
  workflow_meta: Record<string, unknown>
  project_bootstrap_criteria: BootstrapCriterion[]
  specifications_document: Record<string, unknown>
  created_by_user_uuid?: string | null
  /** ISO 8601 — última actividad registrada en el proyecto */
  updated_at: string
  project_code?: string | null
  location_text?: string | null
  estimated_area_sqm?: string | null
  floor_levels_count?: number | null
  /** YYYY-MM-DD */
  deadline?: string | null
  responsible_user_uuid?: string | null
  /** Contacto responsable fuera del equipo de la app (cliente, consultor, etc.) */
  responsible_external_name?: string | null
  responsible_external_email?: string | null
  workflow_template_uuid: string
  current_workflow_step_uuid: string
  current_step_title?: string | null
  current_step_behavior_kind?: string | null
  current_step_icon_key?: string | null
  /** ISO 8601 — presente si el proyecto está archivado */
  archived_at?: string | null
}
