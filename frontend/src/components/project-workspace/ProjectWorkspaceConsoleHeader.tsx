import { ArrowLeft, CircleHelp, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { hasElevatedAccess } from '../../lib/accessPermissions'
import { useAuthStore } from '../../store/authStore'
import { NotificationsBell } from '../NotificationsBell'
import { PrimaryButton } from '../PrimaryButton'
import { IconButton } from '../ui/IconButton'
import { ViewTabs } from '../ui/ViewTabs'
import { ProjectWorkspaceExportMenu } from './ProjectWorkspaceExportMenu'

export type WorkspaceConsoleTabId =
  | 'hub'
  | 'pliego'
  | 'presupuestoMaestro'
  | 'revisiones'
  | 'entregaPlanos'
  | 'eventos'

const CONSOLE_TABS: { id: WorkspaceConsoleTabId; label: string }[] = [
  { id: 'hub', label: 'Resumen' },
  { id: 'pliego', label: 'Pliego' },
  { id: 'presupuestoMaestro', label: 'Presupuesto' },
  { id: 'revisiones', label: 'Revisiones' },
  { id: 'entregaPlanos', label: 'Control de entregas' },
  { id: 'eventos', label: 'Cronología' },
]

type ProjectWorkspaceConsoleHeaderProps = {
  displayTitle: string
  projectUuid: string
  token: string | null
  tab: string
  onSelectTab: (id: WorkspaceConsoleTabId) => void
  onOpenConfig: () => void
  role: string | null
  viewBudget: boolean
  onGoPresupuesto: () => void
  phaseLabel?: string
  clientName?: string | null
  deadline?: string | null
}

function formatDeadline(deadline: string | null | undefined): string {
  if (!deadline?.trim()) return '—'
  const d = new Date(`${deadline.trim()}T12:00:00`)
  if (Number.isNaN(d.getTime())) return deadline
  return d.toLocaleDateString('es', { dateStyle: 'medium' })
}

export function ProjectWorkspaceConsoleHeader({
  displayTitle,
  projectUuid,
  token,
  tab,
  onSelectTab,
  onOpenConfig,
  viewBudget,
  onGoPresupuesto,
  phaseLabel,
  clientName,
  deadline,
}: ProjectWorkspaceConsoleHeaderProps) {
  const permissions = useAuthStore((s) => s.permissions)
  const elevated = hasElevatedAccess(permissions)
  const consoleTabs = CONSOLE_TABS.filter((t) => viewBudget || t.id !== 'presupuestoMaestro')

  const metadataParts = [
    phaseLabel ? `Fase: ${phaseLabel}` : null,
    clientName?.trim() ? `Cliente: ${clientName.trim()}` : null,
    deadline ? `Plazo: ${formatDeadline(deadline)}` : null,
  ].filter(Boolean)

  return (
    <header data-tour="workspace-header" className="shrink-0 space-y-4 border-b border-black/10 pb-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to="/app/projects"
              className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl border border-black/10 bg-white text-muted shadow-sm transition hover:bg-black/3 hover:text-ink"
              aria-label="Volver a proyectos"
            >
              <ArrowLeft className="size-4" strokeWidth={2} aria-hidden />
            </Link>
            <h1 className="du-page-title min-w-0 truncate">{displayTitle}</h1>
          </div>
          {metadataParts.length > 0 ? (
            <p className="mt-2 text-sm text-muted">{metadataParts.join(' · ')}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          {viewBudget && elevated ? (
            <PrimaryButton
              type="button"
              className="hidden rounded-xl px-3 py-2 text-xs font-bold normal-case tracking-normal sm:inline-flex"
              onClick={onGoPresupuesto}
            >
              Ir a presupuesto
            </PrimaryButton>
          ) : null}
          <ProjectWorkspaceExportMenu projectUuid={projectUuid} token={token} />
          <NotificationsBell token={token} />
          <IconButton label="Configuración del proyecto" onClick={onOpenConfig}>
            <Settings className="size-5 shrink-0" strokeWidth={2} aria-hidden />
          </IconButton>
          <Link
            to="/app/tutoriales"
            className="inline-flex size-10 items-center justify-center rounded-xl border border-black/10 bg-white text-muted shadow-sm transition hover:bg-black/3 hover:text-ink"
            title="Ayuda y tutoriales"
            aria-label="Ayuda"
          >
            <CircleHelp className="size-5 shrink-0" strokeWidth={2} aria-hidden />
          </Link>
        </div>
      </div>

      <ViewTabs
        data-tour="workspace-console-tabs"
        ariaLabel="Secciones principales"
        tabs={consoleTabs}
        activeId={tab}
        onChange={(id) => onSelectTab(id as WorkspaceConsoleTabId)}
      />
    </header>
  )
}
