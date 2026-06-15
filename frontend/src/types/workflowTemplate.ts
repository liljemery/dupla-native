export type WorkflowTemplateStep = {
  uuid: string
  sort_index: number
  stable_key: string
  title: string
  icon_key: string
  behavior_kind: string
  blocked_by_step_uuid: string | null
  requires_approval_role: string | null
  on_enter_actions: Record<string, unknown>[]
}

export type WorkflowTemplateDetail = {
  uuid: string
  name: string
  description: string
  icon_key: string
  archived_at: string | null
  created_at: string
  updated_at: string
  steps: WorkflowTemplateStep[]
}

export type WorkflowTemplateListItem = {
  uuid: string
  name: string
  description: string
  icon_key: string
  archived_at: string | null
  preview_projects: { uuid: string; name: string }[]
}
