import { Card } from '../../Card'
import { WorkspaceActionButton } from '../WorkspaceActionButton'
import type { RevisionRow } from '../../../types/projectWorkspace'

const REVISION_ROLE_LABELS: Record<string, string> = {
  ARQUITECTURA: 'Arquitectura',
  CONTROL: 'Control',
  PRESUPUESTO: 'Presupuesto',
  GERENCIA: 'Gerencia',
}

type WorkspaceRevisionesTabProps = {
  flowMsg: string | null
  revDecision: string
  setRevDecision: React.Dispatch<React.SetStateAction<string>>
  revNotes: string
  setRevNotes: React.Dispatch<React.SetStateAction<string>>
  revisions: RevisionRow[]
  onSubmitRevision: () => boolean | void | Promise<boolean | void>
}

export function WorkspaceRevisionesTab({
  flowMsg,
  revDecision,
  setRevDecision,
  revNotes,
  setRevNotes,
  revisions,
  onSubmitRevision,
}: WorkspaceRevisionesTabProps) {
  return (
    <Card className="space-y-4 p-6">
      <h2 className="text-lg font-semibold text-ink">Revisiones</h2>
      <p className="text-sm text-muted">
        Cada registro queda asociado a tu rol (arquitectura, control, presupuesto o gerencia). Para pasar del paso de{' '}
        <span className="font-medium text-ink">revisión de arquitectura</span> al paso de{' '}
        <span className="font-medium text-ink">pliego de condiciones</span>, la última revisión pertinente debe estar{' '}
        <span className="font-medium text-ink">aprobada</span>. En{' '}
        <span className="font-medium text-ink">aprobación de gerencia</span>, un usuario Gerencia debe registrar al
        menos una revisión aquí antes de avanzar de fase.
      </p>
      {flowMsg ? <p className="text-sm text-primary">{flowMsg}</p> : null}
      <div className="space-y-3 border-b border-black/10 pb-4">
        <label className="block text-sm text-muted">
          Decisión
          <select className="du-input mt-1" value={revDecision} onChange={(e) => setRevDecision(e.target.value)}>
            <option value="APPROVED">APPROVED</option>
            <option value="REJECTED">REJECTED</option>
            <option value="PARTIAL">PARTIAL</option>
          </select>
        </label>
        <label className="block text-sm text-muted">
          Notas
          <textarea className="du-input mt-1 min-h-[80px]" value={revNotes} onChange={(e) => setRevNotes(e.target.value)} />
        </label>
        <WorkspaceActionButton
          type="button"
          onAction={onSubmitRevision}
          successLabel="Revisión registrada"
          runningLabel="Registrando…"
        >
          Registrar revisión
        </WorkspaceActionButton>
      </div>
      <ul className="space-y-2 text-sm">
        {revisions.map((r) => {
          const roleLabel = REVISION_ROLE_LABELS[r.revision_role] ?? r.revision_role
          return (
            <li key={r.uuid} className="rounded border border-black/10 px-3 py-2">
              <span className="font-medium">Revisión de {roleLabel}</span>
              <span className="text-muted"> · {r.decision}</span>
              <span className="du-meta ml-2 text-xs">
                {new Date(r.created_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
              </span>
              {r.notes ? <p className="mt-1 text-muted">{r.notes}</p> : null}
            </li>
          )
        })}
      </ul>
      {revisions.length === 0 ? <p className="text-sm text-muted">Sin revisiones.</p> : null}
    </Card>
  )
}
