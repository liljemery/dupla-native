import { AlertCircle, Cpu, Loader2, Pencil, Play, RefreshCw } from 'lucide-react'
import { useMemo, useEffect, useState, type ReactNode } from 'react'

import { useBudgetJob } from '../../../hooks/useBudgetJob'
import type { BudgetRow } from '../../../types/budget'
import type { Project } from '../../../types/project'
import type { SubcontractQuoteRow } from '../../../types/projectWorkspace'
import { processBudgetRows } from '../../../lib/budgetRows'
import { fmtDop } from '../../../lib/budgetFormat'
import { showBudgetPipelinePanel } from '../../../lib/budgetPipelineUi'
import { PrimaryButton } from '../../PrimaryButton'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import {
  BudgetChecklistPanel,
  BudgetQuotesPanel,
} from '../BudgetPipelinePanel'
import { BudgetSectionSwitch, type BudgetSectionId } from '../BudgetSectionSwitch'
import { WorkspacePriceDatabaseTab } from './WorkspacePriceDatabaseTab'
import { BudgetEditableTable } from '../BudgetEditableTable'

const BUDGET_PHASE_LABELS: Record<string, string> = {
  extraction: 'Extrayendo planos y volumetría…',
  vision: 'Analizando planos con IA…',
  budget: 'Generando presupuesto…',
}

function budgetPhaseMessage(job: { phase?: string | null; phase_detail?: string | null }): string {
  if (job.phase_detail?.trim()) return job.phase_detail.trim()
  if (job.phase && BUDGET_PHASE_LABELS[job.phase]) return BUDGET_PHASE_LABELS[job.phase]
  return 'Analizando planos DWG, extrayendo volumetrías y generando presupuesto.'
}

const LIQUIDACION_RATES = {
  seguroPct: 1.5,
  gastosAdminPct: 8,
  transportePct: 2,
  direccionTecnicaPct: 5,
  itbisPct: 18,
}

function computeLiquidacion(direct: number) {
  const { seguroPct, gastosAdminPct, transportePct, direccionTecnicaPct, itbisPct } = LIQUIDACION_RATES
  const seguro = direct * (seguroPct / 100)
  const gastosAdmin = direct * (gastosAdminPct / 100)
  const transporte = direct * (transportePct / 100)
  const direccion = direct * (direccionTecnicaPct / 100)
  const subAntesItbis = direct + seguro + gastosAdmin + transporte + direccion
  const itbis = subAntesItbis * (itbisPct / 100)
  return { seguro, gastosAdmin, transporte, direccion, subAntesItbis, itbis, total: subAntesItbis + itbis }
}


interface EnqueueModalProps {
  onSubmit: (opts: { discipline?: string }) => Promise<boolean>
  onClose: () => void
}

const DISCIPLINES = [
  { value: 'todas', label: 'Todas las disciplinas' },
  { value: 'arquitectura', label: 'Arquitectura' },
  { value: 'estructura', label: 'Estructura' },
  { value: 'electrico', label: 'Electrica' },
  { value: 'sanitario', label: 'Sanitaria' },
]

function EnqueueModal({ onSubmit, onClose }: EnqueueModalProps) {
  const [discipline, setDiscipline] = useState('todas')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-black/10 bg-white p-6 shadow-2xl">
        <h2 className="text-base font-bold text-ink">Iniciar presupuesto con IA</h2>
        <p className="mt-1 text-sm text-muted">
          Se procesarán todos los archivos del proyecto automáticamente.
        </p>

        <div className="mt-5 space-y-4">
          <label className="block space-y-1">
            <span className="text-xs font-bold uppercase tracking-wide text-muted">Disciplina</span>
            <select
              id="enqueue-discipline-select"
              className="du-input w-full py-2 text-sm"
              value={discipline}
              onChange={(e) => setDiscipline(e.target.value)}
            >
              {DISCIPLINES.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            id="enqueue-modal-cancel"
            className="rounded-lg border border-black/15 px-4 py-2 text-sm font-semibold text-muted hover:bg-black/5"
            onClick={onClose}
          >
            Cancelar
          </button>
          <WorkspaceActionButton
            type="button"
            id="enqueue-modal-submit"
            onAction={async () => onSubmit({ discipline })}
            successLabel="Proceso iniciado"
            errorLabel="No se pudo iniciar"
          >
            Procesar
          </WorkspaceActionButton>
        </div>
      </div>
    </div>
  )
}

// ─── Elapsed timer ────────────────────────────────────────────────────────────
function useElapsedSeconds(startIso: string | undefined): number {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startIso) return
    const start = new Date(startIso).getTime()
    const update = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [startIso])

  return startIso ? elapsed : 0
}

// ─── Main component ───────────────────────────────────────────────────────────
type Props = {
  project: Project | null
  projectUuid: string
  token: string | null
  role: string | null
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
  section: BudgetSectionId
  onSectionChange: (section: BudgetSectionId) => void
  flowMsg: string | null
  gerenciaReviewDone: boolean
}

export function WorkspacePresupuestoMaestroTab({
  project,
  projectUuid,
  token,
  role,
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
  section,
  onSectionChange,
  flowMsg,
  gerenciaReviewDone,
}: Props) {
  const { job, result, isPolling, error, enqueue, refresh, saveRows } = useBudgetJob(
    projectUuid,
    token,
  )
  const syncedRows = useMemo(
    () => result?.rows?.map((r) => ({ ...r })) ?? [],
    [result?.rows],
  )
  const [editRows, setEditRows] = useState<BudgetRow[] | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const isEditing = editRows !== null
  const draftRows = isEditing ? editRows : syncedRows
  const elapsed = useElapsedSeconds(
    job?.status === 'queued' || job?.status === 'processing' ? job.created_at : undefined,
  )

  const processedRows = useMemo(() => processBudgetRows(draftRows), [draftRows])

  const direct = useMemo(
    () => processedRows.reduce((sum, r) => sum + (r.row_type === 'line' ? (r.computed_amount || 0) : 0), 0),
    [processedRows],
  )

  const liq = useMemo(() => computeLiquidacion(direct), [direct])
  const isBaseExtractionOnly = result?.output?.mode === 'base_extraction' || result?.extraction?.mode === 'base_extraction'

  const issueDate = useMemo(() => {
    const raw = project?.updated_at
    if (!raw) return new Date()
    const d = new Date(raw)
    return Number.isNaN(d.getTime()) ? new Date() : d
  }, [project?.updated_at])

  const location = project?.location_text?.trim() || 'República Dominicana'

  async function handleEnqueueSubmit(opts: { discipline?: string }) {
    const ok = await enqueue(opts)
    if (ok) setModalOpen(false)
    return ok
  }

  function startEditing() {
    setEditRows(syncedRows.map((r) => ({ ...r })))
    setSaveError(null)
  }

  function exitEditMode() {
    setEditRows(null)
    setSaveError(null)
  }

  const pipelineAvailable = project ? showBudgetPipelinePanel(project.workflow_phase) : false

  const pipelineSharedProps = {
    project: project!,
    projectUuid,
    token,
    role,
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
  }

  function renderPipelineSection() {
    if (!project) {
      return <p className="py-12 text-center text-sm text-muted">Cargando proyecto…</p>
    }
    if (!pipelineAvailable) {
      return (
        <div className="rounded-xl border border-black/10 bg-white p-8 text-center shadow-sm">
          <p className="text-sm text-muted">
            Disponible cuando el proyecto entra en la fase de presupuesto interno.
          </p>
        </div>
      )
    }
    if (section === 'cotizaciones') {
      return <BudgetQuotesPanel {...pipelineSharedProps} />
    }
    return <BudgetChecklistPanel {...pipelineSharedProps} gerenciaReviewDone={gerenciaReviewDone} />
  }

  function renderSectionBody(body: ReactNode) {
    if (section === 'basePrecios') {
      return <WorkspacePriceDatabaseTab projectUuid={projectUuid} token={token} flowMsg={flowMsg} />
    }
    if (section === 'presupuesto') return body
    return renderPipelineSection()
  }

  function withSections(body: ReactNode) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-auto">
        <BudgetSectionSwitch value={section} onChange={onSectionChange} />
        {renderSectionBody(body)}
      </div>
    )
  }

  // ── No job yet (idle) ──
  if (!job && !error) {
    return withSections(
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        {modalOpen && (
          <EnqueueModal
            onSubmit={handleEnqueueSubmit}
            onClose={() => setModalOpen(false)}
          />
        )}
        <div className="flex size-20 items-center justify-center rounded-full bg-primary/10">
          <Cpu className="size-10 text-primary" strokeWidth={1.5} />
        </div>
        <div className="max-w-sm space-y-2">
          <h2 className="text-xl font-bold text-ink">Presupuesto maestro</h2>
          <p className="text-sm leading-relaxed text-muted">
            Procesa los planos DWG del proyecto con la IA de Dupla para obtener un presupuesto detallado por partidas.
          </p>
        </div>
        <PrimaryButton
          id="start-budget-btn"
          type="button"
          className="gap-2 px-6 py-3 text-sm font-bold"
          onClick={() => setModalOpen(true)}
        >
          <Play className="size-4" strokeWidth={2.5} aria-hidden />
          Iniciar presupuesto
        </PrimaryButton>
      </div>,
    )
  }

  // ── Processing / queued ──
  if (job?.status === 'queued' || job?.status === 'processing') {
    return withSections(
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        <div className="relative flex size-20 items-center justify-center rounded-full bg-primary/10">
          <Loader2 className="size-10 animate-spin text-primary" strokeWidth={1.5} />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-ink">Procesando con Dupla OS…</h2>
          <p className="text-sm text-muted">
            {job ? budgetPhaseMessage(job) : 'Analizando planos DWG, extrayendo volumetrías y generando presupuesto.'}
          </p>
          <p className="font-mono text-xs text-muted">
            {elapsed > 0 ? `${elapsed}s transcurridos` : 'Iniciando…'}
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-xs font-semibold text-primary">
          <span className="size-2 animate-pulse rounded-full bg-primary" />
          {job?.phase === 'extraction'
            ? 'Fase 1: extracción'
            : job?.phase === 'vision'
              ? 'Fase 2: visión IA'
              : job?.phase === 'budget'
                ? 'Fase 3: presupuesto'
                : isPolling
                  ? 'Actualizando cada 5 s'
                  : 'En cola'}
        </span>
        <button
          type="button"
          id="budget-refresh-btn"
          className="text-xs text-muted underline underline-offset-2 hover:text-ink"
          onClick={refresh}
        >
          Verificar estado
        </button>
      </div>,
    )
  }

  // ── Partial (base extraction only) ──
  if (job?.status === 'completed_partial' || (job?.status === 'completed' && !result && !isPolling)) {
    return withSections(
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        {modalOpen && (
          <EnqueueModal
            onSubmit={handleEnqueueSubmit}
            onClose={() => setModalOpen(false)}
          />
        )}
        <div className="flex size-20 items-center justify-center rounded-full bg-primary/10">
          <Cpu className="size-10 text-primary" strokeWidth={1.5} />
        </div>
        <div className="max-w-md space-y-2">
          <h2 className="text-xl font-bold text-ink">Presupuesto sin partidas</h2>
          <p className="text-sm leading-relaxed text-muted">
            {job?.discipline
              ? `La corrida (${job.discipline}) terminó sin generar líneas de presupuesto.`
              : 'El procesamiento terminó sin generar líneas de presupuesto.'}{' '}
            Re-procesa con otra disciplina o verifica que los planos tengan capas y nomenclatura identificables.
          </p>
        </div>
        <PrimaryButton
          id="retry-budget-partial-btn"
          type="button"
          className="gap-2 px-6 py-3 text-sm font-bold"
          onClick={() => setModalOpen(true)}
        >
          <RefreshCw className="size-4" strokeWidth={2.5} aria-hidden />
          Re-procesar con disciplina
        </PrimaryButton>
      </div>,
    )
  }

  // ── Failed ──
  if (job?.status === 'failed' || error) {
    return withSections(
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        {modalOpen && (
          <EnqueueModal
            onSubmit={handleEnqueueSubmit}
            onClose={() => setModalOpen(false)}
          />
        )}
        <div className="flex size-20 items-center justify-center rounded-full bg-red-500/10">
          <AlertCircle className="size-10 text-red-500" strokeWidth={1.5} />
        </div>
        <div className="max-w-sm space-y-2">
          <h2 className="text-xl font-bold text-ink">Procesamiento fallido</h2>
          <p className="text-sm leading-relaxed text-muted">{job?.error ?? error ?? 'Error desconocido'}</p>
        </div>
        <PrimaryButton
          id="retry-budget-btn"
          type="button"
          className="gap-2 px-6 py-3 text-sm font-bold"
          onClick={() => setModalOpen(true)}
        >
          <RefreshCw className="size-4" strokeWidth={2.5} aria-hidden />
          Re-procesar
        </PrimaryButton>
      </div>,
    )
  }

  if (isBaseExtractionOnly) {
    return withSections(
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        {modalOpen && (
          <EnqueueModal
            onSubmit={handleEnqueueSubmit}
            onClose={() => setModalOpen(false)}
          />
        )}
        <div className="flex size-20 items-center justify-center rounded-full bg-primary/10">
          <Cpu className="size-10 text-primary" strokeWidth={1.5} />
        </div>
        <div className="max-w-md space-y-2">
          <h2 className="text-xl font-bold text-ink">Extraccion base completada</h2>
          <p className="text-sm leading-relaxed text-muted">
            Esta corrida solo genero artefactos de extraccion y no contiene partidas de presupuesto.
            Re-procesa seleccionando una disciplina o todas las disciplinas.
          </p>
        </div>
        <PrimaryButton
          id="base-extraction-reprocess-btn"
          type="button"
          className="gap-2 px-6 py-3 text-sm font-bold"
          onClick={() => setModalOpen(true)}
        >
          <RefreshCw className="size-4" strokeWidth={2.5} aria-hidden />
          Generar presupuesto
        </PrimaryButton>
      </div>,
    )
  }

  // ── Completed — render real budget ──
  return withSections(
    <div className="flex min-h-0 flex-1 flex-col gap-6 pb-10">
      {modalOpen && (
        <EnqueueModal
          onSubmit={handleEnqueueSubmit}
          onClose={() => setModalOpen(false)}
        />
      )}

      {/* Header card */}
      <div className="rounded-xl border border-black/10 bg-white p-5 shadow-(--shadow-card) sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-bold uppercase tracking-wide text-primary">Grupo Dupla</p>
            <h2 className="text-xl font-bold tracking-tight text-ink md:text-2xl">Presupuesto maestro</h2>
            <p className="text-sm text-muted">
              <span className="font-semibold text-ink">{project?.name ?? 'Obra'}</span>
              {project?.project_code ? (
                <span className="font-mono text-muted"> · {project.project_code}</span>
              ) : null}
              {job?.discipline ? (
                <span className="ml-2 rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-semibold text-primary capitalize">
                  {job.discipline}
                </span>
              ) : null}
            </p>
            <p className="text-xs text-muted">
              Ubicación: {location} · Emisión:{' '}
              {issueDate.toLocaleDateString('es-DO', { day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {!isEditing ? (
              <button
                type="button"
                id="budget-edit-btn"
                className="inline-flex items-center justify-center rounded-lg border border-black/15 p-2 text-muted hover:bg-black/5 hover:text-ink"
                title="Editar partidas, precios y secciones del presupuesto"
                aria-label="Editar presupuesto"
                onClick={startEditing}
              >
                <Pencil className="size-4" strokeWidth={2} aria-hidden />
              </button>
            ) : (
              <button
                type="button"
                id="budget-cancel-edit-btn"
                className="inline-flex items-center gap-2 rounded-lg border border-black/15 px-4 py-2 text-xs font-semibold text-muted hover:bg-black/5"
                onClick={exitEditMode}
              >
                Cancelar edición
              </button>
            )}
            <button
              type="button"
              id="budget-reprocess-btn"
              className="inline-flex items-center gap-2 rounded-lg border border-primary/40 bg-primary/8 px-4 py-2 text-xs font-bold text-primary hover:bg-primary/12"
              onClick={() => setModalOpen(true)}
            >
              <RefreshCw className="size-4" strokeWidth={2} aria-hidden />
              Re-procesar
            </button>
          </div>
        </div>

        {/* Table editable */}
        <div className="mt-6">
          <BudgetEditableTable
            rows={draftRows}
            onRowsChange={setEditRows}
            saveError={saveError}
            editing={isEditing}
            onSave={async (rows) => {
              setSaveError(null)
              const ok = await saveRows(rows)
              if (!ok) {
                setSaveError('No se pudo guardar el presupuesto')
                return false
              }
              setEditRows(null)
              return true
            }}
          />
        </div>

        <div className="mt-4 flex flex-col items-end gap-2 border-t border-black/10 pt-4">
          <p className="text-[11px] font-bold uppercase tracking-wide text-muted">Subtotal directo</p>
          <p className="text-3xl font-bold tabular-nums text-primary">{fmtDop(direct)}</p>
        </div>
      </div>

      {/* Liquidación */}
      <div className="rounded-xl border border-black/10 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-bold uppercase tracking-wide text-muted">Liquidación / indirectos / ITBIS</h3>
        <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          {[
            ['Costos directos', fmtDop(direct)],
            [`Seguro (${LIQUIDACION_RATES.seguroPct}%)`, fmtDop(liq.seguro)],
            [`Gastos administrativos (${LIQUIDACION_RATES.gastosAdminPct}%)`, fmtDop(liq.gastosAdmin)],
            [`Transporte (${LIQUIDACION_RATES.transportePct}%)`, fmtDop(liq.transporte)],
            [`Dirección técnica (${LIQUIDACION_RATES.direccionTecnicaPct}%)`, fmtDop(liq.direccion)],
            ['Subtotal antes ITBIS', fmtDop(liq.subAntesItbis)],
            [`ITBIS (${LIQUIDACION_RATES.itbisPct}%)`, fmtDop(liq.itbis)],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4 border-b border-black/8 py-2">
              <span className="text-muted">{label}</span>
              <span className="tabular-nums text-ink">{value}</span>
            </div>
          ))}
          <div className="flex justify-between gap-4 py-2 sm:col-span-2">
            <span className="font-bold text-ink">Total general estimado</span>
            <span className="text-lg font-bold tabular-nums text-primary">{fmtDop(liq.total)}</span>
          </div>
        </div>
      </div>
    </div>,
  )
}
