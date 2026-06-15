import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bell, CircleHelp, PanelLeft, Settings, Trash2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { generateUuid } from '../lib/uuid'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatConversationSidebar } from '../components/chat/ChatConversationSidebar'
import { ChatMembersButton } from '../components/chat/ChatMembersButton'
import { ChatProjectContextPanel } from '../components/chat/ChatProjectContextPanel'
import { ChatDirectModal } from '../components/chat/ChatDirectModal'
import { ChatGroupModal } from '../components/chat/ChatGroupModal'
import { ChatMessageList } from '../components/chat/ChatMessageList'
import { WorkspaceContextSelect } from '../components/WorkspaceContextSelect'
import {
  canDeleteChatConversation,
  isGroupChatKind,
} from '../lib/chatUi'
import { confirmDestructive } from '../lib/duplaAlert'
import { userDisplayInitials } from '../lib/taskboard'
import { useAuthStore } from '../store/authStore'
import { useChatStore } from '../store/chatStore'
import type { ChatConversationSummary, ChatDirectoryUser, ChatMessage } from '../types/chat'

export function ChatPage() {
  const [searchParams] = useSearchParams()
  const token = useAuthStore((s) => s.token)
  const userUuid = useAuthStore((s) => s.userUuid)
  const email = useAuthStore((s) => s.email)
  const firstName = useAuthStore((s) => s.firstName)
  const lastName = useAuthStore((s) => s.lastName)
  const [conversationQuery, setConversationQuery] = useState('')
  const [headerUnread, setHeaderUnread] = useState(0)
  const conversations = useChatStore((s) => s.conversations)
  const activeConversationUuid = useChatStore((s) => s.activeConversationUuid)
  const setActiveConversationUuid = useChatStore((s) => s.setActiveConversationUuid)
  const setConversations = useChatStore((s) => s.setConversations)
  const messages = useChatStore((s) => s.messages)
  const setMessages = useChatStore((s) => s.setMessages)
  const appendMessages = useChatStore((s) => s.appendMessages)
  const directory = useChatStore((s) => s.directory)
  const setDirectory = useChatStore((s) => s.setDirectory)

  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [showDm, setShowDm] = useState(false)
  const [showGroup, setShowGroup] = useState(false)
  const [dmTarget, setDmTarget] = useState('')
  const [groupTitle, setGroupTitle] = useState('')
  const [groupMemberSearch, setGroupMemberSearch] = useState('')
  const [groupSelectedUuids, setGroupSelectedUuids] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const refreshConversations = useCallback(async () => {
    if (!token) return
    const res = await apiFetch('/api/chat/conversations', { token })
    if (res.ok) {
      setConversations((await res.json()) as ChatConversationSummary[])
    }
  }, [token, setConversations])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch('/api/me/notifications?unread_only=true', { token })
      if (!res.ok || cancelled) return
      const rows = (await res.json()) as unknown[]
      if (!cancelled) setHeaderUnread(rows.length)
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    async function run() {
      const res = await apiFetch('/api/chat/directory', { token })
      if (!res.ok || cancelled) return
      setDirectory((await res.json()) as ChatDirectoryUser[])
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [token, setDirectory])

  useEffect(() => {
    const fromUrl = searchParams.get('conversation')
    if (fromUrl && token) {
      setActiveConversationUuid(fromUrl)
      void refreshConversations()
    }
  }, [searchParams, token, setActiveConversationUuid, refreshConversations])

  useEffect(() => {
    if (!token || conversations.length === 0) return
    if (activeConversationUuid) return
    const general = conversations.find((c) => c.kind === 'GENERAL') ?? conversations[0]
    setActiveConversationUuid(general.uuid)
  }, [token, conversations, activeConversationUuid, setActiveConversationUuid])

  useEffect(() => {
    if (!token || !activeConversationUuid) return
    let cancelled = false
    const conv = activeConversationUuid
    setMessages([])
    async function load() {
      const res = await apiFetch(`/api/chat/conversations/${conv}/messages`, { token })
      if (!res.ok || cancelled) return
      if (useChatStore.getState().activeConversationUuid !== conv) return
      setMessages((await res.json()) as ChatMessage[])
      void refreshConversations()
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token, activeConversationUuid, setMessages, refreshConversations])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, activeConversationUuid])

  const selectConversation = useCallback(
    (uuid: string) => {
      setActiveConversationUuid(uuid)
      setSidebarOpen(false)
    },
    [setActiveConversationUuid],
  )

  async function deleteActiveConversation() {
    if (!token || !activeConversationUuid) return
    const meta = conversations.find((c) => c.uuid === activeConversationUuid)
    if (!meta || !canDeleteChatConversation(meta.kind)) return
    const label = meta.display_title.trim() || 'este chat'
    if (
      !(await confirmDestructive({
        title: `¿Eliminar "${label}"?`,
        text: 'Se borrarán todos los mensajes para todos los participantes. No se puede deshacer.',
      }))
    ) {
      return
    }
    setError(null)
    const convUuid = meta.uuid
    const res = await apiFetch(`/api/chat/conversations/${convUuid}`, {
      method: 'DELETE',
      token,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setError((body as { detail?: string }).detail ?? 'No se pudo eliminar el chat')
      return
    }
    setActiveConversationUuid(null)
    setMessages([])
    await refreshConversations()
  }

  async function openDirect() {
    if (!token || !dmTarget) return
    setError(null)
    const res = await apiFetch('/api/chat/conversations/direct', {
      method: 'POST',
      token,
      body: JSON.stringify({ user_uuid: dmTarget }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setError((body as { detail?: string }).detail ?? 'No se pudo abrir el chat')
      return
    }
    const row = (await res.json()) as ChatConversationSummary
    await refreshConversations()
    selectConversation(row.uuid)
    setShowDm(false)
    setDmTarget('')
  }

  async function createGroup() {
    if (!token) return
    const uuids = groupSelectedUuids
    if (!groupTitle.trim() || uuids.length < 1) {
      setError('Indica nombre del grupo y al menos un miembro.')
      return
    }
    setError(null)
    const res = await apiFetch('/api/chat/conversations/group', {
      method: 'POST',
      token,
      body: JSON.stringify({ title: groupTitle.trim(), member_uuids: uuids }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      setError((body as { detail?: string }).detail ?? 'No se pudo crear el grupo')
      return
    }
    const row = (await res.json()) as ChatConversationSummary
    await refreshConversations()
    selectConversation(row.uuid)
    setShowGroup(false)
    setGroupTitle('')
    setGroupMemberSearch('')
    setGroupSelectedUuids([])
  }

  const groupPickerCandidates = useMemo(() => {
    const q = groupMemberSearch.trim().toLowerCase()
    const selected = new Set(groupSelectedUuids)
    return directory
      .filter((u) => !selected.has(u.uuid))
      .filter((u) => {
        if (q === '') return true
        const hay = `${u.email} ${u.first_name} ${u.last_name}`.toLowerCase()
        return hay.includes(q)
      })
      .slice(0, 50)
  }, [directory, groupMemberSearch, groupSelectedUuids])

  function addGroupMember(uuid: string) {
    setGroupSelectedUuids((prev) => (prev.includes(uuid) ? prev : [...prev, uuid]))
    setGroupMemberSearch('')
  }

  function removeGroupMember(uuid: string) {
    setGroupSelectedUuids((prev) => prev.filter((id) => id !== uuid))
  }

  const send = useCallback(async () => {
    const text = draft.trim()
    if (!token || !text || !activeConversationUuid || !userUuid) return
    setError(null)
    const optimisticUuid = `optimistic-${generateUuid()}`
    const optimistic: ChatMessage = {
      uuid: optimisticUuid,
      conversation_uuid: activeConversationUuid,
      body: text,
      created_at: new Date().toISOString(),
      author: {
        uuid: userUuid,
        email: email ?? '',
        first_name: firstName ?? '',
        last_name: lastName ?? '',
      },
    }
    appendMessages([optimistic])
    setDraft('')
    setSending(true)
    try {
      const res = await apiFetch(`/api/chat/conversations/${activeConversationUuid}/messages`, {
        method: 'POST',
        token,
        body: JSON.stringify({ body: text }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError((body as { detail?: string }).detail ?? 'No se pudo enviar')
        const prev = useChatStore.getState().messages
        setMessages(prev.filter((m) => m.uuid !== optimisticUuid))
        setDraft(text)
        return
      }
      const msg = (await res.json()) as ChatMessage
      const prev = useChatStore.getState().messages
      const without = prev.filter((m) => m.uuid !== optimisticUuid)
      setMessages(without.some((m) => m.uuid === msg.uuid) ? without : [...without, msg])
      void refreshConversations()
    } finally {
      setSending(false)
    }
  }, [
    token,
    draft,
    activeConversationUuid,
    userUuid,
    email,
    firstName,
    lastName,
    appendMessages,
    setMessages,
    refreshConversations,
  ])

  const activeMeta = conversations.find((c) => c.uuid === activeConversationUuid)

  const filteredConversations = useMemo(() => {
    const q = conversationQuery.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter((c) => {
      const blob = `${c.display_title} ${c.last_message_preview ?? ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [conversations, conversationQuery])

  const activeProjectUuid =
    activeMeta?.kind === 'PROJECT' && activeMeta.project_uuid ? activeMeta.project_uuid : null

  const initials = userDisplayInitials(firstName, lastName, email ?? '?')

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 lg:gap-5">
      <header className="shrink-0 space-y-3 border-b border-black/10 pb-4 lg:flex lg:items-start lg:justify-between lg:gap-6 lg:border-0 lg:pb-0">
        <div data-tour="chat-header" className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Consola de mensajes</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink md:text-3xl">Chat interno</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            Canal general, chats directos, grupos y conversaciones por obra. El menú lateral avisa si hay mensajes
            nuevos.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <WorkspaceContextSelect />
          <button
            type="button"
            className="relative rounded-lg border border-black/10 bg-white p-2 text-muted shadow-sm hover:bg-black/[0.03]"
            title={headerUnread > 0 ? `${headerUnread} avisos` : 'Avisos'}
            aria-label="Avisos del sistema"
          >
            <Bell className="size-5" strokeWidth={2} aria-hidden />
            {headerUnread > 0 ? (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-0.5 text-[10px] font-bold text-white">
                {headerUnread > 9 ? '9+' : headerUnread}
              </span>
            ) : null}
          </button>
          <Link
            to="/app/tutoriales"
            className="rounded-lg border border-black/10 bg-white p-2 text-muted shadow-sm hover:bg-black/[0.03]"
            aria-label="Ayuda"
          >
            <CircleHelp className="size-5" strokeWidth={2} aria-hidden />
          </Link>
          <Link
            to="/app/projects"
            className="rounded-lg border border-black/10 bg-white p-2 text-muted shadow-sm hover:bg-black/[0.03]"
            aria-label="Proyectos"
          >
            <Settings className="size-5" strokeWidth={2} aria-hidden />
          </Link>
          <div className="flex size-10 items-center justify-center rounded-full bg-primary text-xs font-bold uppercase text-white shadow-sm ring-2 ring-white">
            {initials}
          </div>
        </div>
      </header>

      <div className="relative flex min-h-0 min-h-[min(52dvh,560px)] flex-1 flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)] lg:min-h-0 lg:flex-row">
        {sidebarOpen ? (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/35 lg:hidden"
            aria-label="Cerrar conversaciones"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}

        <div
          id="chat-conversations-sidebar"
          className={`fixed inset-y-0 left-0 z-40 h-full w-[min(22rem,92vw)] max-w-full shadow-2xl lg:static lg:z-0 lg:flex lg:h-auto lg:shadow-none ${
            sidebarOpen ? 'flex' : 'hidden lg:flex'
          }`}
        >
          <ChatConversationSidebar
            conversations={filteredConversations}
            activeConversationUuid={activeConversationUuid}
            onSelect={selectConversation}
            searchQuery={conversationQuery}
            onSearchQueryChange={setConversationQuery}
            onNewChat={() => {
              setError(null)
              setShowDm(true)
            }}
            onNewGroup={() => {
              setError(null)
              setGroupTitle('')
              setGroupMemberSearch('')
              setGroupSelectedUuids([])
              setShowGroup(true)
            }}
          />
        </div>

        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col border-black/10 lg:border-l">
          <div
            data-tour="chat-toolbar"
            className="flex shrink-0 flex-wrap items-center gap-3 border-b border-black/8 bg-white px-3 py-3 sm:px-5"
          >
            <button
              type="button"
              className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-black/12 bg-[#f8f9fb] px-3 py-2 text-sm font-semibold text-ink lg:hidden"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen((o) => !o)}
            >
              <PanelLeft className="size-4 text-primary" aria-hidden />
              Chats
            </button>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-lg font-bold text-ink">{activeMeta?.display_title ?? 'Chat'}</h2>
              {activeMeta ? (
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                  {activeMeta.kind === 'GENERAL' && <span>Canal visible para todo el equipo.</span>}
                  {activeMeta.kind === 'DIRECT' && <span>Mensaje directo.</span>}
                  {isGroupChatKind(activeMeta.kind) ? (
                    <>
                      <span>
                        {activeMeta.kind === 'GROUP'
                          ? 'Grupo.'
                          : 'Chat grupal de la obra.'}
                      </span>
                      <ChatMembersButton participants={activeMeta.participants} />
                    </>
                  ) : null}
                  {activeMeta.participant_count != null &&
                  activeMeta.kind !== 'DIRECT' &&
                  !isGroupChatKind(activeMeta.kind) ? (
                    <span>· {activeMeta.participant_count} en línea (aprox.)</span>
                  ) : null}
                </div>
              ) : null}
            </div>
            {activeMeta && canDeleteChatConversation(activeMeta.kind) ? (
              <button
                type="button"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 shadow-sm hover:bg-red-50"
                onClick={() => void deleteActiveConversation()}
                title="Eliminar chat"
              >
                <Trash2 className="size-4" strokeWidth={2} aria-hidden />
                Eliminar
              </button>
            ) : null}
          </div>

          <div className="relative flex min-h-0 flex-1 flex-col bg-[#fafafa]">
            {!activeConversationUuid ? (
              <div className="flex flex-1 items-center justify-center px-4 py-8">
                <p className="text-sm text-muted">Cargando conversaciones…</p>
              </div>
            ) : (
              <>
                {messages.length === 0 ? (
                  <div className="flex flex-1 items-center justify-center px-4 py-8">
                    <p className="text-sm text-muted">Aún no hay mensajes. Escribe el primero.</p>
                  </div>
                ) : (
                  <ChatMessageList messages={messages} userUuid={userUuid} bottomRef={bottomRef} />
                )}
                <div data-tour="chat-composer">
                  <ChatComposer
                    value={draft}
                    onChange={setDraft}
                    onSend={send}
                    disabled={!activeConversationUuid}
                    sending={sending}
                    error={error}
                  />
                </div>
              </>
            )}
          </div>
        </div>

        <ChatProjectContextPanel projectUuid={activeProjectUuid} token={token} />
      </div>

      <ChatDirectModal
        open={showDm}
        dmTarget={dmTarget}
        setDmTarget={setDmTarget}
        directory={directory}
        error={error}
        onBackdropClose={() => {
          setError(null)
          setShowDm(false)
        }}
        onCancel={() => {
          setError(null)
          setShowDm(false)
        }}
        onSubmit={openDirect}
      />

      <ChatGroupModal
        open={showGroup}
        groupTitle={groupTitle}
        setGroupTitle={setGroupTitle}
        groupMemberSearch={groupMemberSearch}
        setGroupMemberSearch={setGroupMemberSearch}
        groupSelectedUuids={groupSelectedUuids}
        directory={directory}
        groupPickerCandidates={groupPickerCandidates}
        error={error}
        onBackdropClose={() => {
          setError(null)
          setGroupTitle('')
          setGroupMemberSearch('')
          setGroupSelectedUuids([])
          setShowGroup(false)
        }}
        onCancel={() => {
          setError(null)
          setGroupTitle('')
          setGroupMemberSearch('')
          setGroupSelectedUuids([])
          setShowGroup(false)
        }}
        onAddMember={addGroupMember}
        onRemoveMember={removeGroupMember}
        onCreateGroup={createGroup}
      />
    </div>
  )
}
