import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { boardQueryParams, cardMatchesSearch, CARD_MIME, labelForCreatedPhase } from '../lib/taskboard'
import {
  columnAccentForListTitle,
  computeTaskboardKpis,
  flattenBoardLists,
  type TaskViewMode,
} from '../lib/taskboardViews'
import { formatPersonFullName } from '../lib/personDisplay'
import { TaskboardCardModal } from './TaskboardCardModal'
import { TaskboardCreateModal } from './TaskboardCreateModal'
import { TaskboardListTable } from './TaskboardListTable'
import { TaskboardToolbar } from './TaskboardToolbar'
import { useAuthStore } from '../store/authStore'
import type { TaskAssigneeOption, TaskBoardDto, TaskCardDto, TaskListDto } from '../types/taskBoard'

export type TaskboardViewProps = {
  /** Filtro fijo por proyecto; vacío = tablero global */
  projectUuid?: string
  variant: 'full' | 'embedded'
  /**
   * En modo embebido: ancho máximo del viewport del tablero en columnas (resto con scroll horizontal).
   * Ej. 4 = se ven como mucho 4 columnas a la vez.
   */
  maxVisibleColumns?: number
  /** Oculta la franja de título «Tareas del proyecto» en embebido (el padre ya muestra el encabezado). */
  hideEmbeddedHeader?: boolean
}

export function TaskboardView({
  projectUuid: projectFilter = '',
  variant,
  maxVisibleColumns,
  hideEmbeddedHeader = false,
}: TaskboardViewProps) {
  const token = useAuthStore((s) => s.token)
  const userUuid = useAuthStore((s) => s.userUuid)
  const [searchParams, setSearchParams] = useSearchParams()
  const [board, setBoard] = useState<TaskBoardDto | null>(null)
  const [assignees, setAssignees] = useState<TaskAssigneeOption[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [boardSearch, setBoardSearch] = useState('')
  const [modalCard, setModalCard] = useState<TaskCardDto | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const dragRef = useRef(false)

  const assigneeProjectScope = useMemo(
    () => projectFilter || modalCard?.project_uuid || '',
    [projectFilter, modalCard?.project_uuid],
  )

  const load = useCallback(async () => {
    if (!token) return
    setError(null)
    const qs = boardQueryParams(includeArchived, projectFilter)
    const res = await apiFetch(`/api/tasks/board${qs}`, { token })
    if (!res.ok) {
      setError('No se pudo cargar el tablero')
      setBoard(null)
      return
    }
    setBoard((await res.json()) as TaskBoardDto)
  }, [token, includeArchived, projectFilter])

  const selfAssignees = useMemo(
    () => (userUuid ? assignees.filter((a) => a.uuid === userUuid) : []),
    [assignees, userUuid],
  )

  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (!token) return
      const qs = assigneeProjectScope
        ? `?project_uuid=${encodeURIComponent(assigneeProjectScope)}`
        : ''
      const res = await apiFetch(`/api/tasks/assignees${qs}`, { token })
      if (!res.ok || cancelled) return
      setAssignees((await res.json()) as TaskAssigneeOption[])
    })()
    return () => {
      cancelled = true
    }
  }, [token, assigneeProjectScope])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setLoading(true)
      await load()
      if (!cancelled) setLoading(false)
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [load])

  async function moveCard(cardUuid: string, listUuid: string, position: number) {
    if (!token) return
    const res = await apiFetch(`/api/tasks/cards/${cardUuid}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ list_uuid: listUuid, position }),
    })
    if (!res.ok) return
    await load()
  }

  function onDragEnd() {
    window.setTimeout(() => {
      dragRef.current = false
    }, 0)
  }

  function onDragStartCard(e: React.DragEvent, cardUuid: string) {
    dragRef.current = true
    e.dataTransfer.setData(CARD_MIME, cardUuid)
    e.dataTransfer.effectAllowed = 'move'
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  function sortedCards(list: TaskListDto): TaskCardDto[] {
    return [...list.cards].sort((a, b) => a.position - b.position || a.uuid.localeCompare(b.uuid))
  }

  function onDropOnColumn(e: React.DragEvent, list: TaskListDto) {
    e.preventDefault()
    const cardUuid = e.dataTransfer.getData(CARD_MIME)
    if (!cardUuid) return
    const without = sortedCards(list).filter((c) => c.uuid !== cardUuid)
    void moveCard(cardUuid, list.uuid, without.length)
  }

  function onDropOnCard(e: React.DragEvent, list: TaskListDto, insertIndex: number) {
    e.preventDefault()
    e.stopPropagation()
    const cardUuid = e.dataTransfer.getData(CARD_MIME)
    if (!cardUuid) return
    const sorted = sortedCards(list)
    const target = sorted[insertIndex]
    if (!target || target.uuid === cardUuid) return
    const without = sorted.filter((c) => c.uuid !== cardUuid)
    const pos = without.findIndex((c) => c.uuid === target.uuid)
    if (pos < 0) return
    void moveCard(cardUuid, list.uuid, pos)
  }

  function openCard(card: TaskCardDto) {
    if (dragRef.current) return
    setModalCard(card)
  }

  const lists = useMemo((): TaskListDto[] => {
    if (!board) return []
    return [...board.lists].sort((a, b) => a.position - b.position || a.uuid.localeCompare(b.uuid))
  }, [board])

  const searchNeedle = boardSearch.trim().toLowerCase()

  const displayLists = useMemo(() => {
    if (!searchNeedle) return lists
    return lists.map((list) => ({
      ...list,
      cards: list.cards.filter((c) => cardMatchesSearch(c, searchNeedle)),
    }))
  }, [lists, searchNeedle])

  const displayArchivedCards = useMemo(() => {
    if (!board) return []
    if (!searchNeedle) return board.archived_cards
    return board.archived_cards.filter((c) => cardMatchesSearch(c, searchNeedle))
  }, [board, searchNeedle])

  const listOptions = lists.map((l) => ({ uuid: l.uuid, title: l.title }))

  const embedded = variant === 'embedded'

  const viewMode: TaskViewMode =
    embedded ? 'board' : searchParams.get('view') === 'list' ? 'list' : 'board'

  function setViewMode(next: TaskViewMode) {
    if (embedded) return
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev)
        if (next === 'board') p.delete('view')
        else p.set('view', 'list')
        return p
      },
      { replace: true },
    )
  }

  const kpis = useMemo(() => computeTaskboardKpis(lists), [lists])

  const listRows = useMemo(() => flattenBoardLists(displayLists), [displayLists])

  const boardViewportMaxWidth = useMemo(() => {
    if (!embedded || maxVisibleColumns == null || maxVisibleColumns < 1) return undefined
    const colRem = 14
    const gapRem = 0.5
    const gaps = Math.max(0, maxVisibleColumns - 1)
    return `calc(${maxVisibleColumns} * ${colRem}rem + ${gaps} * ${gapRem}rem)`
  }, [embedded, maxVisibleColumns])

  function columnDotClass(accent: ReturnType<typeof columnAccentForListTitle>): string {
    if (accent === 'green') return 'bg-emerald-500'
    if (accent === 'red') return 'bg-primary'
    if (accent === 'amber') return 'bg-amber-400'
    return 'bg-black/35'
  }

  return (
    <div className={`flex min-h-0 flex-1 flex-col ${embedded ? 'gap-2 overflow-hidden' : 'gap-4'}`}>
      {!embedded ? (
        <div className="shrink-0 space-y-4" data-tour="taskboard-header">
          <nav className="text-[11px] font-semibold uppercase tracking-wide text-muted">
            <Link to="/app/projects" className="hover:text-primary">
              Dupla
            </Link>
            <span className="mx-2 text-black/20">/</span>
            <span className="text-ink">Mis tareas</span>
          </nav>

          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">Mis tareas</h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
                Haz clic en cualquier tarea para ir directamente a trabajar en ella.
              </p>
              {projectFilter ? (
                <p className="mt-3 text-sm text-ink">
                  Filtrando por proyecto.{' '}
                  <Link className="font-semibold text-primary underline-offset-2 hover:underline" to="/app/tasks">
                    Ver todas mis tareas
                  </Link>{' '}
                  ·{' '}
                  <Link
                    className="font-semibold text-primary underline-offset-2 hover:underline"
                    to={`/app/projects/${projectFilter}`}
                  >
                    Volver al proyecto
                  </Link>
                </p>
              ) : null}
            </div>

            <div
              className="flex shrink-0 rounded-lg border border-black/10 bg-[#f8f9fb] p-1 shadow-sm"
              role="tablist"
              aria-label="Vista de tareas"
            >
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === 'board'}
                className={`rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide transition ${
                  viewMode === 'board'
                    ? 'bg-white text-primary shadow-sm ring-1 ring-black/8'
                    : 'text-muted hover:text-ink'
                }`}
                onClick={() => setViewMode('board')}
              >
                Tablero
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === 'list'}
                className={`rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide transition ${
                  viewMode === 'list'
                    ? 'bg-white text-primary shadow-sm ring-1 ring-black/8'
                    : 'text-muted hover:text-ink'
                }`}
                onClick={() => setViewMode('list')}
              >
                Lista
              </button>
              <button
                type="button"
                disabled
                className="cursor-not-allowed rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide text-muted opacity-50"
                title="Próximamente"
              >
                Cronograma
              </button>
            </div>
          </div>

          {board && !loading ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              <div className="rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Asignadas</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{kpis.assigned}</p>
              </div>
              <div className="rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-wide text-muted">En proceso</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{kpis.inProgress}</p>
              </div>
              <div
                className={`rounded-xl border px-4 py-3 shadow-sm ${
                  kpis.atRisk > 0
                    ? 'border-primary/35 bg-primary text-white'
                    : 'border-black/10 bg-white'
                }`}
              >
                <p
                  className={`text-[10px] font-bold uppercase tracking-wide ${kpis.atRisk > 0 ? 'text-white/90' : 'text-muted'}`}
                >
                  Bloqueadas
                </p>
                <p
                  className={`mt-1 text-2xl font-bold tabular-nums ${kpis.atRisk > 0 ? 'text-white' : 'text-ink'}`}
                >
                  {String(kpis.atRisk).padStart(2, '0')}
                </p>
              </div>
              <div className="rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm">
                <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Completadas</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{kpis.completed}</p>
              </div>
              <div className="rounded-xl border border-black/10 bg-white px-4 py-3 shadow-sm sm:col-span-2 lg:col-span-1">
                <p className="text-[10px] font-bold uppercase tracking-wide text-muted">Cumplimiento</p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-600">{kpis.compliancePct}%</p>
              </div>
            </div>
          ) : null}
        </div>
      ) : hideEmbeddedHeader ? null : (
        <h2 className="shrink-0 text-sm font-semibold text-ink">Tareas del proyecto</h2>
      )}

      {loading ? (
        <p className="min-h-0 flex-1 text-sm text-muted">Cargando tablero…</p>
      ) : error || !board ? (
        <p className="text-sm text-primary">{error ?? 'Sin datos'}</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <TaskboardToolbar
            embedded={embedded}
            showAddTask
            onAddTask={() => setCreateOpen(true)}
            boardSearch={boardSearch}
            setBoardSearch={setBoardSearch}
            includeArchived={includeArchived}
            setIncludeArchived={setIncludeArchived}
          />

          {viewMode === 'list' && !embedded ? (
            <TaskboardListTable rows={listRows} onOpenCard={openCard} />
          ) : null}

          <div
            className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-black/10 bg-black/2 shadow-[var(--shadow-card)] ${embedded ? 'min-h-0' : ''} ${viewMode === 'list' && !embedded ? 'hidden' : ''}`}
          >
            <div
              className={
                embedded
                  ? 'mx-auto min-h-0 w-full flex-1 overflow-x-auto overflow-y-hidden p-1.5'
                  : 'min-h-0 flex-1 overflow-x-auto overflow-y-hidden p-2'
              }
              style={boardViewportMaxWidth ? { maxWidth: boardViewportMaxWidth } : undefined}
            >
              <div
                data-tour="taskboard-columns"
                className={
                  embedded
                    ? 'flex h-full min-h-[10rem] w-max min-w-full items-stretch gap-1.5 sm:gap-2'
                    : 'flex h-full min-h-0 w-max min-w-full items-stretch gap-2 sm:gap-3 md:grid md:w-full md:min-w-0 md:gap-2 lg:gap-3'
                }
                style={
                  !embedded && displayLists.length > 0
                    ? {
                        gridTemplateColumns: `repeat(${displayLists.length}, minmax(17.5rem, 1fr))`,
                      }
                    : undefined
                }
              >
                {displayLists.map((list) => (
                  <div
                    key={list.uuid}
                    className={
                      embedded
                        ? 'flex h-full min-h-0 w-52 shrink-0 flex-col rounded-lg border border-black/10 bg-black/2 sm:w-56'
                        : 'flex h-full min-h-0 w-[min(100%,17.5rem)] shrink-0 flex-col rounded-lg border border-black/10 bg-black/2 sm:w-72 md:min-w-0 md:max-w-none md:w-auto md:min-w-[17.5rem]'
                    }
                    onDragOver={onDragOver}
                    onDrop={(e) => onDropOnColumn(e, list)}
                  >
                    <div
                      className={`shrink-0 border-b border-black/10 bg-white font-semibold text-ink ${
                        embedded ? 'px-2 py-1.5 text-xs' : 'px-2.5 py-2 text-sm'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={`size-2 shrink-0 rounded-full ${columnDotClass(columnAccentForListTitle(list.title))}`}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1 truncate">{list.title}</span>
                        <span className="shrink-0 tabular-nums text-muted">{sortedCards(list).length}</span>
                      </div>
                    </div>
                    <div
                      className={`min-h-0 flex-1 overflow-y-auto ${
                        embedded ? 'space-y-1.5 p-1.5' : 'space-y-2 p-2'
                      }`}
                    >
                      {sortedCards(list).map((card, index) => {
                        const createdPhaseLabel = labelForCreatedPhase(card.created_in_phase)
                        return (
                          <div
                            key={card.uuid}
                            draggable
                            onDragStart={(e) => onDragStartCard(e, card.uuid)}
                            onDragEnd={onDragEnd}
                            onDragOver={onDragOver}
                            onDrop={(e) => onDropOnCard(e, list, index)}
                            className={`flex min-w-0 rounded-md border border-black/10 bg-white text-left shadow-card transition hover:border-primary/30 ${
                              embedded
                                ? 'gap-1.5 px-1.5 py-1.5 text-xs'
                                : 'gap-2 px-2 py-2 text-sm'
                            }`}
                          >
                            <div
                              className={`shrink-0 cursor-grab text-black/35 active:cursor-grabbing ${
                                embedded ? 'mt-0 h-3.5 w-3' : 'mt-0.5'
                              }`}
                              aria-hidden
                              title="Arrastrar para mover"
                            >
                              <svg
                                width="16"
                                height="20"
                                viewBox="0 0 16 20"
                                className={embedded ? 'block h-full w-full' : 'block'}
                              >
                                <circle cx="5" cy="5" r="1.5" fill="currentColor" />
                                <circle cx="11" cy="5" r="1.5" fill="currentColor" />
                                <circle cx="5" cy="10" r="1.5" fill="currentColor" />
                                <circle cx="11" cy="10" r="1.5" fill="currentColor" />
                                <circle cx="5" cy="15" r="1.5" fill="currentColor" />
                                <circle cx="11" cy="15" r="1.5" fill="currentColor" />
                              </svg>
                            </div>
                            <button
                              type="button"
                              className="min-w-0 flex-1 cursor-pointer text-left"
                              onClick={() => openCard(card)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault()
                                  openCard(card)
                                }
                              }}
                            >
                              <div className={`font-medium text-ink ${embedded ? 'text-xs' : ''}`}>
                                {card.title}
                              </div>
                              {card.description ? (
                                <p
                                  className={`mt-1 line-clamp-2 text-muted ${
                                    embedded ? 'text-[10px] leading-snug' : 'text-xs'
                                  }`}
                                >
                                  {card.description}
                                </p>
                              ) : null}
                              <div
                                className={`border-t border-black/8 text-[11px] ${
                                  embedded ? 'mt-1.5 space-y-1 pt-1.5' : 'mt-2 space-y-2 pt-2'
                                }`}
                              >
                                {card.project_uuid &&
                                (card.project_name?.trim() || card.project_code?.trim()) ? (
                                  <div className="flex flex-col gap-0.5">
                                    <span className="font-semibold uppercase tracking-wide text-muted">
                                      Proyecto
                                    </span>
                                    <span className="min-w-0 break-words font-medium text-ink">
                                      {card.project_name?.trim() || 'Obra'}
                                      {card.project_code?.trim() ? (
                                        <span className="ml-1 font-mono text-muted">
                                          ({card.project_code.trim()})
                                        </span>
                                      ) : null}
                                    </span>
                                  </div>
                                ) : null}
                                {createdPhaseLabel ? (
                                  <div className="flex flex-col gap-0.5">
                                    <span className="font-semibold uppercase tracking-wide text-muted">
                                      Creada en fase
                                    </span>
                                    <span className="min-w-0 break-words text-ink">{createdPhaseLabel}</span>
                                  </div>
                                ) : null}
                                <div className="flex flex-col gap-0.5">
                                  <span className="font-semibold uppercase tracking-wide text-muted">
                                    Asignado
                                  </span>
                                  <span className="min-w-0 break-words text-ink">
                                    {card.assignee_email
                                      ? formatPersonFullName(
                                          card.assignee_first_name,
                                          card.assignee_last_name,
                                          card.assignee_email,
                                        )
                                      : '—'}
                                  </span>
                                </div>
                                <div className="flex flex-col gap-0.5">
                                  <span className="font-semibold uppercase tracking-wide text-muted">Por</span>
                                  <span className="min-w-0 break-words text-ink">
                                    {card.creator_email
                                      ? formatPersonFullName(
                                          card.creator_first_name,
                                          card.creator_last_name,
                                          card.creator_email,
                                        )
                                      : '—'}
                                  </span>
                                </div>
                              </div>
                            </button>
                            <button
                              type="button"
                              className={`shrink-0 self-start rounded-md border border-primary/50 bg-primary/[0.06] font-semibold uppercase tracking-wide text-primary hover:bg-primary/[0.12] ${
                                embedded
                                  ? 'px-1.5 py-0.5 text-[10px]'
                                  : 'px-2.5 py-1 text-xs'
                              }`}
                              onClick={(e) => {
                                e.stopPropagation()
                                openCard(card)
                              }}
                            >
                              View
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {!embedded && includeArchived && displayArchivedCards.length > 0 ? (
            <div className="shrink-0 border-t border-black/10 pt-6">
              <h2 className="text-lg font-semibold text-ink">Archivadas</h2>
              <p className="du-meta mt-1">Clic para ver detalle o restaurar.</p>
              <div className="mt-4 flex max-h-[min(40vh,24rem)] flex-wrap gap-2 overflow-y-auto">
                {displayArchivedCards.map((c) => (
                  <button
                    key={c.uuid}
                    type="button"
                    className="max-w-xs rounded-md border border-black/10 bg-white px-3 py-2 text-left text-sm shadow-card hover:border-primary/30"
                    onClick={() => setModalCard(c)}
                  >
                    <div className="font-medium text-ink">{c.title}</div>
                    <div className="du-meta mt-1 line-clamp-1">
                      {c.assignee_email
                        ? formatPersonFullName(c.assignee_first_name, c.assignee_last_name, c.assignee_email)
                        : 'Sin asignar'}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {embedded && includeArchived && displayArchivedCards.length > 0 ? (
            <div className="shrink-0 border-t border-black/10 pt-2">
              <p className="text-xs font-medium text-ink">Archivadas ({displayArchivedCards.length})</p>
              <div className="mt-1 flex max-h-24 flex-wrap gap-1 overflow-y-auto">
                {displayArchivedCards.map((c) => (
                  <button
                    key={c.uuid}
                    type="button"
                    className="max-w-[10rem] truncate rounded border border-black/10 bg-white px-2 py-1 text-left text-xs hover:border-primary/30"
                    onClick={() => setModalCard(c)}
                  >
                    {c.title}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {modalCard && token ? (
        <TaskboardCardModal
          token={token}
          card={modalCard}
          assignees={selfAssignees.length > 0 ? selfAssignees : assignees}
          readOnly={false}
          onClose={() => setModalCard(null)}
          onSaved={() => void load()}
        />
      ) : null}

      {createOpen && token && listOptions.length > 0 ? (
        <TaskboardCreateModal
          token={token}
          lists={listOptions}
          assignees={selfAssignees.length > 0 ? selfAssignees : assignees}
          defaultProjectUuid={projectFilter || undefined}
          onClose={() => setCreateOpen(false)}
          onCreated={() => void load()}
        />
      ) : null}
    </div>
  )
}
