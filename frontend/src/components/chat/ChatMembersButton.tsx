import { useState } from 'react'

import { formatPersonFullName } from '../../lib/personDisplay'
import type { ChatParticipantRef } from '../../types/chat'

type ChatMembersButtonProps = {
  participants: ChatParticipantRef[] | null | undefined
  className?: string
  size?: 'xs' | 'sm'
}

export function ChatMembersButton({ participants, className, size = 'sm' }: ChatMembersButtonProps) {
  const [open, setOpen] = useState(false)
  const list = participants ?? []
  if (list.length === 0) return null

  const btnClass =
    size === 'xs'
      ? 'text-[10px] font-semibold uppercase tracking-wide'
      : 'text-xs font-semibold'

  return (
    <>
      <button
        type="button"
        className={`rounded-md border border-black/12 bg-white px-2 py-0.5 text-primary shadow-sm hover:bg-black/[0.03] ${btnClass} ${className ?? ''}`}
        onClick={(e) => {
          e.stopPropagation()
          setOpen(true)
        }}
      >
        Ver miembros
      </button>
      {open ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOpen(false)
          }}
        >
          <div
            className="w-full max-w-sm rounded-xl border border-black/10 bg-white p-5 shadow-xl"
            role="dialog"
            aria-labelledby="chat-members-title"
          >
            <h3 id="chat-members-title" className="text-lg font-semibold text-ink">Integrantes</h3>
            <p className="mt-1 text-sm text-muted">{list.length} persona(s) en este chat</p>
            <ul className="mt-4 space-y-2">
              {list.map((p) => (
                <li key={p.uuid} className="text-sm text-ink">
                  {formatPersonFullName(p.first_name, p.last_name, p.email)}
                </li>
              ))}
            </ul>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-black/5"
                onClick={() => setOpen(false)}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
