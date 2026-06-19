import { Building2, Factory, HardHat, MoreVertical } from 'lucide-react'

import { projectKindLabel } from '../../constants/projectKind'
import {
  dashboardBucketLabel,
  projectDashboardBucket,
  workflowPhaseProgressPct,
} from '../../lib/projectDashboardBuckets'
import type { Project } from '../../types/project'

function gradientForKind(kind: string): string {
  if (kind === 'TENDER') {
    return 'from-violet-600 via-fuchsia-500 to-orange-300'
  }
  if (kind === 'DEVELOPMENT') {
    return 'from-slate-600 via-slate-500 to-amber-200'
  }
  return 'from-primary via-red-500 to-amber-200'
}

function ProjectKindIcon({ kind }: { kind: string }) {
  if (kind === 'TENDER') {
    return <Factory className="size-3" strokeWidth={2} aria-hidden />
  }
  if (kind === 'DEVELOPMENT') {
    return <HardHat className="size-3" strokeWidth={2} aria-hidden />
  }
  return <Building2 className="size-3" strokeWidth={2} aria-hidden />
}

type ProjectFolderCardProps = {
  project: Project
  menuOpen: boolean
  onOpen: () => void
  onMenuToggle: () => void
}

export function ProjectFolderCard({
  project,
  menuOpen,
  onOpen,
  onMenuToggle,
}: ProjectFolderCardProps) {
  const bucket = projectDashboardBucket(project.workflow_phase)
  const pct = workflowPhaseProgressPct(project.workflow_phase)
  const subtitle =
    project.client_name?.trim() ||
    project.location_text?.trim() ||
    projectKindLabel(project.project_kind)

  return (
    <div
      role="button"
      tabIndex={0}
      className="du-project-folder-card w-full cursor-pointer"
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
    >
      <div
        className={`absolute inset-0 bg-gradient-to-br ${gradientForKind(project.project_kind)}`}
        aria-hidden
      />
      <div
        className="absolute inset-0 bg-[radial-gradient(circle_at_22%_18%,rgba(255,255,255,0.5),transparent_42%),radial-gradient(circle_at_82%_28%,rgba(255,200,100,0.38),transparent_38%)] opacity-90"
        aria-hidden
      />
      <div className="absolute inset-0 backdrop-blur-[1px]" aria-hidden />

      <div className="absolute right-5 top-4 z-10 text-right text-white drop-shadow-sm">
        <p className="text-[10px] font-medium uppercase tracking-wider opacity-80">Dupla</p>
        <p className="text-sm font-bold leading-tight">{projectKindLabel(project.project_kind)}</p>
      </div>

      <div className="du-folder-tab-clip absolute bottom-0 left-0 right-0 h-[56%] bg-black/35 backdrop-blur-3xl">
        <div className="relative h-full pb-4 pr-4">
          <button
            type="button"
            className="absolute right-3 top-3 z-20 rounded-lg p-1.5 text-white/45 outline-none transition-colors duration-200 hover:bg-white/10 hover:text-white"
            aria-label={`Más acciones — ${project.name}`}
            aria-expanded={menuOpen}
            onClick={(e) => {
              e.stopPropagation()
              onMenuToggle()
            }}
          >
            <MoreVertical className="size-4" strokeWidth={2} aria-hidden />
          </button>
          {menuOpen ? (
            <div
              className="absolute right-3 top-10 z-30 w-40 rounded-xl border border-black/10 bg-white py-1 shadow-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                className="flex w-full px-3 py-2 text-left text-sm text-ink hover:bg-black/[0.04]"
                onClick={(e) => {
                  e.stopPropagation()
                  onOpen()
                }}
              >
                Abrir obra
              </button>
            </div>
          ) : null}

          <div className="du-folder-card-heading">
            <h3 className="du-folder-card-title">{project.name}</h3>
            <p className="du-folder-card-subtitle">{subtitle}</p>
            <span className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white/75">
              <ProjectKindIcon kind={project.project_kind} />
              {dashboardBucketLabel(bucket)}
            </span>
          </div>

          <div className="absolute bottom-3.5 left-4 right-4 space-y-1.5">
            <div className="h-1.5 overflow-hidden rounded-full bg-white/20">
              <div
                className="h-full min-w-[0.375rem] rounded-full bg-primary-bright shadow-[0_0_8px_rgba(193,13,18,0.6)] transition-[width] duration-500 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-baseline gap-0.5 text-white">
                <span className="text-lg font-bold tabular-nums leading-none">{pct}</span>
                <span className="text-xs font-medium text-white/45">%</span>
              </div>
              <div className="flex items-baseline gap-1.5 text-[10px]">
                <span className="font-semibold uppercase tracking-wider text-white/35">
                  Progreso
                </span>
                {project.project_code?.trim() ? (
                  <span className="font-mono text-white/60">{project.project_code}</span>
                ) : (
                  <span className="text-white/50">{daysLabel(project.updated_at)}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function daysLabel(updatedAt: string | undefined): string {
  if (!updatedAt) return '—'
  const d = new Date(updatedAt)
  if (Number.isNaN(d.getTime())) return '—'
  const diff = Math.floor((Date.now() - d.getTime()) / (24 * 60 * 60 * 1000))
  if (diff === 0) return 'Hoy'
  if (diff === 1) return '1 día'
  return `${diff} días`
}
