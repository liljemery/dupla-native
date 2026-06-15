import { useCallback, useEffect, useState } from 'react'

import { apiFetch } from '../api/client'
import { AdminWorkspacesPanel } from '../components/admin/AdminWorkspacesPanel'
import { AdminUserImportModal } from '../components/AdminUserImportModal'
import { AdminUserModal } from '../components/AdminUserModal'
import { Card } from '../components/Card'
import { PrimaryButton } from '../components/PrimaryButton'
import { ROLE_LABELS, type UserRole } from '../constants/userRoles'
import { canCreateUsers } from '../lib/accessPermissions'
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
  module_ids: number[]
  is_team_leader?: boolean
}

export function AdminUsersPage() {
  const token = useAuthStore((s) => s.token)
  const role = useAuthStore((s) => s.role)
  const currentUserUuid = useAuthStore((s) => s.userUuid)
  const canCreate = canCreateUsers(role)
  const [users, setUsers] = useState<ListedUser[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [deletingUuid, setDeletingUuid] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
  const [editingUser, setEditingUser] = useState<ListedUser | null>(null)

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
    const base = ROLE_LABELS[u.role as UserRole] ?? u.role
    return u.is_team_leader ? `${base} · TL` : base
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
          <h1 className="text-2xl font-semibold text-ink md:text-3xl">Usuarios</h1>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Gestión de credenciales, rol y acceso al workspace. Gerencia puede crear cuentas; Líderes de equipo pueden
            editar y eliminar.
          </p>
        </div>
        {canCreate ? (
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
                <th className="w-40 px-4 py-3">Rol</th>
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
          onClose={closeModal}
          onSaved={() => void refresh()}
        />
      ) : null}
    </div>
  )
}
