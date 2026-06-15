import { WORKFLOW_PHASE_ORDER } from '../../constants/workflowPhases'
import { workflowPhaseLabelForRole, workflowStepTitleForRole } from '../../lib/accessPermissions'
import type { UserRole } from '../../constants/userRoles'

export type TemplateStepProgress = {
  /** 1-based índice del paso actual en la plantilla */
  current: number
  total: number
}

function phaseStepIndex(phase: string): number {
  if (phase === 'FILES_INGESTED') {
    const i = WORKFLOW_PHASE_ORDER.indexOf('AWAITING_FILES')
    return i >= 0 ? i : 0
  }
  const i = WORKFLOW_PHASE_ORDER.indexOf(phase as (typeof WORKFLOW_PHASE_ORDER)[number])
  return i >= 0 ? i : 0
}

function isLegacyWorkflowPhase(phase: string): boolean {
  if (phase === 'FILES_INGESTED') return true
  return (WORKFLOW_PHASE_ORDER as readonly string[]).includes(phase)
}

type WorkflowPhaseStepperProps = {
  workflowPhase: string
  compact?: boolean
  templateStepProgress?: TemplateStepProgress | null
  stepTitle?: string | null
  templateSteps?: { uuid: string; title: string }[] | null
  currentWorkflowStepUuid?: string | null
  viewBudget?: boolean
  role?: UserRole | null
}

export function WorkflowPhaseStepper({
  workflowPhase,
  compact,
  templateStepProgress,
  stepTitle,
  templateSteps,
  currentWorkflowStepUuid,
  viewBudget = true,
  role = null,
}: WorkflowPhaseStepperProps) {
  const totalLegacy = WORKFLOW_PHASE_ORDER.length
  const activeLegacyIdx = phaseStepIndex(workflowPhase)
  const phaseFallbackLabel = workflowPhaseLabelForRole(workflowPhase, role)
  const titleLine = stepTitle?.trim()
    ? workflowStepTitleForRole(stepTitle.trim(), role)
    : phaseFallbackLabel

  if (compact) {
    if (templateStepProgress && templateStepProgress.total > 0) {
      return (
        <div
          data-tour="workspace-flujo-stepper"
          className="rounded-md border border-black/10 bg-black/[0.02] px-2 py-1.5 text-xs text-ink"
        >
          <span className="font-semibold tabular-nums">
            Paso {templateStepProgress.current} / {templateStepProgress.total}
          </span>
          <span className="mt-0.5 block truncate text-[11px] font-medium leading-tight text-muted">{titleLine}</span>
        </div>
      )
    }

    if (!isLegacyWorkflowPhase(workflowPhase)) {
      return (
        <div
          data-tour="workspace-flujo-stepper"
          className="rounded-md border border-black/10 bg-black/[0.02] px-2 py-1.5 text-xs text-ink"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">Paso actual</span>
          <span className="mt-0.5 block truncate text-[11px] font-medium leading-tight text-ink">{titleLine}</span>
        </div>
      )
    }

    return (
      <div
        data-tour="workspace-flujo-stepper"
        className="rounded-md border border-black/10 bg-black/[0.02] px-2 py-1.5 text-xs text-ink"
      >
        <span className="font-semibold tabular-nums">
          Fase {activeLegacyIdx + 1} / {totalLegacy}
        </span>
        <span className="mt-0.5 block truncate text-[11px] font-medium leading-tight text-muted">{titleLine}</span>
      </div>
    )
  }

  /** Debe venir ordenado por `sort_index` de la plantilla (lo prepara el padre). */
  const stepsForStrip =
    templateSteps?.length && currentWorkflowStepUuid ? templateSteps : []

  if (stepsForStrip.length > 0 && currentWorkflowStepUuid) {
    const activeTi = stepsForStrip.findIndex((s) => s.uuid === currentWorkflowStepUuid)
    const activeIdx = activeTi >= 0 ? activeTi : 0
    return (
      <div data-tour="workspace-flujo-stepper" className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Progreso en la plantilla</p>
        <div className="-mx-1 overflow-x-auto pb-1">
          <div className="flex min-w-max items-start px-1">
            {stepsForStrip.map((s, i) => {
              const isDone = i < activeIdx
              const isActive = i === activeIdx
              const stepLabel = workflowStepTitleForRole(s.title.trim() || `Paso ${i + 1}`, role)
              return (
                <div key={s.uuid} className="flex items-start">
                  {i > 0 ? (
                    <div
                      className={`mt-[13px] h-0.5 w-3 shrink-0 sm:w-5 ${isDone || isActive ? 'bg-primary/55' : 'bg-black/12'}`}
                      aria-hidden
                    />
                  ) : null}
                  <div className="flex w-[4.25rem] flex-col items-center gap-1 sm:w-[5.25rem]">
                    <span
                      className={`flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums ${
                        isActive
                          ? 'bg-primary text-white ring-2 ring-primary/30'
                          : isDone
                            ? 'bg-primary/85 text-white'
                            : 'border border-black/15 bg-white text-muted'
                      }`}
                    >
                      {i + 1}
                    </span>
                    <span
                      className={`w-full text-center text-[9px] font-medium leading-tight sm:text-[10px] ${
                        isActive ? 'text-ink' : 'text-muted'
                      }`}
                      title={stepLabel}
                    >
                      {stepLabel}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
        <p className="text-sm font-medium text-ink">
          Actual: <span className="text-primary">{titleLine}</span>
        </p>
      </div>
    )
  }

  if (!isLegacyWorkflowPhase(workflowPhase)) {
    return (
      <div data-tour="workspace-flujo-stepper" className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Estado del flujo</p>
        <p className="text-sm font-medium text-ink">
          Paso actual: <span className="text-primary">{titleLine}</span>
        </p>
      </div>
    )
  }

  if (!viewBudget) {
    return (
      <div data-tour="workspace-flujo-stepper" className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Estado del flujo</p>
        <p className="text-sm font-medium text-ink">
          Paso actual: <span className="text-primary">{titleLine}</span>
        </p>
      </div>
    )
  }

  return (
    <div data-tour="workspace-flujo-stepper" className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Progreso por fase (ISO)</p>
      <div className="-mx-1 overflow-x-auto pb-1">
        <div className="flex min-w-max items-start px-1">
          {WORKFLOW_PHASE_ORDER.map((key, i) => {
            const isDone = i < activeLegacyIdx
            const isActive = i === activeLegacyIdx
            const stepLabel = workflowPhaseLabelForRole(key, role)
            return (
              <div key={key} className="flex items-start">
                {i > 0 ? (
                  <div
                    className={`mt-[13px] h-0.5 w-3 shrink-0 sm:w-5 ${isDone || isActive ? 'bg-primary/55' : 'bg-black/12'}`}
                    aria-hidden
                  />
                ) : null}
                <div className="flex w-[4.25rem] flex-col items-center gap-1 sm:w-[5.25rem]">
                  <span
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums ${
                      isActive
                        ? 'bg-primary text-white ring-2 ring-primary/30'
                        : isDone
                          ? 'bg-primary/85 text-white'
                          : 'border border-black/15 bg-white text-muted'
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span
                    className={`w-full text-center text-[9px] font-medium leading-tight sm:text-[10px] ${
                      isActive ? 'text-ink' : 'text-muted'
                    }`}
                    title={stepLabel}
                  >
                    {stepLabel}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <p className="text-sm font-medium text-ink">
        Actual: <span className="text-primary">{titleLine}</span>
      </p>
    </div>
  )
}
