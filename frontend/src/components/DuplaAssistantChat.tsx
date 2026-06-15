import { ImageIcon, Send, X, Zap } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { useAuthStore } from '../store/authStore'
import { AssistantChatMarkdown } from './AssistantChatMarkdown'

type ChatLine = { role: 'user' | 'assistant'; content: string }

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

const WELCOME_GLOBAL: ChatLine = {
  role: 'assistant',
  content:
    'Hola, soy **Dupla Assistant**. Te ayudo a usar la aplicación paso a paso (proyectos, **Flujo**, archivos, tablero de tareas y mensajes del equipo).\n\nSi tu duda es sobre otra cosa, contame cómo se relaciona con Dupla.',
}

const WELCOME_IN_PROJECT: ChatLine = {
  role: 'assistant',
  content:
    'Estás en la vista de un **proyecto**. Puedes preguntarme sobre **este** proyecto (en qué etapa está, el checklist, cuántos archivos hay, etc.). Cada vez que envías un mensaje, uso los datos actualizados del proyecto.',
}

export function DuplaAssistantChat() {
  const token = useAuthStore((s) => s.token)
  const { projectUuid: projectUuidParam } = useParams<{ projectUuid?: string }>()
  const assistantProjectUuid =
    typeof projectUuidParam === 'string' && UUID_RE.test(projectUuidParam.trim())
      ? projectUuidParam.trim()
      : null
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [lines, setLines] = useState<ChatLine[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [lines, open, scrollToBottom])

  useEffect(() => {
    if (!open || !token) return
    let cancelled = false
    void (async () => {
      const qs =
        assistantProjectUuid != null
          ? `?project_uuid=${encodeURIComponent(assistantProjectUuid)}`
          : ''
      const res = await apiFetch(`/api/me/ai-assistant/history${qs}`, { token })
      if (!res.ok || cancelled) return
      const body = (await res.json()) as { messages: { role: string; content: string }[] }
      const mapped: ChatLine[] = []
      for (const m of body.messages ?? []) {
        if ((m.role === 'user' || m.role === 'assistant') && m.content?.trim()) {
          mapped.push({ role: m.role, content: m.content })
        }
      }
      const welcome = assistantProjectUuid ? WELCOME_IN_PROJECT : WELCOME_GLOBAL
      setLines(mapped.length > 0 ? mapped : [welcome])
    })()
    return () => {
      cancelled = true
    }
  }, [open, token, assistantProjectUuid])

  async function send() {
    const text = input.trim()
    if (!token || !text || busy) return
    setInput('')
    setError(null)
    setBusy(true)
    setLines((prev) => [...prev, { role: 'user', content: text }])
    try {
      const res = await apiFetch('/api/me/ai-assistant/chat', {
        method: 'POST',
        token,
        body: JSON.stringify({
          message: text,
          ...(assistantProjectUuid != null ? { project_uuid: assistantProjectUuid } : {}),
        }),
      })
      const raw = await res.json().catch(() => ({}))
      if (!res.ok) {
        const detail = typeof raw?.detail === 'string' ? raw.detail : 'No se pudo obtener respuesta.'
        setError(detail)
        setLines((prev) => [
          ...prev,
          { role: 'assistant', content: `(${detail})` },
        ])
        return
      }
      const reply = String((raw as { reply?: string }).reply ?? '').trim()
      if (reply) {
        setLines((prev) => [...prev, { role: 'assistant', content: reply }])
      }
    } finally {
      setBusy(false)
    }
  }

  if (!token) return null

  return (
    <div className="pointer-events-none fixed bottom-0 right-0 z-[100] flex flex-col items-end p-4 sm:p-5">
      {open ? (
        <div
          className="pointer-events-auto mb-3 flex max-h-[min(520px,calc(100dvh-8rem))] w-[min(400px,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-black/15 bg-[#f4f4f5] shadow-xl"
          role="dialog"
          aria-label="Dupla Assistant"
        >
          <header className="flex shrink-0 items-center gap-2 bg-[#9f1419] px-4 py-3 text-white">
            <Zap className="h-5 w-5 shrink-0 text-amber-300" aria-hidden />
            <span className="min-w-0 flex-1 text-sm font-bold tracking-tight">Dupla Assistant</span>
            {assistantProjectUuid ? (
              <span className="shrink-0 rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
                Este proyecto
              </span>
            ) : null}
          </header>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
            {lines.map((line, i) => (
              <div
                key={`${assistantProjectUuid ?? 'global'}-${line.role}-${i}`}
                className={
                  line.role === 'user'
                    ? 'ml-8 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm text-ink shadow-sm'
                    : 'mr-6 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm text-ink shadow-sm'
                }
              >
                {line.role === 'assistant' ? (
                  <AssistantChatMarkdown content={line.content} />
                ) : (
                  <span className="whitespace-pre-wrap break-words">{line.content}</span>
                )}
              </div>
            ))}
            {busy ? (
              <div className="mr-6 rounded-lg border border-black/10 bg-white px-3 py-2 text-sm text-muted">
                Pensando…
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
          {error ? <p className="shrink-0 px-3 pb-1 text-xs text-primary">{error}</p> : null}
          <div className="shrink-0 border-t border-black/10 bg-[#f4f4f5] px-2 py-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="shrink-0 rounded-md p-2 text-muted opacity-40"
                disabled
                title="Adjuntar imagen (próximamente)"
                aria-label="Adjuntar imagen, no disponible"
              >
                <ImageIcon className="h-5 w-5" />
              </button>
              <input
                className="min-w-0 flex-1 rounded-lg border border-black/15 bg-white px-3 py-2 text-sm text-ink outline-none ring-primary/25 placeholder:text-muted focus:ring-2"
                placeholder={
                  assistantProjectUuid != null
                    ? 'Preguntá sobre este proyecto…'
                    : 'Preguntá sobre la plataforma…'
                }
                value={input}
                disabled={busy}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
              />
              <button
                type="button"
                disabled={busy || !input.trim()}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#e8a0a2] text-white shadow-sm transition hover:bg-[#df8f92] disabled:opacity-40"
                aria-label="Enviar"
                onClick={() => void send()}
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="pointer-events-auto flex flex-col items-end gap-2">
        {open ? (
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-[#0f172a] text-white shadow-lg ring-2 ring-white/90 hover:bg-[#1e293b]"
            aria-label="Cerrar Dupla Assistant"
            onClick={() => setOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        ) : (
          <button
            type="button"
            className="flex h-14 w-14 items-center justify-center rounded-full bg-[#9f1419] shadow-lg ring-2 ring-white/90 transition hover:bg-[#820f13]"
            aria-label="Abrir Dupla Assistant"
            onClick={() => setOpen(true)}
          >
            <Zap className="h-7 w-7 text-amber-300" />
          </button>
        )}
      </div>
    </div>
  )
}
