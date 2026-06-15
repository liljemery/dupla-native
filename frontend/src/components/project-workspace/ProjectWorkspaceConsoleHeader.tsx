import { CircleHelp, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { hasElevatedAccess } from '../../lib/accessPermissions'
import { useAuthStore } from '../../store/authStore'
import { NotificationsBell } from '../NotificationsBell'
import { PrimaryButton } from '../PrimaryButton'
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
  userInitials: string
  userEmail: string | null
  role: string | null
  viewBudget: boolean
  onGoPresupuesto: () => void
}

export function ProjectWorkspaceConsoleHeader({
  displayTitle,
  projectUuid,
  token,
  tab,
  onSelectTab,
  onOpenConfig,
  userInitials,
  userEmail,
  role,
  viewBudget,
  onGoPresupuesto,
}: ProjectWorkspaceConsoleHeaderProps) {
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role as import('../../constants/userRoles').UserRole | null, isTeamLeader)
  const consoleTabs = CONSOLE_TABS.filter((t) => viewBudget || t.id !== 'presupuestoMaestro')
  return (
    <header data-tour="workspace-header" className="shrink-0 space-y-3 border-b border-black/10 pb-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold text-ink">Consola del proyecto</span>
          <span className="hidden text-muted sm:inline" aria-hidden>
            |
          </span>
          <nav
            data-tour="workspace-console-tabs"
            className="flex flex-wrap gap-1"
            aria-label="Secciones principales"
          >
            {consoleTabs.map((t) => {
              const active = tab === t.id
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onSelectTab(t.id)}
                  className={`rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${
                    active
                      ? 'bg-primary/12 text-primary ring-1 ring-primary/25'
                      : 'text-muted hover:bg-black/[0.04] hover:text-ink'
                  }`}
                >
                  {t.label}
                </button>
              )
            })}
          </nav>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          {viewBudget && elevated ? (
            <PrimaryButton
              type="button"
              className="hidden px-3 py-2 text-xs font-bold normal-case tracking-normal sm:inline-flex"
              onClick={onGoPresupuesto}
            >
              Ir a presupuesto
            </PrimaryButton>
          ) : null}
          <ProjectWorkspaceExportMenu projectUuid={projectUuid} token={token} />
          <NotificationsBell token={token} />
          <button
            type="button"
            className="rounded-lg border border-black/10 bg-white p-2 text-ink shadow-sm transition-colors hover:bg-black/[0.03]"
            aria-label="Configuración del proyecto"
            onClick={onOpenConfig}
          >
            <Settings className="size-5 shrink-0" strokeWidth={2} aria-hidden />
          </button>
          <Link
            to="/app/tutoriales"
            className="rounded-lg border border-black/10 bg-white p-2 text-muted shadow-sm transition-colors hover:bg-black/[0.03] hover:text-ink"
            title="Ayuda y tutoriales"
            aria-label="Ayuda"
          >
            <CircleHelp className="size-5 shrink-0" strokeWidth={2} aria-hidden />
          </Link>
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold uppercase text-white shadow-sm ring-2 ring-white"
            title={userEmail ?? ''}
          >
            {userInitials}
          </div>
        </div>
      </div>

      <nav className="text-sm text-muted" aria-label="Migas de pan">
        <Link className="font-medium text-primary underline-offset-2 hover:underline" to="/app/projects">
          Proyectos
        </Link>
        <span className="mx-2 text-black/25" aria-hidden>
          ›
        </span>
        <span className="font-semibold text-ink">{displayTitle}</span>
      </nav>
    </header>
  )
}
