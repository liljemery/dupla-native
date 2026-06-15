import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Building2, CircleCheck, Factory, HardHat, MapPin, MoreVertical } from 'lucide-react'
import { Link } from 'react-router-dom'

import { apiFetch } from '../../api/client'
import { WORKFLOW_PHASE_LABELS } from '../../constants/workflowPhases'
import { projectKindLabel } from '../../constants/projectKind'
import {
  dashboardBucketLabel,
  projectDashboardBucket,
  workflowPhaseProgressPct,
  type DashboardStatusFilter,
} from '../../lib/projectDashboardBuckets'
import type { Project } from '../../types/project'

type UserNotificationRow = {
  uuid: string
  project_uuid: string | null
  kind: string
  title: string
  body: string | null
  read_at: string | null
  created_at: string
}

type ProjectsDashboardOverviewProps = {
  token: string | null
  loadingList: boolean
  projects: Project[]
  displayProjects: Project[]
  projectSearch: string
  statusFilter: DashboardStatusFilter
  onStatusFilter: (f: DashboardStatusFilter) => void
  stats: { total: number; proceso: number; revision: number; cerrados: number }
  onOpenProject: (uuid: string) => void
}

function projectCardIcon(kind: string) {
  if (kind === 'TENDER') return Factory
  if (kind === 'DEVELOPMENT') return HardHat
  return Building2
}

function projectSubtitle(p: Project): string {
  const loc = p.location_text?.trim()
  const code = p.project_code?.trim()
  if (loc && code) return `${loc} · ${code}`
  if (loc) return loc
  if (code) return code
  const client = p.client_name?.trim()
  return client || projectKindLabel(p.project_kind)
}

export function ProjectsDashboardOverview({
  token,
  loadingList,
  projects,
  displayProjects,
  projectSearch,
  statusFilter,
  onStatusFilter,
  stats,
  onOpenProject,
}: ProjectsDashboardOverviewProps) {
  const [notifs, setNotifs] = useState<UserNotificationRow[]>([])
  const [menuUuid, setMenuUuid] = useState<string | null>(null)

  const activeOnMap = useMemo(
    () => projects.filter((p) => p.workflow_phase !== 'COMPLETE').length,
    [projects],
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch('/api/me/notifications?unread_only=false', { token })
      if (!res.ok || cancelled) return
      const rows = (await res.json()) as UserNotificationRow[]
      const unread = rows.filter((r) => !r.read_at)
      const rest = rows.filter((r) => r.read_at)
      if (!cancelled) setNotifs([...unread, ...rest].slice(0, 6))
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    if (!menuUuid) return
    const onDoc = () => setMenuUuid(null)
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [menuUuid])

  const chips: { id: DashboardStatusFilter; label: string; count: number }[] = useMemo(
    () => [
      { id: 'todos', label: 'Todos', count: stats.total },
      { id: 'proceso', label: 'En proceso', count: stats.proceso },
      { id: 'revision', label: 'En revisión', count: stats.revision },
      { id: 'cerrado', label: 'Cerrado', count: stats.cerrados },
    ],
    [stats],
  )

  const statCards = useMemo(
    () => [
      { key: 'total', label: 'Total proyectos', value: stats.total },
      { key: 'proceso', label: 'En proceso', value: stats.proceso },
      { key: 'revision', label: 'En revisión', value: stats.revision },
      { key: 'cerrados', label: 'Cerrados', value: stats.cerrados },
    ],
    [stats],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 pb-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {statCards.map((s) => (
          <div
            key={s.key}
            className="rounded-xl border border-primary/12 bg-primary/[0.05] px-4 py-4 shadow-[var(--shadow-card)]"
          >
            <p className="text-xs font-semibold uppercase tracking-wider text-primary/90">{s.label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums text-ink">{s.value}</p>
          </div>
        ))}
      </div>

      <section className="rounded-xl border border-black/10 bg-white p-5 shadow-[var(--shadow-card)] sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold text-ink">Panel de control</h2>
        </div>
        <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Filtrar por estado">
          {chips.map((c) => {
            const active = statusFilter === c.id
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onStatusFilter(c.id)}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wide transition ${
                  active
                    ? 'border-primary bg-primary text-white shadow-sm'
                    : 'border-black/12 bg-white text-muted hover:border-black/20 hover:text-ink'
                }`}
              >
                {c.label}
                <span className={`ml-1.5 tabular-nums ${active ? 'text-white/90' : 'text-muted'}`}>
                  ({c.count})
                </span>
              </button>
            )
          })}
        </div>

        <div className="mt-6 space-y-3" data-tour="projects-board">
          {loadingList ? (
            <p className="rounded-lg border border-black/8 bg-black/[0.02] px-4 py-8 text-center text-sm text-muted">
              Cargando proyectos…
            </p>
          ) : null}
          {!loadingList && projects.length === 0 ? (
            <p className="rounded-lg border border-dashed border-black/15 bg-black/[0.02] px-4 py-10 text-center text-sm text-muted">
              Todavía no hay proyectos en tu cuenta.
            </p>
          ) : null}
          {!loadingList && projects.length > 0 && displayProjects.length === 0 ? (
            <p className="rounded-lg border border-black/8 px-4 py-8 text-center text-sm text-muted">
              {projectSearch.trim()
                ? `Ningún resultado para «${projectSearch.trim()}» con este filtro.`
                : 'Ningún proyecto con este filtro.'}
            </p>
          ) : null}
          {!loadingList &&
            displayProjects.map((p) => {
              const Icon = projectCardIcon(p.project_kind)
              const bucket = projectDashboardBucket(p.workflow_phase)
              const pct = workflowPhaseProgressPct(p.workflow_phase)
              const phaseLabel =
                p.current_step_title?.trim() ||
                WORKFLOW_PHASE_LABELS[p.workflow_phase] ||
                p.workflow_phase
              return (
                <div
                  key={p.uuid}
                  role="button"
                  tabIndex={0}
                  className="relative flex cursor-pointer flex-wrap items-stretch gap-4 rounded-xl border border-black/10 bg-white p-4 shadow-sm transition hover:border-primary/25 hover:bg-primary/[0.02] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary/35 sm:flex-nowrap sm:items-center"
                  onClick={() => onOpenProject(p.uuid)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onOpenProject(p.uuid)
                    }
                  }}
                >
                  <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-primary/[0.08] text-primary">
                    <Icon className="size-6" strokeWidth={1.75} aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink">{p.name}</p>
                    <p className="mt-0.5 text-sm text-muted">{projectSubtitle(p)}</p>
                    <div className="mt-3">
                      <div className="mb-1 flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
                        <span>Progreso</span>
                        <span className="tabular-nums text-ink">{pct}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-black/[0.06]">
                        <div
                          className="h-full rounded-full bg-primary transition-[width] duration-300"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row sm:items-center">
                    <span className="rounded-full border border-primary/20 bg-primary/[0.08] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-primary">
                      {dashboardBucketLabel(bucket)}
                    </span>
                    <span className="hidden max-w-[10rem] truncate text-xs text-muted sm:inline" title={phaseLabel}>
                      {phaseLabel}
                    </span>
                    <div className="relative">
                      <button
                        type="button"
                        className="rounded-md p-2 text-muted outline-none transition hover:bg-black/5 hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30"
                        aria-label={`Más acciones — ${p.name}`}
                        aria-expanded={menuUuid === p.uuid}
                        onClick={(e) => {
                          e.stopPropagation()
                          setMenuUuid((id) => (id === p.uuid ? null : p.uuid))
                        }}
                      >
                        <MoreVertical className="size-5" strokeWidth={2} aria-hidden />
                      </button>
                      {menuUuid === p.uuid ? (
                        <div
                          className="absolute right-0 top-full z-20 mt-1 w-44 rounded-lg border border-black/10 bg-white py-1 shadow-lg"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            className="flex w-full px-3 py-2 text-left text-sm text-ink hover:bg-black/[0.04]"
                            onClick={() => {
                              setMenuUuid(null)
                              onOpenProject(p.uuid)
                            }}
                          >
                            Abrir obra
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              )
            })}
        </div>
      </section>

      <div className="grid min-h-0 gap-6 lg:grid-cols-2">
        <section className="flex min-h-[220px] flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)]">
          <h3 className="border-b border-black/8 px-5 py-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Ubicación de proyectos activos
          </h3>
          <div className="relative min-h-[200px] flex-1 bg-linear-to-br from-black/[0.04] via-primary/[0.06] to-black/[0.05]">
            <div
              className="absolute inset-0 opacity-[0.35]"
              style={{
                backgroundImage: `radial-gradient(circle at 20% 30%, rgba(193,13,18,0.12) 0%, transparent 40%),
                  radial-gradient(circle at 75% 60%, rgba(193,13,18,0.1) 0%, transparent 35%),
                  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Ccircle cx='8' cy='10' r='1.2' fill='%23c10d12' opacity='0.25'/%3E%3Ccircle cx='40' cy='35' r='1.2' fill='%23c10d12' opacity='0.2'/%3E%3Ccircle cx='22' cy='48' r='1.2' fill='%23c10d12' opacity='0.22'/%3E%3C/svg%3E")`,
              }}
              aria-hidden
            />
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <div className="flex max-w-xs flex-col items-center gap-3 rounded-xl border border-primary/20 bg-white/95 px-6 py-5 text-center shadow-md backdrop-blur-sm">
                <MapPin className="size-8 text-primary" strokeWidth={1.75} aria-hidden />
                <p className="text-sm font-semibold uppercase tracking-wide text-primary">
                  {activeOnMap} {activeOnMap === 1 ? 'proyecto activo' : 'proyectos activos'}
                </p>
                <p className="text-xs leading-relaxed text-muted">
                  Vista geográfica próximamente. Mientras tanto, abre cada obra para ver ubicación y datos.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="flex min-h-[220px] flex-col rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)]">
          <h3 className="border-b border-black/8 px-5 py-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Alertas recientes
          </h3>
          <ul className="min-h-0 flex-1 divide-y divide-black/8 overflow-y-auto p-2">
            {notifs.length === 0 ? (
              <li className="px-3 py-8 text-center text-sm text-muted">No hay alertas para mostrar.</li>
            ) : (
              notifs.map((n) => (
                <li key={n.uuid} className="flex gap-3 px-3 py-3">
                  <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    {n.read_at ? (
                      <CircleCheck className="size-4" strokeWidth={2} aria-hidden />
                    ) : (
                      <AlertTriangle className="size-4" strokeWidth={2} aria-hidden />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm font-medium leading-snug ${n.read_at ? 'text-muted' : 'text-ink'}`}>
                      {n.title}
                    </p>
                    {n.body ? (
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">{n.body}</p>
                    ) : null}
                    {n.project_uuid ? (
                      <Link
                        className="du-link mt-2 inline-block text-xs font-semibold"
                        to={`/app/projects/${n.project_uuid}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Ir al proyecto
                      </Link>
                    ) : null}
                  </div>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}
