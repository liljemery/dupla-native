import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'
import type { ChatConversationSummary, ChatMessage } from '../types/chat'

function conversationsFingerprint(conversations: ChatConversationSummary[]): string {
  return JSON.stringify(
    conversations.map((c) => [
      c.uuid,
      c.last_message_at,
      c.last_message_preview,
      c.unread_count,
      c.participant_count,
      c.participants?.map((p) => `${p.uuid}:${p.email}`).sort(),
    ]),
  )
}

export function useChatSync() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  const setConversations = useChatStore((s) => s.setConversations)
  const appendMessages = useChatStore((s) => s.appendMessages)
  const clearUnread = useChatStore((s) => s.clearUnread)
  const reset = useChatStore((s) => s.reset)

  const isChatPath = location.pathname === '/app/chat'

  const prevFingerprintRef = useRef<string | null>(null)
  const fingerprintReadyRef = useRef(false)

  useEffect(() => {
    if (!token) {
      reset()
      prevFingerprintRef.current = null
      fingerprintReadyRef.current = false
    }
  }, [token, reset])

  useEffect(() => {
    if (isChatPath) clearUnread()
  }, [isChatPath, clearUnread])

  const chatPathRef = useRef(isChatPath)
  useEffect(() => {
    chatPathRef.current = isChatPath
  }, [isChatPath])

  useEffect(() => {
    if (!token) return
    let cancelled = false

    async function tick() {
      const convRes = await apiFetch('/api/chat/conversations', { token })
      if (!convRes.ok || cancelled) return
      const convData = (await convRes.json()) as ChatConversationSummary[]
      setConversations(convData)

      const fp = conversationsFingerprint(convData)
      if (
        fingerprintReadyRef.current &&
        prevFingerprintRef.current !== null &&
        prevFingerprintRef.current !== fp &&
        !chatPathRef.current
      ) {
        useChatStore.getState().setUnread(true)
      }
      fingerprintReadyRef.current = true
      prevFingerprintRef.current = fp

      const active = useChatStore.getState().activeConversationUuid
      if (!chatPathRef.current || !active) return

      const { messages } = useChatStore.getState()
      const last = messages.length > 0 ? messages[messages.length - 1] : null
      if (last && last.conversation_uuid !== active) return

      const url = last
        ? `/api/chat/conversations/${active}/messages?after_uuid=${encodeURIComponent(last.uuid)}`
        : `/api/chat/conversations/${active}/messages`
      const msgRes = await apiFetch(url, { token })
      if (!msgRes.ok || cancelled) return
      const batch = (await msgRes.json()) as ChatMessage[]
      if (batch.length === 0) return
      appendMessages(batch)
    }

    void tick()
    const id = window.setInterval(() => void tick(), 4000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [token, setConversations, appendMessages])
}
