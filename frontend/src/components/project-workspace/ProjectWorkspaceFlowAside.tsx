import { LayoutDashboard, MessageCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

import { hasElevatedAccess } from '../../lib/accessPermissions'
import { useAuthStore } from '../../store/authStore'
import { Card } from '../Card'
import { WORKFLOW_PHASE_LABELS } from '../../constants/workflowPhases'
import { WorkflowPhaseStepper, type TemplateStepProgress } from './WorkflowPhaseStepper'
import { WorkspaceActionButton } from './WorkspaceActionButton'

type ProjectWorkspaceFlowAsideProps = {
  projectUuid: string
  workflowPhase: string
  phaseLabel: string
  templateStepProgress?: TemplateStepProgress | null
  nextPhase: string | undefined
  flowMsg: string | null
  role: string | null
  viewBudget: boolean
  onAdvancePhase: () => boolean | void | Promise<boolean | void>
  onOpenChat: () => void
}

export function ProjectWorkspaceFlowAside({
  projectUuid,
  workflowPhase,
  phaseLabel,
  templateStepProgress,
  nextPhase,
  flowMsg,
  role,
  viewBudget,
  onAdvancePhase,
  onOpenChat,
}: ProjectWorkspaceFlowAsideProps) {
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role as import('../../constants/userRoles').UserRole | null, isTeamLeader)
  return (
    <aside className="flex w-full shrink-0 flex-col gap-2 md:w-52 lg:w-56 xl:w-64">
      <Card className="p-3 md:p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Estado del flujo</h2>
        {workflowPhase ? (
          <div className="mt-2">
            <WorkflowPhaseStepper
              workflowPhase={workflowPhase}
              compact
              templateStepProgress={templateStepProgress}
              stepTitle={phaseLabel}
              viewBudget={viewBudget}
              role={role as import('../../constants/userRoles').UserRole | null}
            />
          </div>
        ) : (
          <p className="mt-2 text-sm font-medium text-ink">{phaseLabel || '—'}</p>
        )}
        {nextPhase ? (
          <WorkspaceActionButton
            type="button"
            className="mt-2 w-full flex-col gap-0.5 px-2.5 py-2 text-xs font-semibold normal-case leading-tight tracking-normal"
            onAction={onAdvancePhase}
            successLabel="Fase actualizada"
            runningLabel="Procesando…"
          >
            <span className="text-[10px] font-medium uppercase tracking-wide text-white/90">Avanzar a</span>
            <span className="text-center text-[11px] font-semibold leading-snug">
              {WORKFLOW_PHASE_LABELS[nextPhase] ?? nextPhase}
            </span>
          </WorkspaceActionButton>
        ) : (
          <p className="du-meta mt-2 text-sm">Última fase alcanzada.</p>
        )}
        {nextPhase === 'BUDGET_APPROVED' && viewBudget && !elevated ? (
          <p className="mt-2 text-xs text-primary">
            Solo Gerencia o Líder de equipo puede cerrar la aprobación final del presupuesto.
          </p>
        ) : null}
        {flowMsg ? <p className="mt-2 text-sm text-primary">{flowMsg}</p> : null}
      </Card>
      <Card className="p-3 md:p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Acciones rápidas</h2>
        <div className="mt-3 flex flex-col gap-2">
          <Link
            className="du-pill-action flex w-full items-center justify-center gap-2 leading-snug no-underline"
            to={`/app/tasks?mine=true&project_uuid=${encodeURIComponent(projectUuid)}`}
          >
            <span className="flex size-4 shrink-0 items-center justify-center [&>svg]:size-4" aria-hidden>
              <LayoutDashboard />
            </span>
            <span className="text-center">Mis tareas</span>
          </Link>
          <button
            type="button"
            className="du-pill-action flex w-full items-center justify-center gap-2 leading-snug"
            onClick={onOpenChat}
          >
            <span className="flex size-4 shrink-0 items-center justify-center [&>svg]:size-4" aria-hidden>
              <MessageCircle />
            </span>
            <span className="text-center">Chat del proyecto</span>
          </button>
        </div>
      </Card>
    </aside>
  )
}
