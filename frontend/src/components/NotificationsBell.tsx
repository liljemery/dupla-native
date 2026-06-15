import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, CircleCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { apiFetch } from '../api/client'

export type UserNotificationRow = {
  uuid: string
  project_uuid: string | null
  kind: string
  title: string
  body: string | null
  read_at: string | null
  created_at: string
}

type NotificationsBellProps = {
  token: string | null
}

export function NotificationsBell({ token }: NotificationsBellProps) {
  const [open, setOpen] = useState(false)
  const [notifs, setNotifs] = useState<UserNotificationRow[]>([])
  const [loading, setLoading] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const unreadCount = notifs.filter((n) => !n.read_at).length

  const loadNotifs = useCallback(async () => {
    if (!token) {
      setNotifs([])
      return
    }
    setLoading(true)
    try {
      const res = await apiFetch('/api/me/notifications?unread_only=false', { token })
      if (!res.ok) return
      const rows = (await res.json()) as UserNotificationRow[]
      const unread = rows.filter((r) => !r.read_at)
      const rest = rows.filter((r) => r.read_at)
      setNotifs([...unread, ...rest].slice(0, 20))
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void loadNotifs()
  }, [loadNotifs])

  useEffect(() => {
    if (!open) return
    void loadNotifs()
  }, [open, loadNotifs])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  async function markRead(uuid: string) {
    if (!token) return
    const target = notifs.find((n) => n.uuid === uuid)
    if (!target || target.read_at) return
    const res = await apiFetch(`/api/me/notifications/${uuid}/read`, {
      method: 'PATCH',
      token,
    })
    if (!res.ok) return
    const readAt = new Date().toISOString()
    setNotifs((prev) => prev.map((n) => (n.uuid === uuid ? { ...n, read_at: readAt } : n)))
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className="relative rounded-lg border border-black/10 bg-white p-2 text-muted shadow-sm transition hover:bg-black/[0.03] hover:text-ink"
        title={unreadCount > 0 ? `${unreadCount} avisos sin leer` : 'Sin avisos nuevos'}
        aria-label="Avisos"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Bell className="size-5" strokeWidth={2} aria-hidden />
        {unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-0.5 text-[10px] font-bold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 top-full z-50 mt-1 w-[min(calc(100vw-2rem),22rem)] overflow-hidden rounded-lg border border-black/10 bg-white shadow-lg">
          <div className="border-b border-black/8 px-4 py-3">
            <p className="text-sm font-semibold text-ink">Notificaciones</p>
            <p className="text-xs text-muted">
              {unreadCount > 0
                ? `${unreadCount} sin leer`
                : loading
                  ? 'Cargando…'
                  : 'Estás al día'}
            </p>
          </div>
          <ul className="max-h-[min(60vh,20rem)] divide-y divide-black/8 overflow-y-auto">
            {notifs.length === 0 ? (
              <li className="px-4 py-8 text-center text-sm text-muted">
                {loading ? 'Cargando avisos…' : 'No hay notificaciones.'}
              </li>
            ) : (
              notifs.map((n) => (
                <li key={n.uuid}>
                  <button
                    type="button"
                    className={`flex w-full gap-3 px-4 py-3 text-left transition hover:bg-black/[0.03] ${
                      n.read_at ? 'opacity-75' : ''
                    }`}
                    onClick={() => void markRead(n.uuid)}
                  >
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      {n.read_at ? (
                        <CircleCheck className="size-4" strokeWidth={2} aria-hidden />
                      ) : (
                        <AlertTriangle className="size-4" strokeWidth={2} aria-hidden />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={`block text-sm font-medium leading-snug ${n.read_at ? 'text-muted' : 'text-ink'}`}
                      >
                        {n.title}
                      </span>
                      {n.body ? (
                        <span className="mt-1 block line-clamp-2 text-xs leading-relaxed text-muted">{n.body}</span>
                      ) : null}
                      <span className="mt-1 block text-[10px] tabular-nums text-muted">
                        {new Date(n.created_at).toLocaleString()}
                      </span>
                      {n.project_uuid ? (
                        <Link
                          className="du-link mt-2 inline-block text-xs font-semibold"
                          to={`/app/projects/${n.project_uuid}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            setOpen(false)
                            void markRead(n.uuid)
                          }}
                        >
                          Ir al proyecto
                        </Link>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
