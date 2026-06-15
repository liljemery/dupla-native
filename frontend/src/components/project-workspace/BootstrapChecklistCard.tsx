import { ClipboardCheck } from 'lucide-react'

import { bootstrapRequiredPercent } from '../../lib/bootstrapCriteria'
import type { BootstrapCriterion } from '../../types/project'
import { Card } from '../Card'
import { WorkspaceActionButton } from './WorkspaceActionButton'

type Props = {
  criteria: BootstrapCriterion[]
  onChange: (next: BootstrapCriterion[]) => void
  onSave: () => boolean | void | Promise<boolean | void>
  prominent?: boolean
  editable?: boolean
  id?: string
}

export function BootstrapChecklistCard({
  criteria,
  onChange,
  onSave,
  prominent = false,
  editable = true,
  id = 'bootstrap-checklist',
}: Props) {
  const stats = bootstrapRequiredPercent(criteria)

  return (
    <Card
      id={id}
      className={`space-y-4 p-6 ${prominent ? 'border-primary/35 bg-primary/[0.04] ring-1 ring-primary/15' : ''}`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${
            prominent ? 'bg-primary text-white' : 'bg-primary/12 text-primary'
          }`}
        >
          <ClipboardCheck className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-ink">Checklist de arranque</h2>
          <p className="mt-1 text-sm text-muted">
            {editable
              ? 'Documentos requeridos antes de pasar a «Esperando archivos». Marca los ítems obligatorios y guarda.'
              : 'Checklist completado en la fase de arranque. Ya no es editable en esta etapa del flujo.'}
          </p>
        </div>
      </div>
      <p className="text-sm text-muted">
        {stats.pct != null ? (
          <>
            Progreso (obligatorios): <strong className="text-ink">{stats.pct}%</strong> — {stats.label}
          </>
        ) : (
          stats.label
        )}
      </p>
      <ul className="space-y-2">
        {criteria.map((c, i) => (
          <li key={c.id} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={!!c.done}
              disabled={!editable}
              onChange={(e) => {
                if (!editable) return
                const next = [...criteria]
                next[i] = { ...next[i], done: e.target.checked }
                onChange(next)
              }}
            />
            <span>
              {c.label}
              {c.required ? <span className="text-primary"> *</span> : null}
            </span>
          </li>
        ))}
      </ul>
      {editable ? (
        <WorkspaceActionButton type="button" onAction={onSave} successLabel="Checklist guardado">
          Guardar checklist
        </WorkspaceActionButton>
      ) : null}
    </Card>
  )
}
