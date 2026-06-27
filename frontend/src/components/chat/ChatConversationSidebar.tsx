import { Search } from 'lucide-react'
import type { KeyboardEvent } from 'react'

import {
  chatKindLabel,
  formatRelativeChatTime,
  isGroupChatKind,
} from '../../lib/chatUi'
import { ChatMembersButton } from './ChatMembersButton'
import type { ChatConversationSummary } from '../../types/chat'

type ChatConversationSidebarProps = {
  conversations: ChatConversationSummary[]
  activeConversationUuid: string | null
  onSelect: (uuid: string) => void
  onNewChat: () => void
  onNewGroup: () => void
  searchQuery: string
  onSearchQueryChange: (q: string) => void
}

function conversationInitial(c: ChatConversationSummary): string {
  const t = c.display_title.trim()
  if (!t) return '?'
  return t.charAt(0).toUpperCase()
}

function conversationRowKeyDown(e: KeyboardEvent, onSelect: () => void) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    onSelect()
  }
}

export function ChatConversationSidebar({
  conversations,
  activeConversationUuid,
  onSelect,
  onNewChat,
  onNewGroup,
  searchQuery,
  onSearchQueryChange,
}: ChatConversationSidebarProps) {
  return (
    <aside className="flex h-full min-h-0 w-full shrink-0 flex-col bg-[#f8f9fb] lg:w-80 xl:w-[22rem]">
      <div className="border-b border-black/8 px-3 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">Consola de mensajes</p>
        <label className="relative mt-2 block">
          <span className="sr-only">Buscar conversaciones</span>
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted"
            strokeWidth={2}
            aria-hidden
          />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            placeholder="Buscar conversaciones…"
            className="du-input h-9 w-full rounded-lg border-black/10 bg-white py-0 pl-9 pr-3 text-sm"
          />
        </label>
      </div>

      <div className="flex shrink-0 gap-2 border-b border-black/8 px-3 py-2">
        <button
          type="button"
          className="flex-1 rounded-lg bg-primary px-2 py-2 text-center text-[11px] font-bold uppercase tracking-wide text-white shadow-sm hover:opacity-95"
          onClick={onNewChat}
        >
          Nuevo chat
        </button>
        <button
          type="button"
          className="flex-1 rounded-lg border border-black/12 bg-white px-2 py-2 text-[11px] font-bold uppercase tracking-wide text-ink shadow-sm hover:bg-black/[0.03]"
          onClick={onNewGroup}
        >
          Grupo
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <ul className="space-y-1">
          {conversations.map((c) => {
            const active = c.uuid === activeConversationUuid
            const unread = (c.unread_count ?? 0) > 0
            const preview = c.last_message_preview?.trim() || 'Sin mensajes aún'
            const when = formatRelativeChatTime(c.last_message_at)
            return (
              <li key={c.uuid}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(c.uuid)}
                  onKeyDown={(e) => conversationRowKeyDown(e, () => onSelect(c.uuid))}
                  className={`flex w-full cursor-pointer gap-3 rounded-xl border px-3 py-2.5 text-left transition ${
                    active
                      ? 'border-primary/35 bg-white shadow-md ring-1 ring-primary/15'
                      : 'border-transparent bg-transparent hover:bg-white/80'
                  }`}
                >
                  <span
                    className={`flex size-11 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${
                      active ? 'bg-primary text-white' : 'bg-white text-primary ring-1 ring-black/8'
                    }`}
                  >
                    {conversationInitial(c)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-start justify-between gap-2">
                      <span className="line-clamp-2 font-semibold leading-snug text-ink">{c.display_title}</span>
                      {unread ? (
                        <span className="mt-0.5 inline-flex min-h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-bold leading-none text-white">
                          {c.unread_count! > 99 ? '99+' : c.unread_count}
                        </span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted">
                      {chatKindLabel(c.kind)}
                      {when ? ` · ${when}` : ''}
                    </span>
                    {isGroupChatKind(c.kind) && c.participants?.length ? (
                      <span className="mt-1 block">
                        <ChatMembersButton participants={c.participants} size="xs" />
                      </span>
                    ) : null}
                    <span
                      className={`mt-1 line-clamp-2 block text-xs leading-snug ${
                        unread ? 'font-medium text-ink' : 'text-muted'
                      }`}
                    >
                      {preview}
                    </span>
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </aside>
  )
}
