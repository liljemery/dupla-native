import { type FormEvent, useEffect, useRef } from 'react'
import { Send } from 'lucide-react'

type ChatComposerProps = {
  value: string
  onChange: (value: string) => void
  onSend: () => void | Promise<void>
  disabled?: boolean
  sending?: boolean
  error?: string | null
}

export function ChatComposer({
  value,
  onChange,
  onSend,
  disabled,
  sending,
  error,
}: ChatComposerProps) {
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [value])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    void onSend()
  }

  return (
    <form
      className="border-t border-black/10 bg-[#fafafa] px-4 py-3 sm:px-5"
      onSubmit={handleSubmit}
    >
      {error ? <p className="mb-2 text-sm text-primary">{error}</p> : null}
      <label className="du-label sr-only" htmlFor="chat-composer-input">
        Mensaje
      </label>
      <div className="flex items-end gap-2 rounded-xl border border-black/10 bg-white p-2 shadow-sm">
        <textarea
          id="chat-composer-input"
          ref={taRef}
          rows={1}
          className="max-h-[120px] min-h-[44px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm text-ink outline-none placeholder:text-muted"
          placeholder="Escribe un mensaje…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={sending || disabled}
          maxLength={4000}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void onSend()
            }
          }}
        />
        <button
          type="submit"
          className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary text-white shadow-md outline-none transition hover:opacity-92 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-primary/45 focus-visible:ring-offset-2"
          disabled={sending || !value.trim() || disabled}
          aria-label={sending ? 'Enviando' : 'Enviar mensaje'}
        >
          <Send className="size-5" strokeWidth={2} aria-hidden />
        </button>
      </div>
      <p className="mt-2 text-[11px] text-muted">Enter para enviar · Shift+Enter nueva línea</p>
    </form>
  )
}
