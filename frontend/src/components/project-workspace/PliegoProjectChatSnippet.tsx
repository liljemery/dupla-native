import { useCallback, useEffect, useState } from 'react'
import { Send } from 'lucide-react'

import { apiFetch } from '../../api/client'
import { ChatMembersButton } from '../chat/ChatMembersButton'
import { formatPersonFullName } from '../../lib/personDisplay'
import type { ChatMessage, ChatParticipantRef } from '../../types/chat'

type PliegoProjectChatSnippetProps = {
  projectUuid: string
  token: string | null
  userUuid: string | null
}

export function PliegoProjectChatSnippet({ projectUuid, token, userUuid }: PliegoProjectChatSnippetProps) {
  const [conversationUuid, setConversationUuid] = useState<string | null>(null)
  const [participants, setParticipants] = useState<ChatParticipantRef[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!token || !projectUuid) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch(`/api/projects/${projectUuid}/chat/conversation`, {
        method: 'POST',
        token,
      })
      if (!res.ok || cancelled) return
      const j = (await res.json()) as {
        uuid?: string
        participants?: ChatParticipantRef[]
      }
      if (j.uuid && !cancelled) {
        setConversationUuid(j.uuid)
        setParticipants(j.participants ?? [])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, projectUuid])

  const loadMessages = useCallback(async () => {
    if (!token || !conversationUuid) return
    const res = await apiFetch(`/api/chat/conversations/${conversationUuid}/messages`, { token })
    if (!res.ok) return
    const rows = (await res.json()) as ChatMessage[]
    setMessages(rows.slice(-12))
  }, [token, conversationUuid])

  useEffect(() => {
    void loadMessages()
  }, [loadMessages])

  async function send() {
    const body = draft.trim()
    if (!token || !conversationUuid || !body || !userUuid) return
    setSending(true)
    try {
      const res = await apiFetch(`/api/chat/conversations/${conversationUuid}/messages`, {
        method: 'POST',
        token,
        body: JSON.stringify({ body }),
      })
      if (!res.ok) return
      setDraft('')
      await loadMessages()
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col rounded-xl border border-black/10 bg-white">
      <div className="border-b border-black/8 px-3 py-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-primary">Comentarios del equipo</h4>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <ChatMembersButton participants={participants} size="xs" />
          {participants.length === 0 ? (
            <span className="text-[11px] text-muted">Canal grupal de esta obra</span>
          ) : null}
        </div>
      </div>
      <div className="max-h-52 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 ? (
          <p className="text-center text-xs text-muted">Aún no hay mensajes.</p>
        ) : (
          messages.map((m) => {
            const mine = userUuid !== null && m.author.uuid === userUuid
            const name = formatPersonFullName(m.author.first_name, m.author.last_name, m.author.email)
            const time = new Date(m.created_at).toLocaleString(undefined, {
              day: '2-digit',
              month: 'short',
              hour: '2-digit',
              minute: '2-digit',
            })
            return (
              <div key={m.uuid} className={`flex gap-2 ${mine ? 'flex-row-reverse' : ''}`}>
                <div
                  className={`flex size-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                    mine ? 'bg-primary text-white' : 'bg-black/10 text-ink'
                  }`}
                >
                  {name
                    .split(/\s+/)
                    .filter(Boolean)
                    .slice(0, 2)
                    .map((p) => p.charAt(0).toUpperCase())
                    .join('')
                    .slice(0, 2) || '?'}
                </div>
                <div className={`min-w-0 max-w-[85%] ${mine ? 'text-right' : ''}`}>
                  <p className="text-[10px] text-muted">
                    {name} · {time}
                  </p>
                  <p
                    className={`mt-0.5 rounded-lg px-2.5 py-1.5 text-xs leading-snug ${
                      mine ? 'bg-primary text-white' : 'border border-black/10 bg-black/[0.02] text-ink'
                    }`}
                  >
                    {m.body}
                  </p>
                </div>
              </div>
            )
          })
        )}
      </div>
      <div className="border-t border-black/8 p-2">
        <div className="flex gap-1.5 rounded-lg border border-black/12 bg-black/[0.02] p-1">
          <textarea
            rows={2}
            className="min-h-[2.5rem] flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-xs outline-none placeholder:text-muted"
            placeholder="Escribe un comentario…"
            value={draft}
            maxLength={4000}
            disabled={sending || !conversationUuid}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
          />
          <button
            type="button"
            className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary text-white shadow-sm outline-none transition hover:opacity-90 disabled:opacity-40"
            disabled={sending || !draft.trim() || !conversationUuid}
            aria-label="Enviar"
            onClick={() => void send()}
          >
            <Send className="size-4" strokeWidth={2} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  )
}
