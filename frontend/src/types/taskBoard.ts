export type TaskAssigneeOption = {
  uuid: string
  email: string
  first_name: string
  last_name: string
}

export type TaskCardDto = {
  uuid: string
  title: string
  description: string | null
  position: number
  list_uuid: string
  project_uuid: string | null
  project_name: string | null
  project_code: string | null
  created_at: string
  created_by_uuid: string | null
  creator_email: string | null
  creator_first_name: string | null
  creator_last_name: string | null
  assignee_uuid: string | null
  assignee_email: string | null
  assignee_first_name: string | null
  assignee_last_name: string | null
  archived: boolean
  archived_at: string | null
  /** Fase del flujo ISO al crear la tarea (si estaba vinculada a un proyecto). */
  created_in_phase: string | null
}

export type TaskListDto = {
  uuid: string
  title: string
  position: number
  cards: TaskCardDto[]
}

export type TaskBoardDto = {
  lists: TaskListDto[]
  archived_cards: TaskCardDto[]
}

export type TaskCardCommentDto = {
  uuid: string
  body: string
  created_at: string
  author_uuid: string | null
  author_email: string | null
  author_first_name: string | null
  author_last_name: string | null
}
