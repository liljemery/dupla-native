import { Trash2 } from 'lucide-react'

import type { BudgetRow } from '../../types/budget'
import {
  newBlankBudgetLine,
  processBudgetRows,
  rowsForSave,
  type ProcessedBudgetRow,
} from '../../lib/budgetRows'
import { WorkspaceActionButton } from './WorkspaceActionButton'

function fmtDop(n: unknown): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('es-DO', {
    style: 'currency',
    currency: 'DOP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

function fmtUsd(n: unknown, tcRate = 58.5): string {
  const num = Number(n) || 0
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num / tcRate)
}

function fmtQty(q: unknown): string {
  if (q == null || q === '') return ''
  const num = Number(q) || 0
  return new Intl.NumberFormat('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num)
}

function budgetLineProvenanceTooltip(row: ProcessedBudgetRow): string | undefined {
  if (row.row_type !== 'line') return undefined
  const meta = row.metadata
  if (!meta) return undefined
  const parts: string[] = []
  const file = String(meta.source_file ?? '').trim()
  if (file) parts.push(`Plano: ${file}`)
  const level = String(meta.level_name ?? '').trim()
  if (level) parts.push(`Nivel: ${level}`)
  if (meta.requiere_revision) parts.push('Requiere revision')
  return parts.length > 0 ? parts.join('\n') : undefined
}

type BudgetEditableTableProps = {
  rows: BudgetRow[]
  onRowsChange: (rows: BudgetRow[]) => void
  onSave: (rows: BudgetRow[]) => Promise<boolean>
  saveError: string | null
}

export function BudgetEditableTable({ rows, onRowsChange, onSave, saveError }: BudgetEditableTableProps) {
  const processed = processBudgetRows(rows)

  function patchRow(index: number, patch: Partial<BudgetRow>) {
    onRowsChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)))
  }

  function patchAmount(index: number, raw: string, row: ProcessedBudgetRow) {
    const amount = Number(raw) || 0
    if (row.row_type === 'line') {
      const qty = Number(row.quantity) || 0
      const unitPrice = qty > 0 ? amount / qty : Number(row.unit_price) || 0
      patchRow(index, { unit_price: Math.round(unitPrice * 100) / 100 })
      return
    }
    patchRow(index, {
      amount,
      metadata: { ...(row.metadata ?? {}), manual_amount: true },
    })
  }

  function removeRow(index: number) {
    onRowsChange(rows.filter((_, i) => i !== index))
  }

  function addLine() {
    onRowsChange([...rows, newBlankBudgetLine()])
  }

  function addSection() {
    onRowsChange([
      ...rows,
      {
        row_type: 'chapter',
        code: '',
        nat: '',
        unit: '',
        summary: 'Nueva seccion',
        quantity: null,
        unit_price: 0,
        amount: 0,
      },
    ])
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">Edita codigo, partida, cantidades y precios. Guarda para persistir.</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-black/15 px-3 py-1.5 text-xs font-semibold text-ink hover:bg-black/5"
            onClick={addSection}
          >
            + Seccion
          </button>
          <button
            type="button"
            className="rounded-lg border border-black/15 px-3 py-1.5 text-xs font-semibold text-ink hover:bg-black/5"
            onClick={addLine}
          >
            + Partida
          </button>
          <WorkspaceActionButton
            type="button"
            onAction={async () => onSave(rowsForSave(processed))}
            successLabel="Presupuesto guardado"
            errorLabel="No se pudo guardar"
          >
            Guardar presupuesto
          </WorkspaceActionButton>
        </div>
      </div>
      {saveError ? <p className="text-sm text-primary">{saveError}</p> : null}

      <div className="overflow-x-auto rounded-lg border border-black/10">
        <table className="w-full min-w-[980px] border-collapse text-left text-sm">
          <thead className="border-b border-black/10 bg-[#f8f9fb] text-[11px] font-bold uppercase tracking-wide text-muted">
            <tr>
              <th className="w-8 px-2 py-3" />
              <th className="px-2 py-3">Codigo</th>
              <th className="min-w-[220px] px-2 py-3">Partida</th>
              <th className="px-2 py-3">Cantidad</th>
              <th className="px-2 py-3">UD</th>
              <th className="px-2 py-3">P/UD (RD$)</th>
              <th className="px-2 py-3 text-right">Total RD$</th>
              <th className="px-2 py-3 text-right">Total USD</th>
            </tr>
          </thead>
          <tbody>
            {processed.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-sm text-muted">
                  Sin partidas. Agrega una seccion o partida.
                </td>
              </tr>
            ) : (
              processed.map((r, i) => {
                const isLine = r.row_type === 'line' || !r.row_type
                const isChapter = r.row_type === 'chapter'
                const rowClass = isChapter ? 'bg-primary/5 font-semibold' : ''
                const provenanceTip = budgetLineProvenanceTooltip(r)
                const total = r.computed_amount ?? 0
                return (
                  <tr key={`${i}-${r.code}`} className={`border-b border-black/6 ${rowClass}`}>
                    <td className="px-1 py-1">
                      <button
                        type="button"
                        className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"
                        title="Eliminar fila"
                        onClick={() => removeRow(i)}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </td>
                    <td className="px-1 py-1">
                      <input
                        className="du-input w-full min-w-[72px] py-1 text-xs font-mono"
                        value={r.code}
                        onChange={(e) => patchRow(i, { code: e.target.value })}
                      />
                    </td>
                    <td className="px-1 py-1" title={provenanceTip}>
                      <input
                        className="du-input w-full py-1 text-sm"
                        value={r.summary}
                        onChange={(e) => patchRow(i, { summary: e.target.value })}
                      />
                    </td>
                    <td className="px-1 py-1">
                      {isLine ? (
                        <input
                          className="du-input w-24 py-1 text-sm tabular-nums"
                          type="number"
                          step="any"
                          value={r.quantity ?? ''}
                          onChange={(e) =>
                            patchRow(i, { quantity: e.target.value === '' ? null : Number(e.target.value) })
                          }
                        />
                      ) : (
                        <span className="px-2 text-muted">{fmtQty(r.computed_quantity ?? r.quantity)}</span>
                      )}
                    </td>
                    <td className="px-1 py-1">
                      {isLine ? (
                        <input
                          className="du-input w-16 py-1 text-sm uppercase"
                          value={r.unit}
                          onChange={(e) => patchRow(i, { unit: e.target.value })}
                        />
                      ) : (
                        <span className="px-2 text-muted">{r.unit || '—'}</span>
                      )}
                    </td>
                    <td className="px-1 py-1">
                      {isLine ? (
                        <input
                          className="du-input w-28 py-1 text-sm tabular-nums"
                          type="number"
                          step="any"
                          value={r.unit_price ?? ''}
                          onChange={(e) => patchRow(i, { unit_price: Number(e.target.value) || 0 })}
                        />
                      ) : (
                        <span className="px-2 tabular-nums text-muted">{fmtDop(r.computed_unit_price)}</span>
                      )}
                    </td>
                    <td className="px-1 py-1">
                      <input
                        className="du-input w-32 py-1 text-right text-sm tabular-nums font-semibold"
                        type="number"
                        step="any"
                        value={Math.round(total * 100) / 100}
                        onChange={(e) => patchAmount(i, e.target.value, r)}
                      />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-muted">
                      {fmtUsd(total)}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export { fmtDop, fmtUsd }
