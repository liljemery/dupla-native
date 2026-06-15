import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Settings, Trash2 } from 'lucide-react'

import { apiFetch } from '../api/client'
import { Card } from '../components/Card'
import { PrimaryButton } from '../components/PrimaryButton'
import {
  FlowStepsEditor,
  type DraftWorkflowStep,
  normalizeActionsFromApi,
  newDraftId,
  syncStableKeysForSteps,
} from '../components/flows/FlowStepsEditor'
import { FlowTemplateIcon } from '../components/flows/FlowTemplateIcon'
import { coerceFlowTemplateIconKey, DEFAULT_FLOW_TEMPLATE_ICON } from '../constants/flowTemplateIcons'
import type { WorkflowTemplateDetail, WorkflowTemplateListItem } from '../types/workflowTemplate'
import { hasElevatedAccess } from '../lib/accessPermissions'
import { confirmDestructive } from '../lib/duplaAlert'
import { useAuthStore } from '../store/authStore'

export function FlowsHubPage() {
  const token = useAuthStore((s) => s.token)
  const role = useAuthStore((s) => s.role)
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role, isTeamLeader)

  const [q, setQ] = useState('')
  const [rows, setRows] = useState<WorkflowTemplateListItem[]>([])
  const [loadErr, setLoadErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDesc, setCreateDesc] = useState('')
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState<string | null>(null)

  const [cfgOpen, setCfgOpen] = useState(false)
  const [cfgUuid, setCfgUuid] = useState<string | null>(null)
  const [cfgName, setCfgName] = useState('')
  const [cfgDesc, setCfgDesc] = useState('')
  const [cfgBusy, setCfgBusy] = useState(false)
  const [cfgErr, setCfgErr] = useState<string | null>(null)

  const [editOpen, setEditOpen] = useState(false)
  const [editDetail, setEditDetail] = useState<WorkflowTemplateDetail | null>(null)
  const [draftSteps, setDraftSteps] = useState<DraftWorkflowStep[]>([])
  const [editBusy, setEditBusy] = useState(false)
  const [editErr, setEditErr] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!token) return
    setLoadErr(null)
    const qs = new URLSearchParams()
    if (q.trim()) qs.set('q', q.trim())
    const res = await apiFetch(`/api/workflow-templates?${qs.toString()}`, { token })
    if (!res.ok) {
      setLoadErr('No se pudieron cargar los flujos')
      return
    }
    setRows((await res.json()) as WorkflowTemplateListItem[])
  }, [token, q])

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

  async function submitCreate() {
    if (!token) return
    setCreateErr(null)
    setCreateBusy(true)
    try {
      const res = await apiFetch('/api/workflow-templates', {
        method: 'POST',
        token,
        body: JSON.stringify({ name: createName.trim(), description: createDesc.trim() }),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setCreateErr((j as { detail?: string }).detail ?? 'No se pudo crear')
        return
      }
      setCreateOpen(false)
      setCreateName('')
      setCreateDesc('')
      await refresh()
      const detail = j as WorkflowTemplateDetail
      openEdit(detail.uuid)
    } finally {
      setCreateBusy(false)
    }
  }

  async function openEdit(uuid: string) {
    if (!token) return
    setEditErr(null)
    const res = await apiFetch(`/api/workflow-templates/${uuid}`, { token })
    if (!res.ok) return
    const d = (await res.json()) as WorkflowTemplateDetail
    setEditDetail(d)
    const mapped: DraftWorkflowStep[] = d.steps
      .slice()
      .sort((a, b) => a.sort_index - b.sort_index)
      .map((s) => ({
        draft_id: newDraftId(),
        server_step_uuid: s.uuid,
        stable_key: s.stable_key,
        title: s.title,
        icon_key: coerceFlowTemplateIconKey(s.icon_key),
        requires_approval_role: s.requires_approval_role,
        on_enter_actions: normalizeActionsFromApi(s.on_enter_actions),
      }))
    setDraftSteps(
      mapped.length > 0
        ? mapped
        : syncStableKeysForSteps([
            {
              draft_id: newDraftId(),
              stable_key: '',
              title: 'Paso 1',
              icon_key: DEFAULT_FLOW_TEMPLATE_ICON,
              requires_approval_role: null,
              on_enter_actions: [],
            },
          ]),
    )
    setEditOpen(true)
  }

  async function saveEditSteps() {
    if (!token || !editDetail) return
    setEditErr(null)
    setEditBusy(true)
    try {
      const finalSteps = syncStableKeysForSteps(draftSteps)
      const body = {
        steps: finalSteps.map((s) => ({
          stable_key: s.stable_key,
          title: s.title.trim() || s.stable_key,
          behavior_kind: 'CUSTOM_AUTOMATION',
          blocked_by_stable_key: null,
          requires_approval_role: s.requires_approval_role,
          on_enter_actions: s.on_enter_actions,
          icon_key: s.icon_key,
        })),
      }
      const res = await apiFetch(`/api/workflow-templates/${editDetail.uuid}/steps`, {
        method: 'PUT',
        token,
        body: JSON.stringify(body),
      })
      const j = await res.json().catch(() => ({}))
      if (!res.ok) {
        setEditErr((j as { detail?: string }).detail ?? 'No se pudo guardar')
        return
      }
      setEditOpen(false)
      await refresh()
    } finally {
      setEditBusy(false)
    }
  }

  async function saveCfg() {
    if (!token || !cfgUuid) return
    setCfgBusy(true)
    try {
      await apiFetch(`/api/workflow-templates/${cfgUuid}`, {
        method: 'PATCH',
        token,
        body: JSON.stringify({
          name: cfgName.trim(),
          description: cfgDesc.trim(),
        }),
      })
      setCfgOpen(false)
      await refresh()
    } finally {
      setCfgBusy(false)
    }
  }

  function openCfg(row: WorkflowTemplateListItem) {
    setCfgUuid(row.uuid)
    setCfgName(row.name)
    setCfgDesc(row.description)
    setCfgErr(null)
    setCfgOpen(true)
  }

  async function deleteFlow(row: WorkflowTemplateListItem) {
    if (!token) return
    if (row.preview_projects.length > 0) {
      setLoadErr('No se puede eliminar un flujo con proyectos asociados.')
      return
    }
    if (
      !(await confirmDestructive({
        title: `¿Eliminar el flujo «${row.name}»?`,
        text: 'Se borrarán todos sus pasos. No se puede deshacer.',
      }))
    ) {
      return
    }
    setLoadErr(null)
    const res = await apiFetch(`/api/workflow-templates/${row.uuid}`, { method: 'DELETE', token })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      setLoadErr((j as { detail?: string }).detail ?? 'No se pudo eliminar el flujo')
      return
    }
    if (cfgUuid === row.uuid) setCfgOpen(false)
    if (editDetail?.uuid === row.uuid) setEditOpen(false)
    await refresh()
  }

  if (!elevated) {
    return (
      <div className="p-6">
        <p className="text-muted">Solo Gerencia o Líder de equipo puede gestionar flujos.</p>
        <Link className="mt-2 inline-block text-primary underline" to="/app/projects">
          Volver
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-ink md:text-4xl">Flujos</h1>
          <p className="mt-2 text-lg text-muted">
            Crea y edita plantillas de proceso; cada una tiene su tablero de proyectos.
          </p>
        </div>
        <PrimaryButton type="button" className="shrink-0 gap-2" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" strokeWidth={2.5} />
          Nuevo flujo
        </PrimaryButton>
      </div>

      <label className="max-w-xl">
        <span className="sr-only">Buscar</span>
        <input
          type="search"
          className="du-input w-full"
          placeholder="Buscar por nombre de flujo o de proyecto…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>

      {loadErr ? <p className="text-sm text-primary">{loadErr}</p> : null}

      {loading ? (
        <p className="text-sm text-muted">Cargando…</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((r) => (
            <Card key={r.uuid} className="flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <FlowTemplateIcon name={r.icon_key} className="h-5 w-5 shrink-0 text-primary" />
                  <h2 className="truncate text-lg font-semibold text-ink">{r.name}</h2>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    className="rounded-md p-2 text-muted hover:bg-black/5 hover:text-ink"
                    title="Configuración"
                    aria-label="Configuración"
                    onClick={() => openCfg(r)}
                  >
                    <Settings className="h-4 w-4" strokeWidth={2} />
                  </button>
                  <button
                    type="button"
                    className="rounded-md p-2 text-muted hover:bg-red-50 hover:text-red-700 disabled:opacity-40"
                    title={
                      r.preview_projects.length > 0
                        ? 'Elimina los proyectos del flujo antes de borrarlo'
                        : 'Eliminar flujo'
                    }
                    aria-label="Eliminar flujo"
                    disabled={r.preview_projects.length > 0}
                    onClick={() => void deleteFlow(r)}
                  >
                    <Trash2 className="h-4 w-4" strokeWidth={2} />
                  </button>
                </div>
              </div>
              <p className="line-clamp-3 text-sm text-muted">{r.description || '—'}</p>
              <div className="border-t border-black/10 pt-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Proyectos (vista previa)
                </p>
                <ul className="mt-1 space-y-0.5 text-sm">
                  {r.preview_projects.length === 0 ? (
                    <li className="text-muted">Ninguno aún</li>
                  ) : (
                    r.preview_projects.map((p) => (
                      <li key={p.uuid}>
                        <Link className="text-primary underline-offset-2 hover:underline" to={`/app/projects/${p.uuid}`}>
                          {p.name}
                        </Link>
                      </li>
                    ))
                  )}
                </ul>
              </div>
              <div className="mt-auto flex flex-wrap gap-2 pt-2">
                <Link
                  className="du-pill-action inline-flex flex-1 items-center justify-center text-center text-sm font-semibold no-underline"
                  to={`/app/flows/${r.uuid}`}
                >
                  Abrir tablero
                </Link>
                <button
                  type="button"
                  className="rounded-lg border border-black/15 bg-white px-3 py-2 text-sm font-medium hover:bg-black/[0.03]"
                  onClick={() => openEdit(r.uuid)}
                >
                  Editar flujo
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {createOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setCreateOpen(false)
          }}
        >
          <div className="w-full max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-xl" role="dialog">
            <h3 className="text-lg font-semibold text-ink">Nuevo flujo</h3>
            <label className="mt-4 block">
              <span className="du-label">Nombre</span>
              <input className="du-input mt-1 w-full" value={createName} onChange={(e) => setCreateName(e.target.value)} />
            </label>
            <label className="mt-3 block">
              <span className="du-label">Descripción</span>
              <textarea className="du-input mt-1 min-h-[88px] w-full" value={createDesc} onChange={(e) => setCreateDesc(e.target.value)} />
            </label>
            {createErr ? <p className="mt-2 text-sm text-primary">{createErr}</p> : null}
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-black/5" onClick={() => setCreateOpen(false)}>
                Cancelar
              </button>
              <PrimaryButton type="button" disabled={!createName.trim() || createBusy} onClick={() => void submitCreate()}>
                Crear y configurar pasos
              </PrimaryButton>
            </div>
          </div>
        </div>
      ) : null}

      {cfgOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setCfgOpen(false)
          }}
        >
          <div className="w-full max-w-md rounded-xl border border-black/10 bg-white p-6 shadow-xl" role="dialog">
            <h3 className="text-lg font-semibold text-ink">Configuración del flujo</h3>
            <label className="mt-4 block">
              <span className="du-label">Nombre</span>
              <input className="du-input mt-1 w-full" value={cfgName} onChange={(e) => setCfgName(e.target.value)} />
            </label>
            <label className="mt-3 block">
              <span className="du-label">Descripción</span>
              <textarea className="du-input mt-1 min-h-[88px] w-full" value={cfgDesc} onChange={(e) => setCfgDesc(e.target.value)} />
            </label>
            {cfgErr ? <p className="mt-2 text-sm text-primary">{cfgErr}</p> : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              {cfgUuid && rows.find((r) => r.uuid === cfgUuid)?.preview_projects.length === 0 ? (
                <button
                  type="button"
                  className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50"
                  onClick={() => {
                    const row = rows.find((r) => r.uuid === cfgUuid)
                    if (row) void deleteFlow(row)
                  }}
                >
                  Eliminar flujo
                </button>
              ) : null}
              <button type="button" className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-black/5" onClick={() => setCfgOpen(false)}>
                Cerrar
              </button>
              <PrimaryButton type="button" disabled={cfgBusy || !cfgName.trim()} onClick={() => void saveCfg()}>
                Guardar
              </PrimaryButton>
            </div>
          </div>
        </div>
      ) : null}

      {editOpen && editDetail ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setEditOpen(false)
          }}
        >
          <div
            className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-xl"
            role="dialog"
          >
            <div className="shrink-0 border-b border-black/10 px-4 py-3">
              <h3 className="text-lg font-semibold text-ink">Editar pasos — {editDetail.name}</h3>
              <p className="text-sm text-muted">
                «Guardar pasos» reemplaza por completo el flujo en el servidor con la lista que ves (orden del select =
                proceso). Los pasos que saques del borrador dejan de existir al guardar. Vista previa a la derecha.
              </p>
            </div>
            <div className="flex max-h-[calc(92vh-8.5rem)] min-h-0 flex-1 flex-col overflow-hidden p-4">
              <FlowStepsEditor steps={draftSteps} onChange={setDraftSteps} />
            </div>
            {editErr ? <p className="shrink-0 px-4 text-sm text-primary">{editErr}</p> : null}
            <div className="flex shrink-0 justify-end gap-2 border-t border-black/10 px-4 py-3">
              <button type="button" className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-black/5" onClick={() => setEditOpen(false)}>
                Cancelar
              </button>
              <PrimaryButton type="button" disabled={editBusy || draftSteps.length === 0} onClick={() => void saveEditSteps()}>
                Guardar pasos
              </PrimaryButton>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
