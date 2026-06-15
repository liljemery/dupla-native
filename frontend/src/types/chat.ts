export type ChatConversationKind = 'GENERAL' | 'DIRECT' | 'GROUP' | 'PROJECT'

export type ChatParticipantRef = {
  uuid: string
  email: string
  first_name: string
  last_name: string
}

export type ChatConversationSummary = {
  uuid: string
  kind: ChatConversationKind
  display_title: string
  last_message_at: string | null
  last_message_preview?: string | null
  unread_count?: number
  participant_count?: number | null
  participants?: ChatParticipantRef[] | null
  /** Presente cuando `kind === 'PROJECT'`. */
  project_uuid?: string | null
}

export type ChatMessage = {
  uuid: string
  conversation_uuid: string
  body: string
  created_at: string
  author: { uuid: string; email: string; first_name: string; last_name: string }
}

export type ChatDirectoryUser = {
  uuid: string
  email: string
  first_name: string
  last_name: string
}
