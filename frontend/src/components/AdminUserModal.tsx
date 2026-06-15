import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { apiFetch } from '../api/client'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import { canAssignTeamLeader } from '../lib/accessPermissions'
import { ROLE_LABELS, USER_ROLES, type UserRole } from '../constants/userRoles'
import { useAuthStore } from '../store/authStore'
import { PrimaryButton } from './PrimaryButton'
import {
  adminCreateUserSchema,
  adminEditUserSchema,
  type AdminCreateUserForm,
  type AdminEditUserForm,
} from '../schemas/adminUser'

type ListedUser = {
  uuid: string
  email: string
  first_name: string
  last_name: string
  role: string
  module_ids: number[]
  is_team_leader?: boolean
}

type WorkspaceRow = {
  uuid: string
  name: string
}

type Props = {
  token: string
  open: boolean
  mode: 'create' | 'edit'
  user: ListedUser | null
  onClose: () => void
  onSaved: () => void
}

export function AdminUserModal({ token, open, mode, user, onClose, onSaved }: Props) {
  const actorRole = useAuthStore((s) => s.role)
  const activeWorkspaceUuid = useAuthStore((s) => s.activeWorkspaceUuid)
  const assignTeamLeader = canAssignTeamLeader(actorRole)
  const canAssignWorkspaces = actorRole === 'GERENCIA'
  const editableRoles = assignTeamLeader ? USER_ROLES : USER_ROLES.filter((r) => r !== 'GERENCIA')
  const [allWorkspaces, setAllWorkspaces] = useState<WorkspaceRow[]>([])
  const [selectedWorkspaceUuids, setSelectedWorkspaceUuids] = useState<string[]>([])

  const createForm = useForm<AdminCreateUserForm>({
    resolver: zodResolver(adminCreateUserSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      role: 'ARQUITECTURA',
      architectureAccess: true,
    },
  })
  const createRole = useWatch({ control: createForm.control, name: 'role' })

  const editForm = useForm<AdminEditUserForm>({
    resolver: zodResolver(adminEditUserSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      role: 'ARQUITECTURA',
      architectureAccess: true,
      isTeamLeader: false,
    },
  })
  const editRole = useWatch({ control: editForm.control, name: 'role' })

  useEffect(() => {
    if (!open || !canAssignWorkspaces) return
    void (async () => {
      const res = await apiFetch('/api/admin/workspaces', { token })
      if (!res.ok) return
      const rows = (await res.json()) as WorkspaceRow[]
      setAllWorkspaces(rows)
      if (mode === 'create') {
        const defaultUuid = activeWorkspaceUuid ?? rows[0]?.uuid
        setSelectedWorkspaceUuids(defaultUuid ? [defaultUuid] : [])
      }
    })()
  }, [open, canAssignWorkspaces, token, mode, activeWorkspaceUuid])

  useEffect(() => {
    if (!open || !canAssignWorkspaces || mode !== 'edit' || !user) return
    void (async () => {
      const res = await apiFetch(`/api/admin/users/${user.uuid}/workspaces`, { token })
      if (!res.ok) return
      const j = (await res.json()) as { workspace_uuids?: string[] }
      setSelectedWorkspaceUuids(j.workspace_uuids ?? [])
    })()
  }, [open, canAssignWorkspaces, mode, user, token])

  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && user) {
      const hasArch = user.module_ids?.includes(1) ?? true
      editForm.reset({
        first_name: user.first_name,
        last_name: user.last_name,
        email: user.email,
        password: '',
        role: user.role as UserRole,
        architectureAccess: hasArch,
        isTeamLeader: user.is_team_leader ?? false,
      })
    }
    if (mode === 'create') {
      createForm.reset({
        first_name: '',
        last_name: '',
        email: '',
        password: '',
        role: 'ARQUITECTURA',
        architectureAccess: true,
      })
    }
  }, [open, mode, user, createForm, editForm])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  async function saveUserWorkspaces(userUuid: string, role: string) {
    if (!canAssignWorkspaces || role === 'GERENCIA' || selectedWorkspaceUuids.length === 0) return
    await apiFetch(`/api/admin/users/${userUuid}/workspaces`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ workspace_uuids: selectedWorkspaceUuids }),
    })
  }

  async function submitCreate(values: AdminCreateUserForm) {
    const module_ids = values.architectureAccess ? [1] : []
    const res = await apiFetch('/api/admin/users', {
      method: 'POST',
      token,
      body: JSON.stringify({
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        password: values.password,
        role: values.role,
        module_ids,
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      createForm.setError('root', {
        message: (body as { detail?: string }).detail ?? 'No se pudo crear el usuario',
      })
      return
    }
    const created = (await res.json()) as { uuid: string; role: string }
    await saveUserWorkspaces(created.uuid, created.role)
    invalidateAdminUsersDirectoryCache()
    onSaved()
    onClose()
  }

  async function submitEdit(values: AdminEditUserForm) {
    if (!user) return
    const module_ids = values.architectureAccess ? [1] : []
    const body: Record<string, unknown> = {
      first_name: values.first_name,
      last_name: values.last_name,
      email: values.email,
      role: values.role,
      module_ids,
    }
    if (values.password.trim().length > 0) {
      body.password = values.password
    }
    if (assignTeamLeader) {
      body.is_team_leader = values.isTeamLeader ?? false
    }
    const res = await apiFetch(`/api/admin/users/${user.uuid}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      editForm.setError('root', {
        message: (j as { detail?: string }).detail ?? 'No se pudo guardar',
      })
      return
    }
    await saveUserWorkspaces(user.uuid, values.role)
    invalidateAdminUsersDirectoryCache()
    onSaved()
    onClose()
  }

  function toggleWorkspace(uuid: string) {
    setSelectedWorkspaceUuids((prev) => {
      if (prev.includes(uuid)) {
        const next = prev.filter((id) => id !== uuid)
        return next.length > 0 ? next : prev
      }
      return [...prev, uuid]
    })
  }

  function workspaceAssignmentBlock(role: string) {
    if (!canAssignWorkspaces || role === 'GERENCIA' || allWorkspaces.length === 0) return null
    return (
      <div>
        <p className="du-label">Workspaces</p>
        <ul className="mt-2 space-y-2 rounded-lg border border-black/10 p-3">
          {allWorkspaces.map((w) => (
            <li key={w.uuid}>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="rounded border-black/20"
                  checked={selectedWorkspaceUuids.includes(w.uuid)}
                  onChange={() => toggleWorkspace(w.uuid)}
                />
                {w.name}
              </label>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  if (!open) return null

  const isCreate = mode === 'create'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-black/10 bg-white p-6 shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-user-modal-title"
      >
        <h2 id="admin-user-modal-title" className="text-lg font-semibold text-ink">
          {isCreate ? 'Nuevo usuario' : 'Editar usuario'}
        </h2>

        {isCreate ? (
          <form className="mt-6 space-y-4" onSubmit={createForm.handleSubmit(submitCreate)} noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="du-label" htmlFor="um-first">
                  Nombre
                </label>
                <input
                  id="um-first"
                  type="text"
                  autoComplete="given-name"
                  className="du-input mt-1"
                  {...createForm.register('first_name')}
                />
                {createForm.formState.errors.first_name ? (
                  <p className="mt-1 text-sm text-primary">{createForm.formState.errors.first_name.message}</p>
                ) : null}
              </div>
              <div>
                <label className="du-label" htmlFor="um-last">
                  Apellido
                </label>
                <input
                  id="um-last"
                  type="text"
                  autoComplete="family-name"
                  className="du-input mt-1"
                  {...createForm.register('last_name')}
                />
                {createForm.formState.errors.last_name ? (
                  <p className="mt-1 text-sm text-primary">{createForm.formState.errors.last_name.message}</p>
                ) : null}
              </div>
            </div>
            <div>
              <label className="du-label" htmlFor="um-email">
                Correo
              </label>
              <input id="um-email" type="email" autoComplete="off" className="du-input mt-1" {...createForm.register('email')} />
              {createForm.formState.errors.email ? (
                <p className="mt-1 text-sm text-primary">{createForm.formState.errors.email.message}</p>
              ) : null}
            </div>
            <div>
              <label className="du-label" htmlFor="um-password">
                Contraseña inicial
              </label>
              <input
                id="um-password"
                type="password"
                autoComplete="new-password"
                className="du-input mt-1"
                {...createForm.register('password')}
              />
              {createForm.formState.errors.password ? (
                <p className="mt-1 text-sm text-primary">{createForm.formState.errors.password.message}</p>
              ) : (
                <p className="du-meta mt-1">Mínimo 8 caracteres.</p>
              )}
            </div>
            <div>
              <label className="du-label" htmlFor="um-role">
                Rol
              </label>
              <select id="um-role" className="du-input mt-1" {...createForm.register('role')}>
                {editableRoles.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="rounded border-black/20" {...createForm.register('architectureAccess')} />
              Acceso a proyectos y workspace
            </label>
            {workspaceAssignmentBlock(createRole ?? 'ARQUITECTURA')}
            {createForm.formState.errors.root ? (
              <p className="text-sm text-primary">{createForm.formState.errors.root.message}</p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={onClose}>
                Cancelar
              </button>
              <PrimaryButton type="submit" disabled={createForm.formState.isSubmitting}>
                {createForm.formState.isSubmitting ? 'Creando…' : 'Crear usuario'}
              </PrimaryButton>
            </div>
          </form>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={editForm.handleSubmit(submitEdit)} noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="du-label" htmlFor="ue-first">
                  Nombre
                </label>
                <input
                  id="ue-first"
                  type="text"
                  autoComplete="given-name"
                  className="du-input mt-1"
                  {...editForm.register('first_name')}
                />
                {editForm.formState.errors.first_name ? (
                  <p className="mt-1 text-sm text-primary">{editForm.formState.errors.first_name.message}</p>
                ) : null}
              </div>
              <div>
                <label className="du-label" htmlFor="ue-last">
                  Apellido
                </label>
                <input
                  id="ue-last"
                  type="text"
                  autoComplete="family-name"
                  className="du-input mt-1"
                  {...editForm.register('last_name')}
                />
                {editForm.formState.errors.last_name ? (
                  <p className="mt-1 text-sm text-primary">{editForm.formState.errors.last_name.message}</p>
                ) : null}
              </div>
            </div>
            <div>
              <label className="du-label" htmlFor="ue-email">
                Correo
              </label>
              <input id="ue-email" type="email" className="du-input mt-1" {...editForm.register('email')} />
              {editForm.formState.errors.email ? (
                <p className="mt-1 text-sm text-primary">{editForm.formState.errors.email.message}</p>
              ) : null}
            </div>
            <div>
              <label className="du-label" htmlFor="ue-password">
                Nueva contraseña <span className="font-normal text-muted">(opcional)</span>
              </label>
              <input
                id="ue-password"
                type="password"
                autoComplete="new-password"
                className="du-input mt-1"
                placeholder="Dejar vacío para no cambiar"
                {...editForm.register('password')}
              />
              {editForm.formState.errors.password ? (
                <p className="mt-1 text-sm text-primary">{editForm.formState.errors.password.message}</p>
              ) : null}
            </div>
            <div>
              <label className="du-label" htmlFor="ue-role">
                Rol
              </label>
              <select id="ue-role" className="du-input mt-1" {...editForm.register('role')}>
                {editableRoles.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r]}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="rounded border-black/20" {...editForm.register('architectureAccess')} />
              Acceso a proyectos y workspace
            </label>
            {assignTeamLeader ? (
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" className="rounded border-black/20" {...editForm.register('isTeamLeader')} />
                Líder de equipo (permisos elevados excepto crear usuarios)
              </label>
            ) : null}
            {workspaceAssignmentBlock(editRole ?? 'ARQUITECTURA')}
            {editForm.formState.errors.root ? (
              <p className="text-sm text-primary">{editForm.formState.errors.root.message}</p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={onClose}>
                Cancelar
              </button>
              <PrimaryButton type="submit" disabled={editForm.formState.isSubmitting}>
                {editForm.formState.isSubmitting ? 'Guardando…' : 'Guardar cambios'}
              </PrimaryButton>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
