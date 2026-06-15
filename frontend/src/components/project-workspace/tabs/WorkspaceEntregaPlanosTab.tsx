import { useState } from 'react'

import { Card } from '../../Card'
import { PrimaryButton } from '../../PrimaryButton'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import { PLAN_DELIVERY_STATUS_OPTIONS } from '../../../constants/planDeliveryStatus'
import type { PlanDeliveryRow } from '../../../types/planDelivery'

type AddPayload = { description?: string; request_date?: string | null }

type WorkspaceEntregaPlanosTabProps = {
  projectUuid: string
  token: string | null
  planDeliveryRows: PlanDeliveryRow[]
  planDeliveryMsg: string | null
  setPlanDeliveryRows: React.Dispatch<React.SetStateAction<PlanDeliveryRow[]>>
  onAddRow: (payload?: AddPayload) => Promise<boolean> | boolean
  onPatchRow: (rowUuid: string, patch: Record<string, unknown>) => void
  onDeleteRow: (rowUuid: string) => void
}

export function WorkspaceEntregaPlanosTab({
  projectUuid,
  token,
  planDeliveryRows,
  planDeliveryMsg,
  setPlanDeliveryRows,
  onAddRow,
  onPatchRow,
  onDeleteRow,
}: WorkspaceEntregaPlanosTabProps) {
  const [modalOpen, setModalOpen] = useState(false)
  const [draftDescription, setDraftDescription] = useState('')
  const [draftRequestDate, setDraftRequestDate] = useState('')

  const visibleRows = planDeliveryRows.filter((r) => r.status !== 'CANCELADO')

  function openModal() {
    setDraftDescription('')
    setDraftRequestDate('')
    setModalOpen(true)
  }

  async function submitModal(): Promise<boolean> {
    const result = await Promise.resolve(
      onAddRow({
        description: draftDescription,
        request_date: draftRequestDate.trim() ? draftRequestDate : null,
      }),
    )
    if (result !== false) setModalOpen(false)
    return result !== false
  }

  return (
    <Card className="space-y-3 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-ink sm:text-lg">Control entrega de planos</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted sm:text-sm">
            Registro tipo GA-FO-03. Cada solicitud recibe un número <span className="font-mono">SDP NNNN</span> único en
            este proyecto. La columna «Cant. días» muestra el valor registrado o la diferencia entre fechas de solicitud
            y entrega. La tabla lista solo solicitudes activas (se ocultan canceladas).
          </p>
        </div>
        <PrimaryButton
          type="button"
          className="w-full shrink-0 sm:ml-auto sm:w-auto"
          disabled={!token || !projectUuid}
          onClick={openModal}
        >
          Nueva solicitud
        </PrimaryButton>
      </div>
      {planDeliveryMsg ? <p className="text-xs text-primary sm:text-sm">{planDeliveryMsg}</p> : null}
      <div className="overflow-x-auto rounded border border-black/10">
        <table className="w-full min-w-[34rem] text-left text-[11px] leading-tight sm:min-w-[40rem] sm:text-xs">
          <thead className="bg-black/[0.04] text-[10px] font-semibold uppercase tracking-wide text-muted sm:text-[11px]">
            <tr>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">No.</th>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">F. solicitud</th>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">No. sol.</th>
              <th className="min-w-[8rem] px-1.5 py-1 sm:px-2 sm:py-1.5">Descripción</th>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">F. entrega</th>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">Cant. días</th>
              <th className="px-1.5 py-1 sm:px-2 sm:py-1.5">Estado</th>
              <th className="w-14 px-1.5 py-1 sm:px-2 sm:py-1.5" />
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, idx) => (
              <tr key={row.uuid} className="border-t border-black/5 odd:bg-black/[0.015]">
                <td className="px-1.5 py-1 align-top tabular-nums text-muted sm:px-2 sm:py-1.5">{idx + 1}</td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <input
                    type="date"
                    className="du-input max-w-full py-1 text-[11px] sm:w-[9.5rem] sm:text-xs"
                    value={row.request_date ? row.request_date.slice(0, 10) : ''}
                    onChange={(e) => {
                      const v = e.target.value
                      void onPatchRow(row.uuid, {
                        request_date: v ? v : null,
                      })
                    }}
                    aria-label="Fecha de solicitud"
                  />
                </td>
                <td className="px-1.5 py-1 align-top font-mono text-[10px] text-ink sm:px-2 sm:py-1.5 sm:text-[11px]">
                  {row.request_number}
                </td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <input
                    className="du-input min-w-0 max-w-[14rem] py-1 text-[11px] sm:max-w-[18rem] sm:text-xs"
                    value={row.description}
                    onChange={(e) => {
                      const v = e.target.value
                      setPlanDeliveryRows((prev) =>
                        prev.map((r) => (r.uuid === row.uuid ? { ...r, description: v } : r)),
                      )
                    }}
                    onBlur={(e) => {
                      const v = e.target.value.trim()
                      void onPatchRow(row.uuid, { description: v })
                    }}
                    aria-label="Descripción"
                  />
                </td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <input
                    type="date"
                    className="du-input max-w-full py-1 text-[11px] sm:w-[9.5rem] sm:text-xs"
                    value={row.delivery_date ? row.delivery_date.slice(0, 10) : ''}
                    onChange={(e) => {
                      const v = e.target.value
                      void onPatchRow(row.uuid, {
                        delivery_date: v ? v : null,
                      })
                    }}
                    aria-label="Fecha de entrega"
                  />
                </td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <input
                    type="number"
                    min={0}
                    className="du-input w-14 py-1 text-[11px] sm:w-16 sm:text-xs"
                    placeholder="Auto"
                    defaultValue={row.days_count ?? ''}
                    key={`${row.uuid}-days-${row.updated_at}`}
                    onBlur={(e) => {
                      const raw = e.target.value.trim()
                      const n = raw === '' ? null : Number(raw)
                      void onPatchRow(row.uuid, {
                        days_count: n === null || Number.isNaN(n) ? null : n,
                      })
                    }}
                    aria-label="Cantidad de días"
                  />
                  {row.days_resolved != null ? (
                    <div className="du-meta mt-0.5 text-[10px]">Calc: {row.days_resolved}</div>
                  ) : null}
                </td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <select
                    className="du-input max-w-[6.5rem] py-1 text-[11px] sm:max-w-none sm:text-xs"
                    value={row.status}
                    onChange={(e) => void onPatchRow(row.uuid, { status: e.target.value })}
                    aria-label="Estado"
                  >
                    {PLAN_DELIVERY_STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-1.5 py-1 align-top sm:px-2 sm:py-1.5">
                  <button
                    type="button"
                    className="text-[11px] font-medium text-primary underline-offset-2 hover:underline sm:text-xs"
                    onClick={() => void onDeleteRow(row.uuid)}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visibleRows.length === 0 ? (
        <p className="text-xs text-muted sm:text-sm">
          No hay solicitudes activas. Usa «Nueva solicitud» para crear la primera.
        </p>
      ) : null}

      {modalOpen ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setModalOpen(false)
          }}
        >
          <div
            className="w-full max-w-md rounded-xl border border-black/10 bg-white p-5 shadow-xl"
            role="dialog"
            aria-labelledby="plan-delivery-modal-title"
            aria-modal="true"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 id="plan-delivery-modal-title" className="text-base font-semibold text-ink sm:text-lg">
              Nueva solicitud de planos
            </h3>
            <p className="mt-1 text-xs text-muted sm:text-sm">
              Se asignará un número SDP automático. Puedes completar el resto de campos en la tabla.
            </p>
            <label htmlFor="plan-delivery-modal-desc" className="du-label mt-4 block text-xs">
              Descripción
            </label>
            <textarea
              id="plan-delivery-modal-desc"
              className="du-input mt-1 min-h-[4rem] w-full resize-y text-sm"
              value={draftDescription}
              onChange={(e) => setDraftDescription(e.target.value)}
              placeholder="Ej. Plano de arquitectura planta baja"
              rows={3}
            />
            <label htmlFor="plan-delivery-modal-date" className="du-label mt-3 block text-xs">
              Fecha de solicitud (opcional)
            </label>
            <input
              id="plan-delivery-modal-date"
              type="date"
              className="du-input mt-1 w-full max-w-[12rem] text-sm"
              value={draftRequestDate}
              onChange={(e) => setDraftRequestDate(e.target.value)}
            />
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="rounded-lg border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5"
                onClick={() => setModalOpen(false)}
              >
                Cancelar
              </button>
              <WorkspaceActionButton
                type="button"
                disabled={!token || !projectUuid}
                onAction={submitModal}
                successLabel="Solicitud creada"
              >
                Crear solicitud
              </WorkspaceActionButton>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
