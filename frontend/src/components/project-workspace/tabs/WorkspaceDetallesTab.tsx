import { useState } from 'react'
import { Link } from 'react-router-dom'

import { apiFetch } from '../../../api/client'
import { projectKindLabel } from '../../../constants/projectKind'
import { downloadBlob, filenameFromContentDisposition } from '../../../lib/download'
import type { Project } from '../../../types/project'
import { Card } from '../../Card'

type WorkspaceDetallesTabProps = {
  project: Project | null
  projectError: string | null
  phaseLabel: string
  token: string | null
  onOpenChat: () => void
}

export function WorkspaceDetallesTab({
  project,
  projectError,
  phaseLabel,
  token,
  onOpenChat,
}: WorkspaceDetallesTabProps) {
  const [docBusy, setDocBusy] = useState(false)

  async function downloadDocumentaryReport() {
    if (!token || !project) return
    setDocBusy(true)
    try {
      const res = await apiFetch(`/api/projects/${project.uuid}/exports/documentary-report.pdf`, { token })
      if (!res.ok) return
      const blob = await res.blob()
      downloadBlob(blob, filenameFromContentDisposition(res, `informe-documental-${project.uuid}.pdf`))
    } finally {
      setDocBusy(false)
    }
  }

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold text-ink">Detalles del proyecto</h2>
      {projectError ? <p className="mt-3 text-sm text-primary">{projectError}</p> : null}
      {!project && !projectError ? <p className="mt-3 text-sm text-muted">Cargando…</p> : null}
      {project ? (
        <>
          <dl className="mt-6 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="du-meta">Nombre</dt>
              <dd className="mt-1 text-sm font-medium text-ink">{project.name}</dd>
            </div>
            <div>
              <dt className="du-meta">Cliente</dt>
              <dd className="mt-1 text-sm text-ink">{project.client_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="du-meta">Tipo de proyecto</dt>
              <dd className="mt-1 text-sm text-ink">{projectKindLabel(project.project_kind)}</dd>
            </div>
            <div>
              <dt className="du-meta">Estado legado</dt>
              <dd className="mt-1 text-sm text-ink">{project.status}</dd>
            </div>
            <div>
              <dt className="du-meta">Fase del flujo</dt>
              <dd className="mt-1 text-sm font-medium text-ink">{phaseLabel}</dd>
            </div>
            <div>
              <dt className="du-meta">Código de proyecto</dt>
              <dd className="mt-1 text-sm text-ink">{project.project_code ?? '—'}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="du-meta">Ubicación</dt>
              <dd className="mt-1 text-sm text-ink">{project.location_text ?? '—'}</dd>
            </div>
            <div>
              <dt className="du-meta">Área estimada (m²)</dt>
              <dd className="mt-1 text-sm text-ink">{project.estimated_area_sqm ?? '—'}</dd>
            </div>
            <div>
              <dt className="du-meta">Niveles</dt>
              <dd className="mt-1 text-sm text-ink">
                {project.floor_levels_count != null ? String(project.floor_levels_count) : '—'}
              </dd>
            </div>
            <div>
              <dt className="du-meta">Fecha límite</dt>
              <dd className="mt-1 text-sm text-ink">{project.deadline ?? '—'}</dd>
            </div>
            <div>
              <dt className="du-meta">Responsable externo</dt>
              <dd className="mt-1 text-sm text-ink">
                {project.responsible_external_name?.trim() ||
                project.responsible_external_email?.trim() ? (
                  <>
                    {project.responsible_external_name?.trim() ? (
                      <span>{project.responsible_external_name.trim()}</span>
                    ) : null}
                    {project.responsible_external_name?.trim() &&
                    project.responsible_external_email?.trim() ? (
                      <span className="text-muted"> · </span>
                    ) : null}
                    {project.responsible_external_email?.trim() ? (
                      <span className="break-all">{project.responsible_external_email.trim()}</span>
                    ) : null}
                  </>
                ) : (
                  '—'
                )}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="du-meta">Identificador</dt>
              <dd className="mt-1 font-mono text-xs text-muted">{project.uuid}</dd>
            </div>
          </dl>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link
              data-tour="workspace-project-tasks-link"
              className="du-pill-action"
              to={`/app/tasks?project_uuid=${encodeURIComponent(project.uuid)}`}
            >
              Tablero del proyecto
            </Link>
            <button
              data-tour="workspace-project-chat-btn"
              type="button"
              className="du-pill-action"
              onClick={onOpenChat}
            >
              Chat del proyecto
            </button>
            <button
              type="button"
              disabled={docBusy || !token}
              className="du-pill-action border-primary/25 bg-primary/[0.05] font-semibold text-primary"
              onClick={() => void downloadDocumentaryReport()}
            >
              {docBusy ? 'Generando…' : 'Informe documental (PDF)'}
            </button>
          </div>
        </>
      ) : null}
    </Card>
  )
}
