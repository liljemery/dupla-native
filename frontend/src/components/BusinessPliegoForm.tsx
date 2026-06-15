import { useMemo, useState } from 'react'
import { ChevronRight, Printer, Download } from 'lucide-react'

import { CONSTRUCTION_PLIEGO_CHAPTERS } from '../constants/constructionPliegoStructure'
import { confirmPliegoSectionApproval } from '../lib/duplaAlert'
import {
  constructionChapterProgress,
  isConstructionChapterComplete,
  lineSubtotal,
} from '../lib/constructionPliegoState'
import { confirmAction } from '../lib/duplaAlert'
import type { ConstructionLineValue } from '../types/constructionPliego'

import { WorkspaceActionButton } from './project-workspace/WorkspaceActionButton'

type BusinessPliegoFormProps = {
  documentTitle: string
  lineValues: Record<string, ConstructionLineValue>
  onLineChange: (idItem: string, patch: Partial<ConstructionLineValue>) => void
  specSummary: string
  onSpecSummaryChange: (value: string) => void
  onGenerate: (force: boolean) => Promise<void>
  generateBusy: boolean
  saveBusy: boolean
  onSave: () => boolean | void | Promise<boolean | void>
  approved: boolean
  generatedAt: string | null
  flowMsg: string | null
  onExportPdf?: () => void
  onExportXlsx?: () => void
  approvedChapters?: Record<number, string>
  canApproveChapter?: boolean
  onApproveChapter?: (chapterNum: number) => void
}

function fmtMoney(n: number): string {
  return new Intl.NumberFormat('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export function BusinessPliegoForm({
  documentTitle,
  lineValues,
  onLineChange,
  specSummary,
  onSpecSummaryChange,
  onGenerate,
  generateBusy,
  saveBusy,
  onSave,
  approved,
  generatedAt,
  flowMsg,
  onExportPdf,
  onExportXlsx,
  approvedChapters = {},
  canApproveChapter = false,
  onApproveChapter,
}: BusinessPliegoFormProps) {
  const [open, setOpen] = useState<Record<number, boolean>>(() => {
    const o: Record<number, boolean> = {}
    CONSTRUCTION_PLIEGO_CHAPTERS.forEach((ch, i) => {
      o[ch.num] = i < 2
    })
    return o
  })

  const chapterSubtotals = useMemo(() => {
    const out: Record<number, number> = {}
    for (const ch of CONSTRUCTION_PLIEGO_CHAPTERS) {
      let s = 0
      for (const it of ch.items) {
        const sub = lineSubtotal(lineValues[it.id_item] ?? { unidad: '', cantidad: '', unitario: '' })
        if (sub != null) s += sub
      }
      out[ch.num] = Math.round(s * 100) / 100
    }
    return out
  }, [lineValues])

  const docTotal = useMemo(
    () => Math.round(Object.values(chapterSubtotals).reduce((a, b) => a + b, 0) * 100) / 100,
    [chapterSubtotals],
  )

  function toggleChapter(num: number) {
    setOpen((prev) => ({ ...prev, [num]: !prev[num] }))
  }

  async function approveChapter(chapterNum: number, chapterTitle: string, chapterSubtotal: number) {
    if (!canApproveChapter || !onApproveChapter || approvedChapters[chapterNum]) return
    if (!isConstructionChapterComplete(chapterNum, lineValues)) return
    const costHint = `El subtotal de esta sección (${fmtMoney(chapterSubtotal)}) se asumirá como base para el presupuesto maestro del proyecto.`
    if (
      !(await confirmPliegoSectionApproval({
        sectionTitle: `${chapterNum}. ${chapterTitle}`,
        costHint,
      }))
    ) {
      return
    }
    onApproveChapter(chapterNum)
  }

  return (
    <div className="relative overflow-hidden rounded-xl border border-black/10 bg-white shadow-[var(--shadow-card)] print:border-0 print:shadow-none">
      {!approved ? (
        <div
          className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center overflow-hidden"
          aria-hidden
        >
          <span className="rotate-[-18deg] select-none text-[clamp(3rem,14vw,8rem)] font-black uppercase tracking-widest text-black/[0.045]">
            Borrador
          </span>
        </div>
      ) : null}

      <div className="relative z-10 border-b border-black/10 bg-white/95 px-4 py-4 sm:px-6 print:px-0">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">Documento técnico</p>
            <h3 className="mt-1 text-xl font-bold tracking-tight text-ink sm:text-2xl">{documentTitle}</h3>
            {generatedAt ? (
              <p className="mt-1 text-xs text-muted">
                Borrador generado: {new Date(generatedAt).toLocaleString()}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            <button
              type="button"
              className="rounded-lg border border-black/12 p-2 text-muted transition hover:bg-black/[0.04] hover:text-ink"
              title="Imprimir"
              aria-label="Imprimir"
              onClick={() => window.print()}
            >
              <Printer className="size-5" strokeWidth={2} aria-hidden />
            </button>
            {onExportPdf ? (
              <button
                type="button"
                className="rounded-lg border border-black/12 p-2 text-muted transition hover:bg-black/[0.04] hover:text-ink"
                title="Descargar PDF"
                aria-label="Descargar PDF"
                onClick={onExportPdf}
              >
                <Download className="size-5" strokeWidth={2} aria-hidden />
              </button>
            ) : null}
            {onExportXlsx ? (
              <button
                type="button"
                className="rounded-lg border border-black/12 px-2 py-2 text-xs font-semibold text-ink transition hover:bg-black/[0.04]"
                onClick={onExportXlsx}
              >
                Excel
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 print:hidden">
          <button
            type="button"
            className="rounded-lg border border-primary/35 bg-primary/[0.08] px-3 py-2 text-xs font-semibold uppercase tracking-wide text-primary hover:bg-primary/[0.12] disabled:opacity-50"
            disabled={generateBusy}
            onClick={() => void onGenerate(false)}
          >
            {generateBusy ? 'Generando…' : 'Generar borrador'}
          </button>
          <button
            type="button"
            className="rounded-lg border border-black/15 bg-white px-3 py-2 text-xs font-medium text-ink hover:bg-black/[0.03] disabled:opacity-50"
            disabled={generateBusy}
            onClick={() => {
              void (async () => {
                if (
                  await confirmAction({
                    title: '¿Regenerar?',
                    text: 'Se reemplaza el borrador de texto auxiliar y se anula un pliego aprobado previo al guardar.',
                    confirmLabel: 'Regenerar',
                  })
                ) {
                  void onGenerate(true)
                }
              })()
            }}
          >
            Regenerar
          </button>
          <WorkspaceActionButton
            type="button"
            disabled={saveBusy}
            onAction={onSave}
            successLabel="Pliego guardado"
            runningLabel="Guardando…"
          >
            Guardar
          </WorkspaceActionButton>
        </div>
        {approved ? (
          <p className="mt-3 text-xs font-medium text-emerald-800">Pliego aprobado.</p>
        ) : null}
        {flowMsg ? <p className="mt-2 text-sm text-primary">{flowMsg}</p> : null}

        <div className="mt-4 border-t border-black/8 pt-4 print:hidden">
          <label className="text-xs font-semibold text-muted" htmlFor="bp-spec-summary">
            Resumen ejecutivo
          </label>
          <p className="mt-1 text-[11px] leading-relaxed text-muted">
            Síntesis para auditoría y exportaciones (mín. 10 caracteres si no usas partidas estructuradas en servidor).
          </p>
          <textarea
            id="bp-spec-summary"
            className="mt-2 min-h-[96px] w-full rounded-lg border border-black/12 bg-white p-3 text-sm leading-relaxed text-ink outline-none focus:border-primary/35 focus:ring-1 focus:ring-primary/25"
            value={specSummary}
            onChange={(e) => onSpecSummaryChange(e.target.value)}
            placeholder="Síntesis del alcance, supuestos y riesgos relevantes…"
            aria-label="Resumen ejecutivo del pliego"
          />
        </div>
      </div>

      <div className="relative z-10 divide-y divide-black/8 px-2 pb-4 pt-2 sm:px-4">
        {CONSTRUCTION_PLIEGO_CHAPTERS.map((chapter) => {
          const isOpen = open[chapter.num]
          const numLabel = String(chapter.num).padStart(2, '0')
          const chSub = chapterSubtotals[chapter.num] ?? 0
          const chapterApprovedAt = approvedChapters[chapter.num]
          const chapterComplete = isConstructionChapterComplete(chapter.num, lineValues)
          const progress = constructionChapterProgress(chapter.num, lineValues)

          return (
            <div key={chapter.num} className="bg-white">
              <div className="flex items-stretch gap-0">
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-3 px-2 py-3 text-left transition hover:bg-black/[0.02] sm:px-3"
                  aria-expanded={isOpen}
                  onClick={() => toggleChapter(chapter.num)}
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-bold text-white">
                    {numLabel}
                  </span>
                  <span className="min-w-0 flex-1 font-semibold text-ink">
                    {chapter.num}. {chapter.titulo}
                  </span>
                  {chapterApprovedAt ? (
                    <span className="shrink-0 rounded-md border border-emerald-600/25 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-900">
                      Aprobada
                    </span>
                  ) : (
                    <span className="hidden shrink-0 text-[10px] tabular-nums text-muted sm:inline">
                      {progress.done}/{progress.total} partidas
                    </span>
                  )}
                  <span className="hidden shrink-0 text-xs tabular-nums text-muted sm:inline">
                    Subtotal cap. {fmtMoney(chSub)}
                  </span>
                  <ChevronRight
                    className={`size-5 shrink-0 text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`}
                    aria-hidden
                  />
                </button>
                {canApproveChapter && !chapterApprovedAt ? (
                  <button
                    type="button"
                    className="shrink-0 border-l border-black/8 px-3 text-[11px] font-semibold uppercase tracking-wide text-primary transition hover:bg-primary/[0.06] disabled:cursor-not-allowed disabled:opacity-40 sm:px-4"
                    disabled={!chapterComplete}
                    title={
                      chapterComplete
                        ? undefined
                        : 'Completa unidad, cantidad y precio unitario en todas las partidas del capítulo'
                    }
                    onClick={() => void approveChapter(chapter.num, chapter.titulo, chSub)}
                  >
                    Aprobar sección
                  </button>
                ) : null}
              </div>
              {isOpen ? (
                <div className="border-t border-black/6 px-2 pb-4 pt-3 sm:px-4">
                  <div className="overflow-x-auto rounded-lg border border-black/10">
                    <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                      <thead className="border-b border-black/10 bg-[#f8f9fb] text-[10px] font-bold uppercase tracking-wide text-muted">
                        <tr>
                          <th className="whitespace-nowrap px-2 py-2 sm:px-3">Num</th>
                          <th className="min-w-[180px] px-2 py-2 sm:px-3">Partida</th>
                          <th className="whitespace-nowrap px-2 py-2 sm:px-3">Unidad</th>
                          <th className="whitespace-nowrap px-2 py-2 sm:px-3">Cantidad</th>
                          <th className="whitespace-nowrap px-2 py-2 sm:px-3">P/UD</th>
                          <th className="whitespace-nowrap px-2 py-2 text-right sm:px-3">Subtotal</th>
                        </tr>
                      </thead>
                      <tbody>
                        {chapter.items.map((it) => {
                          const v = lineValues[it.id_item] ?? {
                            unidad: it.unidad_default,
                            cantidad: '',
                            unitario: '',
                          }
                          const sub = lineSubtotal(v)
                          return (
                            <tr key={it.id_item} className="border-b border-black/[0.06] last:border-0">
                              <td className="whitespace-nowrap px-2 py-2 font-mono text-xs text-primary sm:px-3">
                                {it.id_item}
                              </td>
                              <td className="px-2 py-2 text-ink sm:px-3">{it.descripcion}</td>
                              <td className="px-2 py-2 sm:px-3">
                                <input
                                  className="du-input w-full min-w-[4.5rem] py-1.5 text-sm"
                                  value={v.unidad}
                                  onChange={(e) => onLineChange(it.id_item, { unidad: e.target.value })}
                                  aria-label={`Unidad ${it.id_item}`}
                                />
                              </td>
                              <td className="px-2 py-2 sm:px-3">
                                <input
                                  className="du-input w-full min-w-[5rem] py-1.5 text-sm tabular-nums"
                                  inputMode="decimal"
                                  value={v.cantidad}
                                  onChange={(e) => onLineChange(it.id_item, { cantidad: e.target.value })}
                                  aria-label={`Cantidad ${it.id_item}`}
                                />
                              </td>
                              <td className="px-2 py-2 sm:px-3">
                                <input
                                  className="du-input w-full min-w-[5rem] py-1.5 text-sm tabular-nums"
                                  inputMode="decimal"
                                  value={v.unitario}
                                  onChange={(e) => onLineChange(it.id_item, { unitario: e.target.value })}
                                  aria-label={`Precio unitario ${it.id_item}`}
                                />
                              </td>
                              <td className="whitespace-nowrap px-2 py-2 text-right text-sm font-semibold tabular-nums text-ink sm:px-3">
                                {sub != null ? fmtMoney(sub) : '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-right text-xs font-semibold text-muted">
                    Subtotal capítulo: <span className="text-primary">{fmtMoney(chSub)}</span>
                  </p>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>

      <div className="relative z-10 border-t border-black/10 bg-white/95 px-4 py-4 sm:px-6">
        <div className="flex flex-col items-end gap-1">
          <p className="text-[11px] font-bold uppercase tracking-wide text-muted">Total directo (partidas)</p>
          <p className="text-2xl font-bold tabular-nums text-primary">{fmtMoney(docTotal)}</p>
        </div>
      </div>
    </div>
  )
}
