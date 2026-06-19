import { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { AdminPermissionsPage } from '../components/admin/AdminPermissionsPage'
import { AdminWorkspacesPanel } from '../components/admin/AdminWorkspacesPanel'
import { AdminUserImportModal } from '../components/AdminUserImportModal'
import { AdminUserModal } from '../components/AdminUserModal'
import { Card } from '../components/Card'
import { PrimaryButton } from '../components/PrimaryButton'
import { SYSTEM_ROLE_LABELS } from '../constants/userRoles'
import { canCreateUsers, canManagePermissions } from '../lib/accessPermissions'
import { invalidateAdminUsersDirectoryCache } from '../lib/adminUsersDirectoryCache'
import { formatPersonFullName } from '../lib/personDisplay'
import { confirmDestructive } from '../lib/duplaAlert'
import { useAuthStore } from '../store/authStore'

type ListedUser = {
  uuid: string
  email: string
  first_name: string
  last_name: string
  role: string
  role_slugs?: string[]
  role_names?: string[]
  module_ids: number[]
}

export function AdminUsersPage() {
  const token = useAuthStore((s) => s.token)
  const permissions = useAuthStore((s) => s.permissions)
  const currentUserUuid = useAuthStore((s) => s.userUuid)
  const canCreate = canCreateUsers(permissions)
  const canManagePerms = canManagePermissions(permissions)
  const [tab, setTab] = useState<'users' | 'permissions'>('users')
  const [users, setUsers] = useState<ListedUser[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [deletingUuid, setDeletingUuid] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
  const [editingUser, setEditingUser] = useState<ListedUser | null>(null)
  const [rolesRefreshKey, setRolesRefreshKey] = useState(0)

  const bumpRolesRefresh = useCallback(() => {
    setRolesRefreshKey((k) => k + 1)
  }, [])

  const refresh = useCallback(async () => {
    if (!token) return
    setListError(null)
    const res = await apiFetch('/api/admin/users', { token })
    if (!res.ok) {
      setListError('No se pudo cargar la lista de usuarios')
      return
    }
    setUsers((await res.json()) as ListedUser[])
  }, [token])

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

  function openCreate() {
    setModalMode('create')
    setEditingUser(null)
    setModalOpen(true)
  }

  function openEdit(u: ListedUser) {
    setModalMode('edit')
    setEditingUser(u)
    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditingUser(null)
  }

  function roleLabel(u: ListedUser): string {
    if (u.role_names?.length) return u.role_names.join(', ')
    const slugs = u.role_slugs ?? [u.role]
    return slugs.map((s) => SYSTEM_ROLE_LABELS[s] ?? s).join(', ')
  }

  async function deleteUser(u: ListedUser) {
    if (!token) return
    if (u.uuid === currentUserUuid) return

    const name = formatPersonFullName(u.first_name, u.last_name, u.email)
    if (
      !(await confirmDestructive({
        title: `¿Eliminar a ${name}?`,
        text: 'Se revocará su acceso de inmediato. Esta acción no se puede deshacer.',
      }))
    ) {
      return
    }

    setDeletingUuid(u.uuid)
    setListError(null)
    try {
      const res = await apiFetch(`/api/admin/users/${u.uuid}`, {
        method: 'DELETE',
        token,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setListError((body as { detail?: string }).detail ?? 'No se pudo eliminar el usuario')
        return
      }
      invalidateAdminUsersDirectoryCache()
      await refresh()
    } finally {
      setDeletingUuid(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6">
      <div className="flex shrink-0 flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink md:text-3xl">Administración</h1>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Usuarios, roles y permisos del workspace.
          </p>
        </div>
        {tab === 'users' && canCreate ? (
          <div className="flex shrink-0 flex-wrap gap-2 self-start">
            <button
              type="button"
              className="rounded-md border border-black/15 px-4 py-2.5 text-sm font-semibold uppercase tracking-wide text-ink hover:bg-black/4"
              onClick={() => setImportModalOpen(true)}
            >
              Importar usuarios
            </button>
            <PrimaryButton type="button" onClick={openCreate}>
              Nuevo usuario
            </PrimaryButton>
          </div>
        ) : null}
      </div>

      <div className="flex gap-2 border-b border-black/10">
        <button
          type="button"
          className={`px-4 py-2 text-sm font-medium ${tab === 'users' ? 'border-b-2 border-primary text-ink' : 'text-muted'}`}
          onClick={() => setTab('users')}
        >
          Usuarios
        </button>
        {canManagePerms ? (
          <button
            type="button"
            className={`px-4 py-2 text-sm font-medium ${tab === 'permissions' ? 'border-b-2 border-primary text-ink' : 'text-muted'}`}
            onClick={() => setTab('permissions')}
          >
            Roles y permisos
          </button>
        ) : null}
      </div>

      {tab === 'permissions' && token && canManagePerms ? (
        <AdminPermissionsPage token={token} onRolesChanged={bumpRolesRefresh} />
      ) : null}

      {tab === 'users' ? (
        <>
          {token && canCreate ? <AdminWorkspacesPanel token={token} /> : null}

          <Card className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
            <div className="shrink-0 border-b border-black/10 px-4 py-3 text-sm font-semibold text-ink">
              Usuarios registrados
            </div>
            {listError ? <p className="shrink-0 px-4 py-3 text-sm text-primary">{listError}</p> : null}
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full min-w-[640px] table-fixed text-left text-sm">
                <thead className="sticky top-0 z-10 bg-[#f7f7f7] text-xs uppercase text-muted shadow-[inset_0_-1px_0_rgba(0,0,0,0.06)]">
                  <tr>
                    <th className="px-4 py-3">Nombre</th>
                    <th className="px-4 py-3">Correo</th>
                    <th className="w-48 px-4 py-3">Roles</th>
                    <th className="w-44 px-4 py-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingList ? (
                    <tr>
                      <td className="px-4 py-8 text-muted" colSpan={4}>
                        Cargando…
                      </td>
                    </tr>
                  ) : null}
                  {!loadingList && users.length === 0 ? (
                    <tr>
                      <td className="px-4 py-8 text-muted" colSpan={4}>
                        No hay usuarios registrados.
                      </td>
                    </tr>
                  ) : null}
                  {!loadingList &&
                    users.map((u) => {
                      const isSelf = u.uuid === currentUserUuid
                      const isDeleting = deletingUuid === u.uuid
                      return (
                        <tr key={u.uuid} className="border-t border-black/5">
                          <td className="truncate px-4 py-3 text-ink">
                            {formatPersonFullName(u.first_name, u.last_name, u.email)}
                          </td>
                          <td className="truncate px-4 py-3 text-muted">{u.email}</td>
                          <td className="px-4 py-3 text-muted">{roleLabel(u)}</td>
                          <td className="px-4 py-3 text-right">
                            <div className="inline-flex flex-wrap items-center justify-end gap-3">
                              <button
                                type="button"
                                className="du-link text-xs font-medium uppercase tracking-wide"
                                onClick={() => openEdit(u)}
                              >
                                Editar
                              </button>
                              <button
                                type="button"
                                className="text-xs font-medium uppercase tracking-wide text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                                disabled={isSelf || isDeleting}
                                title={isSelf ? 'No puedes eliminar tu propia cuenta' : undefined}
                                onClick={() => void deleteUser(u)}
                              >
                                {isDeleting ? 'Eliminando…' : 'Eliminar'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          </Card>

          {token && canCreate ? (
            <AdminUserImportModal
              token={token}
              open={importModalOpen}
              onClose={() => setImportModalOpen(false)}
              onImported={() => void refresh()}
            />
          ) : null}

          {token ? (
            <AdminUserModal
              token={token}
              open={modalOpen}
              mode={modalMode}
              user={editingUser}
              rolesRefreshKey={rolesRefreshKey}
              onClose={closeModal}
              onSaved={() => void refresh()}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
