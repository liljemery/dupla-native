import { useMemo, type RefObject } from 'react'

import {
  formatMessageTime,
  groupMessagesForDisplay,
  isOptimisticMessageId,
  type MessageDisplayGroup,
} from '../../lib/chatUi'
import { formatPersonFullName } from '../../lib/personDisplay'
import type { ChatMessage } from '../../types/chat'

type ChatMessageListProps = {
  messages: ChatMessage[]
  userUuid: string | null
  bottomRef: RefObject<HTMLDivElement | null>
}

function MessageGroupBlock({
  group,
  userUuid,
}: {
  group: MessageDisplayGroup
  userUuid: string | null
}) {
  const mine = userUuid !== null && group.author.uuid === userUuid
  const first = group.messages[0]
  const headerTime = formatMessageTime(first.created_at)

  return (
    <div
      className={`flex w-full flex-col gap-1 ${mine ? 'items-end' : 'items-start'}`}
    >
      <div
        className={`du-meta mb-0.5 max-w-[85%] px-0.5 ${mine ? 'text-right' : 'text-left'}`}
      >
        <span className={mine ? 'font-semibold text-ink' : 'text-muted'}>
          {formatPersonFullName(group.author.first_name, group.author.last_name, group.author.email)}
        </span>
        <span className="text-muted"> · {headerTime}</span>
      </div>
      {group.messages.map((m) => {
        const pending = isOptimisticMessageId(m.uuid)
        return (
          <div
            key={m.uuid}
            className={`max-w-[85%] rounded-2xl px-3 py-2.5 text-sm shadow-sm ${
              mine
                ? 'border border-primary/20 bg-primary text-white'
                : 'border border-black/10 bg-white text-ink'
            } ${pending ? 'opacity-75' : ''}`}
          >
            <p className="whitespace-pre-wrap wrap-break-word">{m.body}</p>
          </div>
        )
      })}
    </div>
  )
}

export function ChatMessageList({ messages, userUuid, bottomRef }: ChatMessageListProps) {
  const groups = useMemo(() => groupMessagesForDisplay(messages), [messages])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-4">
        {groups.map((g) => (
          <MessageGroupBlock key={g.key} group={g} userUuid={userUuid} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
