import { canMarkControlReview } from '../../../lib/accessPermissions'
import { useAuthStore } from '../../../store/authStore'
import { apiFetch } from '../../../api/client'
import { Card } from '../../Card'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import type { SubcontractQuoteRow } from '../../../types/projectWorkspace'

type WorkspacePresupuestoTabProps = {
  role: string | null
  workflowPhase: string | null
  projectUuid: string
  token: string | null
  flowMsg: string | null
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

export function WorkspacePresupuestoTab({
  role,
  workflowPhase,
  projectUuid,
  token,
  flowMsg,
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
}: WorkspacePresupuestoTabProps) {
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const canMarkControl = canMarkControlReview(role as import('../../../constants/userRoles').UserRole | null, isTeamLeader)
  const awaitingBudgetApproval = workflowPhase === 'MANAGEMENT_APPROVAL'
  const missingControlGate = awaitingBudgetApproval && !bpDraft.control_review_done
  const missingClientVersion = awaitingBudgetApproval && !clientVersion.trim()
  return (
    <div className="space-y-6">
      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold text-ink">Pipeline de presupuesto</h2>
        <p className="text-sm text-muted">
          Esta fase sigue al <strong className="text-ink">pliego de condiciones</strong>. El orden operativo es:
        </p>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
          <li>Cotizaciones de subcontratación</li>
          <li>Volumetría</li>
          <li>Análisis de costo</li>
          <li>Presupuesto interno marcado como completo</li>
          <li className="font-medium text-ink">Revisión de Control</li>
          <li>Versión aprobada por el cliente registrada</li>
          <li>Avance a gerencia / cierre (desde la pestaña Flujo)</li>
        </ol>
        {flowMsg ? <p className="text-sm text-primary">{flowMsg}</p> : null}
        {awaitingBudgetApproval && (missingControlGate || missingClientVersion) ? (
          <div className="rounded-md border border-primary/25 bg-primary/[0.06] px-3 py-2 text-sm text-ink">
            Antes de pasar a «Presupuesto aprobado por cliente», debes marcar la revisión de Control y completar la
            etiqueta de versión del cliente (y guardar).{' '}
            {missingControlGate ? <span className="font-medium text-primary"> Falta revisión de Control.</span> : null}{' '}
            {missingClientVersion ? (
              <span className="font-medium text-primary"> Falta versión aprobada por el cliente.</span>
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
          ).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!bpDraft[key]}
                onChange={(e) => setBpDraft((d) => ({ ...d, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
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
        <h3 className="text-md font-semibold text-ink">Cotizaciones</h3>
        <div className="flex flex-wrap gap-2">
          <input
            className="du-input flex-1 min-w-[160px]"
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
            className="du-input flex-1 min-w-[120px]"
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
  )
}
