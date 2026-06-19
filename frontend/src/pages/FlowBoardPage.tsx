import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiFetch } from '../api/client'
import { Card } from '../components/Card'
import { ProjectsBoardView } from '../components/projects/ProjectsBoardView'
import { PROJECT_CARD_MIME } from '../constants/projectsPage'
import type { Project } from '../types/project'
import type { WorkflowTemplateDetail } from '../types/workflowTemplate'
import { hasElevatedAccess } from '../lib/accessPermissions'
import { confirmDestructive } from '../lib/duplaAlert'
import { useAuthStore } from '../store/authStore'

export function FlowBoardPage() {
  const { flowUuid } = useParams<{ flowUuid: string }>()
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const permissions = useAuthStore((s) => s.permissions)
  const elevated = hasElevatedAccess(permissions)

  const [template, setTemplate] = useState<WorkflowTemplateDetail | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [loadErr, setLoadErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [projectSearch, setProjectSearch] = useState('')
  const [boardMsg, setBoardMsg] = useState<string | null>(null)
  const dragRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!token || !flowUuid) return
    setLoadErr(null)
    const [tRes, pRes] = await Promise.all([
      apiFetch(`/api/workflow-templates/${flowUuid}`, { token }),
      apiFetch(`/api/workflow-templates/${flowUuid}/projects`, { token }),
    ])
    if (!tRes.ok) {
      setLoadErr('No se pudo cargar el flujo')
      return
    }
    if (!pRes.ok) {
      setLoadErr('No se pudieron cargar los proyectos')
      return
    }
    setTemplate((await tRes.json()) as WorkflowTemplateDetail)
    setProjects((await pRes.json()) as Project[])
  }, [token, flowUuid])

  useEffect(() => {
    let c = false
    void (async () => {
      setLoading(true)
      await refresh()
      if (!c) setLoading(false)
    })()
    return () => {
      c = true
    }
  }, [refresh])

  const filteredProjects = useMemo(() => {
    const q = projectSearch.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => {
      const blob = `${p.name} ${p.project_code ?? ''} ${p.client_name ?? ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [projects, projectSearch])

  const orderedStepIds = useMemo(
    () => (template?.steps ?? []).slice().sort((a, b) => a.sort_index - b.sort_index).map((s) => s.uuid),
    [template],
  )

  const boardColumns = useMemo(() => {
    if (!template) return undefined
    return template.steps
      .slice()
      .sort((a, b) => a.sort_index - b.sort_index)
      .map((s) => ({
        id: s.uuid,
        title: s.title,
        behaviorKind: s.behavior_kind,
        iconKey: s.icon_key,
      }))
  }, [template])

  function isAdjacentStep(project: Project, targetStepId: string): boolean {
    const cur = project.current_workflow_step_uuid
    const ci = orderedStepIds.indexOf(cur)
    const ti = orderedStepIds.indexOf(targetStepId)
    if (ci < 0 || ti < 0) return false
    return ti === ci + 1 || ti === ci - 1
  }

  async function transitionProjectOnBoard(p: Project, targetStepId: string) {
    if (!token) return
    if (!isAdjacentStep(p, targetStepId)) {
      setBoardMsg('Solo puedes mover el proyecto al paso inmediatamente anterior o siguiente.')
      return
    }
    setBoardMsg(null)
    const res = await apiFetch(`/api/projects/${p.uuid}/transitions`, {
      method: 'POST',
      token,
      body: JSON.stringify({ target_step_uuid: targetStepId }),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setBoardMsg((j as { detail?: string }).detail ?? 'No se pudo actualizar el paso')
      return
    }
    await refresh()
  }

  function onDragEndBoard() {
    window.setTimeout(() => {
      dragRef.current = false
    }, 0)
  }

  function onDragStartProject(e: React.DragEvent, projectUuid: string) {
    dragRef.current = true
    e.dataTransfer.setData(PROJECT_CARD_MIME, projectUuid)
    e.dataTransfer.effectAllowed = 'move'
  }

  function onDragOverBoard(e: React.DragEvent) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  function onDropOnPhaseColumn(e: React.DragEvent, columnId: string) {
    e.preventDefault()
    const id = e.dataTransfer.getData(PROJECT_CARD_MIME)
    if (!id) return
    const p = projects.find((x) => x.uuid === id)
    if (!p) return
    void transitionProjectOnBoard(p, columnId)
  }

  async function deleteFlow() {
    if (!token || !flowUuid || !template) return
    if (projects.length > 0) {
      setBoardMsg('No se puede eliminar un flujo con proyectos asociados.')
      return
    }
    if (
      !(await confirmDestructive({
        title: `¿Eliminar el flujo «${template.name}»?`,
        text: 'Se borrarán todos sus pasos. No se puede deshacer.',
      }))
    ) {
      return
    }
    setBoardMsg(null)
    const res = await apiFetch(`/api/workflow-templates/${flowUuid}`, { method: 'DELETE', token })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      setBoardMsg((j as { detail?: string }).detail ?? 'No se pudo eliminar el flujo')
      return
    }
    navigate('/app/flows')
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <Link
            to="/app/flows"
            className="text-sm font-medium text-primary underline-offset-2 hover:underline"
          >
            ← Flujos
          </Link>
          <h1 className="mt-2 text-3xl font-semibold text-ink md:text-4xl">
            {template?.name ?? 'Flujo'}
          </h1>
          <p className="mt-2 text-lg text-muted md:text-xl">
            Proyectos que usan este flujo. Arrastra tarjetas entre columnas adyacentes.
          </p>
          {loadErr ? (
            <p className="mt-2 text-sm font-medium text-primary" role="alert">
              {loadErr}
            </p>
          ) : null}
        </div>
        <label className="min-w-0 sm:max-w-md">
          <span className="sr-only">Buscar</span>
          <input
            type="search"
            className="du-input h-9 w-full rounded-lg border-black/10 py-0 text-sm"
            placeholder="Buscar proyecto…"
            value={projectSearch}
            onChange={(e) => setProjectSearch(e.target.value)}
          />
        </label>
        {elevated && projects.length === 0 && template ? (
          <button
            type="button"
            className="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
            onClick={() => void deleteFlow()}
          >
            Eliminar flujo
          </button>
        ) : null}
      </div>

      <Card className="border-primary/15 bg-primary/[0.04] p-4">
        <p className="text-sm text-ink">
          <span className="font-semibold">Descripción: </span>
          {template?.description?.trim() ? template.description : '—'}
        </p>
      </Card>

      <ProjectsBoardView
        loadingList={loading}
        projects={projects}
        filteredProjects={filteredProjects}
        projectSearch={projectSearch}
        boardMsg={boardMsg}
        onDropOnPhaseColumn={onDropOnPhaseColumn}
        onDragOverBoard={onDragOverBoard}
        onDragStartProject={onDragStartProject}
        onDragEndBoard={onDragEndBoard}
        onOpenCard={(uuid) => navigate(`/app/projects/${uuid}`)}
        boardColumns={boardColumns}
        columnMode="step"
      />
    </div>
  )
}
