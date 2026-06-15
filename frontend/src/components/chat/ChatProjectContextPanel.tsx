import { useEffect, useState } from 'react'
import { FileText, ImageIcon, Link2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { apiFetch } from '../../api/client'
import { WORKFLOW_PHASE_LABELS } from '../../constants/workflowPhases'
import { workflowPhaseProgressPct } from '../../lib/projectDashboardBuckets'
import type { Project } from '../../types/project'

type ProjectFileRow = {
  uuid: string
  original_name: string
  mime: string | null
  created_at: string
}

type ChatProjectContextPanelProps = {
  projectUuid: string | null
  token: string | null
}

export function ChatProjectContextPanel({ projectUuid, token }: ChatProjectContextPanelProps) {
  const [project, setProject] = useState<Project | null>(null)
  const [files, setFiles] = useState<ProjectFileRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      if (!token || !projectUuid) {
        await Promise.resolve()
        if (cancelled) return
        setProject(null)
        setFiles([])
        setLoading(false)
        return
      }
      setLoading(true)
      const [pr, fr] = await Promise.all([
        apiFetch(`/api/projects/${projectUuid}`, { token }),
        apiFetch(`/api/projects/${projectUuid}/files?limit=6&offset=0`, { token }),
      ])
      if (cancelled) return
      if (pr.ok) setProject((await pr.json()) as Project)
      else setProject(null)
      if (fr.ok) {
        const j = (await fr.json()) as { items?: ProjectFileRow[] }
        setFiles(Array.isArray(j.items) ? j.items : [])
      } else {
        setFiles([])
      }
      setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [token, projectUuid])

  if (!projectUuid) {
    return (
      <aside className="hidden w-[340px] shrink-0 flex-col border-l border-black/10 bg-[#f8f9fb] xl:flex">
        <div className="p-5">
          <p className="text-sm font-semibold text-ink">Contexto</p>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Abre un chat de <strong className="text-ink">obra</strong> para ver resumen de proyecto y archivos
            recientes.
          </p>
        </div>
      </aside>
    )
  }

  const pct = project ? workflowPhaseProgressPct(project.workflow_phase) : 0
  const phaseLabel = project
    ? WORKFLOW_PHASE_LABELS[project.workflow_phase] ?? project.workflow_phase
    : ''

  function fileIcon(mime: string | null) {
    if (mime?.startsWith('image/')) return ImageIcon
    return FileText
  }

  function fmtSize(name: string) {
    return name.length > 28 ? `${name.slice(0, 26)}…` : name
  }

  return (
    <aside className="hidden w-[min(100%,380px)] shrink-0 flex-col border-l border-black/10 bg-[#f8f9fb] xl:flex">
      <div className="max-h-[40vh] shrink-0 overflow-hidden border-b border-black/8 bg-black/[0.03]">
        <div className="aspect-[21/9] w-full bg-linear-to-br from-primary/20 via-black/10 to-primary/30" />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
        {loading ? <p className="text-xs text-muted">Cargando…</p> : null}
        {project ? (
          <>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Obra</p>
              <p className="mt-1 text-base font-bold text-ink">{project.name}</p>
              {project.client_name ? (
                <p className="mt-0.5 text-xs text-muted">{project.client_name}</p>
              ) : null}
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs font-semibold text-muted">
                <span>Avance</span>
                <span className="tabular-nums text-primary">{pct}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-black/10">
                <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-2 text-xs text-muted leading-snug">{phaseLabel}</p>
            </div>
            <Link
              className="inline-flex items-center gap-2 rounded-lg border border-black/12 bg-white px-3 py-2 text-xs font-semibold text-primary shadow-sm no-underline hover:bg-black/[0.02]"
              to={`/app/projects/${projectUuid}`}
            >
              <Link2 className="size-3.5 shrink-0" aria-hidden />
              Abrir consola del proyecto
            </Link>
          </>
        ) : !loading ? (
          <p className="text-xs text-muted">No se pudo cargar el proyecto.</p>
        ) : null}

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Archivos recientes</p>
          <ul className="mt-2 space-y-2">
            {files.length === 0 ? (
              <li className="text-xs text-muted">Sin archivos en esta vista.</li>
            ) : (
              files.map((f) => {
                const Icon = fileIcon(f.mime)
                return (
                  <li
                    key={f.uuid}
                    className="flex items-center gap-2 rounded-lg border border-black/8 bg-white px-2 py-2 text-xs"
                  >
                    <Icon className="size-4 shrink-0 text-primary" aria-hidden />
                    <span className="min-w-0 flex-1 truncate font-medium text-ink" title={f.original_name}>
                      {fmtSize(f.original_name)}
                    </span>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      </div>
    </aside>
  )
}
