import { useEffect, useState } from 'react'

import { apiFetch } from '../../../api/client'
import { hasElevatedAccess, canViewBudget, isBudgetWorkflowPhase, workflowPhaseLabelForRole } from '../../../lib/accessPermissions'
import { useAuthStore } from '../../../store/authStore'
import { WORKFLOW_DOC_PHASE_HINTS } from '../../../constants/workflowDocMapping'
import { downloadBlob, filenameFromContentDisposition } from '../../../lib/download'
import type { Project } from '../../../types/project'
import { Card } from '../../Card'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import { WorkspacePillActionButton } from '../WorkspacePillActionButton'
import { WorkflowPhaseStepper, type TemplateStepProgress } from '../WorkflowPhaseStepper'

type WorkspaceFlujoTabProps = {
  project: Project | null
  projectUuid: string
  token: string | null
  phaseLabel: string
  templateStepProgress?: TemplateStepProgress | null
  orderedTemplateSteps?: { uuid: string; title: string }[] | null
  flowMsg: string | null
  nextPhase: string | undefined
  onAdvancePhase: () => boolean | void | Promise<boolean | void>
  pliegoApproved: boolean
  pliegoReadyForApproval: boolean
  canApprovePliego: boolean
  onApprovePliego: () => boolean | void | Promise<boolean | void>
  onOpenPliego: () => void
  onOpenPresupuesto: () => void
}

export function WorkspaceFlujoTab({
  project,
  projectUuid,
  token,
  phaseLabel,
  templateStepProgress,
  orderedTemplateSteps,
  flowMsg,
  nextPhase,
  onAdvancePhase,
  pliegoApproved,
  pliegoReadyForApproval,
  canApprovePliego,
  onApprovePliego,
  onOpenPliego,
  onOpenPresupuesto,
}: WorkspaceFlujoTabProps) {
  const [fileTotal, setFileTotal] = useState<number | null>(null)
  const [docBusy, setDocBusy] = useState(false)

  const showPliegoApproveCta =
    project?.workflow_phase === 'SPECIFICATIONS' &&
    nextPhase === 'BUDGETING_PIPELINE' &&
    canApprovePliego &&
    !pliegoApproved &&
    pliegoReadyForApproval
  const showPliegoPrepareCta =
    project?.workflow_phase === 'SPECIFICATIONS' &&
    nextPhase === 'BUDGETING_PIPELINE' &&
    canApprovePliego &&
    !pliegoApproved &&
    !pliegoReadyForApproval
  const permissions = useAuthStore((s) => s.permissions)
  const viewBudget = canViewBudget(permissions)
  const docHintRaw = project ? WORKFLOW_DOC_PHASE_HINTS[project.workflow_phase] : undefined
  const docHint =
    viewBudget && docHintRaw && !isBudgetWorkflowPhase(project?.workflow_phase ?? '') ? docHintRaw : null
  const showBudgetPipelineHint =
    viewBudget &&
    !!project &&
    ['BUDGETING_PIPELINE', 'MANAGEMENT_APPROVAL', 'BUDGET_APPROVED', 'COMPLETE'].includes(project.workflow_phase)
  const elevated = hasElevatedAccess(permissions)

  useEffect(() => {
    if (!token || !projectUuid) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch(`/api/projects/${projectUuid}/files?limit=1&offset=0`, { token })
      if (!res.ok || cancelled) return
      const body = (await res.json()) as { total: number }
      if (!cancelled) setFileTotal(body.total)
    })()
    return () => {
      cancelled = true
    }
  }, [token, projectUuid])

  if (!project) {
    return (
      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold text-ink">Flujo de trabajo</h2>
        <p className="text-sm text-muted">Cargando…</p>
      </Card>
    )
  }

  return (
    <Card className="space-y-4 p-6">
      <h2 className="text-lg font-semibold text-ink">Flujo de trabajo</h2>
      <WorkflowPhaseStepper
        workflowPhase={project.workflow_phase}
        templateStepProgress={templateStepProgress}
        stepTitle={phaseLabel}
        templateSteps={orderedTemplateSteps}
        currentWorkflowStepUuid={project.current_workflow_step_uuid}
        viewBudget={viewBudget}
        permissions={permissions}
      />
      {docHint ? (
        <p className="rounded-md border border-black/10 bg-black/2 px-3 py-2 text-xs text-muted">{docHint}</p>
      ) : null}

      <div className="rounded-md border border-black/10 bg-black/2 p-4">
        <p className="text-sm font-medium text-ink">Documentación y archivos</p>
        <p className="mt-1 text-sm text-muted">
          Archivos en el proyecto:{' '}
          <strong className="text-ink">{fileTotal != null ? fileTotal : '…'}</strong>
        </p>
        <WorkspacePillActionButton
          type="button"
          disabled={docBusy || !token}
          className="mt-3 border-primary/30 bg-primary/6 text-sm font-semibold text-primary"
          successLabel="PDF generado"
          runningLabel="Generando…"
          onAction={async () => {
            if (!token) return false
            setDocBusy(true)
            try {
              const res = await apiFetch(`/api/projects/${projectUuid}/exports/documentary-report.pdf`, {
                token,
              })
              if (!res.ok) return false
              const blob = await res.blob()
              downloadBlob(
                blob,
                filenameFromContentDisposition(res, `informe-documental-${projectUuid}.pdf`),
              )
              return true
            } finally {
              setDocBusy(false)
            }
          }}
        >
          Descargar informe documental (PDF)
        </WorkspacePillActionButton>
      </div>

      <p className="rounded-md border border-black/10 bg-black/2 px-3 py-2 text-sm text-muted">
        Fase actual: <span className="font-semibold text-ink">{phaseLabel}</span>. Avanza solo cuando el trabajo de
        esta etapa esté hecho; si el botón falla, el mensaje de arriba indica el motivo.
      </p>
      {flowMsg ? <p className="text-sm text-primary">{flowMsg}</p> : null}
      {showPliegoPrepareCta ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-black/15 bg-black/4 px-3 py-2.5">
          <p className="min-w-0 flex-1 text-sm text-ink">
            Genera o completa el pliego en la pestaña Pliego antes de solicitar la aprobación.
          </p>
          <button
            type="button"
            className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/3"
            onClick={onOpenPliego}
          >
            Ir al pliego
          </button>
        </div>
      ) : null}
      {showPliegoApproveCta ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-primary/25 bg-primary/6 px-3 py-2.5">
          <p className="min-w-0 flex-1 text-sm text-ink">
            Aprueba el pliego de condiciones (GA-FO-01) para poder avanzar al presupuesto.
          </p>
          <button
            type="button"
            className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/3"
            onClick={onOpenPliego}
          >
            Ir al pliego
          </button>
          <WorkspaceActionButton
            type="button"
            className="px-3 py-2 text-xs font-semibold normal-case tracking-normal"
            onAction={onApprovePliego}
            successLabel="Pliego aprobado"
            runningLabel="Aprobando…"
          >
            Aprobar pliego
          </WorkspaceActionButton>
        </div>
      ) : null}
      {nextPhase ? (
        <WorkspaceActionButton
          type="button"
          onAction={onAdvancePhase}
          successLabel="Fase actualizada"
          runningLabel="Procesando…"
        >
          Avanzar a: {workflowPhaseLabelForRole(nextPhase, permissions)}
        </WorkspaceActionButton>
      ) : (
        <p className="text-sm text-muted">El proyecto completó el flujo definido.</p>
      )}
      {nextPhase === 'BUDGET_APPROVED' && viewBudget && !elevated ? (
        <p className="text-sm text-primary">
          Solo Gerencia o Líder de equipo puede marcar la aprobación final del presupuesto.
        </p>
      ) : null}

      {showBudgetPipelineHint ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-black/15 bg-black/4 px-3 py-2.5">
          <p className="min-w-0 flex-1 text-sm text-ink">
            Pipeline de presupuesto, cotizaciones e hitos: pestaña Presupuesto.
          </p>
          <button
            type="button"
            className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/3"
            onClick={onOpenPresupuesto}
          >
            Ir a Presupuesto
          </button>
        </div>
      ) : null}
    </Card>
  )
}
