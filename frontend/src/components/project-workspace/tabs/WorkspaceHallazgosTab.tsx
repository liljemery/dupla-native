import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Box,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  FileWarning,
  Sparkles,
} from 'lucide-react'

import { apiFetch } from '../../../api/client'
import {
  downloadFinalHumanPdf,
  downloadFinalTechnicalExcel,
  downloadFinalTechnicalPdf,
  downloadClashTechnicalExcel,
} from '../../../api/clashWorkflow'
import {
  downloadClashHumanPdf,
  downloadClashTechnicalPdf,
  getCoordinationFolders,
  getCoordinationInventory,
  type CoordinationInventory,
} from '../../../api/structuralAnalysis'
import { ClashWorkflowPanel } from '../../clash-workflow/ClashWorkflowPanel'
import { useStructuralAnalysisJob } from '../../../hooks/useStructuralAnalysisJob'
import { formatCoordinationInventorySummary } from '../../../lib/coordinationInventory'
import type { Project } from '../../../types/project'
import type { TechnicalFindingRow } from '../../../types/projectWorkspace'
import type {
  StructuralAnalysisReport,
  StructuralAnalyzedDocument,
  StructuralClash,
  StructuralClashPriority,
  StructuralClashRelationship,
  StructuralZoningRow,
} from '../../../types/structuralAnalysisReport'
import { Card } from '../../Card'
import { PrimaryButton } from '../../PrimaryButton'
import { WorkspaceActionButton } from '../WorkspaceActionButton'

const SEVERITY_OPTIONS = ['crítico', 'alto', 'medio', 'bajo'] as const

type WorkspaceHallazgosTabProps = {
  project: Project | null
  projectUuid: string
  token: string | null
  findings: TechnicalFindingRow[]
  onRefresh: () => Promise<void>
  onContinueToPliego: () => void
}

function priorityLabel(p: StructuralClashPriority): { text: string; className: string } {
  switch (p) {
    case 'critical':
      return { text: 'Crítico', className: 'bg-primary text-white' }
    case 'high':
      return { text: 'Alta prioridad', className: 'border border-primary/40 bg-primary/8 text-primary' }
    case 'warning':
      return { text: 'Advertencia', className: 'border border-amber-500/50 bg-amber-500/10 text-amber-900' }
    default:
      return { text: 'Informativo', className: 'border border-black/15 bg-black/4 text-muted' }
  }
}

function runStatusBadge(status: StructuralAnalysisReport['run_status']): { label: string; className: string } {
  switch (status) {
    case 'completed':
      return { label: 'Análisis completado', className: 'bg-primary/12 text-primary' }
    case 'running':
      return { label: 'Análisis en curso', className: 'bg-amber-500/15 text-amber-900' }
    case 'failed':
      return { label: 'Análisis con errores', className: 'bg-primary/15 text-primary' }
    default:
      return { label: 'Pendiente de análisis', className: 'bg-black/6 text-muted' }
  }
}

function ZoningStatusBadge({ status }: { status: StructuralZoningRow['status'] }) {
  if (status === 'validated') {
    return (
      <span className="inline-flex rounded-md bg-emerald-600/12 px-2 py-0.5 text-xs font-semibold text-emerald-800">
        Validado
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex rounded-md bg-primary/12 px-2 py-0.5 text-xs font-semibold text-primary">
        Error
      </span>
    )
  }
  return (
    <span className="inline-flex rounded-md bg-amber-500/15 px-2 py-0.5 text-xs font-semibold text-amber-900">
      Aviso
    </span>
  )
}

function ClashCard({
  clash,
  expanded,
  onToggle,
}: {
  clash: StructuralClash
  expanded: boolean
  onToggle: () => void
}) {
  const pill = priorityLabel(clash.priority)
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        className="flex w-full items-start gap-3 p-4 text-left outline-none transition hover:bg-black/2 focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-inset"
        onClick={onToggle}
      >
        <span className="mt-0.5 shrink-0 text-muted" aria-hidden>
          {expanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-ink">{clash.title}</h3>
            <span className={`rounded-md px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${pill.className}`}>
              {pill.text}
            </span>
          </div>
          {!expanded ? <p className="mt-1 line-clamp-2 text-sm text-muted">{clash.description}</p> : null}
        </div>
      </button>
      {expanded ? (
        <div className="border-t border-black/10 px-4 pb-4 pt-2 pl-12 sm:pl-14">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
            <div
              className="flex aspect-video w-full shrink-0 items-center justify-center rounded-lg border border-black/10 bg-linear-to-br from-slate-200/90 to-slate-400/50 sm:h-24 sm:w-36 sm:aspect-auto"
              aria-hidden
            >
              {clash.thumbnail_url ? (
                <img src={clash.thumbnail_url} alt="" className="h-full w-full rounded-lg object-cover" />
              ) : (
                <Box className="h-10 w-10 text-slate-600/70" aria-hidden />
              )}
            </div>
            <div className="min-w-0 flex-1 space-y-2 text-sm">
              <p className="text-ink">{clash.description}</p>
              {clash.location_label ? (
                <p>
                  <span className="font-medium text-muted">Ubicación</span>
                  <span className="text-ink"> · {clash.location_label}</span>
                </p>
              ) : null}
              {clash.disciplines.length > 0 ? (
                <p>
                  <span className="font-medium text-muted">Disciplinas</span>
                  <span className="text-ink"> · {clash.disciplines.join(', ')}</span>
                </p>
              ) : null}
              {clash.confidence ? (
                <p>
                  <span className="font-medium text-muted">Confianza</span>
                  <span className="text-ink"> · {clash.confidence}</span>
                </p>
              ) : null}
              {clash.geometry_sources ? (
                <p>
                  <span className="font-medium text-muted">Fuentes geom.</span>
                  <span className="text-ink"> · {clash.geometry_sources}</span>
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}

function RelationshipBanner({ rel }: { rel: StructuralClashRelationship }) {
  return (
    <div className="rounded-lg border border-primary/25 bg-primary/6 px-4 py-3 text-sm text-ink">
      <p className="font-semibold text-primary">Conflicto entre hallazgos</p>
      <p className="mt-1 text-muted">{rel.message}</p>
      <p className="mt-2 font-mono text-xs text-muted">IDs: {rel.clash_ids.join(' · ')}</p>
    </div>
  )
}

function geometryBadge(doc: StructuralAnalyzedDocument): { text: string; className: string } | null {
  if (doc.geometry_quality === 'exact') {
    return { text: 'Geometría exacta (SVF1)', className: 'bg-emerald-600/12 text-emerald-800' }
  }
  if (doc.geometry_source?.includes('local_ezdxf') || doc.geometry_source?.includes('dxf_ezdxf')) {
    return { text: 'Geometría exacta (CAD)', className: 'bg-emerald-600/12 text-emerald-800' }
  }
  if (doc.geometry_quality === 'proxy' || doc.aps_result === 'proxy') {
    return { text: 'Proxy APS', className: 'bg-amber-500/15 text-amber-900' }
  }
  if (doc.geometry_source?.includes('pdf_companion')) {
    return { text: 'PDF compañero', className: 'bg-slate-500/12 text-slate-700' }
  }
  if (doc.aps_result === 'quota_exceeded') {
    return { text: 'APS sin cuota', className: 'bg-primary/12 text-primary' }
  }
  return null
}

function DocumentRow({
  doc,
  onRetry,
}: {
  doc: StructuralAnalyzedDocument
  onRetry: (id: string) => void
}) {
  const ok = doc.status === 'ok'
  const warning = doc.status === 'warning'
  const badge = geometryBadge(doc)
  return (
    <li className="flex items-start gap-2 border-b border-black/6 py-2.5 text-sm last:border-0">
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
      ) : warning ? (
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
      ) : (
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{doc.file_name}</p>
        <p className="text-xs text-muted">
          {doc.discipline_label}
          {typeof doc.element_count === 'number' ? ` · ${doc.element_count} elementos` : ''}
          {typeof doc.viewer_elements === 'number' && doc.viewer_elements > 0
            ? ` · ${doc.viewer_elements} exactos`
            : ''}
          {warning ? ' · sin geometría extraíble' : ''}
        </p>
        {badge ? (
          <span className={`mt-1 inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${badge.className}`}>
            {badge.text}
          </span>
        ) : null}
        {doc.aps_note ? <p className="mt-1 text-xs text-muted">{doc.aps_note}</p> : null}
        {!ok && doc.retryable ? (
          <button
            type="button"
            className="du-link mt-1 inline text-xs font-semibold"
            onClick={() => onRetry(doc.id)}
          >
            Reintentar
          </button>
        ) : null}
      </div>
    </li>
  )
}

export function WorkspaceHallazgosTab({
  project,
  projectUuid,
  token,
  findings,
  onRefresh,
  onContinueToPliego,
}: WorkspaceHallazgosTabProps) {
  const { report, job, isPolling, error: jobError, enqueue } = useStructuralAnalysisJob(projectUuid, token)
  const [expandedClashIds, setExpandedClashIds] = useState<Set<string>>(() => new Set())
  const [pdfBusy, setPdfBusy] = useState<
    | 'technical_excel'
    | 'technical_pdf'
    | 'human'
    | 'final_technical_excel'
    | 'final_technical_pdf'
    | 'final_human'
    | null
  >(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [folderOptions, setFolderOptions] = useState<Array<{ uuid: string; path: string }>>([])
  const [selectedFolderUuid, setSelectedFolderUuid] = useState<string>('')
  const [inventory, setInventory] = useState<CoordinationInventory | null>(null)
  const [inventoryLoading, setInventoryLoading] = useState(false)
  const [inventoryError, setInventoryError] = useState<string | null>(null)

  useEffect(() => {
    if (!token || !projectUuid) return
    void (async () => {
      const folders = await getCoordinationFolders(projectUuid, token)
      setFolderOptions(folders.map((f) => ({ uuid: f.uuid, path: f.path })))
      const last = (project?.workflow_meta as Record<string, unknown> | undefined)?.coordination_last_folder_uuid
      if (typeof last === 'string' && last && folders.some((f) => f.uuid === last)) {
        setSelectedFolderUuid(last)
      } else if (folders.length === 1) {
        setSelectedFolderUuid(folders[0].uuid)
      }
    })()
  }, [token, projectUuid, project?.workflow_meta])

  useEffect(() => {
    if (!token || !projectUuid) return
    setInventoryLoading(true)
    setInventoryError(null)
    void (async () => {
      const result = await getCoordinationInventory(
        projectUuid,
        token,
        selectedFolderUuid || null,
      )
      if (result.ok) {
        setInventory(result.data)
      } else {
        setInventory(null)
        setInventoryError(result.message)
      }
      setInventoryLoading(false)
    })()
  }, [token, projectUuid, selectedFolderUuid])

  const canRunAnalysis = Boolean(
    token &&
      !isPolling &&
      report.run_status !== 'running' &&
      inventory?.ready,
  )

  const canDownloadPdf = report.run_status === 'completed' && Boolean(job) && Boolean(token)

  const summaryTotal =
    report.summary.total_clashes ?? report.summary.errors
  const summaryCritical = report.summary.critical ?? report.summary.warnings
  const summaryNonCritical = report.summary.non_critical ?? report.summary.ok

  const showWorkflow = report.run_status === 'completed' && Boolean(job)

  function handleDownload(
    kind:
      | 'technical_excel'
      | 'technical_pdf'
      | 'human'
      | 'final_technical_excel'
      | 'final_technical_pdf'
      | 'final_human',
  ) {
    if (!token) return
    if ((kind === 'technical_excel' || kind === 'technical_pdf' || kind === 'human') && !canDownloadPdf)
      return
    if (kind.startsWith('final') && report.run_status !== 'completed') return
    void (async () => {
      setPdfError(null)
      setPdfBusy(kind)
      try {
        switch (kind) {
          case 'technical_excel':
            await downloadClashTechnicalExcel(projectUuid, token, job?.id)
            break
          case 'technical_pdf':
            await downloadClashTechnicalPdf(projectUuid, token, job?.id)
            break
          case 'human':
            await downloadClashHumanPdf(projectUuid, token, job?.id)
            break
          case 'final_technical_excel':
            await downloadFinalTechnicalExcel(projectUuid, token)
            break
          case 'final_technical_pdf':
            await downloadFinalTechnicalPdf(projectUuid, token)
            break
          case 'final_human':
            await downloadFinalHumanPdf(projectUuid, token)
            break
        }
      } catch (e) {
        setPdfError(e instanceof Error ? e.message : 'No se pudo descargar el archivo')
      } finally {
        setPdfBusy(null)
      }
    })()
  }

  const [discipline, setDiscipline] = useState('')
  const [severity, setSeverity] = useState<string>('medio')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [evidenceRef, setEvidenceRef] = useState('')
  const [submitBusy, setSubmitBusy] = useState(false)
  const [localErr, setLocalErr] = useState<string | null>(null)

  const statusPill = useMemo(() => runStatusBadge(report.run_status), [report.run_status])

  const toggleClash = useCallback((id: string) => {
    setExpandedClashIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const submit = useCallback(async (): Promise<boolean> => {
    if (!token || !discipline.trim() || !title.trim() || !description.trim()) return false
    setSubmitBusy(true)
    setLocalErr(null)
    try {
      const body = {
        discipline: discipline.trim(),
        severity: severity.trim() || 'medio',
        title: title.trim(),
        description: description.trim(),
        evidence_ref: evidenceRef.trim() || null,
      }
      const res = await apiFetch(`/api/projects/${projectUuid}/technical-findings`, {
        method: 'POST',
        token,
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setLocalErr((j as { detail?: string }).detail ?? 'No se pudo guardar el hallazgo')
        return false
      }
      setTitle('')
      setDescription('')
      setEvidenceRef('')
      await onRefresh()
      return true
    } finally {
      setSubmitBusy(false)
    }
  }, [token, projectUuid, discipline, severity, title, description, evidenceRef, onRefresh])

  const onDocRetry = useCallback(() => {
    // Re-análisis por documento: pendiente de endpoint dedicado.
  }, [])

  const runAnalysis = useCallback(() => {
    void enqueue({ folder_uuid: selectedFolderUuid || undefined })
  }, [enqueue, selectedFolderUuid])

  const projectDisplayName = project?.name ?? inventory?.project_name ?? 'Proyecto'

  return (
    <div className="space-y-8">
      {report.analysis_mode === 'smoke' ? (
        <div
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-950"
          role="status"
        >
          Modo demo — la detección de clashes está simulada. Los hallazgos provienen de fixtures de desarrollo, no
          del motor Dupla geométrico.
        </div>
      ) : null}
      <Card className="border-primary/20 bg-primary/4 p-4">
        <h3 className="text-sm font-semibold text-ink">Información de coordinación</h3>
        <p className="mt-1 text-xs text-muted">
          Proyecto «{projectDisplayName}». Elige la carpeta de entrega (ej. TEST_01): se analizarán todos los .dwg
          dentro de ella y subcarpetas, agrupados por la etiqueta de disciplina de cada archivo en Archivos (ARQ, EST,
          ELC, etc.).
        </p>
        <div className="mt-3">
          <label htmlFor="coord-folder" className="text-xs font-medium uppercase tracking-wide text-muted">
            Carpeta fuente
          </label>
          <select
            id="coord-folder"
            className="du-input mt-1 w-full max-w-xl"
            value={selectedFolderUuid}
            onChange={(e) => setSelectedFolderUuid(e.target.value)}
          >
            <option value="">— Seleccionar carpeta —</option>
            {folderOptions.map((f) => (
              <option key={f.uuid} value={f.uuid}>
                {f.path}
              </option>
            ))}
          </select>
        </div>
        {inventoryLoading ? (
          <p className="mt-3 text-sm text-muted">Cargando inventario…</p>
        ) : inventoryError ? (
          <p className="mt-3 text-sm text-primary" role="alert">
            {inventoryError}
          </p>
        ) : inventory ? (
          <div className="mt-3 space-y-2 text-sm">
            <p className="text-ink">{formatCoordinationInventorySummary(inventory)}</p>
            {inventory.blockers.length > 0 ? (
              <ul className="list-disc space-y-1 pl-5 text-primary">
                {inventory.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            ) : (
              <p className="text-emerald-800">Listo para ejecutar análisis de clashes.</p>
            )}
          </div>
        ) : null}
      </Card>

      <header className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${statusPill.className}`}
            >
              {statusPill.label}
            </span>
            {isPolling ? (
              <span className="text-xs text-muted">
                {report.extraction_progress && report.extraction_progress.total > 0
                  ? `Extrayendo planos ${report.extraction_progress.processed}/${report.extraction_progress.total}…`
                  : job?.progress && job.progress.total > 0
                    ? `Extrayendo planos ${job.progress.processed}/${job.progress.total}…`
                    : 'Actualizando cada 5 s…'}
              </span>
            ) : null}
          </div>
          {jobError ? <p className="text-sm text-primary">{jobError}</p> : null}
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 space-y-2">
              <h2 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{report.title}</h2>
              <p className="max-w-3xl text-sm text-muted sm:text-base">{report.subtitle}</p>
            </div>
            <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
              <PrimaryButton
                type="button"
                disabled={!canRunAnalysis}
                onClick={runAnalysis}
              >
                {isPolling || report.run_status === 'running'
                  ? (() => {
                      const p = report.extraction_progress ?? job?.progress
                      if (p && p.total > 0) {
                        return p.phase === 'clash'
                          ? `Detectando clashes (${p.processed}/${p.total})…`
                          : `Extrayendo planos ${p.processed}/${p.total}…`
                      }
                      return 'Análisis en curso…'
                    })()
                  : 'Ejecutar análisis de clashes'}
              </PrimaryButton>
              <WorkspaceActionButton
                type="button"
                onAction={() => {
                  const base = import.meta.env.VITE_API_BASE ?? ''
                  window.open(`${base}/api/projects/${projectUuid}/viewer`, '_blank', 'noopener,noreferrer')
                }}
              >
                Ver en visor APS
              </WorkspaceActionButton>
              <div className="grid grid-cols-3 gap-2 sm:gap-3">
              <Card className="flex flex-col items-center justify-center gap-1 border-primary/20 bg-primary/6 p-3 sm:p-4">
                <span className="text-xs font-semibold uppercase tracking-wide text-primary">Total de Clashes</span>
                <span className="flex items-center gap-1 text-2xl font-bold tabular-nums text-primary sm:text-3xl">
                  <CircleAlert className="h-5 w-5 shrink-0 sm:h-6 sm:w-6" aria-hidden />
                  {String(summaryTotal).padStart(2, '0')}
                </span>
              </Card>
              <Card className="flex flex-col items-center justify-center gap-1 border-primary/30 bg-primary/10 p-3 sm:p-4">
                <span className="text-xs font-semibold uppercase tracking-wide text-primary">Críticos</span>
                <span className="flex items-center gap-1 text-2xl font-bold tabular-nums text-primary sm:text-3xl">
                  <AlertTriangle className="h-5 w-5 shrink-0 sm:h-6 sm:w-6" aria-hidden />
                  {String(summaryCritical).padStart(2, '0')}
                </span>
              </Card>
              <Card className="flex flex-col items-center justify-center gap-1 border-emerald-600/20 bg-emerald-600/8 p-3 sm:p-4">
                <span className="text-xs font-semibold uppercase tracking-wide text-emerald-900">No Críticos</span>
                <span className="flex items-center gap-1 text-2xl font-bold tabular-nums text-emerald-900 sm:text-3xl">
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-700 sm:h-6 sm:w-6" aria-hidden />
                  {summaryNonCritical}
                </span>
              </Card>
            </div>
            </div>
          </div>
        </header>

      {showWorkflow ? (
        <ClashWorkflowPanel projectUuid={projectUuid} token={token} visible={showWorkflow} />
      ) : null}

        {report.run_status === 'pending' && report.clashes.length === 0 && !job ? (
          <Card className="border-dashed p-6 text-center">
            <p className="text-sm text-muted">
              {selectedFolderUuid
                ? 'Selecciona una carpeta con planos etiquetados (ARQ/EST) y pulsa «Ejecutar análisis de clashes».'
                : 'Elige la carpeta de entrega (ej. TEST_01) en el panel de coordinación arriba.'}
            </p>
          </Card>
        ) : null}

        {report.clash_relationships.length > 0 ? (
          <section className="space-y-3" aria-label="Relaciones entre hallazgos">
            {report.clash_relationships.map((rel) => (
              <RelationshipBanner key={rel.id} rel={rel} />
            ))}
          </section>
        ) : null}

        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <section className="min-w-0 flex-1 space-y-4" aria-labelledby="hallazgos-clashes-heading">
            <h3 id="hallazgos-clashes-heading" className="text-lg font-semibold text-ink">
              Conflictos detectados
            </h3>
            <div className="space-y-3">
              {report.clashes.length === 0 ? (
                <p className="text-sm text-muted">No se detectaron conflictos en la última corrida.</p>
              ) : (
                report.clashes.map((c) => (
                  <ClashCard
                    key={c.id}
                    clash={c}
                    expanded={expandedClashIds.has(c.id)}
                    onToggle={() => toggleClash(c.id)}
                  />
                ))
              )}
            </div>
          </section>

          <aside className="w-full shrink-0 space-y-4 lg:w-80" aria-label="Contexto del análisis">
            <Card className="p-4">
              <h3 className="text-sm font-semibold text-ink">Documentación analizada</h3>
              <ul className="mt-2">
                {report.analyzed_documents.map((d) => (
                  <DocumentRow key={d.id} doc={d} onRetry={onDocRetry} />
                ))}
              </ul>
            </Card>
            <Card className="border-primary/20 bg-primary/5 p-4">
              <div className="flex gap-2">
                <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
                <div>
                  <h3 className="text-sm font-semibold text-ink">Resumen Dupla</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink">{report.ai_insight}</p>
                </div>
              </div>
            </Card>
          </aside>
        </div>

        <section aria-labelledby="hallazgos-zoning-heading">
          <h3 id="hallazgos-zoning-heading" className="text-lg font-semibold text-ink">
            Estado de zonificación
          </h3>
          {report.zoning_rows.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Sin datos de zonificación en esta corrida (MVP).</p>
          ) : (
          <Card className="mt-3 overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-black/10 bg-black/3 text-xs font-semibold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">Zona</th>
                  <th className="px-4 py-3">Área (m²)</th>
                  <th className="px-4 py-3">Tipo de uso</th>
                  <th className="px-4 py-3">Observaciones</th>
                  <th className="px-4 py-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {report.zoning_rows.map((row) => (
                  <tr key={row.id} className="border-b border-black/6 last:border-0">
                    <td className="px-4 py-3 font-medium text-ink">{row.zone_name}</td>
                    <td className="px-4 py-3 tabular-nums text-muted">{row.area_sqm.toLocaleString('es-DO')}</td>
                    <td className="px-4 py-3 text-ink">{row.use_type}</td>
                    <td className="max-w-md px-4 py-3 text-muted">{row.ai_remarks}</td>
                    <td className="px-4 py-3">
                      <ZoningStatusBadge status={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          )}
        </section>

        <details className="group rounded-xl border border-black/10 bg-white shadow-(--shadow-card)">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-ink marker:content-none [&::-webkit-details-marker]:hidden">
            <span className="flex items-center justify-between gap-2">
              Registro manual de hallazgos
              <ChevronDown className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
            </span>
          </summary>
          <div className="space-y-4 border-t border-black/10 px-5 py-4">
            <p className="text-sm text-muted">
              Los datos del informe superior provienen del motor de coordinación Dupla. Esto sigue guardando hallazgos
              técnicos manuales en el proyecto.
            </p>
            {localErr ? <p className="text-sm text-primary">{localErr}</p> : null}
            <ul className="divide-y divide-black/10 border-y border-black/10">
              {findings.length === 0 ? (
                <li className="py-4 text-sm text-muted">Ningún hallazgo manual registrado todavía.</li>
              ) : (
                findings.map((f) => (
                  <li key={f.uuid} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-medium text-ink">{f.title}</span>
                      <span className="rounded bg-black/6 px-1.5 py-0.5 text-xs font-medium text-muted">
                        {f.severity}
                      </span>
                      <span className="text-xs text-muted">{f.discipline}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink">{f.description}</p>
                    {f.evidence_ref ? (
                      <p className="mt-1 text-xs text-muted">Ref.: {f.evidence_ref}</p>
                    ) : null}
                    <p className="mt-1 text-xs text-muted">{new Date(f.created_at).toLocaleString()}</p>
                  </li>
                ))
              )}
            </ul>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm text-muted sm:col-span-2">
                Disciplina
                <input
                  className="du-input mt-1"
                  value={discipline}
                  onChange={(e) => setDiscipline(e.target.value)}
                  placeholder="ej. arquitectura, instalaciones"
                />
              </label>
              <label className="block text-sm text-muted">
                Severidad
                <select
                  className="du-input mt-1"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  {SEVERITY_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-muted">
                Título
                <input className="du-input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="block text-sm text-muted sm:col-span-2">
                Descripción
                <textarea
                  className="du-input mt-1 min-h-[88px]"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <label className="block text-sm text-muted sm:col-span-2">
                Referencia de evidencia (opcional)
                <input
                  className="du-input mt-1"
                  value={evidenceRef}
                  onChange={(e) => setEvidenceRef(e.target.value)}
                  placeholder="Plan, folio o enlace interno"
                />
              </label>
            </div>
            <WorkspaceActionButton
              type="button"
              disabled={submitBusy || !token}
              onAction={submit}
              successLabel="Hallazgo guardado"
              runningLabel="Guardando…"
            >
              Guardar hallazgo
            </WorkspaceActionButton>
          </div>
        </details>

      {showWorkflow ? (
        <section className="space-y-4" aria-label="Reportes de corrida">
          <h3 className="text-sm font-semibold text-ink">Reportes de corrida</h3>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={!canDownloadPdf || pdfBusy !== null}
              onClick={() => handleDownload('technical_excel')}
            >
              <FileWarning className="mr-2 h-4 w-4 text-muted" aria-hidden />
              {pdfBusy === 'technical_excel' ? 'Descargando…' : 'Reporte técnico de corrida (Excel)'}
            </button>
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={!canDownloadPdf || pdfBusy !== null}
              onClick={() => handleDownload('technical_pdf')}
            >
              <FileWarning className="mr-2 h-4 w-4 text-muted" aria-hidden />
              {pdfBusy === 'technical_pdf' ? 'Descargando…' : 'Reporte técnico de corrida (PDF)'}
            </button>
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={!canDownloadPdf || pdfBusy !== null}
              onClick={() => handleDownload('human')}
            >
              <FileWarning className="mr-2 h-4 w-4 text-muted" aria-hidden />
              {pdfBusy === 'human' ? 'Descargando…' : 'Reporte de coordinación (PDF)'}
            </button>
          </div>
        </section>
      ) : null}

      {showWorkflow ? (
        <section className="space-y-4 border-t border-black/10 pt-6" aria-label="Informes finales">
          <h3 className="text-sm font-semibold text-ink">Exportar informe final</h3>
          <p className="text-xs text-muted">
            Incluye las decisiones registradas o el estado inicial detectado por el motor si aún no se revisó.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={pdfBusy !== null}
              onClick={() => handleDownload('final_technical_excel')}
            >
              {pdfBusy === 'final_technical_excel' ? 'Descargando…' : 'Exportar informe técnico final (Excel)'}
            </button>
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={pdfBusy !== null}
              onClick={() => handleDownload('final_technical_pdf')}
            >
              {pdfBusy === 'final_technical_pdf' ? 'Descargando…' : 'Exportar informe técnico final (PDF)'}
            </button>
            <button
              type="button"
              className="du-pill-action disabled:opacity-50"
              disabled={pdfBusy !== null}
              onClick={() => handleDownload('final_human')}
            >
              {pdfBusy === 'final_human' ? 'Descargando…' : 'Lista de chequeo GA-FO-08 (PDF)'}
            </button>
          </div>
        </section>
      ) : null}

      <footer className="flex flex-col gap-3 border-t border-black/10 bg-white pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1 text-sm text-muted">
          <p>{report.footer_status_message}</p>
          {pdfError ? <p className="mt-1 text-xs text-primary">{pdfError}</p> : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <PrimaryButton
            type="button"
            className="inline-flex items-center gap-2 normal-case tracking-normal"
            onClick={() => onContinueToPliego()}
          >
            Continuar al pliego
            <ChevronRight className="h-4 w-4" aria-hidden />
          </PrimaryButton>
        </div>
      </footer>
    </div>
  )
}
