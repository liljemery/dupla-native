import { useMemo } from 'react'
import { LayoutGrid, Search } from 'lucide-react'

import { FlowTemplateIcon } from '../flows/FlowTemplateIcon'
import { Card } from '../Card'
import { FilterBar } from '../ui/FilterBar'
import {
  effectivePrevWorkflowPhase,
  NEXT_WORKFLOW_PHASE,
  WORKFLOW_PHASE_LABELS,
  WORKFLOW_PHASE_ORDER,
} from '../../constants/workflowPhases'
import {
  formatProjectUpdatedAt,
  isProjectDeadlinePast,
  PROJECT_BOARD_PHASE_ICONS,
} from '../../constants/projectsPage'
import { projectKindLabel } from '../../constants/projectKind'
import { workflowPhaseProgressPct } from '../../lib/projectDashboardBuckets'
import type { Project } from '../../types/project'

export type BoardColumnDef = {
  id: string
  title: string
  behaviorKind?: string
  /** Lucide key del paso (plantilla); solo en tablero por paso. */
  iconKey?: string
}

type ProjectsBoardViewProps = {
  loadingList: boolean
  projects: Project[]
  filteredProjects: Project[]
  projectSearch: string
  onProjectSearchChange?: (q: string) => void
  boardMsg: string | null
  onDropOnPhaseColumn: (e: React.DragEvent, columnId: string) => void
  onDragOverBoard: (e: React.DragEvent) => void
  onDragStartProject: (e: React.DragEvent, projectUuid: string) => void
  onDragEndBoard: () => void
  onOpenCard: (projectUuid: string) => void
  /** Si se define, columnas dinámicas (tablero por plantilla); las ids son UUID de paso. */
  boardColumns?: BoardColumnDef[]
  columnMode?: 'phase' | 'step'
}

function PhaseLikeIcon({ behaviorKind }: { behaviorKind?: string }) {
  const bk = behaviorKind ?? ''
  const Icon =
    PROJECT_BOARD_PHASE_ICONS[bk as keyof typeof PROJECT_BOARD_PHASE_ICONS] ?? LayoutGrid
  return <Icon className="h-4 w-4 shrink-0 text-white" strokeWidth={2} aria-hidden />
}

function ColumnHeaderGlyph({
  columnMode,
  behaviorKind,
  iconKey,
}: {
  columnMode: 'phase' | 'step'
  behaviorKind?: string
  iconKey?: string
}) {
  if (columnMode === 'step' && iconKey?.trim()) {
    return <FlowTemplateIcon name={iconKey} className="h-4 w-4 shrink-0 text-white" strokeWidth={2} />
  }
  return <PhaseLikeIcon behaviorKind={behaviorKind} />
}

export function ProjectsBoardView({
  loadingList,
  projects,
  filteredProjects,
  projectSearch,
  onProjectSearchChange,
  boardMsg,
  onDropOnPhaseColumn,
  onDragOverBoard,
  onDragStartProject,
  onDragEndBoard,
  onOpenCard,
  boardColumns,
  columnMode = 'phase',
}: ProjectsBoardViewProps) {
  const useSteps = columnMode === 'step' && boardColumns && boardColumns.length > 0
  const orderedStepIds = useSteps ? boardColumns!.map((c) => c.id) : []

  function stepAdjacency(p: Project): { hasNext: boolean; hasPrev: boolean } {
    const cur = p.current_workflow_step_uuid
    const i = orderedStepIds.indexOf(cur)
    if (i < 0) return { hasNext: false, hasPrev: false }
    return { hasNext: i < orderedStepIds.length - 1, hasPrev: i > 0 }
  }

  const phaseColumns: BoardColumnDef[] = useMemo(() => {
    const order = [...WORKFLOW_PHASE_ORDER]
    const fixedIds = new Set<string>(order)
    const extras = new Set<string>()
    for (const p of filteredProjects) {
      if (!fixedIds.has(p.workflow_phase)) extras.add(p.workflow_phase)
    }
    const ids = [...order, ...Array.from(extras).sort()]
    return ids.map((pk) => ({
      id: pk,
      title: WORKFLOW_PHASE_LABELS[pk] ?? pk,
      behaviorKind: pk,
    }))
  }, [filteredProjects])

  const columns: BoardColumnDef[] = useSteps ? boardColumns! : phaseColumns

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {onProjectSearchChange ? (
        <FilterBar
          search={
            <label className="relative block" data-tour="projects-search">
              <span className="sr-only">Buscar proyectos</span>
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
                strokeWidth={2}
                aria-hidden
              />
              <input
                type="search"
                className="du-input h-9 w-full rounded-xl border-black/10 py-0 pl-9 pr-3 text-sm placeholder:text-muted/90"
                placeholder="Buscar proyectos…"
                value={projectSearch}
                onChange={(e) => onProjectSearchChange(e.target.value)}
                autoComplete="off"
                aria-label="Buscar proyectos"
              />
            </label>
          }
        >
          <span className="text-sm text-muted">Tablero Kanban</span>
        </FilterBar>
      ) : null}

      <Card
        data-tour="projects-board"
        rounded2xl
        elevated
        className="flex min-h-0 flex-1 flex-col overflow-hidden p-0"
      >
      {boardMsg ? (
        <div className="flex shrink-0 border-b border-black/10 bg-white px-4 py-3">
          <p className="text-sm text-primary">{boardMsg}</p>
        </div>
      ) : null}
      {loadingList ? (
        <p className="shrink-0 px-4 py-6 text-sm text-muted">Cargando tablero…</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-3 pb-4">
          {projectSearch.trim() && filteredProjects.length === 0 && projects.length > 0 ? (
            <p className="shrink-0 px-2 pb-3 text-sm text-muted">
              Ningún proyecto coincide con «{projectSearch.trim()}». Prueba otro término o borra la búsqueda.
            </p>
          ) : null}
          <div className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
            <div className="flex h-full w-max min-w-full items-stretch gap-2">
              {columns.map((col) => {
                const inColumn = filteredProjects.filter((p) =>
                  useSteps ? p.current_workflow_step_uuid === col.id : p.workflow_phase === col.id,
                )
                return (
                  <div
                    key={col.id}
                    className="flex h-full min-h-0 w-[11rem] shrink-0 flex-col rounded-xl border border-black/8 bg-surface-elevated shadow-[var(--shadow-card)] sm:w-[12rem]"
                    onDragOver={onDragOverBoard}
                    onDrop={(e) => onDropOnPhaseColumn(e, col.id)}
                  >
                    <div
                      className="flex min-h-[5.5rem] shrink-0 flex-col items-center justify-center gap-1.5 rounded-t-xl border-b border-white/20 bg-primary px-2 py-3 text-center text-white shadow-sm sm:min-h-24"
                      title={col.title}
                    >
                      <ColumnHeaderGlyph
                        columnMode={columnMode}
                        behaviorKind={col.behaviorKind ?? col.id}
                        iconKey={col.iconKey}
                      />
                      <span className="w-full text-[10px] font-semibold uppercase leading-snug tracking-wide sm:text-xs">
                        {col.title}
                      </span>
                    </div>
                    <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
                      {inColumn.map((p) => {
                        const hasNext = useSteps
                          ? stepAdjacency(p).hasNext
                          : NEXT_WORKFLOW_PHASE[p.workflow_phase] !== undefined
                        const hasPrev = useSteps
                          ? stepAdjacency(p).hasPrev
                          : effectivePrevWorkflowPhase(p.project_kind, p.workflow_phase) !== undefined
                        const canMovePhase = hasNext || hasPrev
                        const pct = workflowPhaseProgressPct(p.workflow_phase)
                        return (
                          <div
                            key={p.uuid}
                            role="button"
                            tabIndex={0}
                            draggable={canMovePhase}
                            className={`group relative cursor-pointer overflow-hidden rounded-xl border border-black/8 bg-white text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-md ${
                              canMovePhase ? '' : 'opacity-[0.92]'
                            }`}
                            onClick={() => onOpenCard(p.uuid)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                onOpenCard(p.uuid)
                              }
                            }}
                            onDragStart={(e) => onDragStartProject(e, p.uuid)}
                            onDragEnd={onDragEndBoard}
                          >
                            <div
                              className={`absolute inset-y-1 left-0 w-0.5 rounded-full ${canMovePhase ? 'bg-primary' : 'bg-black/20'}`}
                              aria-hidden
                            />
                            <div className="relative px-3 pb-2.5 pt-2">
                              <p className="mb-0.5 text-[10px] font-semibold uppercase leading-tight tracking-wide text-muted sm:text-xs">
                                {projectKindLabel(p.project_kind)}
                              </p>
                              <h3 className="line-clamp-2 text-xs font-semibold leading-snug tracking-tight text-ink sm:text-sm">
                                {p.name}
                              </h3>
                              {p.project_code?.trim() ? (
                                <p className="mt-0.5 font-mono text-[10px] leading-tight text-muted">{p.project_code}</p>
                              ) : null}
                              <div className="mt-2">
                                <div className="mb-1 flex justify-between text-[10px] font-semibold text-muted">
                                  <span>Progreso</span>
                                  <span className="tabular-nums text-ink">{pct}%</span>
                                </div>
                                <div className="h-1.5 overflow-hidden rounded-full bg-black/[0.06]">
                                  <div
                                    className="h-full rounded-full bg-primary transition-[width] duration-300"
                                    style={{ width: `${pct}%` }}
                                  />
                                </div>
                              </div>
                              <div className="mt-2 space-y-1">
                                <div className="flex items-start gap-1">
                                  <span className="du-meta w-9 shrink-0 text-[10px] sm:text-xs">Cliente</span>
                                  <span className="min-w-0 flex-1 text-xs leading-snug text-ink sm:text-sm">
                                    {p.client_name?.trim() ? (
                                      <span className="line-clamp-2">{p.client_name}</span>
                                    ) : (
                                      <span className="text-muted">—</span>
                                    )}
                                  </span>
                                </div>
                                <div className="flex items-start gap-1 border-t border-black/[0.06] pt-1">
                                  <span className="du-meta w-9 shrink-0 text-[10px] sm:text-xs">Act.</span>
                                  <time
                                    className="min-w-0 flex-1 text-[10px] tabular-nums leading-snug text-ink sm:text-xs"
                                    dateTime={p.updated_at}
                                  >
                                    {formatProjectUpdatedAt(p.updated_at)}
                                  </time>
                                </div>
                              </div>
                              <div className="mt-1.5 flex items-start justify-between gap-1 border-t border-black/[0.05] pt-1">
                                <div className="flex min-w-0 flex-wrap items-center gap-1">
                                  {!canMovePhase ? (
                                    <span className="rounded bg-black/[0.05] px-1 py-0.5 text-[10px] font-semibold uppercase leading-tight tracking-wide text-muted sm:text-xs">
                                      Fin flujo
                                    </span>
                                  ) : (
                                    <span className="text-[10px] font-medium uppercase leading-tight tracking-wide text-muted sm:text-xs">
                                      {hasPrev ? '←' : ''}
                                      {hasPrev && hasNext ? ' ' : ''}
                                      {hasNext ? '→' : ''}
                                    </span>
                                  )}
                                  {isProjectDeadlinePast(p.deadline, p.workflow_phase) ? (
                                    <span className="rounded bg-primary/15 px-1 py-0.5 text-[9px] font-bold uppercase leading-tight text-primary">
                                      Plazo
                                    </span>
                                  ) : null}
                                </div>
                                <span className="text-[10px] font-medium leading-tight text-muted opacity-0 transition-opacity duration-200 group-hover:opacity-100 sm:text-xs">
                                  Abrir →
                                </span>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
      </Card>
    </div>
  )
}
