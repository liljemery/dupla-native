import { ChevronRight, MessageSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Fragment, useEffect, useMemo, useState } from 'react'

import { formatPersonFullName } from '../lib/personDisplay'
import {
  priorityLabelForListTitle,
  statusPresentationForListTitle,
  type FlatTaskRow,
} from '../lib/taskboardViews'
import { hueClassForUuid, labelForCreatedPhase, userDisplayInitials } from '../lib/taskboard'
import type { TaskCardDto } from '../types/taskBoard'

const PAGE_SIZE = 12

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('es', { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return '—'
  }
}

type TaskboardListTableProps = {
  rows: FlatTaskRow[]
  onOpenCard: (card: TaskCardDto) => void
}

export function TaskboardListTable({ rows, onOpenCard }: TaskboardListTableProps) {
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      await Promise.resolve()
      if (!cancelled) setPage(1)
    })()
    return () => {
      cancelled = true
    }
  }, [rows])

  const grouped = useMemo(() => {
    const map = new Map<string, FlatTaskRow[]>()
    const order: string[] = []
    for (const row of rows) {
      const key = row.card.project_uuid ?? '__sin_proyecto__'
      if (!map.has(key)) {
        map.set(key, [])
        order.push(key)
      }
      map.get(key)!.push(row)
    }
    return { map, order }
  }, [rows])

  const flatOrdered = useMemo(() => {
    const out: FlatTaskRow[] = []
    for (const key of grouped.order) {
      const chunk = grouped.map.get(key)
      if (chunk) out.push(...chunk)
    }
    return out
  }, [grouped])

  const total = flatOrdered.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * PAGE_SIZE
  const pageRows = flatOrdered.slice(start, start + PAGE_SIZE)

  const rowsByGroupKey = useMemo(() => {
    const m = new Map<string, FlatTaskRow[]>()
    for (const r of pageRows) {
      const key = r.card.project_uuid ?? '__sin_proyecto__'
      if (!m.has(key)) m.set(key, [])
      m.get(key)!.push(r)
    }
    return m
  }, [pageRows])

  const groupOrderOnPage = useMemo(() => {
    const seen = new Set<string>()
    const ord: string[] = []
    for (const r of pageRows) {
      const key = r.card.project_uuid ?? '__sin_proyecto__'
      if (!seen.has(key)) {
        seen.add(key)
        ord.push(key)
      }
    }
    return ord
  }, [pageRows])

  function projectHeading(key: string): { title: string; badge: string } {
    if (key === '__sin_proyecto__') {
      return { title: 'Sin proyecto vinculado', badge: `${grouped.map.get(key)?.length ?? 0} tareas` }
    }
    const first = grouped.map.get(key)?.[0]
    const name = first?.card.project_name?.trim() || 'Obra'
    const code = first?.card.project_code?.trim()
    const count = grouped.map.get(key)?.length ?? 0
    return {
      title: code ? `${code}: ${name}` : name,
      badge: `${count} tareas`,
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)]">
      <div className="min-h-0 flex-1 overflow-x-auto overflow-y-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-black/10 bg-[#f8f9fb] text-xs font-semibold uppercase tracking-wide text-muted">
            <tr>
              <th className="w-10 px-3 py-3" aria-hidden />
              <th className="px-3 py-3">Tarea</th>
              <th className="px-3 py-3">Fase</th>
              <th className="px-3 py-3">Estado</th>
              <th className="px-3 py-3">Prioridad</th>
              <th className="px-3 py-3">Creada</th>
              <th className="px-3 py-3">Asignado por</th>
              <th className="w-14 px-2 py-3 text-center" aria-label="Comentarios">
                <MessageSquare className="mx-auto size-4 text-muted" aria-hidden />
              </th>
              <th className="px-3 py-3">Acción</th>
            </tr>
          </thead>
          <tbody>
            {total === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-sm text-muted">
                  No hay tareas que coincidan con la búsqueda.
                </td>
              </tr>
            ) : (
              groupOrderOnPage.map((gKey) => {
                const chunk = rowsByGroupKey.get(gKey) ?? []
                const { title, badge } = projectHeading(gKey)
                return (
                  <Fragment key={gKey}>
                    <tr className="bg-primary/[0.07]">
                      <td colSpan={9} className="px-4 py-2.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-xs font-bold uppercase tracking-wide text-ink">
                            Proyecto: {title}
                          </span>
                          <span className="rounded-full border border-primary/25 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-primary">
                            {badge}
                          </span>
                        </div>
                      </td>
                    </tr>
                    {chunk.map(({ card, listTitle }) => {
                      const phase = labelForCreatedPhase(card.created_in_phase)
                      const status = statusPresentationForListTitle(listTitle)
                      const pri = priorityLabelForListTitle(listTitle)
                      const creatorEmail = card.creator_email ?? ''
                      const creatorName = creatorEmail
                        ? formatPersonFullName(
                            card.creator_first_name,
                            card.creator_last_name,
                            card.creator_email ?? '',
                          )
                        : '—'
                      const creatorUuid = card.created_by_uuid ?? card.uuid
                      const initials = creatorEmail
                        ? userDisplayInitials(
                            card.creator_first_name,
                            card.creator_last_name,
                            creatorEmail,
                          )
                        : '?'
                      const hue = hueClassForUuid(creatorUuid)

                      return (
                        <tr
                          key={card.uuid}
                          className="border-b border-black/[0.06] bg-white hover:bg-black/[0.015]"
                        >
                          <td className="px-3 py-3 align-middle">
                            <span className="inline-block size-4 rounded border border-black/15 bg-white" aria-hidden />
                          </td>
                          <td className="max-w-[240px] px-3 py-3 align-middle">
                            <button
                              type="button"
                              className="block w-full text-left font-semibold text-ink hover:text-primary hover:underline"
                              onClick={() => onOpenCard(card)}
                            >
                              {card.title}
                            </button>
                            {card.description ? (
                              <p className="mt-1 line-clamp-1 text-xs text-muted">{card.description}</p>
                            ) : null}
                          </td>
                          <td className="whitespace-nowrap px-3 py-3 align-middle text-ink">
                            {phase ?? '—'}
                          </td>
                          <td className="px-3 py-3 align-middle">
                            <span
                              className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${status.pillClass}`}
                            >
                              {status.label}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-3 py-3 align-middle">
                            <span className="inline-flex items-center gap-2 text-ink">
                              <span className={`size-2 shrink-0 rounded-full ${pri.dotClass}`} aria-hidden />
                              {pri.label}
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-3 py-3 align-middle text-muted">
                            {formatShortDate(card.created_at)}
                          </td>
                          <td className="px-3 py-3 align-middle">
                            <div className="flex items-center gap-2">
                              <span
                                className={`flex size-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold uppercase text-white ${hue}`}
                              >
                                {initials}
                              </span>
                              <span className="min-w-0 truncate text-xs font-medium text-ink">{creatorName}</span>
                            </div>
                          </td>
                          <td className="px-2 py-3 text-center align-middle text-xs text-muted">—</td>
                          <td className="px-3 py-3 align-middle">
                            {card.project_uuid ? (
                              <Link
                                className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-primary hover:underline"
                                to={`/app/projects/${card.project_uuid}`}
                              >
                                Ir a fase
                                <ChevronRight className="size-3.5 shrink-0" aria-hidden />
                              </Link>
                            ) : (
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-primary hover:underline"
                                onClick={() => onOpenCard(card)}
                              >
                                Abrir
                                <ChevronRight className="size-3.5 shrink-0" aria-hidden />
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {total > 0 ? (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-black/10 bg-[#f8f9fb] px-4 py-3 text-xs text-muted">
          <p>
            Mostrando {Math.min(total, start + 1)}–{Math.min(total, start + pageRows.length)} de {total} tareas
            asignadas
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={safePage <= 1}
              className="rounded-md border border-black/12 bg-white px-2.5 py-1 font-semibold text-ink disabled:opacity-40"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Anterior
            </button>
            <span className="tabular-nums font-semibold text-ink">
              {safePage} / {totalPages}
            </span>
            <button
              type="button"
              disabled={safePage >= totalPages}
              className="rounded-md border border-black/12 bg-white px-2.5 py-1 font-semibold text-ink disabled:opacity-40"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Siguiente
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
