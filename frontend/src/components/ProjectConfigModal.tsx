import { useCallback, useEffect, useState } from 'react'

import { hasElevatedAccess } from '../lib/accessPermissions'
import { useAuthStore } from '../store/authStore'
import { apiFetch } from '../api/client'
import { Card } from './Card'
import { PrimaryButton } from './PrimaryButton'
import { ProjectMemberPicker } from './projects/ProjectMemberPicker'
import { isValidUuidString, normalizeDirectoryUsers, type DirectoryUserRow } from '../lib/directoryUsers'
import { formatPersonFullName } from '../lib/personDisplay'
import type { Project } from '../types/project'

type MemberRow = DirectoryUserRow

type ProjectConfigModalProps = {
  open: boolean
  onClose: () => void
  projectUuid: string
  token: string | null
  role: string | null
  project: Project | null
  projectError: string | null
  onProjectSaved: (p: Project) => void
  adminUsers: MemberRow[]
  memberRows: MemberRow[]
  memberSelection: Set<string>
  setMemberSelection: React.Dispatch<React.SetStateAction<Set<string>>>
  membersBusy: boolean
  setMembersBusy: (v: boolean) => void
  membersMsg: string | null
  setMembersMsg: (v: string | null) => void
  setMemberRows: (rows: MemberRow[]) => void
}

export function ProjectConfigModal({
  open,
  onClose,
  projectUuid,
  token,
  role,
  project,
  projectError,
  onProjectSaved,
  adminUsers,
  memberRows,
  memberSelection,
  setMemberSelection,
  membersBusy,
  setMembersBusy,
  membersMsg,
  setMembersMsg,
  setMemberRows,
}: ProjectConfigModalProps) {
  const isTeamLeader = useAuthStore((s) => s.isTeamLeader)
  const elevated = hasElevatedAccess(role as import('../constants/userRoles').UserRole | null, isTeamLeader)
  const [name, setName] = useState('')
  const [clientName, setClientName] = useState('')
  const [projectCode, setProjectCode] = useState('')
  const [locationText, setLocationText] = useState('')
  const [areaSqm, setAreaSqm] = useState('')
  const [floors, setFloors] = useState('')
  const [deadline, setDeadline] = useState('')
  const [responsibleUuid, setResponsibleUuid] = useState('')
  const [responsibleExternalName, setResponsibleExternalName] = useState('')
  const [responsibleExternalEmail, setResponsibleExternalEmail] = useState('')
  const [saveBusy, setSaveBusy] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !project) return
    setName(project.name)
    setClientName(project.client_name ?? '')
    setProjectCode(project.project_code ?? '')
    setLocationText(project.location_text ?? '')
    setAreaSqm(project.estimated_area_sqm != null ? String(project.estimated_area_sqm) : '')
    setFloors(project.floor_levels_count != null ? String(project.floor_levels_count) : '')
    setDeadline(project.deadline ?? '')
    setResponsibleUuid(project.responsible_user_uuid ?? '')
    setResponsibleExternalName(project.responsible_external_name ?? '')
    setResponsibleExternalEmail(project.responsible_external_email ?? '')
    setSaveMsg(null)
  }, [open, project])

  const saveMeta = useCallback(async () => {
    if (!token || !projectUuid || !project) return
    setSaveBusy(true)
    setSaveMsg(null)
    const payload: Record<string, unknown> = {
      name: name.trim() || project.name,
      client_name: clientName.trim() || null,
      project_code: projectCode.trim() || null,
      location_text: locationText.trim() || null,
    }
    if (areaSqm.trim()) {
      payload.estimated_area_sqm = Number(areaSqm)
    } else {
      payload.estimated_area_sqm = null
    }
    if (floors.trim()) {
      payload.floor_levels_count = parseInt(floors, 10)
    } else {
      payload.floor_levels_count = null
    }
    payload.deadline = deadline.trim() || null
    payload.responsible_user_uuid = responsibleUuid.trim() || null
    payload.responsible_external_name = responsibleExternalName.trim() || null
    payload.responsible_external_email = responsibleExternalEmail.trim() || null

    const res = await apiFetch(`/api/projects/${projectUuid}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    })
    setSaveBusy(false)
    if (!res.ok) {
      setSaveMsg('No se pudo guardar')
      return
    }
    const body = (await res.json()) as Project
    onProjectSaved(body)
    setSaveMsg('Guardado')
  }, [
    token,
    projectUuid,
    project,
    name,
    clientName,
    projectCode,
    locationText,
    areaSqm,
    floors,
    deadline,
    responsibleUuid,
    responsibleExternalName,
    responsibleExternalEmail,
    onProjectSaved,
  ])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="project-config-title"
    >
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Cerrar" onClick={onClose} />
      <div className="relative z-10 flex max-h-[min(92dvh,900px)] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-black/10 px-4 py-3">
          <h2 id="project-config-title" className="text-lg font-semibold text-ink">
            Configuración del proyecto
          </h2>
          <button
            type="button"
            className="rounded-md px-2 py-1 text-sm text-muted hover:bg-black/[0.04] hover:text-ink"
            onClick={onClose}
          >
            Cerrar
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {projectError ? <p className="mb-3 text-sm text-primary">{projectError}</p> : null}
          {!project ? (
            <p className="text-sm text-muted">Cargando…</p>
          ) : (
            <div className="space-y-6">
              <Card className="p-4">
                <h3 className="text-sm font-semibold text-ink">Datos generales</h3>
                <label className="mt-3 block text-sm text-muted">
                  Nombre
                  <input
                    className="du-input mt-1"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={255}
                  />
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Cliente
                  <input
                    className="du-input mt-1"
                    value={clientName}
                    onChange={(e) => setClientName(e.target.value)}
                    maxLength={255}
                  />
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Código de proyecto
                  <input
                    className="du-input mt-1"
                    value={projectCode}
                    onChange={(e) => setProjectCode(e.target.value)}
                    maxLength={80}
                  />
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Ubicación
                  <textarea
                    className="du-input mt-1 min-h-[72px]"
                    value={locationText}
                    onChange={(e) => setLocationText(e.target.value)}
                    rows={3}
                  />
                </label>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm text-muted">
                    Área estimada (m²)
                    <input
                      className="du-input mt-1"
                      type="number"
                      min={0}
                      step="0.01"
                      value={areaSqm}
                      onChange={(e) => setAreaSqm(e.target.value)}
                    />
                  </label>
                  <label className="block text-sm text-muted">
                    Niveles
                    <input
                      className="du-input mt-1"
                      type="number"
                      min={0}
                      step="1"
                      value={floors}
                      onChange={(e) => setFloors(e.target.value)}
                    />
                  </label>
                </div>
                <label className="mt-3 block text-sm text-muted">
                  Fecha límite
                  <input
                    className="du-input mt-1"
                    type="date"
                    value={deadline}
                    onChange={(e) => setDeadline(e.target.value)}
                  />
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Responsable interno
                  <select
                    className="du-input mt-1"
                    value={responsibleUuid}
                    onChange={(e) => setResponsibleUuid(e.target.value)}
                  >
                    <option value="">—</option>
                    {project.created_by_user_uuid &&
                    !memberRows.some((r) => r.uuid === project.created_by_user_uuid) ? (
                      <option value={project.created_by_user_uuid}>Creador del proyecto</option>
                    ) : null}
                    {memberRows.map((r) => (
                      <option key={r.uuid} value={r.uuid}>
                        {formatPersonFullName(r.first_name, r.last_name, r.email)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Responsable externo (nombre)
                  <input
                    className="du-input mt-1"
                    value={responsibleExternalName}
                    onChange={(e) => setResponsibleExternalName(e.target.value)}
                    maxLength={255}
                    placeholder="Ej. contacto del cliente"
                  />
                </label>
                <label className="mt-3 block text-sm text-muted">
                  Responsable externo (correo)
                  <input
                    type="email"
                    className="du-input mt-1"
                    value={responsibleExternalEmail}
                    onChange={(e) => setResponsibleExternalEmail(e.target.value)}
                    maxLength={255}
                    placeholder="Opcional"
                  />
                </label>
                {saveMsg ? <p className="mt-2 text-sm text-primary">{saveMsg}</p> : null}
                <PrimaryButton type="button" className="mt-4" disabled={saveBusy} onClick={() => void saveMeta()}>
                  {saveBusy ? 'Guardando…' : 'Guardar datos'}
                </PrimaryButton>
              </Card>

              <Card className="p-4">
                <h3 className="text-sm font-semibold text-ink">Sistema (solo lectura)</h3>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="du-meta">Fase de flujo</dt>
                    <dd className="font-mono text-xs text-ink">{project.workflow_phase}</dd>
                  </div>
                  <div>
                    <dt className="du-meta">Estado técnico legado</dt>
                    <dd className="font-mono text-xs text-ink">{project.status}</dd>
                  </div>
                  <div>
                    <dt className="du-meta">UUID</dt>
                    <dd className="break-all font-mono text-[10px] text-muted/90">{project.uuid}</dd>
                  </div>
                  <div>
                    <dt className="du-meta">Última actualización</dt>
                    <dd className="text-xs text-ink">{new Date(project.updated_at).toLocaleString()}</dd>
                  </div>
                </dl>
              </Card>

              {elevated ? (
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-ink">Equipo con acceso</h3>
                  {membersMsg ? <p className="mt-2 text-sm text-primary">{membersMsg}</p> : null}
                  <div className="mt-3">
                    <ProjectMemberPicker
                      users={adminUsers}
                      lockedUuids={
                        project.created_by_user_uuid
                          ? new Set([project.created_by_user_uuid])
                          : new Set()
                      }
                      extraSelected={memberSelection}
                      onExtraChange={setMemberSelection}
                      disabled={membersBusy}
                      hint="Añade por rol o una a una. El creador no se puede quitar. Requiere módulo Arquitectura."
                    />
                  </div>
                  <PrimaryButton
                    type="button"
                    className="mt-4"
                    disabled={membersBusy}
                    onClick={() => {
                      if (!token || !projectUuid) return
                      setMembersBusy(true)
                      setMembersMsg(null)
                      void (async () => {
                        try {
                          const chosen = Array.from(memberSelection)
                          if (chosen.some((id) => !isValidUuidString(id))) {
                            setMembersMsg(
                              'La selección tiene identificadores inválidos. Recarga la página o vuelve a abrir el proyecto.',
                            )
                            return
                          }
                          const res = await apiFetch(`/api/projects/${projectUuid}/members`, {
                            method: 'PUT',
                            token,
                            body: JSON.stringify({
                              member_user_uuids: chosen,
                            }),
                          })
                          if (!res.ok) {
                            let msg = 'No se pudo guardar la lista de miembros'
                            try {
                              const errBody = (await res.json()) as { detail?: unknown }
                              const d = errBody.detail
                              if (typeof d === 'string') msg = d
                              else if (Array.isArray(d) && d.length > 0) {
                                const first = d[0] as { msg?: string }
                                if (typeof first?.msg === 'string') msg = first.msg
                              }
                            } catch {
                              /* ignore */
                            }
                            setMembersMsg(msg)
                            return
                          }
                          setMembersMsg('Lista de acceso actualizada')
                          const m = await apiFetch(`/api/projects/${projectUuid}/members`, { token })
                          if (m.ok) {
                            setMemberRows(normalizeDirectoryUsers(await m.json()))
                          }
                        } finally {
                          setMembersBusy(false)
                        }
                      })()
                    }}
                  >
                    {membersBusy ? 'Guardando…' : 'Guardar acceso'}
                  </PrimaryButton>
                </Card>
              ) : (
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-ink">Equipo con acceso</h3>
                  <ul className="mt-3 space-y-2 text-sm">
                    {memberRows.length === 0 ? (
                      <li className="text-muted">No hay miembros adicionales.</li>
                    ) : (
                      memberRows.map((r) => (
                        <li key={r.uuid}>{formatPersonFullName(r.first_name, r.last_name, r.email)}</li>
                      ))
                    )}
                  </ul>
                </Card>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
