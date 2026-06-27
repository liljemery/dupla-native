import { apiFetch } from '../../api/client'
import {
  canMarkControlReview,
  canMarkManagementReview,
} from '../../lib/accessPermissions'
import { useAuthStore } from '../../store/authStore'
import type { SubcontractQuoteRow } from '../../types/projectWorkspace'
import type { Project } from '../../types/project'
import { Card } from '../Card'
import { WorkspaceActionButton } from './WorkspaceActionButton'

const DEFAULT_CURRENCY = 'DOP'

type BudgetPipelineSharedProps = {
  project: Project
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
}

function fmtLinePrice(price: unknown, currency: string): string {
  const num = Number(price) || 0
  if (currency === 'DOP') {
    return new Intl.NumberFormat('es-DO', {
      style: 'currency',
      currency: 'DOP',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num)
  }
  return `${num.toLocaleString('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
}

export function BudgetChecklistPanel({
  project,
  role,
  bpDraft,
  setBpDraft,
  clientVersion,
  setClientVersion,
  onSaveBudgetPipeline,
}: Pick<
  BudgetPipelineSharedProps,
  | 'project'
  | 'role'
  | 'bpDraft'
  | 'setBpDraft'
  | 'clientVersion'
  | 'setClientVersion'
  | 'onSaveBudgetPipeline'
>) {
  const permissions = useAuthStore((s) => s.permissions)
  const canMarkControl = canMarkControlReview(permissions)
  const canMarkGerencia = canMarkManagementReview(permissions)
  const phase = project.workflow_phase
  const awaitingGerencia = phase === 'MANAGEMENT_APPROVAL'
  const afterGerencia = phase === 'BUDGET_APPROVED' || phase === 'COMPLETE'
  const missingGerenciaGate = awaitingGerencia && !bpDraft.management_review_done

  return (
    <Card className="space-y-4 p-6">
      <h3 className="text-base font-semibold text-ink">Checklist del presupuesto</h3>
      <p className="text-sm text-muted">
        Marca los hitos del pipeline antes de enviar a gerencia. Control valida antes del envío; Gerencia aprueba en
        la fase «Aprobación de gerencia».
      </p>
      {missingGerenciaGate ? (
        <div className="rounded-md border border-primary/25 bg-primary/6 px-3 py-2 text-sm text-ink">
          Para avanzar en Flujo: marca la aprobación de Gerencia abajo y guarda el checklist.{' '}
          <span className="font-medium text-primary">Falta revisión de Gerencia.</span>
        </div>
      ) : null}
      <div className="space-y-3 border-t border-black/10 pt-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Hitos</p>
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
              {volumetryLocked ? <span className="text-xs text-muted">(automático)</span> : null}
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
          {!canMarkControl ? <span className="text-xs text-muted">(solo Control o Gerencia)</span> : null}
        </label>
      </div>
      {(awaitingGerencia || afterGerencia || phase === 'BUDGETING_PIPELINE') ? (
        <div className="space-y-2 border-l-2 border-primary/35 pl-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Gerencia</p>
          <label className={`flex items-center gap-2 text-sm ${!canMarkGerencia ? 'opacity-60' : ''}`}>
            <input
              type="checkbox"
              disabled={!canMarkGerencia || phase === 'BUDGETING_PIPELINE'}
              checked={!!bpDraft.management_review_done}
              onChange={(e) => setBpDraft((d) => ({ ...d, management_review_done: e.target.checked }))}
            />
            Aprobación de Gerencia completada
            {!canMarkGerencia ? <span className="text-xs text-muted">(solo Gerencia)</span> : null}
            {phase === 'BUDGETING_PIPELINE' ? (
              <span className="text-xs text-muted">(disponible en aprobación de gerencia)</span>
            ) : null}
          </label>
        </div>
      ) : null}
      {afterGerencia ? (
        <div className="space-y-2 border-t border-black/10 pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Cliente (opcional)</p>
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
      ) : null}
      <WorkspaceActionButton type="button" onAction={onSaveBudgetPipeline} successLabel="Checklist guardado">
        Guardar checklist
      </WorkspaceActionButton>
    </Card>
  )
}

export function BudgetQuotesPanel({
  projectUuid,
  token,
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
}: Pick<
  BudgetPipelineSharedProps,
  | 'projectUuid'
  | 'token'
  | 'newQuoteTitle'
  | 'setNewQuoteTitle'
  | 'activeQuote'
  | 'setActiveQuote'
  | 'lineItem'
  | 'setLineItem'
  | 'linePrice'
  | 'setLinePrice'
  | 'quotes'
  | 'onLoadAuxLists'
>) {
  return (
    <Card className="space-y-4 p-6">
      <h3 className="text-base font-semibold text-ink">Cotizaciones de subcontratación</h3>
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
          placeholder="Precio (RD$)"
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
                currency: DEFAULT_CURRENCY,
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
      {quotes.length === 0 ? (
        <p className="text-sm text-muted">Aún no hay cotizaciones en este proyecto.</p>
      ) : (
        quotes.map((q) => (
          <div key={q.uuid} className="rounded border border-black/5 p-3 text-sm">
            <div className="font-medium">{q.title ?? 'Sin título'}</div>
            <ul className="mt-2 list-disc pl-5 text-muted">
              {q.lines.map((l) => (
                <li key={l.uuid}>
                  {l.item_label} — {fmtLinePrice(l.price, l.currency === 'MXN' ? 'DOP' : l.currency)}
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </Card>
  )
}
