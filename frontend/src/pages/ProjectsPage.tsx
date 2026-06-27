import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ClipboardList,
  Plus,
  Settings,
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { apiFetch, apiStatusErrorMessage } from '../api/client'
import { CreateProjectModal } from '../components/projects/CreateProjectModal'
import { NotificationsBell } from '../components/NotificationsBell'
import { WorkspaceContextSelect } from '../components/WorkspaceContextSelect'
import { ProjectsBoardView } from '../components/projects/ProjectsBoardView'
import { ProjectsDashboardOverview } from '../components/projects/ProjectsDashboardOverview'
import { IconButton } from '../components/ui/IconButton'
import { PageHeader, PageToolbarDivider, PageToolbarItem } from '../components/ui/PageHeader'
import { ViewTabs } from '../components/ui/ViewTabs'
import { PROJECT_CARD_MIME } from '../constants/projectsPage'
import { isAdjacentWorkflowTransitionAllowed } from '../constants/workflowPhases'
import type { Project } from '../types/project'
import type { WorkflowTemplateDetail } from '../types/workflowTemplate'

const PROJECTS_VIEW_FLOW_STORAGE_KEY = 'dupla.projects.viewWorkflowTemplateUuid'
import { projectDashboardBucket, type DashboardStatusFilter } from '../lib/projectDashboardBuckets'
import { hasElevatedAccess, canViewArchivedProjects } from '../lib/accessPermissions'
import { useAuthStore } from '../store/authStore'
import type { ProjectKindValue } from '../constants/projectKind'
import type { DirectoryUserRow } from '../lib/directoryUsers'
import { loadAdminDirectoryUsers } from '../lib/adminUsersDirectoryCache'

function readStoredViewFlowUuid(): string | null {
  try {
    const raw = localStorage.getItem(PROJECTS_VIEW_FLOW_STORAGE_KEY)
    if (!raw || raw === 'all') return null
    const t = raw.trim()
    return t || null
  } catch {
    return null
  }
}

export function ProjectsPage() {
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const permissions = useAuthStore((s) => s.permissions)
  const elevated = hasElevatedAccess(permissions)
  const canViewArchived = canViewArchivedProjects(permissions)
  const userUuid = useAuthStore((s) => s.userUuid)
  const [projects, setProjects] = useState<Project[]>([])
  const [name, setName] = useState('Nuevo proyecto')
  const [client, setClient] = useState('')
  const [createMembers, setCreateMembers] = useState<Set<string>>(new Set())
  const [adminUsersCreate, setAdminUsersCreate] = useState<DirectoryUserRow[]>([])
  const [projectsLoadError, setProjectsLoadError] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const feedbackClearRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [viewMode, setViewMode] = useState<'resumen' | 'tablero'>('resumen')
  const [statusFilter, setStatusFilter] = useState<DashboardStatusFilter>('todos')
  const [boardMsg, setBoardMsg] = useState<string | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [projectKind, setProjectKind] = useState<ProjectKindValue>('CLIENT')
  const [createFiles, setCreateFiles] = useState<File[]>([])
  const [createProjectCode, setCreateProjectCode] = useState('')
  const [createLocation, setCreateLocation] = useState('')
  const [createArea, setCreateArea] = useState('')
  const [createFloors, setCreateFloors] = useState('')
  const [createDeadline, setCreateDeadline] = useState('')
  const [createResponsible, setCreateResponsible] = useState('')
  const [createResponsibleExternalName, setCreateResponsibleExternalName] = useState('')
  const [createResponsibleExternalEmail, setCreateResponsibleExternalEmail] = useState('')
  const [projectSearch, setProjectSearch] = useState('')
  const dragRef = useRef(false)
  const [workflowTemplates, setWorkflowTemplates] = useState<{ uuid: string; name: string }[]>([])
  const [workflowTemplateUuid, setWorkflowTemplateUuid] = useState('')
  const [viewFlowUuid, setViewFlowUuid] = useState<string | null>(readStoredViewFlowUuid)
  const [boardTemplate, setBoardTemplate] = useState<WorkflowTemplateDetail | null>(null)
  const [projectsSettingsOpen, setProjectsSettingsOpen] = useState(false)
  const [includeArchived, setIncludeArchived] = useState(false)

  const projectsListUrl = useCallback(() => {
    const qs = includeArchived ? '?include_archived=true' : ''
    return `/api/projects${qs}`
  }, [includeArchived])

  const filteredProjects = useMemo(() => {
    const q = projectSearch.trim().toLowerCase()
    if (!q) return projects
    return projects.filter((p) => {
      const blob = `${p.name} ${p.project_code ?? ''} ${p.client_name ?? ''}`.toLowerCase()
      return blob.includes(q)
    })
  }, [projects, projectSearch])

  const projectsForViews = useMemo(() => {
    if (statusFilter === 'todos') return filteredProjects
    return filteredProjects.filter((p) => projectDashboardBucket(p.workflow_phase) === statusFilter)
  }, [filteredProjects, statusFilter])

  const stats = useMemo(() => {
    const o = { total: projects.length, proceso: 0, revision: 0, cerrados: 0 }
    for (const p of projects) {
      const b = projectDashboardBucket(p.workflow_phase)
      if (b === 'cerrado') o.cerrados += 1
      else if (b === 'revision') o.revision += 1
      else o.proceso += 1
    }
    return o
  }, [projects])

  const boardColumns = useMemo(() => {
    if (!boardTemplate) return undefined
    return boardTemplate.steps
      .slice()
      .sort((a, b) => a.sort_index - b.sort_index)
      .map((s) => ({
        id: s.uuid,
        title: s.title,
        behaviorKind: s.behavior_kind,
        iconKey: s.icon_key,
      }))
  }, [boardTemplate])

  const refresh = useCallback(async () => {
    if (!token) return
    setProjectsLoadError(null)
    if (viewFlowUuid) {
      const [pRes, tRes] = await Promise.all([
        apiFetch(`/api/workflow-templates/${viewFlowUuid}/projects`, { token }),
        apiFetch(`/api/workflow-templates/${viewFlowUuid}`, { token }),
      ])
      if (!pRes.ok || !tRes.ok) {
        try {
          localStorage.removeItem(PROJECTS_VIEW_FLOW_STORAGE_KEY)
        } catch {
          /* ignore */
        }
        setViewFlowUuid(null)
        setBoardTemplate(null)
        const fallback = await apiFetch(projectsListUrl(), { token })
        if (!fallback.ok) {
          setProjectsLoadError('No se pudieron cargar proyectos')
          return
        }
        setProjects((await fallback.json()) as Project[])
        setProjectsLoadError('El flujo guardado ya no está disponible; se muestran todos los proyectos.')
        return
      }
      setProjects((await pRes.json()) as Project[])
      setBoardTemplate((await tRes.json()) as WorkflowTemplateDetail)
      return
    }
    const res = await apiFetch(projectsListUrl(), { token })
    if (!res.ok) {
      setProjectsLoadError('No se pudieron cargar proyectos')
      return
    }
    setProjects((await res.json()) as Project[])
    setBoardTemplate(null)
  }, [token, viewFlowUuid, projectsListUrl])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setLoadingList(true)
      await refresh()
      if (!cancelled) setLoadingList(false)
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [refresh])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const res = await apiFetch('/api/workflow-templates/active', { token })
      if (!res.ok || cancelled) return
      const list = (await res.json()) as WorkflowTemplateDetail[]
      const opts = list.map((t) => ({ uuid: t.uuid, name: t.name }))
      setWorkflowTemplates(opts)
      setWorkflowTemplateUuid((prev) => {
        if (prev && opts.some((x) => x.uuid === prev)) return prev
        return opts[0]?.uuid ?? ''
      })
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    if (!elevated || !token) return
    let cancelled = false
    void (async () => {
      const rows = await loadAdminDirectoryUsers(token)
      if (cancelled || rows === null) return
      setAdminUsersCreate(rows)
    })()
    return () => {
      cancelled = true
    }
  }, [elevated, token])

  useEffect(() => {
    return () => {
      if (feedbackClearRef.current) clearTimeout(feedbackClearRef.current)
    }
  }, [])

  useEffect(() => {
    if (!createModalOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setCreateModalOpen(false)
        setCreateError(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [createModalOpen])

  useEffect(() => {
    if (!projectsSettingsOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setProjectsSettingsOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [projectsSettingsOpen])

  function closeCreateModal() {
    setCreateModalOpen(false)
    setCreateError(null)
  }

  async function createProject(e?: React.FormEvent) {
    e?.preventDefault()
    if (!token) return
    setCreateError(null)
    if (workflowTemplates.length === 0) {
      setCreateError('No hay plantillas de flujo activas. Crea una en Flujos.')
      return
    }
    if (!workflowTemplateUuid.trim()) {
      setCreateError('Elige una plantilla de flujo.')
      return
    }
    if (projectKind === 'TENDER' && createFiles.length === 0) {
      setCreateError('Los proyectos de licitación requieren al menos un archivo al crear.')
      return
    }
    setSubmitting(true)
    try {
      const fd = new FormData()
      fd.append('name', name.trim())
      fd.append('client_name', client.trim())
      fd.append('project_kind', projectKind)
      fd.append('workflow_template_uuid', workflowTemplateUuid.trim())
      if (elevated && createMembers.size > 0) {
        fd.append('member_user_uuids', JSON.stringify(Array.from(createMembers)))
      }
      if (createProjectCode.trim()) fd.append('project_code', createProjectCode.trim())
      if (createLocation.trim()) fd.append('location_text', createLocation.trim())
      if (createArea.trim()) fd.append('estimated_area_sqm', createArea.trim())
      if (createFloors.trim()) fd.append('floor_levels_count', createFloors.trim())
      if (createDeadline.trim()) fd.append('deadline', createDeadline.trim())
      if (createResponsible.trim()) fd.append('responsible_user_uuid', createResponsible.trim())
      if (createResponsibleExternalName.trim())
        fd.append('responsible_external_name', createResponsibleExternalName.trim())
      if (createResponsibleExternalEmail.trim())
        fd.append('responsible_external_email', createResponsibleExternalEmail.trim())
      for (const f of createFiles) {
        fd.append('files', f)
      }
      const res = await apiFetch('/api/projects', {
        method: 'POST',
        token,
        body: fd,
      })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setCreateError((j as { detail?: string }).detail ?? apiStatusErrorMessage(res.status))
        return
      }
      setFeedback('Proyecto creado. Ábrelo en la tabla o en el tablero, o crea otro.')
      if (feedbackClearRef.current) clearTimeout(feedbackClearRef.current)
      feedbackClearRef.current = setTimeout(() => setFeedback(null), 6000)
      setName('Nuevo proyecto')
      setClient('')
      setProjectKind('CLIENT')
      setCreateFiles([])
      setCreateMembers(new Set())
      setCreateProjectCode('')
      setCreateLocation('')
      setCreateArea('')
      setCreateFloors('')
      setCreateDeadline('')
      setCreateResponsible('')
      setCreateResponsibleExternalName('')
      setCreateResponsibleExternalEmail('')
      closeCreateModal()
      await refresh()
    } finally {
      setSubmitting(false)
    }
  }

  async function transitionProjectOnBoard(p: Project, targetColumnId: string) {
    if (!token) return
    if (boardTemplate) {
      const ordered = boardTemplate.steps
        .slice()
        .sort((a, b) => a.sort_index - b.sort_index)
        .map((s) => s.uuid)
      const cur = p.current_workflow_step_uuid
      const ci = ordered.indexOf(cur)
      const ti = ordered.indexOf(targetColumnId)
      if (ci < 0 || ti < 0) {
        setBoardMsg('Este proyecto no está en un paso reconocido de este flujo.')
        return
      }
      if (ti !== ci + 1 && ti !== ci - 1) {
        setBoardMsg('Solo puedes mover el proyecto al paso inmediatamente anterior o siguiente.')
        return
      }
      setBoardMsg(null)
      const res = await apiFetch(`/api/projects/${p.uuid}/transitions`, {
        method: 'POST',
        token,
        body: JSON.stringify({ target_step_uuid: targetColumnId }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setBoardMsg((j as { detail?: string }).detail ?? 'No se pudo actualizar el paso')
        return
      }
      await refresh()
      return
    }
    if (!isAdjacentWorkflowTransitionAllowed(p.project_kind, p.workflow_phase, targetColumnId)) {
      setBoardMsg(
        p.project_kind === 'TENDER'
          ? 'Los proyectos de licitación no pueden retroceder por debajo de «Revisión de arquitectura». Solo puedes mover a la fase inmediatamente siguiente o, si aplica, retroceder un paso desde esa fase en adelante.'
          : 'Solo puedes mover el proyecto a la fase inmediatamente anterior o siguiente.',
      )
      return
    }
    setBoardMsg(null)
    const res = await apiFetch(`/api/projects/${p.uuid}/transitions`, {
      method: 'POST',
      token,
      body: JSON.stringify({ target_phase: targetColumnId }),
    })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) {
      setBoardMsg((j as { detail?: string }).detail ?? 'No se pudo actualizar la fase')
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

  function onDropOnPhaseColumn(e: React.DragEvent, phaseKey: string) {
    e.preventDefault()
    const id = e.dataTransfer.getData(PROJECT_CARD_MIME)
    if (!id) return
    const p = projects.find((x) => x.uuid === id)
    if (!p) return
    void transitionProjectOnBoard(p, phaseKey)
  }

  function openCard(projectUuid: string) {
    if (dragRef.current) return
    navigate(`/app/projects/${projectUuid}`)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {feedback ?? ''}
      </div>
      {feedback ? (
        <div
          className="du-callout flex flex-wrap items-center justify-between gap-3 border-primary/25"
          role="status"
        >
          <span>{feedback}</span>
          <button
            type="button"
            className="du-link text-xs uppercase tracking-wide"
            onClick={() => setFeedback(null)}
          >
            Cerrar
          </button>
        </div>
      ) : null}

      <div className="du-page-shell" data-tour="projects-heading">
        <PageHeader
          title="Proyectos"
          subtitle="Gestiona obras, plazos y progreso del equipo."
          toolbar={
            <>
              <PageToolbarItem>
                <Link
                  className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold text-ink no-underline transition hover:bg-slate-100"
                  to="/app/tasks?mine=true"
                  data-tour="projects-mi-trabajo"
                >
                  <ClipboardList className="size-4 text-primary" strokeWidth={2} aria-hidden />
                  Mis tareas
                </Link>
              </PageToolbarItem>
              <PageToolbarDivider />
              <PageToolbarItem>
                <WorkspaceContextSelect variant="toolbar" />
              </PageToolbarItem>
              <PageToolbarDivider />
              <PageToolbarItem>
                <NotificationsBell token={token} />
              </PageToolbarItem>
              <PageToolbarItem>
                <IconButton
                  label="Configuración de vista: flujo por defecto"
                  variant="ghost"
                  className="rounded-full"
                  onClick={() => setProjectsSettingsOpen(true)}
                >
                  <Settings className="size-5 shrink-0" strokeWidth={2} aria-hidden />
                </IconButton>
              </PageToolbarItem>
              {elevated ? (
                <PageToolbarItem>
                  <button
                    type="button"
                    data-tour="projects-new"
                    className="du-cta-primary gap-1 px-2.5 py-1.5 text-xs uppercase"
                    onClick={() => {
                      setCreateError(null)
                      setCreateModalOpen(true)
                    }}
                  >
                    <Plus className="size-3.5 shrink-0" strokeWidth={2.5} aria-hidden />
                    Nuevo proyecto
                  </button>
                </PageToolbarItem>
              ) : null}
            </>
          }
        />
        {projectsLoadError ? (
          <p className="mt-2 text-sm font-medium text-primary" role="alert">
            {projectsLoadError}
          </p>
        ) : null}
        <ViewTabs
          className="mt-4"
          data-tour="projects-view-toggle"
          ariaLabel="Vista principal"
          tabs={[
            { id: 'resumen', label: 'Resumen' },
            { id: 'tablero', label: 'Tablero' },
          ]}
          activeId={viewMode}
          onChange={(id) => setViewMode(id as 'resumen' | 'tablero')}
        />
        {viewMode === 'tablero' ? (
          <p className="mt-3 text-sm leading-relaxed text-muted">
            {boardTemplate
              ? `Proyectos del flujo «${boardTemplate.name}». Arrastra una tarjeta al paso anterior o siguiente.`
              : elevated
                ? 'Columnas por fase. Arrastra una tarjeta a la columna de al lado cuando la aplicación lo permita.'
                : 'Vista en columnas por fase del proceso.'}
          </p>
        ) : null}
        {canViewArchived ? (
          <label className="mt-4 flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => setIncludeArchived(e.target.checked)}
            />
            Ver proyectos archivados
          </label>
        ) : null}
      </div>

      {viewMode === 'resumen' ? (
        <ProjectsDashboardOverview
          loadingList={loadingList}
          projects={projects}
          displayProjects={projectsForViews}
          projectSearch={projectSearch}
          onProjectSearchChange={setProjectSearch}
          statusFilter={statusFilter}
          onStatusFilter={setStatusFilter}
          stats={stats}
          onOpenProject={(uuid) => navigate(`/app/projects/${uuid}`)}
        />
      ) : (
        <ProjectsBoardView
          loadingList={loadingList}
          projects={projects}
          filteredProjects={projectsForViews}
          projectSearch={projectSearch}
          onProjectSearchChange={setProjectSearch}
          boardMsg={boardMsg}
          onDropOnPhaseColumn={onDropOnPhaseColumn}
          onDragOverBoard={onDragOverBoard}
          onDragStartProject={onDragStartProject}
          onDragEndBoard={onDragEndBoard}
          onOpenCard={openCard}
          boardColumns={boardColumns}
          columnMode={boardTemplate ? 'step' : 'phase'}
        />
      )}

      {projectsSettingsOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="projects-view-settings-title"
          onClick={() => setProjectsSettingsOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-xl border border-black/10 bg-white p-5 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="projects-view-settings-title" className="text-lg font-semibold text-ink">
              Vista de proyectos
            </h2>
            <p className="mt-2 text-sm text-muted">
              Elige el flujo por defecto: solo verás proyectos de ese flujo y el tablero usará columnas por paso.
            </p>
            <label className="mt-4 block">
              <span className="du-label">Flujo por defecto</span>
              <select
                className="du-input mt-1 w-full"
                value={viewFlowUuid ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  const next = v ? v : null
                  try {
                    if (next) localStorage.setItem(PROJECTS_VIEW_FLOW_STORAGE_KEY, next)
                    else localStorage.removeItem(PROJECTS_VIEW_FLOW_STORAGE_KEY)
                  } catch {
                    /* ignore */
                  }
                  setViewFlowUuid(next)
                  setProjectsSettingsOpen(false)
                }}
              >
                <option value="">Todos los proyectos (por fase)</option>
                {workflowTemplates.map((t) => (
                  <option key={t.uuid} value={t.uuid}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="du-pill-action"
                onClick={() => setProjectsSettingsOpen(false)}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {createModalOpen && elevated ? (
        <CreateProjectModal
          onClose={closeCreateModal}
          onSubmit={createProject}
          name={name}
          setName={setName}
          client={client}
          setClient={setClient}
          projectKind={projectKind}
          setProjectKind={setProjectKind}
          createFiles={createFiles}
          setCreateFiles={setCreateFiles}
          createProjectCode={createProjectCode}
          setCreateProjectCode={setCreateProjectCode}
          createLocation={createLocation}
          setCreateLocation={setCreateLocation}
          createArea={createArea}
          setCreateArea={setCreateArea}
          createFloors={createFloors}
          setCreateFloors={setCreateFloors}
          createDeadline={createDeadline}
          setCreateDeadline={setCreateDeadline}
          createResponsible={createResponsible}
          setCreateResponsible={setCreateResponsible}
          createResponsibleExternalName={createResponsibleExternalName}
          setCreateResponsibleExternalName={setCreateResponsibleExternalName}
          createResponsibleExternalEmail={createResponsibleExternalEmail}
          setCreateResponsibleExternalEmail={setCreateResponsibleExternalEmail}
          createMembers={createMembers}
          setCreateMembers={setCreateMembers}
          adminUsersCreate={adminUsersCreate}
          userUuid={userUuid}
          error={createError}
          submitting={submitting}
          workflowTemplates={workflowTemplates}
          workflowTemplateUuid={workflowTemplateUuid}
          setWorkflowTemplateUuid={setWorkflowTemplateUuid}
        />
      ) : null}
    </div>
  )
}
