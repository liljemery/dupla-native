import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { apiFetch } from '../../../api/client'
import { hasElevatedAccess, canMarkControlReview, canViewBudget, isBudgetWorkflowPhase, workflowPhaseLabelForRole } from '../../../lib/accessPermissions'
import { bootstrapRequiredPercent } from '../../../lib/bootstrapCriteria'
import { useAuthStore } from '../../../store/authStore'
import { WORKFLOW_DOC_PHASE_HINTS } from '../../../constants/workflowDocMapping'
import { downloadBlob, filenameFromContentDisposition } from '../../../lib/download'
import type { SubcontractQuoteRow } from '../../../types/projectWorkspace'
import type { BootstrapCriterion, Project } from '../../../types/project'
import { BootstrapChecklistCard } from '../BootstrapChecklistCard'
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
  bootstrapDraft: BootstrapCriterion[]
  setBootstrapDraft: React.Dispatch<React.SetStateAction<BootstrapCriterion[]>>
  nextPhase: string | undefined
  role: string | null
  onSaveBootstrap: () => boolean | void | Promise<boolean | void>
  onAdvancePhase: () => boolean | void | Promise<boolean | void>
  pliegoApproved: boolean
  canApprovePliego: boolean
  onApprovePliego: () => boolean | void | Promise<boolean | void>
  onOpenPliego: () => void
  bpDraft: Record<string, unknown>
  setBpDraft: React.Dispatch<React.SetStateAction<Record<string, unknown>>>
  clientVersion: string
  setClientVersion: React.Dispatch<React.SetStateAction<string>>
  onSaveBudgetPipeline: () => boolean | void | Promise<boolean | void>
  newQuoteTitle: string
  setNewQuoteTitle: React.Dispatch<React.SetStateAction<string>>
  activeQuote: string
  setActiveQuote: React.Dispatch<React.SetStateAction<string>>
  lineItem: string
  setLineItem: React.Dispatch<React.SetStateAction<string>>
  linePrice: string
  setLinePrice: React.Dispatch<React.SetStateAction<string>>
  quotes: SubcontractQuoteRow[]
  onLoadAuxLists: () => Promise<void>
}

export function WorkspaceFlujoTab({
  project,
  projectUuid,
  token,
  phaseLabel,
  templateStepProgress,
  orderedTemplateSteps,
  flowMsg,
  bootstrapDraft,
  setBootstrapDraft,
  nextPhase,
  role,
  onSaveBootstrap,
  onAdvancePhase,
  pliegoApproved,
  canApprovePliego,
  onApprovePliego,
  onOpenPliego,
  bpDraft,
  setBpDraft,
  clientVersion,
  setClientVersion,
  onSaveBudgetPipeline,
  newQuoteTitle,
  setNewQuoteTitle,
  activeQuote,
  setActiveQuote,
  lineItem,
  setLineItem,
  linePrice,
  setLinePrice,
  quotes,
  onLoadAuxLists,
}: WorkspaceFlujoTabProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [fileTotal, setFileTotal] = useState<number | null>(null)
  const [docBusy, setDocBusy] = useState(false)

  const showPliegoApproveCta =
    project?.workflow_phase === 'SPECIFICATIONS' &&
    nextPhase === 'BUDGETING_PIPELINE' &&
    canApprovePliego &&
    !pliegoApproved
  const bootstrapStats = useMemo(() => bootstrapRequiredPercent(bootstrapDraft), [bootstrapDraft])
  const showBootstrapProminent =
    project?.workflow_phase === 'BOOTSTRAPPING' ||
    (bootstrapStats.required > 0 && bootstrapStats.done < bootstrapStats.required)

  useEffect(() => {
    if (searchParams.get('focus') !== 'bootstrap') return
    const el = document.getElementById('bootstrap-checklist')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('focus')
        return next
      },
      { replace: true },
    )
  }, [searchParams, setSearchParams])
  const roleTyped = role as import('../../../constants/userRoles').UserRole | null
  const viewBudget = canViewBudget(roleTyped)
  const docHintRaw = project ? WORKFLOW_DOC_PHASE_HINTS[project.workflow_phase] : undefined
  const docHint =
    viewBudget && docHintRaw && !isBudgetWorkflowPhase(project?.workflow_phase ?? '') ? docHintRaw : null
  const showBudgetPanel =
    viewBudget &&
    !!project &&
    ['BUDGETING_PIPELINE', 'MANAGEMENT_APPROVAL', 'BUDGET_APPROVED', 'COMPLETE'].includes(project.workflow_phase)
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role as import('../../../constants/userRoles').UserRole | null, isTeamLeader)
  const canMarkControl = canMarkControlReview(role as import('../../../constants/userRoles').UserRole | null, isTeamLeader)
  const awaitingBudgetApproval = project?.workflow_phase === 'MANAGEMENT_APPROVAL'
  const missingControlGate = awaitingBudgetApproval && !bpDraft.control_review_done
  const missingClientVersion = awaitingBudgetApproval && !clientVersion.trim()

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
    <div className="flex w-full flex-col gap-4">
      <BootstrapChecklistCard
        criteria={bootstrapDraft}
        onChange={setBootstrapDraft}
        onSave={onSaveBootstrap}
        prominent={showBootstrapProminent}
      />

      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold text-ink">Flujo de trabajo</h2>
        <>
          <WorkflowPhaseStepper
            workflowPhase={project.workflow_phase}
            templateStepProgress={templateStepProgress}
            stepTitle={phaseLabel}
            templateSteps={orderedTemplateSteps}
            currentWorkflowStepUuid={project.current_workflow_step_uuid}
            viewBudget={viewBudget}
            role={roleTyped}
          />
          {docHint ? (
            <p className="rounded-md border border-black/10 bg-black/[0.02] px-3 py-2 text-xs text-muted">{docHint}</p>
          ) : null}

          <div className="rounded-md border border-black/10 bg-black/[0.02] p-4">
            <p className="text-sm font-medium text-ink">Documentación y archivos</p>
            <p className="mt-1 text-sm text-muted">
              Archivos en el proyecto:{' '}
              <strong className="text-ink">{fileTotal != null ? fileTotal : '…'}</strong>
            </p>
            <WorkspacePillActionButton
              type="button"
              disabled={docBusy || !token}
              className="mt-3 border-primary/30 bg-primary/[0.06] text-sm font-semibold text-primary"
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

          <p className="rounded-md border border-black/10 bg-black/[0.02] px-3 py-2 text-sm text-muted">
            Fase actual: <span className="font-semibold text-ink">{phaseLabel}</span>. Avanza solo cuando el trabajo de
            esta etapa esté hecho; si el botón falla, el mensaje de arriba indica el motivo.
          </p>
          {flowMsg ? <p className="text-sm text-primary">{flowMsg}</p> : null}
          {showPliegoApproveCta ? (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-primary/25 bg-primary/[0.06] px-3 py-2.5">
              <p className="min-w-0 flex-1 text-sm text-ink">
                Aprueba el pliego de condiciones (GA-FO-01) para poder avanzar al presupuesto.
              </p>
              <button
                type="button"
                className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm hover:bg-black/[0.03]"
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
              Avanzar a: {workflowPhaseLabelForRole(nextPhase, roleTyped)}
            </WorkspaceActionButton>
          ) : (
            <p className="text-sm text-muted">El proyecto completó el flujo definido.</p>
          )}
          {nextPhase === 'BUDGET_APPROVED' && viewBudget && !elevated ? (
            <p className="text-sm text-primary">
              Solo Gerencia o Líder de equipo puede marcar la aprobación final del presupuesto.
            </p>
          ) : null}

          {showBudgetPanel ? (
            <div className="space-y-6 border-t border-black/10 pt-6">
              <Card className="space-y-4 p-6">
                <h3 className="text-base font-semibold text-ink">Pipeline de presupuesto</h3>
                <p className="text-sm text-muted">
                  Hitos y revisión de Control se registran aquí antes de avanzar a «Presupuesto aprobado por cliente».
                </p>
                {awaitingBudgetApproval && (missingControlGate || missingClientVersion) ? (
                  <div className="rounded-md border border-primary/25 bg-primary/[0.06] px-3 py-2 text-sm text-ink">
                    Para avanzar: marca la revisión de Control y la etiqueta de versión aprobada por el cliente (guarda
                    abajo).{' '}
                    {missingControlGate ? <span className="font-medium text-primary">Falta revisión de Control.</span> : null}{' '}
                    {missingClientVersion ? (
                      <span className="font-medium text-primary">Falta versión del cliente.</span>
                    ) : null}
                  </div>
                ) : null}
                <div className="space-y-3 border-t border-black/10 pt-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">Hitos del pipeline</p>
                  {(
                    [
                      ['subcontracts_done', 'Cotizaciones de subcontratación listas'],
                      ['volumetry_done', 'Volumetría completada'],
                      ['cost_analysis_done', 'Análisis de costo completado'],
                      ['budget_marked_complete', 'Presupuesto interno completado'],
                    ] as const
                  ).map(([key, label]) => {
                    const isVolumetry = key === 'volumetry_done'
                    const volumetryLocked = isVolumetry && role !== 'GERENCIA'
                    return (
                    <label key={key} className={`flex items-center gap-2 text-sm ${volumetryLocked ? 'opacity-80' : ''}`}>
                      <input
                        type="checkbox"
                        checked={!!bpDraft[key]}
                        disabled={volumetryLocked}
                        title={
                          volumetryLocked
                            ? 'Se marca automáticamente al completar presupuesto maestro con partidas'
                            : undefined
                        }
                        onChange={(e) => setBpDraft((d) => ({ ...d, [key]: e.target.checked }))}
                      />
                      {label}
                      {volumetryLocked ? (
                        <span className="text-xs text-muted">(automático)</span>
                      ) : null}
                    </label>
                    )
                  })}
                </div>
                <div className="space-y-2 border-l-2 border-primary/35 pl-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">Control</p>
                  <label className={`flex items-center gap-2 text-sm ${!canMarkControl ? 'opacity-60' : ''}`}>
                    <input
                      type="checkbox"
                      disabled={!canMarkControl}
                      checked={!!bpDraft.control_review_done}
                      onChange={(e) => setBpDraft((d) => ({ ...d, control_review_done: e.target.checked }))}
                    />
                    Revisión de Control completada
                    {!canMarkControl ? (
                      <span className="text-xs text-muted">(solo Control o Gerencia)</span>
                    ) : null}
                  </label>
                </div>
                <div className="space-y-2 border-t border-black/10 pt-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">Cliente</p>
                  <label className="block text-sm text-muted">
                    Etiqueta de versión aprobada por el cliente
                    <input
                      className="du-input mt-1"
                      value={clientVersion}
                      onChange={(e) => setClientVersion(e.target.value)}
                      placeholder="ej. v2"
                    />
                  </label>
                </div>
                <WorkspaceActionButton type="button" onAction={onSaveBudgetPipeline} successLabel="Pipeline guardado">
                  Guardar estado del pipeline
                </WorkspaceActionButton>
              </Card>
              <Card className="space-y-4 p-6">
                <h3 className="text-base font-semibold text-ink">Cotizaciones</h3>
                <div className="flex flex-wrap gap-2">
                  <input
                    className="du-input min-w-[160px] flex-1"
                    placeholder="Título de cotización"
                    value={newQuoteTitle}
                    onChange={(e) => setNewQuoteTitle(e.target.value)}
                  />
                  <WorkspaceActionButton
                    type="button"
                    onAction={async () => {
                      if (!token) return false
                      const res = await apiFetch(`/api/projects/${projectUuid}/subcontracts`, {
                        method: 'POST',
                        token,
                        body: JSON.stringify({ title: newQuoteTitle.trim() || null }),
                      })
                      if (!res.ok) return false
                      setNewQuoteTitle('')
                      await onLoadAuxLists()
                      return true
                    }}
                    successLabel="Cotización creada"
                  >
                    Nueva cotización
                  </WorkspaceActionButton>
                </div>
                <label className="block text-sm text-muted">
                  Cotización activa para líneas
                  <select className="du-input mt-1" value={activeQuote} onChange={(e) => setActiveQuote(e.target.value)}>
                    <option value="">—</option>
                    {quotes.map((q) => (
                      <option key={q.uuid} value={q.uuid}>
                        {q.title ?? q.uuid.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex flex-wrap gap-2">
                  <input
                    className="du-input min-w-[120px] flex-1"
                    placeholder="Ítem"
                    value={lineItem}
                    onChange={(e) => setLineItem(e.target.value)}
                  />
                  <input
                    className="du-input w-28"
                    placeholder="Precio"
                    type="number"
                    value={linePrice}
                    onChange={(e) => setLinePrice(e.target.value)}
                  />
                  <WorkspaceActionButton
                    type="button"
                    disabled={!activeQuote}
                    onAction={async () => {
                      if (!token || !activeQuote) return false
                      const res = await apiFetch(`/api/projects/${projectUuid}/subcontracts/${activeQuote}/lines`, {
                        method: 'POST',
                        token,
                        body: JSON.stringify({
                          item_label: lineItem.trim(),
                          price: Number(linePrice),
                          currency: 'MXN',
                        }),
                      })
                      if (!res.ok) return false
                      setLineItem('')
                      setLinePrice('')
                      await onLoadAuxLists()
                      return true
                    }}
                    successLabel="Línea agregada"
                  >
                    Agregar línea
                  </WorkspaceActionButton>
                </div>
                {quotes.map((q) => (
                  <div key={q.uuid} className="rounded border border-black/5 p-3 text-sm">
                    <div className="font-medium">{q.title ?? 'Sin título'}</div>
                    <ul className="mt-2 list-disc pl-5 text-muted">
                      {q.lines.map((l) => (
                        <li key={l.uuid}>
                          {l.item_label} — {l.price} {l.currency}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </Card>
            </div>
          ) : null}
        </>
      </Card>
    </div>
  )
}
