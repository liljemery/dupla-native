import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { MoreHorizontal, Settings } from 'lucide-react'

import { apiFetch } from '../api/client'
import { boardQueryParams, cardMatchesSearch, CARD_MIME, userDisplayInitials } from '../lib/taskboard'
import {
  columnAccentForListTitle,
  flattenBoardLists,
  type TaskViewMode,
} from '../lib/taskboardViews'
import { formatPersonFullName } from '../lib/personDisplay'
import { TaskboardCardModal } from './TaskboardCardModal'
import { TaskboardCreateModal } from './TaskboardCreateModal'
import { TaskboardSettingsModal } from './TaskboardSettingsModal'
import { TaskboardListTable } from './TaskboardListTable'
import { TaskboardToolbar } from './TaskboardToolbar'
import { useAuthStore } from '../store/authStore'
import type { TaskAssigneeOption, TaskBoardDto, TaskCardDto, TaskListDto } from '../types/taskBoard'

const TASK_CARD_PALETTES = [
  { bg: 'bg-[#f4d9ec]', seg: 'bg-[#262626]', track: 'bg-black/10', avatar: 'bg-white text-[#b1568f]' },
  { bg: 'bg-[#e4dcf7]', seg: 'bg-[#262626]', track: 'bg-black/10', avatar: 'bg-white text-[#6a58b0]' },
  { bg: 'bg-[#f3e24f]', seg: 'bg-[#262626]', track: 'bg-black/15', avatar: 'bg-white text-[#8a7a10]' },
  { bg: 'bg-white', seg: 'bg-[#262626]', track: 'bg-black/10', avatar: 'bg-[#f0f0f3] text-[#1f1f1f]' },
] as const

function taskCardPalette(uuid: string) {
  let h = 0
  for (let i = 0; i < uuid.length; i += 1) h = (h * 31 + uuid.charCodeAt(i)) >>> 0
  return TASK_CARD_PALETTES[h % TASK_CARD_PALETTES.length]
}

function cardProgressSegments(accent: ReturnType<typeof columnAccentForListTitle>): number {
  if (accent === 'green') return 6
  if (accent === 'amber') return 3
  return 1
}

function formatCardDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const yy = String(d.getFullYear()).slice(-2)
  return `${dd}.${mm}.${yy}`
}

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
  const canEditBoard = useAuthStore((s) => s.hasPermission('tasks.board.edit'))
  const canViewAllTasks = useAuthStore((s) => s.hasPermission('tasks.board.view_all'))
  const canAssignOthers = useAuthStore((s) => s.hasPermission('tasks.board.assign'))
  const canManageBoard = useAuthStore((s) => s.hasPermission('tasks.board.manage'))
  const [searchParams, setSearchParams] = useSearchParams()
  const [board, setBoard] = useState<TaskBoardDto | null>(null)
  const [assignees, setAssignees] = useState<TaskAssigneeOption[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [boardSearch, setBoardSearch] = useState('')
  const [modalCard, setModalCard] = useState<TaskCardDto | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const dragRef = useRef(false)

  const assigneeProjectScope = useMemo(
    () => projectFilter || modalCard?.project_uuid || '',
    [projectFilter, modalCard?.project_uuid],
  )

  const load = useCallback(async () => {
    if (!token) return
    setError(null)
    const qs = boardQueryParams(includeArchived, projectFilter, canViewAllTasks)
    const res = await apiFetch(`/api/tasks/board${qs}`, { token })
    if (!res.ok) {
      setError('No se pudo cargar el tablero')
      setBoard(null)
      return
    }
    setBoard((await res.json()) as TaskBoardDto)
  }, [token, includeArchived, projectFilter, canViewAllTasks])

  const assigneeOptions = useMemo(() => {
    if (canAssignOthers) return assignees
    if (userUuid) return assignees.filter((a) => a.uuid === userUuid)
    return []
  }, [assignees, canAssignOthers, userUuid])

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
    if (!canEditBoard) return
    e.preventDefault()
    const cardUuid = e.dataTransfer.getData(CARD_MIME)
    if (!cardUuid) return
    const without = sortedCards(list).filter((c) => c.uuid !== cardUuid)
    void moveCard(cardUuid, list.uuid, without.length)
  }

  function onDropOnCard(e: React.DragEvent, list: TaskListDto, insertIndex: number) {
    if (!canEditBoard) return
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
            <span className="text-ink">{canViewAllTasks ? 'Tareas' : 'Mis tareas'}</span>
          </nav>

          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">
                {canViewAllTasks ? 'Tareas del workspace' : 'Mis tareas'}
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
                {canViewAllTasks
                  ? 'Revisa las tareas pendientes y asígnalas al equipo.'
                  : 'Haz clic en cualquier tarea para ir directamente a trabajar en ella.'}
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

            <div className="flex shrink-0 items-start gap-2">
              {canManageBoard ? (
                <button
                  type="button"
                  className="flex size-10 items-center justify-center rounded-lg border border-black/10 bg-white/60 text-muted shadow-sm backdrop-blur-md transition hover:border-primary/30 hover:text-primary"
                  aria-label="Configurar tablero"
                  title="Configurar columnas"
                  onClick={() => setSettingsOpen(true)}
                >
                  <Settings className="size-5" strokeWidth={2} aria-hidden />
                </button>
              ) : null}
              <div
                className="flex rounded-lg border border-black/10 bg-white/40 p-1 backdrop-blur-md"
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
          </div>

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
            showAddTask={canEditBoard}
            onAddTask={() => setCreateOpen(true)}
            boardSearch={boardSearch}
            setBoardSearch={setBoardSearch}
            includeArchived={includeArchived}
            setIncludeArchived={setIncludeArchived}
            viewAll={canViewAllTasks}
          />

          {viewMode === 'list' && !embedded ? (
            <TaskboardListTable rows={listRows} onOpenCard={openCard} />
          ) : null}

          <div
            className={`flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-black/10 ${embedded ? 'min-h-0' : ''} ${viewMode === 'list' && !embedded ? 'hidden' : ''}`}
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
                        ? 'flex h-full min-h-0 w-52 shrink-0 flex-col overflow-hidden rounded-xl border border-black/10 bg-white/35 backdrop-blur-md sm:w-56'
                        : 'flex h-full min-h-0 w-[min(100%,17.5rem)] shrink-0 flex-col overflow-hidden rounded-xl border border-black/10 bg-white/35 backdrop-blur-md sm:w-72 md:min-w-0 md:max-w-none md:w-auto md:min-w-[17.5rem]'
                    }
                    onDragOver={canEditBoard ? onDragOver : undefined}
                    onDrop={canEditBoard ? (e) => onDropOnColumn(e, list) : undefined}
                  >
                    <div
                      className={`shrink-0 border-b border-black/10 bg-white/70 font-semibold text-ink ${
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
                        const palette = taskCardPalette(card.uuid)
                        const filled = cardProgressSegments(columnAccentForListTitle(list.title))
                        const assigneeName = card.assignee_email
                          ? formatPersonFullName(
                              card.assignee_first_name,
                              card.assignee_last_name,
                              card.assignee_email,
                            )
                          : 'Sin asignar'
                        const initials = card.assignee_email
                          ? userDisplayInitials(
                              card.assignee_first_name,
                              card.assignee_last_name,
                              card.assignee_email,
                            )
                          : '—'
                        const dateLabel = formatCardDate(card.created_at)
                        return (
                          <div
                            key={card.uuid}
                            role="button"
                            tabIndex={0}
                            draggable={canEditBoard}
                            onDragStart={canEditBoard ? (e) => onDragStartCard(e, card.uuid) : undefined}
                            onDragEnd={canEditBoard ? onDragEnd : undefined}
                            onDragOver={canEditBoard ? onDragOver : undefined}
                            onDrop={canEditBoard ? (e) => onDropOnCard(e, list, index) : undefined}
                            onClick={() => openCard(card)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                openCard(card)
                              }
                            }}
                            className={`group relative flex min-w-0 flex-col justify-between rounded-2xl text-left shadow-sm outline-none transition hover:-translate-y-0.5 hover:shadow-md focus-visible:ring-2 focus-visible:ring-primary/40 ${palette.bg} ${
                              embedded ? 'min-h-28 cursor-pointer p-2.5' : 'min-h-40 cursor-pointer p-3.5'
                            } ${canEditBoard ? '' : 'cursor-default hover:translate-y-0 hover:shadow-sm'}`}
                          >
                            <button
                              type="button"
                              aria-label="Abrir tarea"
                              className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-full text-black/40 transition hover:bg-black/5 hover:text-black/70"
                              onClick={(e) => {
                                e.stopPropagation()
                                openCard(card)
                              }}
                            >
                              <MoreHorizontal className="size-4" aria-hidden />
                            </button>

                            <div className="flex items-center gap-2 pr-7">
                              <span
                                className={`flex shrink-0 items-center justify-center rounded-full font-bold ${palette.avatar} ${
                                  embedded ? 'size-7 text-[10px]' : 'size-8 text-[11px]'
                                }`}
                              >
                                {initials}
                              </span>
                              <div className="min-w-0 flex-1">
                                <p
                                  className={`truncate font-semibold text-[#1f1f1f] ${
                                    embedded ? 'text-xs' : 'text-sm'
                                  }`}
                                >
                                  {assigneeName}
                                </p>
                                {dateLabel ? (
                                  <p className="truncate text-[11px] text-black/45">{dateLabel}</p>
                                ) : null}
                              </div>
                            </div>

                            <div className={`min-w-0 ${embedded ? 'mt-2' : 'mt-3'}`}>
                              <h4
                                className={`line-clamp-2 break-words font-bold leading-snug text-[#1f1f1f] ${
                                  embedded ? 'text-xs' : 'text-sm'
                                }`}
                              >
                                {card.title}
                              </h4>
                              {!embedded && card.project_name?.trim() ? (
                                <p className="mt-0.5 truncate text-[11px] font-medium text-black/40">
                                  {card.project_name.trim()}
                                </p>
                              ) : null}
                              {card.description?.trim() ? (
                                <p
                                  className={`mt-1 break-words text-black/55 ${
                                    embedded ? 'line-clamp-3 text-[10px] leading-snug' : 'line-clamp-4 text-xs leading-snug'
                                  }`}
                                >
                                  {card.description}
                                </p>
                              ) : null}
                            </div>

                            <div className={`flex items-center gap-1 ${embedded ? 'mt-2' : 'mt-3'}`} aria-hidden>
                              {Array.from({ length: 6 }).map((_, i) => (
                                <span
                                  key={i}
                                  className={`h-1.5 flex-1 rounded-full ${i < filled ? palette.seg : palette.track}`}
                                />
                              ))}
                            </div>
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
          assignees={assigneeOptions}
          readOnly={!canEditBoard}
          onClose={() => setModalCard(null)}
          onSaved={() => void load()}
        />
      ) : null}

      {createOpen && token && listOptions.length > 0 && canEditBoard ? (
        <TaskboardCreateModal
          token={token}
          lists={listOptions}
          assignees={assigneeOptions}
          defaultProjectUuid={projectFilter || undefined}
          onClose={() => setCreateOpen(false)}
          onCreated={() => void load()}
        />
      ) : null}

      {settingsOpen && token && board ? (
        <TaskboardSettingsModal
          token={token}
          lists={lists}
          onClose={() => setSettingsOpen(false)}
          onChanged={() => void load()}
        />
      ) : null}
    </div>
  )
}
