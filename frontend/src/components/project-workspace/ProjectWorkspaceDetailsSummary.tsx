import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { apiFetch } from '../../api/client'
import { projectKindLabel } from '../../constants/projectKind'
import { downloadBlob, filenameFromContentDisposition } from '../../lib/download'
import type { Project } from '../../types/project'

type Props = {
  project: Project
  phaseLabel: string
  token: string | null
  onOpenChat: () => void
}

export function ProjectWorkspaceDetailsSummary({ project, phaseLabel, token, onOpenChat }: Props) {
  const [docBusy, setDocBusy] = useState(false)

  async function downloadDocumentaryReport() {
    if (!token) return
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
    <details className="group rounded-xl border border-black/10 bg-white shadow-(--shadow-card)">
      <summary className="cursor-pointer list-none px-5 py-4 text-sm font-semibold uppercase tracking-wide text-muted marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="flex items-center justify-between gap-2">
          Datos del proyecto
          <ChevronDown className="size-4 shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
        </span>
      </summary>
      <div className="border-t border-black/8 px-5 pb-5 pt-4">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className="du-meta">Cliente</dt>
          <dd className="mt-0.5 text-sm text-ink">{project.client_name ?? '—'}</dd>
        </div>
        <div>
          <dt className="du-meta">Tipo</dt>
          <dd className="mt-0.5 text-sm text-ink">{projectKindLabel(project.project_kind)}</dd>
        </div>
        <div>
          <dt className="du-meta">Fase</dt>
          <dd className="mt-0.5 text-sm font-medium text-ink">{phaseLabel}</dd>
        </div>
        <div>
          <dt className="du-meta">Código</dt>
          <dd className="mt-0.5 font-mono text-sm text-ink">{project.project_code ?? '—'}</dd>
        </div>
        <div>
          <dt className="du-meta">Plazo</dt>
          <dd className="mt-0.5 text-sm text-ink">{project.deadline ?? '—'}</dd>
        </div>
        <div>
          <dt className="du-meta">Área (m²)</dt>
          <dd className="mt-0.5 text-sm text-ink">{project.estimated_area_sqm ?? '—'}</dd>
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <dt className="du-meta">Ubicación</dt>
          <dd className="mt-0.5 text-sm text-ink">{project.location_text ?? '—'}</dd>
        </div>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2 border-t border-black/8 pt-4">
        <Link
          className="du-pill-action"
          to={`/app/tasks?project_uuid=${encodeURIComponent(project.uuid)}`}
        >
          Tareas
        </Link>
        <button type="button" className="du-pill-action" onClick={onOpenChat}>
          Chat
        </button>
        <button
          type="button"
          disabled={docBusy || !token}
          className="du-pill-action border-primary/25 bg-primary/[0.05] font-semibold text-primary"
          onClick={() => void downloadDocumentaryReport()}
        >
          {docBusy ? 'Generando…' : 'Informe PDF'}
        </button>
      </div>
      </div>
    </details>
  )
}
