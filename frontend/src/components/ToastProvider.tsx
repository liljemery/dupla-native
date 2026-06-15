import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────
export type ToastVariant = 'error' | 'warning' | 'success' | 'info'

export interface Toast {
  id: string
  message: string
  variant: ToastVariant
}

interface ToastContextValue {
  addToast: (message: string, variant?: ToastVariant) => void
}

// ─── Context ──────────────────────────────────────────────────────────────────
const ToastContext = createContext<ToastContextValue>({
  addToast: () => undefined,
})

export function useToast() {
  return useContext(ToastContext)
}

// ─── Singleton emitter (used by apiFetch outside React tree) ──────────────────
let _emit: ((message: string, variant?: ToastVariant) => void) | null = null

export function emitToast(message: string, variant: ToastVariant = 'error') {
  _emit?.(message, variant)
}

// ─── Toast item ───────────────────────────────────────────────────────────────
const VARIANT_STYLES: Record<ToastVariant, string> = {
  error:
    'border-red-500/20 bg-red-50 text-red-900',
  warning:
    'border-amber-500/20 bg-amber-50 text-amber-900',
  success:
    'border-emerald-500/20 bg-emerald-50 text-emerald-900',
  info:
    'border-primary/20 bg-primary/[0.06] text-ink',
}

const PROGRESS_COLOR: Record<ToastVariant, string> = {
  error: 'bg-red-500',
  warning: 'bg-amber-500',
  success: 'bg-emerald-500',
  info: 'bg-primary',
}

const AUTO_DISMISS_MS = 5000

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`relative flex max-w-sm items-start gap-3 overflow-hidden rounded-xl border px-4 py-3 shadow-lg backdrop-blur-sm animate-in slide-in-from-right-4 fade-in duration-200 ${VARIANT_STYLES[toast.variant]}`}
    >
      <p className="flex-1 text-sm font-medium leading-snug">{toast.message}</p>
      <button
        type="button"
        aria-label="Cerrar"
        className="mt-px shrink-0 rounded-sm opacity-60 hover:opacity-100"
        onClick={() => onDismiss(toast.id)}
      >
        <svg className="size-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
          <path d="M4.22 4.22a.75.75 0 0 1 1.06 0L8 6.94l2.72-2.72a.75.75 0 1 1 1.06 1.06L9.06 8l2.72 2.72a.75.75 0 1 1-1.06 1.06L8 9.06l-2.72 2.72a.75.75 0 0 1-1.06-1.06L6.94 8 4.22 5.28a.75.75 0 0 1 0-1.06Z" />
        </svg>
      </button>
      {/* progress bar */}
      <span
        className={`absolute bottom-0 left-0 h-[2px] ${PROGRESS_COLOR[toast.variant]}`}
        style={{ animation: `du-toast-shrink ${AUTO_DISMISS_MS}ms linear forwards` }}
      />
    </div>
  )
}

// ─── Provider ─────────────────────────────────────────────────────────────────
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timerMap = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timerMap.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timerMap.current.delete(id)
    }
  }, [])

  const addToast = useCallback(
    (message: string, variant: ToastVariant = 'error') => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`
      setToasts((prev) => [...prev.slice(-4), { id, message, variant }])
      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
      timerMap.current.set(id, timer)
    },
    [dismiss],
  )

  // Expose to singleton emitter so apiFetch can call it
  _emit = addToast

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div
        aria-label="Notificaciones"
        className="fixed top-5 right-5 z-[9999] flex flex-col items-end gap-2"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
