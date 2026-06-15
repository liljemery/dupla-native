import { useCallback, useEffect, useLayoutEffect, useState } from 'react'

import { apiFetch } from '../../../api/client'
import { Card } from '../../Card'
import {
  PROJECT_EVENT_TYPE_OPTIONS,
  projectEventSearchPlaceholder,
} from '../../../constants/projectEventTypes'
import { describeProjectEvent, type ProjectEventRow } from '../../../lib/projectEventTraceability'

const PAGE_SIZE = 20
const POLL_MS = 5000
const SEARCH_DEBOUNCE_MS = 400

type ProjectEventsPage = {
  items: ProjectEventRow[]
  total: number
  limit: number
  offset: number
}

type WorkspaceEventosTabProps = {
  token: string | null
  projectUuid: string
}

export function WorkspaceEventosTab({ token, projectUuid }: WorkspaceEventosTabProps) {
  const [page, setPage] = useState(0)
  const [eventType, setEventType] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [data, setData] = useState<ProjectEventsPage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const offset = page * PAGE_SIZE

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(searchInput), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [searchInput])

  useLayoutEffect(() => {
    setPage(0)
  }, [eventType, debouncedQ])

  const fetchPage = useCallback(async () => {
    if (!token || !projectUuid) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(offset))
      if (eventType.trim()) params.set('event_type', eventType.trim())
      if (debouncedQ.trim()) params.set('q', debouncedQ.trim())
      const res = await apiFetch(`/api/projects/${projectUuid}/events?${params.toString()}`, { token })
      if (!res.ok) {
        setError('No se pudieron cargar los eventos')
        setData(null)
        return
      }
      setData((await res.json()) as ProjectEventsPage)
    } finally {
      setLoading(false)
    }
  }, [token, projectUuid, offset, eventType, debouncedQ])

  useEffect(() => {
    if (!token || !projectUuid) return
    void fetchPage()
    const id = window.setInterval(() => void fetchPage(), POLL_MS)
    return () => window.clearInterval(id)
  }, [token, projectUuid, fetchPage])

  const total = data?.total ?? 0
  const items = data?.items ?? []
  const fromIdx = total === 0 ? 0 : offset + 1
  const toIdx = Math.min(offset + PAGE_SIZE, total)
  const canPrev = page > 0
  const canNext = offset + PAGE_SIZE < total

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-lg font-semibold text-ink">Trazabilidad del proyecto</h2>
        <p className="text-xs text-muted">
          Actualización cada {POLL_MS / 1000} s. La búsqueda espera {SEARCH_DEBOUNCE_MS / 1000} s sin escribir.
        </p>
      </div>

      <div className="mt-4 flex flex-col gap-3 border-b border-black/10 pb-4 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="block min-w-[12rem] flex-1 text-sm">
          <span className="du-meta">Tipo de evento</span>
          <select
            className="du-input mt-1 w-full"
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            aria-label="Filtrar por tipo de evento"
          >
            <option value="">Todos</option>
            {PROJECT_EVENT_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block min-w-[min(100%,16rem)] flex-[2] text-sm">
          <span className="du-meta">Buscar en el evento</span>
          <input
            type="search"
            className="du-input mt-1 w-full"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={projectEventSearchPlaceholder(eventType)}
            autoComplete="off"
            aria-label="Buscar en eventos"
          />
        </label>
      </div>

      {error ? <p className="mt-3 text-sm text-primary">{error}</p> : null}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
        <span>
          {total === 0 ? 'Sin resultados' : `Mostrando ${fromIdx}–${toIdx} de ${total}`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-md border border-black/15 bg-white px-3 py-1.5 text-sm font-medium text-ink disabled:opacity-40"
            disabled={!canPrev || loading}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            Anterior
          </button>
          <button
            type="button"
            className="rounded-md border border-black/15 bg-white px-3 py-1.5 text-sm font-medium text-ink disabled:opacity-40"
            disabled={!canNext || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>

      <ul className="mt-4 space-y-3">
        {items.map((ev) => {
          const trace = describeProjectEvent(ev)
          return (
            <li key={ev.uuid} className="rounded-lg border border-black/10 bg-white p-4 shadow-[var(--shadow-card)]">
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-black/5 pb-2">
                <h3 className="text-sm font-semibold text-ink">{trace.title}</h3>
                <time className="shrink-0 text-xs tabular-nums text-muted" dateTime={ev.created_at}>
                  {new Date(ev.created_at).toLocaleString('es')}
                </time>
              </div>
              <p className="mt-3 text-sm">
                <span className="font-medium text-muted">Realizado por</span>{' '}
                <span className="break-all text-ink">{ev.actor_email ?? 'Sistema o proceso automático'}</span>
              </p>
              {trace.rows.length > 0 ? (
                <dl className="mt-3 space-y-2 text-sm">
                  {trace.rows.map((row, idx) => (
                    <div
                      key={`${ev.uuid}-${idx}-${row.label}`}
                      className="grid gap-0.5 border-t border-black/[0.06] pt-2 first:border-t-0 first:pt-0 sm:grid-cols-[minmax(0,9rem)_1fr] sm:gap-3"
                    >
                      <dt className="font-medium text-muted">{row.label}</dt>
                      <dd className="min-w-0 break-words text-ink">{row.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </li>
          )
        })}
      </ul>
      {items.length === 0 && !loading ? (
        <p className="mt-4 text-sm text-muted">Sin eventos que coincidan con los filtros.</p>
      ) : null}
    </Card>
  )
}
