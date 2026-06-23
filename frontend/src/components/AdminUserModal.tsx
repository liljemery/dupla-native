import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'

import { apiFetch } from '../api/client'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import { canManagePermissions } from '../lib/accessPermissions'
import { USER_ROLES } from '../constants/userRoles'
import { useAuthStore } from '../store/authStore'
import { PrimaryButton } from './PrimaryButton'
import { AdminUserPermissionsPanel } from './admin/AdminUserPermissionsPanel'
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
  role_slugs?: string[]
  role_uuids?: string[]
  module_ids: number[]
}

type RoleOption = { uuid: string; slug: string; name: string; is_system: boolean }

type WorkspaceRow = { uuid: string; name: string }

type Props = {
  token: string
  open: boolean
  mode: 'create' | 'edit'
  user: ListedUser | null
  rolesRefreshKey?: number
  onClose: () => void
  onSaved: () => void
}

function primaryRoleUuidFromUser(user: ListedUser, roles: RoleOption[]): string {
  const slugs = user.role_slugs ?? [user.role]
  const primarySlug =
    USER_ROLES.find((r) => slugs.includes(r)) ?? slugs.find((s) => s !== 'TEAM_LEADER') ?? slugs[0]
  return roles.find((r) => r.slug === primarySlug)?.uuid ?? roles[0]?.uuid ?? ''
}

export function AdminUserModal({ token, open, mode, user, rolesRefreshKey = 0, onClose, onSaved }: Props) {
  const permissions = useAuthStore((s) => s.permissions)
  const activeWorkspaceUuid = useAuthStore((s) => s.activeWorkspaceUuid)
  const canManagePerms = canManagePermissions(permissions)
  const canAssignGerencia = canManagePerms
  const [roles, setRoles] = useState<RoleOption[]>([])
  const [rolesLoading, setRolesLoading] = useState(false)
  const [allWorkspaces, setAllWorkspaces] = useState<WorkspaceRow[]>([])
  const [selectedWorkspaceUuids, setSelectedWorkspaceUuids] = useState<string[]>([])
  const [permissionsOpen, setPermissionsOpen] = useState(false)

  const assignablePrimaryRoles = useMemo(
    () =>
      roles.filter((r) => {
        if (r.slug === 'TEAM_LEADER') return false
        if (r.slug === 'GERENCIA' && !canAssignGerencia) return false
        return true
      }),
    [roles, canAssignGerencia],
  )

  const createForm = useForm<AdminCreateUserForm>({
    resolver: zodResolver(adminCreateUserSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      primaryRoleUuid: '',
      teamLeader: false,
      architectureAccess: true,
    },
  })
  const createRoleUuid = useWatch({ control: createForm.control, name: 'primaryRoleUuid' })

  const editForm = useForm<AdminEditUserForm>({
    resolver: zodResolver(adminEditUserSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      primaryRoleUuid: '',
      teamLeader: false,
      architectureAccess: true,
    },
  })
  const editRoleUuid = useWatch({ control: editForm.control, name: 'primaryRoleUuid' })

  const closeModal = useCallback(() => {
    setPermissionsOpen(false)
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return
    void (async () => {
      setRolesLoading(true)
      const res = await apiFetch('/api/admin/roles', { token })
      if (res.ok) setRoles((await res.json()) as RoleOption[])
      setRolesLoading(false)
    })()
  }, [open, token, rolesRefreshKey])

  useEffect(() => {
    if (!open || !canManagePerms) return
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
  }, [open, canManagePerms, token, mode, activeWorkspaceUuid])

  useEffect(() => {
    if (!open || !canManagePerms || mode !== 'edit' || !user) return
    void (async () => {
      const res = await apiFetch(`/api/admin/users/${user.uuid}/workspaces`, { token })
      if (!res.ok) return
      const j = (await res.json()) as { workspace_uuids?: string[] }
      setSelectedWorkspaceUuids(j.workspace_uuids ?? [])
    })()
  }, [open, canManagePerms, mode, user, token])

  useEffect(() => {
    if (!open || assignablePrimaryRoles.length === 0) return
    const defaultUuid = assignablePrimaryRoles[0]?.uuid ?? ''
    if (mode === 'edit' && user) {
      const slugs = user.role_slugs ?? [user.role]
      editForm.reset({
        first_name: user.first_name,
        last_name: user.last_name,
        email: user.email,
        password: '',
        primaryRoleUuid: primaryRoleUuidFromUser(user, assignablePrimaryRoles) || defaultUuid,
        teamLeader: slugs.includes('TEAM_LEADER'),
        architectureAccess: user.module_ids?.includes(1) ?? true,
      })
    }
    if (mode === 'create') {
      createForm.reset({
        first_name: '',
        last_name: '',
        email: '',
        password: '',
        primaryRoleUuid: defaultUuid,
        teamLeader: false,
        architectureAccess: true,
      })
    }
  }, [open, mode, user, createForm, editForm, assignablePrimaryRoles])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeModal()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, closeModal])

  function roleUuidsForSubmit(primaryRoleUuid: string, teamLeader: boolean): string[] {
    const ids = [primaryRoleUuid]
    if (teamLeader) {
      const tl = roles.find((r) => r.slug === 'TEAM_LEADER')?.uuid
      if (tl) ids.push(tl)
    }
    if (ids.some((id) => !id)) {
      throw new Error('Roles no cargados')
    }
    return ids
  }

  function isGerenciaRole(roleUuid: string): boolean {
    return roles.find((r) => r.uuid === roleUuid)?.slug === 'GERENCIA'
  }

  async function saveUserWorkspaces(userUuid: string, primaryRoleUuid: string) {
    if (!canManagePerms || isGerenciaRole(primaryRoleUuid) || selectedWorkspaceUuids.length === 0) return
    await apiFetch(`/api/admin/users/${userUuid}/workspaces`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ workspace_uuids: selectedWorkspaceUuids }),
    })
  }

  async function submitCreate(values: AdminCreateUserForm) {
    const module_ids = values.architectureAccess ? [1] : []
    let role_uuids: string[]
    try {
      role_uuids = roleUuidsForSubmit(values.primaryRoleUuid, values.teamLeader ?? false)
    } catch {
      createForm.setError('root', { message: 'Espera a que carguen los roles' })
      return
    }
    const res = await apiFetch('/api/admin/users', {
      method: 'POST',
      token,
      body: JSON.stringify({
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email,
        password: values.password,
        role_uuids,
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
    await saveUserWorkspaces(created.uuid, values.primaryRoleUuid)
    invalidateAdminUsersDirectoryCache()
    onSaved()
    closeModal()
  }

  async function submitEdit(values: AdminEditUserForm) {
    if (!user) return
    const module_ids = values.architectureAccess ? [1] : []
    let role_uuids: string[]
    try {
      role_uuids = roleUuidsForSubmit(values.primaryRoleUuid, values.teamLeader ?? false)
    } catch {
      editForm.setError('root', { message: 'Espera a que carguen los roles' })
      return
    }
    const body: Record<string, unknown> = {
      first_name: values.first_name,
      last_name: values.last_name,
      email: values.email,
      role_uuids,
      module_ids,
    }
    if (values.password.trim().length > 0) {
      body.password = values.password
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
    await saveUserWorkspaces(user.uuid, values.primaryRoleUuid)
    invalidateAdminUsersDirectoryCache()
    onSaved()
    closeModal()
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

  function workspaceAssignmentBlock(primaryRoleUuid: string) {
    if (!canManagePerms || isGerenciaRole(primaryRoleUuid) || allWorkspaces.length === 0) return null
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
        if (e.target === e.currentTarget) closeModal()
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
            <UserFields
              form={createForm}
              idPrefix="um"
              roleOptions={assignablePrimaryRoles}
              rolesLoading={rolesLoading}
            />
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="rounded border-black/20" {...createForm.register('architectureAccess')} />
              Acceso a proyectos y workspace
            </label>
            {canAssignGerencia ? (
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" className="rounded border-black/20" {...createForm.register('teamLeader')} />
                Líder de equipo
              </label>
            ) : null}
            {workspaceAssignmentBlock(createRoleUuid ?? '')}
            {createForm.formState.errors.root ? (
              <p className="text-sm text-primary">{createForm.formState.errors.root.message}</p>
            ) : null}
            <ModalActions
              onClose={closeModal}
              submitting={createForm.formState.isSubmitting}
              disabled={rolesLoading || assignablePrimaryRoles.length === 0}
              create
            />
          </form>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={editForm.handleSubmit(submitEdit)} noValidate>
            <UserFields
              form={editForm}
              idPrefix="ue"
              roleOptions={assignablePrimaryRoles}
              rolesLoading={rolesLoading}
              edit
            />
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="rounded border-black/20" {...editForm.register('architectureAccess')} />
              Acceso a proyectos y workspace
            </label>
            {canAssignGerencia ? (
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" className="rounded border-black/20" {...editForm.register('teamLeader')} />
                Líder de equipo
              </label>
            ) : null}
            {workspaceAssignmentBlock(editRoleUuid ?? '')}
            {canManagePerms && user ? (
              <>
                <button
                  type="button"
                  className="text-sm text-primary hover:underline"
                  onClick={() => setPermissionsOpen((v) => !v)}
                >
                  {permissionsOpen ? 'Ocultar permisos especiales' : 'Permisos especiales'}
                </button>
                <AdminUserPermissionsPanel
                  token={token}
                  userUuid={user.uuid}
                  open={permissionsOpen}
                  onClose={() => setPermissionsOpen(false)}
                />
              </>
            ) : null}
            {editForm.formState.errors.root ? (
              <p className="text-sm text-primary">{editForm.formState.errors.root.message}</p>
            ) : null}
            <ModalActions
              onClose={closeModal}
              submitting={editForm.formState.isSubmitting}
              disabled={rolesLoading || assignablePrimaryRoles.length === 0}
            />
          </form>
        )}
      </div>
    </div>
  )
}

function UserFields({
  form,
  idPrefix,
  roleOptions,
  rolesLoading,
  edit = false,
}: {
  form: ReturnType<typeof useForm<AdminCreateUserForm>> | ReturnType<typeof useForm<AdminEditUserForm>>
  idPrefix: string
  roleOptions: RoleOption[]
  rolesLoading: boolean
  edit?: boolean
}) {
  const errors = form.formState.errors
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="du-label" htmlFor={`${idPrefix}-first`}>
            Nombre
          </label>
          <input id={`${idPrefix}-first`} type="text" className="du-input mt-1" {...form.register('first_name')} />
          {'first_name' in errors && errors.first_name ? (
            <p className="mt-1 text-sm text-primary">{String(errors.first_name.message)}</p>
          ) : null}
        </div>
        <div>
          <label className="du-label" htmlFor={`${idPrefix}-last`}>
            Apellido
          </label>
          <input id={`${idPrefix}-last`} type="text" className="du-input mt-1" {...form.register('last_name')} />
          {'last_name' in errors && errors.last_name ? (
            <p className="mt-1 text-sm text-primary">{String(errors.last_name.message)}</p>
          ) : null}
        </div>
      </div>
      <div>
        <label className="du-label" htmlFor={`${idPrefix}-email`}>
          Correo
        </label>
        <input id={`${idPrefix}-email`} type="email" className="du-input mt-1" {...form.register('email')} />
        {'email' in errors && errors.email ? (
          <p className="mt-1 text-sm text-primary">{String(errors.email.message)}</p>
        ) : null}
      </div>
      <div>
        <label className="du-label" htmlFor={`${idPrefix}-password`}>
          {edit ? (
            <>
              Nueva contraseña <span className="font-normal text-muted">(opcional)</span>
            </>
          ) : (
            'Contraseña inicial'
          )}
        </label>
        <input
          id={`${idPrefix}-password`}
          type="password"
          className="du-input mt-1"
          placeholder={edit ? 'Dejar vacío para no cambiar' : undefined}
          {...form.register('password')}
        />
      </div>
      <div>
        <label className="du-label" htmlFor={`${idPrefix}-role`}>
          Rol principal
        </label>
        <select
          id={`${idPrefix}-role`}
          className="du-input mt-1"
          disabled={rolesLoading || roleOptions.length === 0}
          {...form.register('primaryRoleUuid')}
        >
          {rolesLoading ? <option value="">Cargando roles…</option> : null}
          {!rolesLoading && roleOptions.length === 0 ? <option value="">Sin roles disponibles</option> : null}
          {roleOptions.map((r) => (
            <option key={r.uuid} value={r.uuid}>
              {r.name}
            </option>
          ))}
        </select>
        {'primaryRoleUuid' in errors && errors.primaryRoleUuid ? (
          <p className="mt-1 text-sm text-primary">{String(errors.primaryRoleUuid.message)}</p>
        ) : null}
      </div>
    </>
  )
}

function ModalActions({
  onClose,
  submitting,
  disabled = false,
  create = false,
}: {
  onClose: () => void
  submitting: boolean
  disabled?: boolean
  create?: boolean
}) {
  return (
    <div className="flex flex-wrap justify-end gap-2 pt-2">
      <button type="button" className="rounded-md px-3 py-2 text-sm text-muted hover:text-ink" onClick={onClose}>
        Cancelar
      </button>
      <PrimaryButton type="submit" disabled={submitting || disabled}>
        {submitting ? (create ? 'Creando…' : 'Guardando…') : create ? 'Crear usuario' : 'Guardar cambios'}
      </PrimaryButton>
    </div>
  )
}
