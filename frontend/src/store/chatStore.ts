import { create } from 'zustand'

import type { ChatConversationSummary, ChatDirectoryUser, ChatMessage } from '../types/chat'

type ChatState = {
  conversations: ChatConversationSummary[]
  activeConversationUuid: string | null
  messages: ChatMessage[]
  directory: ChatDirectoryUser[]
  hasUnread: boolean
  setConversations: (conversations: ChatConversationSummary[]) => void
  setActiveConversationUuid: (uuid: string | null) => void
  setMessages: (messages: ChatMessage[]) => void
  appendMessages: (incoming: ChatMessage[]) => void
  setDirectory: (directory: ChatDirectoryUser[]) => void
  setUnread: (value: boolean) => void
  clearUnread: () => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationUuid: null,
  messages: [],
  directory: [],
  hasUnread: false,
  setConversations: (conversations) => set({ conversations }),
  setActiveConversationUuid: (activeConversationUuid) => set({ activeConversationUuid }),
  setMessages: (messages) => set({ messages }),
  appendMessages: (incoming) => {
    if (incoming.length === 0) return
    const active = get().activeConversationUuid
    const filtered = active
      ? incoming.filter((m) => m.conversation_uuid === active)
      : incoming
    if (filtered.length === 0) return
    const seen = new Set(get().messages.map((m) => m.uuid))
    const next = [...get().messages]
    for (const m of filtered) {
      if (!seen.has(m.uuid)) {
        seen.add(m.uuid)
        next.push(m)
      }
    }
    set({ messages: next })
  },
  setDirectory: (directory) => set({ directory }),
  setUnread: (value) => set({ hasUnread: value }),
  clearUnread: () => set({ hasUnread: false }),
  reset: () =>
    set({
      conversations: [],
      activeConversationUuid: null,
      messages: [],
      directory: [],
      hasUnread: false,
    }),
}))
