import { AlertCircle, Cpu, Loader2, Play, RefreshCw } from 'lucide-react'
import { useMemo, useEffect, useRef, useState } from 'react'

import { useBudgetJob } from '../../../hooks/useBudgetJob'
import type { Project } from '../../../types/project'
import { PrimaryButton } from '../../PrimaryButton'
import { WorkspaceActionButton } from '../WorkspaceActionButton'

// ─── formatters ───────────────────────────────────────────────────────────────
function fmtDop(n: any): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('es-DO', {
    style: 'currency',
    currency: 'DOP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

function fmtUsd(n: any, tcRate = 58.5): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num / tcRate)
}

function fmtQty(q: any): string {
  if (q == null || q === '') return ''
  if (typeof q === 'string' && q.startsWith('=')) return ''
  const num = Number(q) || 0
  if (num === 0 && !q) return ''
  return new Intl.NumberFormat('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num)
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
  onSubmit: (opts: { discipline?: string }) => void
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
            onAction={() => {
              onSubmit({ discipline })
              return true
            }}
            successLabel="Proceso iniciado"
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
  const ref = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!startIso) { setElapsed(0); return }
    const start = new Date(startIso).getTime()
    ref.current = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => { if (ref.current) clearInterval(ref.current) }
  }, [startIso])

  return elapsed
}

// ─── Main component ───────────────────────────────────────────────────────────
type Props = {
  project: Project | null
  projectUuid: string
  token: string | null
}

export function WorkspacePresupuestoMaestroTab({ project, projectUuid, token }: Props) {
  const { job, result, isPolling, error, enqueue, refresh } = useBudgetJob(projectUuid, token)
  const [modalOpen, setModalOpen] = useState(false)
  const elapsed = useElapsedSeconds(
    job?.status === 'queued' || job?.status === 'processing' ? job.created_at : undefined,
  )

  const processedRows = useMemo(() => {
    if (!result?.rows) return []
    const newRows = result.rows.map(r => ({ ...r })) as any[]
    
    for (const r of newRows) {
      if (r.row_type === 'line') {
        const qty = Number(r.quantity) || 0
        const price = Number(r.unit_price) || 0
        r.computed_amount = qty * price
      }
    }
    for (const r of newRows) {
      if (r.row_type === 'subtotal') {
        const indices = r.metadata?.source_row_indices || []
        r.computed_amount = indices.reduce((sum: number, idx: number) => sum + (newRows[idx]?.computed_amount || 0), 0)
        r.computed_unit_price = r.computed_amount
        r.computed_quantity = 1
      }
    }
    for (const r of newRows) {
      if (r.row_type === 'chapter') {
        const subIdx = r.metadata?.subtotal_row_index
        if (typeof subIdx === 'number' && newRows[subIdx]) {
          r.computed_amount = newRows[subIdx].computed_amount
          r.computed_unit_price = newRows[subIdx].computed_unit_price
          r.computed_quantity = newRows[subIdx].computed_quantity
        } else {
          r.computed_amount = 0
        }
      }
    }
    return newRows
  }, [result?.rows])

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

  function handleEnqueueSubmit(opts: { discipline?: string }) {
    setModalOpen(false)
    void enqueue(opts)
  }

  // ── No job yet (idle) ──
  if (!job && !error) {
    return (
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
      </div>
    )
  }

  // ── Processing / queued ──
  if (job?.status === 'queued' || job?.status === 'processing') {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-6 py-20 text-center">
        <div className="relative flex size-20 items-center justify-center rounded-full bg-primary/10">
          <Loader2 className="size-10 animate-spin text-primary" strokeWidth={1.5} />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-bold text-ink">Procesando con IA…</h2>
          <p className="text-sm text-muted">
            Analizando planos DWG, extrayendo volumetrías y generando presupuesto.
          </p>
          <p className="font-mono text-xs text-muted">
            {elapsed > 0 ? `${elapsed}s transcurridos` : 'Iniciando…'}
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-1.5 text-xs font-semibold text-primary">
          <span className="size-2 animate-pulse rounded-full bg-primary" />
          {isPolling ? 'Actualizando cada 5 s' : 'En cola'}
        </span>
        <button
          type="button"
          id="budget-refresh-btn"
          className="text-xs text-muted underline underline-offset-2 hover:text-ink"
          onClick={refresh}
        >
          Verificar estado
        </button>
      </div>
    )
  }

  // ── Failed ──
  if (job?.status === 'failed' || error) {
    return (
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
      </div>
    )
  }

  if (isBaseExtractionOnly) {
    return (
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
      </div>
    )
  }

  // ── Completed — render real budget ──
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 pb-10">
      {modalOpen && (
        <EnqueueModal
          onSubmit={handleEnqueueSubmit}
          onClose={() => setModalOpen(false)}
        />
      )}

      {/* Header card */}
      <div className="rounded-xl border border-black/10 bg-white p-5 shadow-[var(--shadow-card)] sm:p-6">
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
          <div className="flex shrink-0 flex-wrap gap-2">
            <button
              type="button"
              id="budget-reprocess-btn"
              className="inline-flex items-center gap-2 rounded-lg border border-primary/40 bg-primary/[0.08] px-4 py-2 text-xs font-bold text-primary hover:bg-primary/[0.12]"
              onClick={() => setModalOpen(true)}
            >
              <RefreshCw className="size-4" strokeWidth={2} aria-hidden />
              Re-procesar
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="mt-6 overflow-x-auto rounded-lg border border-black/10">
          <table className="w-full min-w-[920px] border-collapse text-left text-sm">
            <thead className="border-b border-black/10 bg-[#f8f9fb] text-[11px] font-bold uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-3">Código</th>
                <th className="min-w-[220px] px-3 py-3">Partida</th>
                <th className="px-3 py-3">Cantidad / UD</th>
                <th className="px-3 py-3">P/UD (RD$)</th>
                <th className="px-3 py-3 text-right">Total RD$</th>
                <th className="px-3 py-3 text-right">Total USD</th>
              </tr>
            </thead>
            <tbody>
              {processedRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-sm text-muted">
                    El presupuesto no contiene partidas.
                  </td>
                </tr>
              ) : (
                processedRows.map((r, i) => (
                  <tr key={`${r.code}-${i}`} className="border-b border-black/[0.06] hover:bg-black/[0.015]">
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-muted">{r.code}</td>
                    <td className="px-3 py-2.5 font-medium text-ink">{r.summary}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-muted">
                      {fmtQty(r.row_type === 'chapter' || r.row_type === 'subtotal' ? r.computed_quantity : r.quantity)}{' '}
                      {r.unit ? <span className="text-ink">{r.unit}</span> : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 tabular-nums">
                      {fmtDop(r.row_type === 'line' ? r.unit_price : r.computed_unit_price)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums font-semibold text-ink">
                      {fmtDop(r.computed_amount)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-muted">
                      {fmtUsd(r.computed_amount)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
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
    </div>
  )
}
